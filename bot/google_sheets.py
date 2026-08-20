import os, sqlite3, logging, asyncio
from datetime import datetime, timedelta
import pytz, gspread
from oauth2client.service_account import ServiceAccountCredentials
from .config import SHEET_ID, DB_PATH, get_credentials_path, CHANNEL_ID
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
    "докдок": 100,
    "про докторов": 180,
    "докту": 110,
    "32топ": 100,
}

PLATFORM_ALIASES = {
    "яндекс": ["яндекс", "ян", "yandex"],
    "google": ["google", "гугл"],
    "2гис": ["2гис", "гис", "2 гис"],
    "авито": ["авито", "avito"],
    "вк": ["вк", "vk"],
    "отзовик": ["отзовик", "otzovik"],
    "доктору": ["доктору", "docto", "doctoru", "докто ру"],
    "докдок": ["докдок", "doc doc", "doc"],
    "про докторов": ["про докторов", "продокторов", "pro doctors"],
    "докту": ["докту", "doctu"],
    "32топ": ["32топ", "32top", "32 топ"],
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

# ============ ПУБЛИКАЦИЯ СЛОТОВ ============
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

            # --- 1. Первичная публикация ---
            to_publish = []
            for row_idx, row in enumerate(records[1:], start=2):
                if len(row) < 8:
                    continue
                date_str = row[0].strip()
                time_str = row[1].strip()
                if not date_str or not time_str:
                    continue
                # Проверяем, не публиковалась ли уже
                q_val = row[16].strip() if len(row) > 16 else ""
                p_val = row[15].strip() if len(row) > 15 else ""
                o_val = row[14].strip() if len(row) > 14 else ""
                i_val = row[8].strip() if len(row) > 8 else ""
                if q_val in ("1", "999") or p_val == "1" or o_val == "1" or i_val in ("1", "999"):
                    continue
                # Проверяем, что не в работе
                j_val = row[9].strip().lower() if len(row) > 9 else ""
                if j_val == "в работе":
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
                    # Публикуем первый раз, ставим Q=1
                    for row_idx in row_ids:
                        try:
                            sheet.update_cell(row_idx, 17, 1)  # Q (колонка 17)
                        except Exception as e:
                            logger.error(f"Не удалось обновить Q для строки {row_idx}: {e}")
                    await publish_scheduled_slot(
                        bot, active_slots, platform, count_available,
                        date, time, row_ids, attempt=1
                    )
                    logger.info(f"Опубликован слот {platform} ({count_available} шт.) – попытка 1")

            # --- 2. Перепубликация через 2 часа ---
            expired_slots = []
            for msg_id, slot in list(active_slots.items()):
                if slot.get("attempt", 1) >= 4:
                    continue
                publish_time = slot.get("publish_time")
                if publish_time and (now - publish_time).total_seconds() >= 7200:
                    available_rows = []
                    for row_idx in slot["row_ids"]:
                        try:
                            j_val = sheet.cell(row_idx, 10).value.lower() if sheet.cell(row_idx, 10).value else ""
                            if j_val != "в работе":
                                available_rows.append(row_idx)
                        except:
                            continue
                    if available_rows:
                        expired_slots.append((msg_id, slot, available_rows))

            for msg_id, slot, available_rows in expired_slots:
                try:
                    await bot.edit_message_text(
                        chat_id=CHANNEL_ID, message_id=msg_id,
                        text="Срок размещения истёк. Неразобранные отзывы будут переопубликованы."
                    )
                except:
                    pass
                del active_slots[msg_id]

                new_attempt = slot["attempt"] + 1
                # Определяем столбец для пометки
                if new_attempt == 2:
                    col_idx = 15  # P
                elif new_attempt == 3:
                    col_idx = 14  # O
                elif new_attempt == 4:
                    col_idx = 8   # I
                else:
                    col_idx = None

                if col_idx:
                    for row_idx in available_rows:
                        try:
                            sheet.update_cell(row_idx, col_idx, 1)
                        except Exception as e:
                            logger.error(f"Не удалось обновить столбец {col_idx} для строки {row_idx}: {e}")

                from .handlers.slots import publish_scheduled_slot
                await publish_scheduled_slot(
                    bot, active_slots, slot["platform"], len(available_rows),
                    slot["date"], slot["time"], available_rows, attempt=new_attempt
                )
                logger.info(f"Переопубликован слот {slot['platform']} ({len(available_rows)} шт.) – попытка {new_attempt}")

            # --- 3. Закрытие в 23:30 ---
            if now.hour == 23 and now.minute >= 30:
                for msg_id, slot in list(active_slots.items()):
                    for row_idx in slot["row_ids"]:
                        try:
                            j_val = sheet.cell(row_idx, 10).value.lower() if sheet.cell(row_idx, 10).value else ""
                            if j_val != "в работе":
                                sheet.update_cell(row_idx, 9, 999)  # I
                                sheet.format(f"I{row_idx}", {
                                    "backgroundColor": {"red": 1, "green": 0, "blue": 0}
                                })
                        except Exception as e:
                            logger.error(f"Не удалось пометить строку {row_idx}: {e}")
                    try:
                        await bot.edit_message_text(
                            chat_id=CHANNEL_ID, message_id=msg_id,
                            text="Рабочий день завершён. Все слоты закрыты."
                        )
                    except:
                        pass
                    del active_slots[msg_id]
                logger.info("Все слоты закрыты в 23:30")

        except Exception as e:
            logger.error(f"Ошибка в планировщике слотов: {e}")
        await asyncio.sleep(60)

# ============ ОБНОВЛЕНИЕ СТАТИСТИКИ ============
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
            # Обнуляем периодические счётчики
            cur.execute("""
                UPDATE users SET
                yandex_passed=0, google_passed=0, gis_passed=0, avito_passed=0, vk_passed=0,
                otzovik_passed=0, doctoru_passed=0, dokdok_passed=0, prodoctors_passed=0,
                doctu_passed=0, top32_passed=0
            """)
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
                    # Сопоставление платформы и полей
                    field_map = {
                        "яндекс": "yandex",
                        "google": "google",
                        "2гис": "gis",
                        "авито": "avito",
                        "вк": "vk",
                        "отзовик": "otzovik",
                        "доктору": "doctoru",
                        "докдок": "dokdok",
                        "про докторов": "prodoctors",
                        "докту": "doctu",
                        "32топ": "top32",
                    }
                    field_prefix = field_map.get(platform)
                    if field_prefix:
                        passed_field = f"{field_prefix}_passed"
                        total_field = f"{field_prefix}_total"
                        cur.execute(f"UPDATE users SET {passed_field} = {passed_field} + 1, {total_field} = {total_field} + 1 WHERE user_id = ?", (uid,))
                    try:
                        sheet.update_cell(row_idx, 9, 1)   # I = 1
                    except:
                        pass
                else:
                    try:
                        sheet.update_cell(row_idx, 9, 2)   # I = 2
                    except:
                        pass
                processed += 1

            conn.commit()

            # Пересчёт выплат и total_earned
            cur.execute("""
                SELECT user_id, yandex_passed, google_passed, gis_passed, avito_passed, vk_passed,
                       otzovik_passed, doctoru_passed, dokdok_passed, prodoctors_passed,
                       doctu_passed, top32_passed, total_earned
                FROM users
            """)
            for user_row in cur.fetchall():
                uid = user_row[0]
                period_total = (
                    user_row[1] * PRICES.get("яндекс", 0) +
                    user_row[2] * PRICES.get("google", 0) +
                    user_row[3] * PRICES.get("2гис", 0) +
                    user_row[4] * PRICES.get("авито", 0) +
                    user_row[5] * PRICES.get("вк", 0) +
                    user_row[6] * PRICES.get("отзовик", 0) +
                    user_row[7] * PRICES.get("доктору", 0) +
                    user_row[8] * PRICES.get("докдок", 0) +
                    user_row[9] * PRICES.get("про докторов", 0) +
                    user_row[10] * PRICES.get("докту", 0) +
                    user_row[11] * PRICES.get("32топ", 0)
                )
                cur.execute("UPDATE users SET payout = ? WHERE user_id = ?", (period_total, uid))
                cur.execute("UPDATE users SET total_earned = total_earned + ? WHERE user_id = ?", (period_total, uid))
            conn.commit()

            # Реферальные бонусы
            cur.execute("""
                SELECT user_id, referrer, yandex_total, google_total, gis_total
                FROM users WHERE referrer != '0'
            """)
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
