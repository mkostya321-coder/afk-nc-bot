import os
import sqlite3
import logging
from datetime import datetime, timedelta    # ← обязательно есть timedelta
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

async def update_stats_from_sheet():
    while True:
        now = datetime.now(moscow_tz)
        target_times = [
            now.replace(hour=10, minute=0, second=0, microsecond=0),
            now.replace(hour=20, minute=0, second=0, microsecond=0)
        ]
        future_times = [t if t > now else t + timedelta(days=1) for t in target_times]
        next_target = min(future_times)
        sleep_seconds = (next_target - now).total_seconds()
        await asyncio.sleep(sleep_seconds)

        try:
            creds_path = "/data/google_key.json"
            if not os.path.exists(creds_path):
                creds_path = "google_key.json"
            if not os.path.exists(creds_path):
                logger.error("Файл google_key.json не найден")
                continue

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

                for row in records[1:]:
                    if len(row) < 6:
                        continue
                    platform = row[0].strip().lower()
                    status = row[4].strip().lower()
                    executor = row[5].strip()

                    executor = executor.lstrip("@").lower()

                    if status != "опубликован":
                        continue
                    if not executor:
                        continue

                    user = get_user_by_username(executor)
                    if not user:
                        continue
                    user_id = user["user_id"]

                    if platform == "яндекс":
                        cur.execute("UPDATE users SET yandex_passed = yandex_passed + 1 WHERE user_id = ?", (user_id,))
                    elif platform == "google":
                        cur.execute("UPDATE users SET google_passed = google_passed + 1 WHERE user_id = ?", (user_id,))
                    elif platform == "2гис":
                        cur.execute("UPDATE users SET gis_passed = gis_passed + 1 WHERE user_id = ?", (user_id,))
                    elif platform == "авито":
                        cur.execute("UPDATE users SET avito_passed = avito_passed + 1 WHERE user_id = ?", (user_id,))
                    elif platform == "вк":
                        cur.execute("UPDATE users SET vk_passed = vk_passed + 1 WHERE user_id = ?", (user_id,))
                    elif platform == "отзовик":
                        cur.execute("UPDATE users SET otzovik_passed = otzovik_passed + 1 WHERE user_id = ?", (user_id,))
                    elif platform in ("доктору", "docto.ru"):
                        cur.execute("UPDATE users SET doctoru_passed = doctoru_passed + 1 WHERE user_id = ?", (user_id,))

                conn.commit()

                cur.execute(
                    "SELECT user_id, yandex_passed, google_passed, gis_passed, "
                    "avito_passed, vk_passed, otzovik_passed, doctoru_passed FROM users"
                )
                for user_row in cur.fetchall():
                    uid = user_row[0]
                    total = (
                        user_row[1] * PRICES.get("яндекс", 0) +
                        user_row[2] * PRICES.get("google", 0) +
                        user_row[3] * PRICES.get("2гис", 0) +
                        user_row[4] * PRICES.get("авито", 0) +
                        user_row[5] * PRICES.get("вк", 0) +
                        user_row[6] * PRICES.get("отзовик", 0) +
                        user_row[7] * PRICES.get("доктору", 0)
                    )
                    cur.execute("UPDATE users SET payout = ? WHERE user_id = ?", (total, uid))
                conn.commit()

                cur.execute(
                    "SELECT user_id, referrer, yandex_passed, google_passed, gis_passed "
                    "FROM users WHERE referrer != '0'"
                )
                for row in cur.fetchall():
                    user_id, referrer, yandex, google, gis = row
                    if yandex >= 10 and (google + gis) >= 15:
                        cur.execute("SELECT referral_bonus_paid FROM users WHERE user_id = ?", (user_id,))
                        paid = cur.fetchone()[0]
                        if not paid:
                            cur.execute("UPDATE users SET payout = payout + 200 WHERE user_id = ?", (user_id,))
                            cur.execute("UPDATE users SET referral_bonus_paid = 1 WHERE user_id = ?", (user_id,))
                            ref_user = get_user_by_username(referrer)
                            if ref_user:
                                cur.execute("UPDATE users SET payout = payout + 450 WHERE user_id = ?", (ref_user["user_id"],))
                conn.commit()

        except Exception as e:
            logger.error(f"Ошибка при обновлении из Google Таблицы: {e}")
