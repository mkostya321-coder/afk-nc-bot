import os, sqlite3, logging, asyncio
from datetime import datetime, timedelta
import pytz, gspread
from oauth2client.service_account import ServiceAccountCredentials
from .config import SHEET_ID, DB_PATH, get_credentials_path
from .database import get_user_by_username

logger = logging.getLogger(__name__)
moscow_tz = pytz.timezone("Europe/Moscow")

PRICES = {
    "яндекс": 150, "google": 50, "2гис": 50,
    "авито": 700, "вк": 50, "отзовик": 100, "доктору": 100,
}

PLATFORM_ALIASES = {
    "яндекс": ["яндекс", "ян", "yandex"],
    "google": ["google", "гугл"],
    "2гис": ["2гис", "гис", "2 гис"],
    "авито": ["авито", "avito"],
    "вк": ["вк", "vk"],
    "отзовик": ["отзовик", "otzovik"],
    "доктору": ["доктору", "docto", "doctoru", "докто ру"],
}

def match_platform(raw_name: str) -> str | None:
    name = raw_name.strip().lower()
    for std, aliases in PLATFORM_ALIASES.items():
        for a in aliases:
            if a in name:
                return std
    return None

def get_credentials():
    path = get_credentials_path()
    if not os.path.exists(path):
        logger.error(f"Файл ключа не найден: {path}")
        return None
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    return ServiceAccountCredentials.from_json_keyfile_name(path, scope)

