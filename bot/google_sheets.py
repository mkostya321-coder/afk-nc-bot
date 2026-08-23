import os, sqlite3, logging, asyncio
from datetime import datetime, timedelta
import pytz, gspread
from oauth2client.service_account import ServiceAccountCredentials
from .config import SHEET_ID, DB_PATH, get_credentials_path, CHANNEL_ID
from .database import get_user_by_username, get_user

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

SHEET_NAME_TO_PLATFORM = {
    "яндекс": "яндекс", "yandex": "яндекс",
    "google": "google",
    "2гис": "2гис",
    "авито": "авито", "avito": "авито",
    "вк": "вк", "vk": "вк",
    "отзовик": "отзовик", "otzovik": "отзовик",
    "доктору": "доктору", "doctoru": "доктору",
    "докдок": "докдок",
    "продокторов": "про докторов", "про докторов": "про докторов", "prodoctors": "про докторов",
    "докту": "докту", "doctu": "докту",
    "32топ": "32топ", "32top": "32топ", "32 топ": "32топ",
}

def match_platform(raw_name: str) -> str | None:
    name = raw_name.strip().lower()
    for std, aliases in PLATFORM_ALIASES.items():
        for a in aliases:
            if a in name:
                return std
    return None

def platform_from_sheet_name(sheet_name: str) -> str | None:
    key = sheet_name.strip().lower()
    return SHEET_NAME_TO_PLATFORM.get(key)

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
            spreadsheet = client.open_by_key(SHEET_ID)
            worksheets = spreadsheet.worksheets()
            now = datetime.now(moscow_tz)

            for sheet in worksheets:
                sheet_name = sheet.title
                platform = platform_from_sheet_name(sheet_name)
                if not platform:
                    continue

                records = sheet.get_all_values()
                if not records or len(records) < 2:
                    continue

                # --- Первичная публикация ---
                to_publish = []
                for row_idx, row in enumerate(records[1:], start=2):
                    if len(row) < 8:
                        continue
                    date_str = row[0].strip()
                    time_str = row[1].strip()
                    if not date_str or not time_str:
                        continue
                    q_val = row[16].strip() if len(row) > 16 else ""
                    p_val = row[15].strip() if len(row) > 15 else ""
                    o_val = row[14].strip() if len(row) > 14 else ""
                    i_val = row[8].strip() if len(row) > 8 else ""
                    if q_val in ("1", "999") or p_val == "1" or o_val == "1" or i_val in ("1", "999", "333", "666", "888"):
                        continue
                    j_val = row[9].strip().lower() if len(row) > 9 else ""
                    if j_val in ("в работе", "на модерации", "на модерации с опз"):
                        continue
                    try:
                        slot_time = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%Y %H:%M")
                        slot_time = moscow_tz.localize(slot_time)
                    except:
                        continue
                    if now >= slot_time:
                        to_publish.append((row_idx, row))

                if to_publish:
                    from collections import defaultdict
                    groups = defaultdict(list)
                    for row_idx, row in to_publish:
                        date_str = row[0].strip()
                        time_str = row[1].strip()
                        groups[(date_str, time_str)].append((row_idx, row))

                    from .handlers.slots import publish_scheduled_slot
                    for (date, time), items in groups.items():
                        count_available = len(items)
                        row_ids = [item[0] for item in items]
                        for row_idx in row_ids:
                            try:
                                sheet.update_cell(row_idx, 17, 1)  # Q
                            except Exception as e:
                                logger.error(f"Не удалось обновить Q для строки {row_idx} на листе {sheet_name}: {e}")
                        await publish_scheduled_slot(
                            bot, active_slots, platform, count_available,
                            date, time, row_ids, attempt=1
                        )
                        logger.info(f"Опубликован слот {platform} ({count_available} шт.) – попытка 1 (лист {sheet_name})")

                # --- Перепубликация через 2 часа ---
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
                                if j_val not in ("в работе", "на модерации", "на модерации с опз"):
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
                        col_idx = 9   # I (исправлено с 8 на 9)
                    else:
                        col_idx = None

                    if col_idx:
                        for row_idx in available_rows:
                            try:
                                sheet.update_cell(row_idx, col_idx, 1)
                            except Exception as e:
                                logger.error(f"Не удалось обновить столбец {col_idx} для строки {row_idx} на листе {sheet_name}: {e}")

                    await publish_scheduled_slot(
                        bot, active_slots, slot["platform"], len(available_rows),
                        slot["date"], slot["time"], available_rows, attempt=new_attempt
                    )
                    logger.info(f"Переопубликован слот {slot['platform']} ({len(available_rows)} шт.) – попытка {new_attempt} (лист {sheet_name})")

                # --- Закрытие в 23:30 (НОВАЯ ЛОГИКА) ---
                if now.hour == 23 and now.minute >= 30:
                    # Собираем всех пользователей с активными сессиями
                    from bot.handlers.slots import slot_requests
                    users_with_sessions = list(slot_requests.keys())

                    # Проходим по всем слотам и строкам
                    for msg_id, slot in list(active_slots.items()):
                        # Получаем список строк
                        rows_to_process = []
                        for row_idx in slot.get("row_ids", []):
                            try:
                                j_val = sheet.cell(row_idx, 10).value or ""
                                k_val = sheet.cell(row_idx, 11).value or ""
                                rows_to_process.append((row_idx, j_val, k_val))
                            except:
                                continue

                        # Группируем по пользователю (K)
                        user_rows = {}
                        for row_idx, j_val, k_val in rows_to_process:
                            if k_val:
                                user_rows.setdefault(k_val, []).append((row_idx, j_val))

                        # Обрабатываем каждого пользователя
                        for k_val, row_list in user_rows.items():
                            # Проверяем, есть ли у пользователя активная сессия
                            user_id = None
                            # Извлекаем user_id из K (формат @username или просто имя)
                            # В K хранится @username или имя, нужно найти пользователя по username
                            username = k_val.lstrip('@')
                            user = get_user_by_username(username)
                            if user:
                                user_id = user['user_id']
                            else:
                                # если не нашли, пропускаем
                                continue

                            if user_id in users_with_sessions:
                                # Пользователь не завершил слот
                                # Для всех строк с J == "на модерации" меняем на "на модерации с ОПЗ"
                                # Для всех строк с J == "в работе" снимаем
                                for row_idx, j_val in row_list:
                                    if j_val.lower() == "на модерации":
                                        try:
                                            sheet.update_cell(row_idx, 10, "на модерации с ОПЗ")
                                            # I = 333 (на модерации) - уже стоит, если было, но оставим
                                        except Exception as e:
                                            logger.error(f"Ошибка обновления статуса ОПЗ для строки {row_idx}: {e}")
                                    elif j_val.lower() == "в работе":
                                        try:
                                            sheet.update_cell(row_idx, 10, "не принят в работу")
                                            sheet.update_cell(row_idx, 11, "")  # очищаем исполнителя
                                            sheet.update_cell(row_idx, 9, 888)   # I = 888
                                            sheet.format(f"I{row_idx}", {
                                                "backgroundColor": {"red": 0, "green": 0, "blue": 0.8}  # синий
                                            })
                                        except Exception as e:
                                            logger.error(f"Ошибка снятия строки {row_idx}: {e})

                                # Уведомляем пользователя
                                try:
                                    await bot.send_message(
                                        user_id,
                                        "⚠️ Вы не успели выполнить все отзывы до 23:59 МСК. "
                                        "Невыполненные отзывы сняты с вас. "
                                        "Оплата за выполненные отзывы в этом слоте будет снижена на 50%."
                                    )
                                except:
                                    pass
                                # Удаляем сессию пользователя
                                if user_id in slot_requests:
                                    del slot_requests[user_id]

                    # Закрываем все слоты (удаляем из active_slots)
                    for msg_id in list(active_slots.keys()):
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

# ============ ОБНОВЛЕНИЕ СТАТИСТИКИ (с поддержкой ОПЗ и новых статусов) ============
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
        spreadsheet = client.open_by_key(SHEET_ID)

        # Собираем все строки со всех листов
        all_rows = []
        for sheet in spreadsheet.worksheets():
            records = sheet.get_all_values()
            if len(records) > 1:
                for row in records[1:]:
                    all_rows.append(row)

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
            for row in all_rows:
                if len(row) < 10:
                    continue
                platform_raw = row[3].strip()
                status = row[9].strip().lower()
                flag_stat = row[8].strip()
                executor = row[10].strip()

                # Пропускаем уже обработанные (I не 0 и не пусто)
                if flag_stat not in ("", "0"):
                    continue

                platform = match_platform(platform_raw)
                if not platform:
                    continue

                executor_clean = executor.lstrip("@").lower()
                user = get_user_by_username(executor_clean)

                # Обработка статусов
                if status == "опубликован":
                    # Полная оплата
                    if user:
                        uid = user["user_id"]
                        price = PRICES.get(platform, 0)
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
                        # Начисляем полную сумму
                        cur.execute("UPDATE users SET payout = payout + ?, total_earned = total_earned + ? WHERE user_id = ?", (price, price, uid))
                        # Ставим I=1
                        # отметим, что обработано позже
                    else:
                        # пользователь не найден, ставим I=2
                        pass

                elif status == "опубликован опз":
                    # Оплата с 20% штрафом
                    if user:
                        uid = user["user_id"]
                        price = PRICES.get(platform, 0)
                        price_opz = int(price * 0.8)  # 20% меньше
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
                        cur.execute("UPDATE users SET payout = payout + ?, total_earned = total_earned + ? WHERE user_id = ?", (price_opz, price_opz, uid))
                    else:
                        pass

                elif status == "удален":
                    # Вычитаем полную цену
                    if user:
                        uid = user["user_id"]
                        price = PRICES.get(platform, 0)
                        cur.execute("UPDATE users SET payout = payout - ?, total_earned = total_earned - ? WHERE user_id = ?", (price, price, uid))
                        cur.execute("UPDATE users SET payout = MAX(payout, 0), total_earned = MAX(total_earned, 0) WHERE user_id = ?", (uid,))
                        # Уменьшаем общий счетчик
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
                            total_field = f"{field_prefix}_total"
                            cur.execute(f"UPDATE users SET {total_field} = {total_field} - 1 WHERE user_id = ? AND {total_field} > 0", (uid,))
                    # Ставим I=3
                elif status == "опубликован не по тх":
                    # Игнорируем
                    pass

                processed += 1

            conn.commit()

            # Пересчёт выплат (пересчитываем на основе passed)
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
                # total_earned уже обновлён, не пересчитываем
            conn.commit()

            # Реферальные бонусы (без изменений)
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

            # Обновляем флаги I в Google Sheets для обработанных строк
            for sheet in spreadsheet.worksheets():
                records = sheet.get_all_values()
                for row_idx, row in enumerate(records[1:], start=2):
                    if len(row) < 10:
                        continue
                    flag_stat = row[8].strip()
                    if flag_stat not in ("", "0"):
                        continue
                    status = row[9].strip().lower()
                    if status == "опубликован":
                        try:
                            sheet.update_cell(row_idx, 9, 1)  # I=1
                        except:
                            pass
                    elif status == "опубликован опз":
                        try:
                            sheet.update_cell(row_idx, 9, 1)  # I=1, но мы могли бы использовать другой код, но оставим 1
                        except:
                            pass
                    elif status == "удален":
                        try:
                            sheet.update_cell(row_idx, 9, 3)  # I=3
                        except:
                            pass
                    elif status == "опубликован не по тх":
                        try:
                            sheet.update_cell(row_idx, 9, 4)  # I=4
                        except:
                            pass
                    # Для статусов "на модерации" и "на модерации с ОПЗ" мы не меняем I, они остаются 0 или 333

        logger.info(f"Статистика обновлена, обработано строк: {processed}")

    except Exception as e:
        logger.error(f"Ошибка обновления статистики: {e}")
