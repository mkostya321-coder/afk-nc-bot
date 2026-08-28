import os, sqlite3, logging, asyncio, secrets
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

# Расширенный словарь с точными названиями листов (без ведущих пробелов)
SHEET_NAME_TO_PLATFORM = {
    # Точные названия из логов (без пробелов в начале)
    "ЯНДЕКС (К)": "яндекс",
    "2ГИС (Г)": "2гис",
    "google (С)": "google",
    "АВИТО (А)": "авито",          # исправлено – без пробела в начале
    "Продокторов (ПР)": "про докторов",
    "ВК (ВК)": "вк",
    "ДокДок (ДД)": "докдок",
    "32Топ (Т)": "32топ",
    "Докту (ДК)": "докту",
    # Варианты без скобок
    "ЯНДЕКС": "яндекс", "Яндекс": "яндекс", "yandex": "яндекс",
    "2ГИС": "2гис", "2гис": "2гис",
    "google": "google", "Google": "google", "GOOGLE": "google",
    "АВИТО": "авито", "Авито": "авито", "avito": "авито",
    "Продокторов": "про докторов", "про докторов": "про докторов", "prodoctors": "про докторов",
    "ВК": "вк", "вк": "вк", "vk": "вк",
    "ДокДок": "докдок", "докдок": "докдок",
    "32Топ": "32топ", "32топ": "32топ", "32top": "32топ",
    "Докту": "докту", "докту": "докту", "doctu": "докту",
}

def match_platform(raw_name: str) -> str | None:
    name = raw_name.strip().lower()
    for std, aliases in PLATFORM_ALIASES.items():
        for a in aliases:
            if a in name:
                return std
    return None

