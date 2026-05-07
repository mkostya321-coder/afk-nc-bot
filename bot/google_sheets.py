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


async def monitor_schedule(bot, active_slots: dict):
    """
    Каждые 60 секунд проверяет таблицу на наступление времени публикации.
    Если находит подходящие строки – группирует по платформе и времени,
    публикует слот в канал и запоминает его в active_slots.
    """
    logger.info("Планировщик слотов запущен")
    while True:
        try:
            creds_path = "/data/google_key.json"
            if not os.path.exists(creds_path):
                creds_path = "google_key.json"
            if not os.path.exists(creds_path):
                logger.error("Файл google_key.json не найден – мониторинг остановлен")
                await asyncio.sleep(60)
                continue

            scope = [
                "https://spreadsheets.google.com/feeds",
                "https://www.googleapis.com/auth/drive"
            ]
            creds = ServiceAccountCredentials.from_json_keyfile_name(creds_path, scope)
            client = gspread.authorize(creds)
            sheet = client.open_by_key(SHEET_ID).sheet1
            records = sheet.get_all_values()
            now = datetime.now(moscow_tz)

            # Ищем строки, у которых дата и время уже наступили, а слот ещё не опубликован
            to_publish = []   # (platform, row_idx, row_data)
            for row_idx, row in enumerate(records[1:], start=2):
                if len(row) < 8:        # минимально нужны столбцы A-H
                    continue
                date_str = row[0].strip()   # A – дата (например, "07.05.2026")
                time_str = row[1].strip()   # B – время (например, "14:00")
                flag = row[4].strip()       # E – флаг обновления (0/1/2)

                if flag != "0":
                    continue

                try:
                    slot_time = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%Y %H:%M")
                    slot_time = moscow_tz.localize(slot_time)
                except:
                    continue

                if now >= slot_time:
                    platform_raw = row[3].strip()   # D – платформа
                    platform = match_platform(platform_raw)
                    if platform:
                        to_publish.append((platform, row_idx, row))

            if not to_publish:
                await asyncio.sleep(60)
                continue

            # Группируем по платформе и времени
            from collections import defaultdict
            groups = defaultdict(list)
            for platform, row_idx, row in to_publish:
                date_str = row[0].strip()
                time_str = row[1].strip()
                groups[(platform, date_str, time_str)].append((row_idx, row))

            # Публикуем слоты
            for (platform, date, time), items in groups.items():
                count_available = len(items)
                row_ids = [item[0] for item in items]

                # Импортируем функцию публикации (чтобы избежать циклического импорта)
                from .handlers.slots import publish_scheduled_slot
                await publish_scheduled_slot(
                    bot, active_slots, platform, count_available,
                    date, time, row_ids
                )

                # Помечаем строки флагом 1 (опубликовано)
                for row_idx in row_ids:
                    try:
                        sheet.update_cell(row_idx, 5, 1)   # столбец E = 1
                    except Exception as e:
                        logger.error(f"Не удалось обновить флаг для строки {row_idx}: {e}")

        except Exception as e:
            logger.error(f"Ошибка в планировщике слотов: {e}")

        await asyncio.sleep(60)
