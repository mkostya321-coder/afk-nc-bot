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

# Расширенный словарь с точными названиями листов (включая пробелы и скобки)
SHEET_NAME_TO_PLATFORM = {
    # Обычные названия (без пробелов и скобок)
    "яндекс": "яндекс", "yandex": "яндекс",
    "google": "google",
    "2гис": "2гис",
    "авито": "авито", "avito": "авито",
    "продокторов": "про докторов", "про докторов": "про докторов", "prodoctors": "про докторов",
    "вк": "вк", "vk": "вк",
    "докдок": "докдок",
    "32топ": "32топ", "32top": "32топ", "32 топ": "32топ",
    "докту": "докту", "doctu": "докту",
    # Точные названия из логов (с пробелами и скобками)
    "ЯНДЕКС (К)": "яндекс",
    "2ГИС (Г)": "2гис",
    "google (С)": "google",
    " АВИТО (А)": "авито",   # с пробелом в начале
    "Продокторов (ПР)": "про докторов",
    "ВК (ВК)": "вк",
    "ДокДок (ДД)": "докдок",
    "32Топ (Т)": "32топ",
    "Докту (ДК)": "докту",
    # Варианты с заглавными без скобок
    "Яндекс": "яндекс", "ЯНДЕКС": "яндекс",
    "Google": "google", "GOOGLE": "google",
    "2ГИС": "2гис", "2Гис": "2гис",
    "Авито": "авито", "АВИТО": "авито",
    "Продокторов": "про докторов", "ПРОДОКТОРОВ": "про докторов",
    "ВК": "вк", "VK": "вк",
    "ДокДок": "докдок", "ДОКДОК": "докдок",
    "32ТОП": "32топ", "32Топ": "32топ",
    "Докту": "докту", "ДОКТУ": "докту",
}

def match_platform(raw_name: str) -> str | None:
    name = raw_name.strip().lower()
    for std, aliases in PLATFORM_ALIASES.items():
        for a in aliases:
            if a in name:
                return std
    return None

def platform_from_sheet_name(sheet_name: str) -> str | None:
    key = sheet_name.strip()
    # сначала точное совпадение
    if key in SHEET_NAME_TO_PLATFORM:
        return SHEET_NAME_TO_PLATFORM[key]
    # потом пробуем привести к нижнему регистру
    key_lower = key.lower()
    if key_lower in SHEET_NAME_TO_PLATFORM:
        return SHEET_NAME_TO_PLATFORM[key_lower]
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
                                sheet.update_cell(row_idx, 17, 1)  # Q (первая публикация)
                                sheet.update_cell(row_idx, 19, review_id)  # S – уникальный ID
                            except Exception as e:
                                logger.error(f"Не удалось обновить Q/ID для строки {row_idx}: {e}")
                        await publish_scheduled_slot(
                            bot, active_slots, platform, count_available,
                            date, time, row_ids, attempt=1
                        )
                        logger.info(f"✅ Слот {platform} опубликован (лист {sheet_name})")
                else:
                    logger.info(f"ℹ️ Нет строк для публикации на листе '{sheet_name}'")

                # --- Перепубликация через 2 часа (попытки 2, 3, 4) ---
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
                        col_idx = 15  # P (вторая публикация)
                    elif new_attempt == 3:
                        col_idx = 14  # O (третья публикация)
                    elif new_attempt == 4:
                        col_idx = 9   # I (четвёртая, завершительная)
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

                # --- Закрытие в 23:30 ---
                if now.hour == 23 and now.minute >= 30:
                    logger.info("🕒 Начинаем закрытие слотов в 23:30")
                    from bot.handlers.slots import slot_requests
                    users_with_sessions = list(slot_requests.keys())

                    for msg_id, slot in list(active_slots.items()):
                        rows_to_process = []
                        for row_idx in slot.get("row_ids", []):
                            try:
                                j_val = sheet.cell(row_idx, 10).value or ""
                                k_val = sheet.cell(row_idx, 11).value or ""
                                rows_to_process.append((row_idx, j_val, k_val))
                            except:
                                continue

                        user_rows = {}
                        for row_idx, j_val, k_val in rows_to_process:
                            if k_val:
                                user_rows.setdefault(k_val, []).append((row_idx, j_val))

                        for k_val, row_list in user_rows.items():
                            user_id = None
                            username = k_val.lstrip('@')
                            user = get_user_by_username(username)
                            if user:
                                user_id = user['user_id']
                            else:
                                continue

                            if user_id in users_with_sessions:
                                for row_idx, j_val in row_list:
                                    if j_val.lower() == "на модерации":
                                        try:
                                            sheet.update_cell(row_idx, 10, "на модерации с ОПЗ")
                                        except Exception as e:
                                            logger.error(f"Ошибка обновления статуса ОПЗ для строки {row_idx}: {e}")
                                    elif j_val.lower() == "в работе":
                                        try:
                                            sheet.update_cell(row_idx, 10, "не принят в работу