def platform_from_sheet_name(sheet_name: str) -> str | None:
    # Убираем пробелы в начале и конце
    key = sheet_name.strip()
    # Сначала точное совпадение
    if key in SHEET_NAME_TO_PLATFORM:
        return SHEET_NAME_TO_PLATFORM[key]
    # Потом пробуем без учёта регистра
    key_lower = key.lower()
    if key_lower in SHEET_NAME_TO_PLATFORM:
        return SHEET_NAME_TO_PLATFORM[key_lower]
    # Если ничего не найдено, пробуем сопоставить по первому слову (например, "ЯНДЕКС")
    first_word = key.split()[0] if key.split() else key
    if first_word in SHEET_NAME_TO_PLATFORM:
        return SHEET_NAME_TO_PLATFORM[first_word]
    first_word_lower = first_word.lower()
    if first_word_lower in SHEET_NAME_TO_PLATFORM:
        return SHEET_NAME_TO_PLATFORM[first_word_lower]
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
                logger.error("❌ Не удалось получить credentials для Google Sheets")
                await asyncio.sleep(60)
                continue
            client = gspread.authorize(creds)
            spreadsheet = client.open_by_key(SHEET_ID)
            worksheets = spreadsheet.worksheets()
            now = datetime.now(moscow_tz)
            logger.info(f"🔍 Проверка таблицы в {now.strftime('%H:%M')}, листов: {len(worksheets)}")
            sheet_names = [ws.title for ws in worksheets]
            logger.info(f"📋 Названия листов: {sheet_names}")

            for sheet in worksheets:
                sheet_name = sheet.title
                platform = platform_from_sheet_name(sheet_name)
                if not platform:
                    logger.info(f"⏭️ Пропускаем лист '{sheet_name}' (неизвестная платформа)")
                    continue
                logger.info(f"📋 Обработка листа '{sheet_name}' (платформа: {platform})")

                records = sheet.get_all_values()
                if not records or len(records) < 2:
                    logger.info(f"ℹ️ Лист '{sheet_name}' пуст или только заголовки")
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
                    logger.info(f"📢 Найдено {len(to_publish)} строк для публикации на листе '{sheet_name}'")
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
                        logger.info(f"🚀 Публикуем слот {platform} на {date} {time}, {count_available} шт.")
                        for row_idx in row_ids:
                            try:
                                review_id = secrets.token_hex(4)
                                sheet.update_cell(row_idx, 17, 1)  # Q
                                sheet.update_cell(row_idx, 19, review_id)  # S
                            except Exception as e:
                                logger.error(f"Не удалось обновить Q/ID для строки {row_idx}: {e}")
                        await publish_scheduled_slot(
                            bot, active_slots, platform, count_available,
                            date, time, row_ids, attempt=1
                        )
                        logger.info(f"✅ Слот {platform} опубликован (лист {sheet_name})")
                else:
                    logger.info(f"ℹ️ Нет строк для публикации на листе '{sheet_name}'")

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
                    logger.info(f"🔄 Перепубликация слота {slot['platform']} (попытка {slot['attempt']+1})")
                    try:
                        await bot.edit_message_text(
                            chat_id=CHANNEL_ID, message_id=msg_id,
                            text="Срок размещения истёк. Неразобранные отзывы будут переопубликованы."
                        )
                    except:
                        pass
                    del active_slots[msg_id]

                    new_attempt = slot["attempt"] + 1
                    if new_attempt == 2:
                        col_idx = 15  # P
                    elif new_attempt == 3:
                        col_idx = 14  # O
                    elif new_attempt == 4:
                        col_idx = 9   # I
                    else:
                        col_idx = None

                    if col_idx:
                        for row_idx in available_rows:
                            try:
                                sheet.update_cell(row_idx, col_idx, 1)
                            except Exception as e:
                                logger.error(f"Не удалось обновить столбец {col_idx} для строки {row_idx}: {e}")

                    await publish_scheduled_slot(
                        bot, active_slots, slot["platform"], len(available_rows),
                        slot["date"], slot["time"], available_rows, attempt=new_attempt
                    )
                    logger.info(f"✅ Слот {slot['platform']} переопубликован (попытка {new_attempt})")

                # ---------- ЗАКРЫТИЕ В 23:30 (ОБРАБОТКА ВСЕХ АКТИВНЫХ СЕССИЙ) ----------
                if now.hour == 23 and now.minute >= 30:
                    logger.info("🕒 Начинаем закрытие слотов в 23:30")
                    from bot.handlers.slots import slot_requests

                    # 1. Обрабатываем все активные сессии пользователей
                    if slot_requests:
                        logger.info(f"👥 Найдено {len(slot_requests)} активных сессий пользователей")
                        for user_id, request in list(slot_requests.items()):
                            assigned_rows = request.get("assigned_rows", [])
                            if not assigned_rows:
                                continue

                            # Обновляем строки на всех листах
                            for sheet in spreadsheet.worksheets():
                                for row_idx in assigned_rows:
                                    try:
                                        j_val = sheet.cell(row_idx, 10).value or ""
                                        if j_val.lower() == "на модерации":
                                            sheet.update_cell(row_idx, 10, "на модерации с ОПЗ")
                                            logger.info(f"✅ Строка {row_idx} переведена в 'на модерации с ОПЗ'")
                                        elif j_val.lower() == "в работе":
                                            sheet.update_cell(row_idx, 10, "не принят в работу")
                                            sheet.update_cell(row_idx, 11, "")
                                            sheet.update_cell(row_idx, 9, 888)
                                            sheet.format(f"I{row_idx}", {
                                                "backgroundColor": {"red": 0, "green": 0, "blue": 0.8}
                                            })
                                            logger.info(f"✅ Строка {row_idx} снята (не принят в работу)")
                                    except Exception as e:
                                        logger.error(f"Ошибка обновления строки {row_idx}: {e}")

                            # Отправляем уведомление пользователю
                            try:
                                await bot.send_message(
                                    user_id,
                                    "⚠️ Вы не успели выполнить все отзывы до 23:59 МСК. "
                                    "Невыполненные отзывы сняты с вас. "
                                    "Оплата за выполненные отзывы в этом слоте будет снижена на 30%."
                                )
                                logger.info(f"📩 Уведомление отправлено пользователю {user_id}")
                            except Exception as e:
                                logger.error(f"Не удалось отправить уведомление пользователю {user_id}: {e}")

                            # Удаляем сессию пользователя
                            del slot_requests[user_id]

                    # 2. Закрываем все активные слоты
                    for msg_id in list(active_slots.keys()):
                        try:
                            await bot.edit_message_text(
                                chat_id=CHANNEL_ID, message_id=msg_id,
                                text="Рабочий день завершён. Все слоты закрыты."
                            )
                        except Exception as e:
                            logger.error(f"Не удалось отредактировать сообщение слота {msg_id}: {e}")
                        del active_slots[msg_id]
                    logger.info("✅ Все слоты закрыты в 23:30")

        except Exception as e:
            logger.error(f"❌ Ошибка в планировщике слотов: {e}", exc_info=True)
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
        wait_seconds = (next_target - now).total_seconds()
        logger.info(f"⏳ Следующее обновление статистики в {next_target.strftime('%H:%M')}, ждём {wait_seconds/60:.1f} мин.")
        await asyncio.sleep(wait_seconds)
        await update_stats_from_sheet_once()

