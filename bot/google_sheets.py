import os, sqlite3, logging, asyncio
from datetime import datetime, timedelta
import pytz, gspread
from oauth2client.service_account import ServiceAccountCredentials
from .config import SHEET_ID, DB_PATH, get_credentials_path, CHANNEL_ID
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

# ------------------------ МОНИТОРИНГ СЛОТОВ ------------------------
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

            # 1. Публикация новых слотов (E=0, дата/время наступили)
            to_publish = []
            for row_idx, row in enumerate(records[1:], start=2):
                if len(row) < 8:
                    continue
                date_str = row[0].strip()
                time_str = row[1].strip()
                if not date_str or not time_str:
                    continue
                flag_e = row[4].strip()
                if flag_e != "0":
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
                    # Первая публикация – ставим O=1, сдвигаем время в B на +2 часа
                    for row_idx in row_ids:
                        try:
                            sheet.update_cell(row_idx, 15, 1)   # O = 1
                            new_time = (datetime.strptime(time, "%H:%M") + timedelta(hours=2)).strftime("%H:%M")
                            sheet.update_cell(row_idx, 2, new_time)  # B
                            sheet.update_cell(row_idx, 5, 1)     # E = 1
                        except Exception as e:
                            logger.error(f"Не удалось обновить O/B/E для строки {row_idx}: {e}")
                    await publish_scheduled_slot(
                        bot, active_slots, platform, count_available,
                        date, time, row_ids, attempt=1
                    )
                    logger.info(f"Опубликован слот {platform} ({count_available} шт.) – попытка 1")

            # 2. Проверка истёкших слотов (перепубликация)
            expired_slots = []
            for msg_id, slot in list(active_slots.items()):
                # Смотрим на время в столбце B первой строки слота
                first_row = slot["row_ids"][0]
                try:
                    b_val = sheet.cell(first_row, 2).value   # столбец B
                    if b_val:
                        next_time = datetime.strptime(f"{slot['date']} {b_val}", "%d.%m.%Y %H:%M")
                        next_time = moscow_tz.localize(next_time)
                        if now >= next_time:
                            # Пора перепубликовать или завершить
                            available_rows = []
                            for row_idx in slot["row_ids"]:
                                val_e = sheet.cell(row_idx, 5).value
                                if val_e == "1":   # не взято
                                    available_rows.append(row_idx)
                            if available_rows:
                                expired_slots.append((msg_id, slot, available_rows))
                            else:
                                # Все разобраны – удаляем слот
                                try:
                                    await bot.edit_message_text(
                                        chat_id=CHANNEL_ID, message_id=msg_id,
                                        text="Все отзывы этого слота разобраны."
                                    )
                                except:
                                    pass
                                del active_slots[msg_id]
                except:
                    continue

            for msg_id, slot, available_rows in expired_slots:
                current_attempt = slot.get("attempt", 1)
                # Закрываем старый пост
                try:
                    await bot.edit_message_text(
                        chat_id=CHANNEL_ID, message_id=msg_id,
                        text="Срок размещения истёк. Неразобранные отзывы будут переопубликованы."
                    )
                except:
                    pass
                del active_slots[msg_id]

                if current_attempt == 1:
                    # Ставим P=1, сдвигаем время на +2 часа, E=1
                    for row_idx in available_rows:
                        try:
                            sheet.update_cell(row_idx, 16, 1)   # P = 1
                            b_val = sheet.cell(row_idx, 2).value
                            new_time = (datetime.strptime(b_val, "%H:%M") + timedelta(hours=2)).strftime("%H:%M")
                            sheet.update_cell(row_idx, 2, new_time)
                            sheet.update_cell(row_idx, 5, 1)
                        except Exception as e:
                            logger.error(f"Не удалось обновить P/B/E для строки {row_idx}: {e}")
                    new_attempt = 2
                elif current_attempt == 2:
                    # Ставим Q=1
                    for row_idx in available_rows:
                        try:
                            sheet.update_cell(row_idx, 17, 1)   # Q = 1
                            b_val = sheet.cell(row_idx, 2).value
                            new_time = (datetime.strptime(b_val, "%H:%M") + timedelta(hours=2)).strftime("%H:%M")
                            sheet.update_cell(row_idx, 2, new_time)
                            sheet.update_cell(row_idx, 5, 1)
                        except Exception as e:
                            logger.error(f"Не удалось обновить Q/B/E для строки {row_idx}: {e}")
                    new_attempt = 3
                else:   # 3-я попытка уже была – финальная (4-я)
                    # Ставим E=1, больше не перепубликовываем
                    for row_idx in available_rows:
                        try:
                            sheet.update_cell(row_idx, 5, 1)
                        except Exception as e:
                            logger.error(f"Не удалось обновить E для строки {row_idx}: {e}")
                    logger.info(f"Слот {slot['platform']} перепубликован последний раз ({len(available_rows)} шт.)")
                    continue   # не публикуем заново

                # Перепубликовываем слот с оставшимися строками
                from .handlers.slots import publish_scheduled_slot
                await publish_scheduled_slot(
                    bot, active_slots, slot["platform"], len(available_rows),
                    slot["date"], b_val if b_val else time, available_rows,
                    attempt=new_attempt
                )
                logger.info(f"Переопубликован слот {slot['platform']} ({len(available_rows)} шт.) – попытка {new_attempt}")

            # 3. Закрытие всех слотов в 22:00
            if now.hour == 22 and now.minute == 0:
                for msg_id in list(active_slots.keys()):
                    try:
                        await bot.edit_message_text(
                            chat_id=CHANNEL_ID, message_id=msg_id,
                            text="Рабочий день завершён. Все слоты закрыты."
                        )
                    except:
                        pass
                    del active_slots[msg_id]
                logger.info("Все слоты закрыты в 22:00")

        except Exception as e:
            logger.error(f"Ошибка в планировщике слотов: {e}")
        await asyncio.sleep(60)

# ------------------------ ОБНОВЛЕНИЕ СТАТИСТИКИ ------------------------
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
