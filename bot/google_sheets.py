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

            # 1. Проверка истёкших слотов (2 часа)
            expired_slots = []
            for msg_id, slot in list(active_slots.items()):
                publish_time = slot.get("publish_time")
                if publish_time and (now - publish_time).total_seconds() >= 7200:
                    # если слот не тронут (count равен изначальному и row_ids не изменились)
                    if slot["count"] == slot.get("initial_count", 0):
                        expired_slots.append((msg_id, slot))
            for msg_id, slot in expired_slots:
                # Закрываем старый пост
                try:
                    await bot.edit_message_text(
                        chat_id=CHANNEL_ID,
                        message_id=msg_id,
                        text="Срок размещения истёк. Слот будет переопубликован."
                    )
                except:
                    pass
                # Сбрасываем флаги в таблице для этих строк
                for row_idx in slot["row_ids"]:
                    try:
                        sheet.update_cell(row_idx, 5, 0)   # E = 0
                    except Exception as e:
                        logger.error(f"Не удалось сбросить флаг для строки {row_idx}: {e}")
                # Удаляем из активных
                del active_slots[msg_id]
                # Публикуем заново
                from .handlers.slots import publish_scheduled_slot
                await publish_scheduled_slot(
                    bot, active_slots, slot["platform"], slot["initial_count"],
                    slot["date"], slot["time"], slot["row_ids"]
                )
                logger.info(f"Переопубликован слот {slot['platform']} (истекло 2 часа)")

            # 2. Публикация новых слотов по времени
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
                    await publish_scheduled_slot(
                        bot, active_slots, platform, count_available,
                        date, time, row_ids
                    )
                    logger.info(f"Опубликован слот {platform} ({count_available} шт.)")
                    for row_idx in row_ids:
                        try:
                            sheet.update_cell(row_idx, 5, 1)
                        except Exception as e:
                            logger.error(f"Не удалось обновить флаг для строки {row_idx}: {e}")

        except Exception as e:
            logger.error(f"Ошибка в планировщике слотов: {e}")
        await asyncio.sleep(60)

# Остальная часть (update_stats_from_sheet и т.д.) остаётся без изменений