async def update_stats_from_sheet_once():
    try:
        logger.info("🔄 Запуск обновления статистики")
        creds = get_credentials()
        if not creds:
            logger.error("❌ Нет credentials для обновления статистики")
            return
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key(SHEET_ID)

        updates = []

        for sheet in spreadsheet.worksheets():
            records = sheet.get_all_values()
            if len(records) < 2:
                continue
            sheet_name = sheet.title
            logger.info(f"📊 Обработка листа '{sheet_name}' для статистики")

            for row_idx, row in enumerate(records[1:], start=2):
                if len(row) < 10:
                    continue
                platform_raw = row[3].strip()
                status = row[9].strip().lower()
                flag_stat = row[8].strip()
                executor = row[10].strip()

                if flag_stat not in ("", "0"):
                    continue

                platform = match_platform(platform_raw)
                if not platform:
                    continue

                executor_clean = executor.lstrip("@").lower()
                user = get_user_by_username(executor_clean)
                e_value = None

                if status == "опубликован":
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
                        with sqlite3.connect(DB_PATH) as conn:
                            cur = conn.cursor()
                            if field_prefix:
                                passed_field = f"{field_prefix}_passed"
                                total_field = f"{field_prefix}_total"
                                cur.execute(f"UPDATE users SET {passed_field} = {passed_field} + 1, {total_field} = {total_field} + 1 WHERE user_id = ?", (uid,))
                            cur.execute("UPDATE users SET payout = payout + ?, total_earned = total_earned + ? WHERE user_id = ?", (price, price, uid))
                            conn.commit()
                        e_value = 1
                        logger.info(f"✅ Начислено {price}₽ пользователю {uid} за {platform}")
                    else:
                        e_value = 2

                elif status == "опубликован опз":
                    if user:
                        uid = user["user_id"]
                        price = PRICES.get(platform, 0)
                        price_opz = int(price * 0.7)
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
                        with sqlite3.connect(DB_PATH) as conn:
                            cur = conn.cursor()
                            if field_prefix:
                                passed_field = f"{field_prefix}_passed"
                                total_field = f"{field_prefix}_total"
                                cur.execute(f"UPDATE users SET {passed_field} = {passed_field} + 1, {total_field} = {total_field} + 1 WHERE user_id = ?", (uid,))
                            cur.execute("UPDATE users SET payout = payout + ?, total_earned = total_earned + ? WHERE user_id = ?", (price_opz, price_opz, uid))
                            conn.commit()
                        e_value = 1
                        logger.info(f"✅ Начислено {price_opz}₽ (ОПЗ) пользователю {uid} за {platform}")
                    else:
                        e_value = 2

                elif status == "удален":
                    if user:
                        uid = user["user_id"]
                        price = PRICES.get(platform, 0)
                        with sqlite3.connect(DB_PATH) as conn:
                            cur = conn.cursor()
                            cur.execute("UPDATE users SET payout = payout - ?, total_earned = total_earned - ? WHERE user_id = ?", (price, price, uid))
                            cur.execute("UPDATE users SET payout = MAX(payout, 0), total_earned = MAX(total_earned, 0) WHERE user_id = ?", (uid,))
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
                            conn.commit()
                        e_value = 3
                        logger.info(f"✅ Вычтено {price}₽ у пользователя {uid} за удалённый отзыв ({platform})")
                    else:
                        e_value = 2

                elif status == "опубликован не по тх":
                    e_value = 4
                    logger.info(f"ℹ️ Строка {row_idx} на листе {sheet_name}: опубликован не по ТХ, пропускаем")

                if e_value is not None:
                    updates.append((sheet, row_idx, e_value))

        for sheet, row_idx, e_value in updates:
            try:
                sheet.update_cell(row_idx, 5, e_value)
                logger.info(f"✅ Обновлён E строки {row_idx} на {e_value} (лист {sheet.title})")
            except Exception as e:
                logger.error(f"❌ Не удалось обновить E для строки {row_idx}: {e}")

        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT user_id, yandex_passed, google_passed, gis_passed, avito_passed, vk_passed,
                       otzovik_passed, doctoru_passed, dokdok_passed, prodoctors_passed,
                       doctu_passed, top32_passed
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
            conn.commit()

        logger.info(f"✅ Статистика обновлена, обработано строк: {len(updates)}")

    except Exception as e:
        logger.error(f"❌ Ошибка обновления статистики: {e}", exc_info=True)