async def monitor_schedule(bot, active_slots: dict):
    logger.info("📅 Планировщик слотов запущен")
    while True:
        try:
            creds = get_credentials()
            if not creds:
                await asyncio.sleep(60)
                continue
            client = gspread.authorize(creds)
            sheet = client.open_by_key(SHEET_ID).sheet1
            records = sheet.get_all_values()
            now = datetime.now(moscow_tz)

            to_publish = []
            for row_idx, row in enumerate(records[1:], start=2):
                if len(row) < 8:
                    continue
                date_str = row[0].strip()
                time_str = row[1].strip()
                if not date_str or not time_str:
                    continue
                flag = row[4].strip()
                if flag != "0":
                    continue
                try:
                    slot_time = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%Y %H:%M")
                    slot_time = moscow_tz.localize(slot_time)
                except:
                    continue
                if now >= slot_time:
                    platform_raw = row[3].strip()
                    platform = match_platform(platform_raw)
                    if platform:
                        to_publish.append((platform, row_idx, row))

            if to_publish:
                from collections import defaultdict
                groups = defaultdict(list)
                for platform, row_idx, row in to_publish:
                    date_str = row[0].strip()
                    time_str = row[1].strip()
                    groups[(platform, date_str, time_str)].append((row_idx, row))

                from .handlers.slots import publish_scheduled_slot
                for (platform, date, time), items in groups.items():
                    count_available = len(items)
                    row_ids = [item[0] for item in items]
                    await publish_scheduled_slot(bot, active_slots, platform, count_available, date, time, row_ids)
                    logger.info(f"Опубликован слот {platform} ({count_available} шт.)")
                    for row_idx in row_ids:
                        try:
                            sheet.update_cell(row_idx, 5, 1)
                        except Exception as e:
                            logger.error(f"Не удалось обновить флаг для строки {row_idx}: {e}")

        except Exception as e:
            logger.error(f"Ошибка в планировщике слотов: {e}")
        await asyncio.sleep(60)

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
    try:
        creds = get_credentials()
        if not creds:
            return
        client = gspread.authorize(creds)
        sheet = client.open_by_key(SHEET_ID).sheet1
        records = sheet.get_all_values()

        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.cursor()
            cur.execute("UPDATE users SET yandex_passed=0, google_passed=0, gis_passed=0, avito_passed=0, vk_passed=0, otzovik_passed=0, doctoru_passed=0")
            conn.commit()

            processed = 0
            for row_idx, row in enumerate(records[1:], start=2):
                if len(row) < 10:
                    continue
                platform_raw = row[3].strip()
                status = row[9].strip().lower()
                flag_stat = row[8].strip()
                executor = row[10].strip()

                if flag_stat != "0" or status != "опубликован":
                    continue

                platform = match_platform(platform_raw)
                if not platform:
                    continue

                executor_clean = executor.lstrip("@").lower()
                user = get_user_by_username(executor_clean)
                if user:
                    uid = user["user_id"]
                    if platform == "яндекс":
                        cur.execute("UPDATE users SET yandex_passed = yandex_passed + 1, yandex_total = yandex_total + 1 WHERE user_id = ?", (uid,))
                    elif platform == "google":
                        cur.execute("UPDATE users SET google_passed = google_passed + 1, google_total = google_total + 1 WHERE user_id = ?", (uid,))
                    elif platform == "2гис":
                        cur.execute("UPDATE users SET gis_passed = gis_passed + 1, gis_total = gis_total + 1 WHERE user_id = ?", (uid,))
                    elif platform == "авито":
                        cur.execute("UPDATE users SET avito_passed = avito_passed + 1, avito_total = avito_total + 1 WHERE user_id = ?", (uid,))
                    elif platform == "вк":
                        cur.execute("UPDATE users SET vk_passed = vk_passed + 1, vk_total = vk_total + 1 WHERE user_id = ?", (uid,))
                    elif platform == "отзовик":
                        cur.execute("UPDATE users SET otzovik_passed = otzovik_passed + 1, otzovik_total = otzovik_total + 1 WHERE user_id = ?", (uid,))
                    elif platform == "доктору":
                        cur.execute("UPDATE users SET doctoru_passed = doctoru_passed + 1, doctoru_total = doctoru_total + 1 WHERE user_id = ?", (uid,))
                    try:
                        sheet.update_cell(row_idx, 9, 1)
                    except:
                        pass
                else:
                    try:
                        sheet.update_cell(row_idx, 9, 2)
                    except:
                        pass
                processed += 1

            conn.commit()

            cur.execute("SELECT user_id, yandex_passed, google_passed, gis_passed, avito_passed, vk_passed, otzovik_passed, doctoru_passed, total_earned FROM users")
            for user_row in cur.fetchall():
                uid = user_row[0]
                period_total = (
                    user_row[1] * PRICES.get("яндекс", 0) + user_row[2] * PRICES.get("google", 0) +
                    user_row[3] * PRICES.get("2гис", 0) + user_row[4] * PRICES.get("авито", 0) +
                    user_row[5] * PRICES.get("вк", 0) + user_row[6] * PRICES.get("отзовик", 0) +
                    user_row[7] * PRICES.get("доктору", 0)
                )
                cur.execute("UPDATE users SET payout = ? WHERE user_id = ?", (period_total, uid))
                cur.execute("UPDATE users SET total_earned = total_earned + ? WHERE user_id = ?", (period_total, uid))
            conn.commit()

            cur.execute("SELECT user_id, referrer, yandex_total, google_total, gis_total FROM users WHERE referrer != '0'")
            for row in cur.fetchall():
                user_id, referrer, yandex, google, gis = row
                if yandex >= 10 and (google + gis) >= 15:
                    cur.execute("SELECT referral_bonus_paid FROM users WHERE user_id = ?", (user_id,))
                    paid = cur.fetchone()[0]
                    if not paid:
                        cur.execute("UPDATE users SET payout = payout + 200, total_earned = total_earned + 200 WHERE user_id = ?", (user_id,))
                        cur.execute("UPDATE users SET referral_bonus_paid = 1 WHERE user_id = ?", (user_id,))
                        ref_user = get_user_by_username(referrer)
                        if ref_user:
                            cur.execute("UPDATE users SET payout = payout + 450, total_earned = total_earned + 450 WHERE user_id = ?", (ref_user["user_id"],))
            conn.commit()

        logger.info(f"Статистика обновлена, обработано строк: {processed}")

    except Exception as e:
        logger.error(f"Ошибка обновления статистики: {e}")
