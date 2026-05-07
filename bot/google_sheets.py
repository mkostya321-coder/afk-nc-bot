import os
import sqlite3
import logging
from datetime import datetime, timedelta
import pytz
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import asyncio

from .config import SHEET_ID, DB_PATH
from .database import get_user_by_username

logger = logging.getLogger(__name__)
moscow_tz = pytz.timezone("Europe/Moscow")

PRICES = {
    "яндекс": 150,
    "google": 50,
    "2гис": 50,
    "авито": 700,
    "вк": 50,
    "отзовик": 100,
    "доктору": 100,
}

PLATFORM_ALIASES = {
    "яндекс":   ["яндекс", "ян", "yandex"],
    "google":   ["google", "гугл", "гугл"],
    "2гис":     ["2гис", "гис", "2 гис"],
    "авито":    ["авито", "avito"],
    "вк":       ["вк", "vk"],
    "отзовик":  ["отзовик", "otzovik"],
    "доктору":  ["доктору", "docto", "doctoru", "докто ру"],
}

def match_platform(raw_name: str) -> str | None:
    name = raw_name.strip().lower()
    for standard, aliases in PLATFORM_ALIASES.items():
        for alias in aliases:
            if alias in name:
                return standard
    return None

async def update_stats_from_sheet():
    while True:
        now = datetime.now(moscow_tz)
        target_times = [
            now.replace(hour=10, minute=0, second=0, microsecond=0),
            now.replace(hour=20, minute=0, second=0, microsecond=0)
        ]
        future_times = [t if t > now else t + timedelta(days=1) for t in target_times]
        next_target = min(future_times)
        await asyncio.sleep((next_target - now).total_seconds())

        await update_stats_from_sheet_once()

async def update_stats_from_sheet_once():
    processed = 0
    try:
        creds_path = "/data/google_key.json"
        if not os.path.exists(creds_path):
            creds_path = "google_key.json"
        if not os.path.exists(creds_path):
            logger.error("Файл google_key.json не найден")
            return

        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive"
        ]
        creds = ServiceAccountCredentials.from_json_keyfile_name(creds_path, scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(SHEET_ID).sheet1
        records = sheet.get_all_values()

        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE users SET yandex_passed=0, google_passed=0, "
                "gis_passed=0, avito_passed=0, vk_passed=0, "
                "otzovik_passed=0, doctoru_passed=0"
            )
            conn.commit()

            for row_idx, row in enumerate(records[1:], start=2):
                if len(row) < 7:
                    continue
                platform_raw = row[0].strip()
                flag = row[1].strip()
                status = row[5].strip().lower()
                executor = row[6].strip()

                if flag != "0" or status != "опубликован":
                    continue
                if not executor:
                    continue

                platform = match_platform(platform_raw)
                if not platform:
                    continue

                executor_clean = executor.lstrip("@").lower()
                user = get_user_by_username(executor_clean)
                if not user:
                    # Пользователь не найден → ставим флаг 2
                    try:
                        sheet.update_cell(row_idx, 2, 2)
                    except Exception as e:
                        logger.warning(f"Не удалось обновить флаг для {executor}: {e}")
                    continue

                user_id = user["user_id"]

                if platform == "яндекс":
                    cur.execute(
                        "UPDATE users SET yandex_passed = yandex_passed + 1, yandex_total = yandex_total + 1 WHERE user_id = ?",
                        (user_id,)
                    )
                elif platform == "google":
                    cur.execute(
                        "UPDATE users SET google_passed = google_passed + 1, google_total = google_total + 1 WHERE user_id = ?",
                        (user_id,)
                    )
                elif platform == "2гис":
                    cur.execute(
                        "UPDATE users SET gis_passed = gis_passed + 1, gis_total = gis_total + 1 WHERE user_id = ?",
                        (user_id,)
                    )
                elif platform == "авито":
                    cur.execute(
                        "UPDATE users SET avito_passed = avito_passed + 1, avito_total = avito_total + 1 WHERE user_id = ?",
                        (user_id,)
                    )
                elif platform == "вк":
                    cur.execute(
                        "UPDATE users SET vk_passed = vk_passed + 1, vk_total = vk_total + 1 WHERE user_id = ?",
                        (user_id,)
                    )
                elif platform == "отзовик":
                    cur.execute(
                        "UPDATE users SET otzovik_passed = otzovik_passed + 1, otzovik_total = otzovik_total + 1 WHERE user_id = ?",
                        (user_id,)
                    )
                elif platform == "доктору":
                    cur.execute(
                        "UPDATE users SET doctoru_passed = doctoru_passed + 1, doctoru_total = doctoru_total + 1 WHERE user_id = ?",
                        (user_id,)
                    )

                try:
                    sheet.update_cell(row_idx, 2, 1)
                    processed += 1
                except Exception as e:
                    logger.error(f"Не удалось обновить флаг для строки {row_idx}: {e}")

            conn.commit()

            cur.execute(
                "SELECT user_id, yandex_passed, google_passed, gis_passed, "
                "avito_passed, vk_passed, otzovik_passed, doctoru_passed, total_earned FROM users"
            )
            for user_row in cur.fetchall():
                uid = user_row[0]
                period_total = (
                    user_row[1] * PRICES.get("яндекс", 0) +
                    user_row[2] * PRICES.get("google", 0) +
                    user_row[3] * PRICES.get("2гис", 0) +
                    user_row[4] * PRICES.get("авито", 0) +
                    user_row[5] * PRICES.get("вк", 0) +
                    user_row[6] * PRICES.get("отзовик", 0) +
                    user_row[7] * PRICES.get("доктору", 0)
                )
                cur.execute("UPDATE users SET payout = ? WHERE user_id = ?", (period_total, uid))
                cur.execute("UPDATE users SET total_earned = total_earned + ? WHERE user_id = ?", (period_total, uid))
            conn.commit()

            # Реферальные бонусы по общим счётчикам
            cur.execute(
                "SELECT user_id, referrer, yandex_total, google_total, gis_total "
                "FROM users WHERE referrer != '0'"
            )
            for row in cur.fetchall():
                user_id, referrer, yandex, google, gis = row
                if yandex >= 10 and (google + gis) >= 15:
                    cur.execute("SELECT referral_bonus_paid FROM users WHERE user_id = ?", (user_id,))
                    paid = cur.fetchone()[0]
                    if not paid:
                        cur.execute(
                            "UPDATE users SET payout = payout + 200, total_earned = total_earned + 200 WHERE user_id = ?",
                            (user_id,)
                        )
                        cur.execute("UPDATE users SET referral_bonus_paid = 1 WHERE user_id = ?", (user_id,))
                        ref_user = get_user_by_username(referrer)
                        if ref_user:
                            cur.execute(
                                "UPDATE users SET payout = payout + 450, total_earned = total_earned + 450 WHERE user_id = ?",
                                (ref_user["user_id"],)
                            )
            conn.commit()

        logger.info(f"Статистика успешно обновлена. Обработано новых строк: {processed}")

    except Exception as e:
        logger.error(f"Ошибка при обновлении из Google Таблицы: {e}")
        raise
