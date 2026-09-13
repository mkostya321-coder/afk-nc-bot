# bot/username_checker.py
import asyncio
import logging
import gspread
import sqlite3
from datetime import datetime, timedelta
import pytz
from oauth2client.service_account import ServiceAccountCredentials
from bot.config import SHEET_ID, DB_PATH, get_credentials_path
from bot.database import get_user_by_username, update_user_field, get_user
from bot.helpers import platform_from_sheet_name, get_column_mapping

logger = logging.getLogger(__name__)
moscow_tz = pytz.timezone("Europe/Moscow")

CHECK_DAYS = [1, 4, 6]  # вт, пт, вс


async def username_checker(bot):
    """Проверка username по МСК: вт/пт/вс с 2:30 до 6:00."""
    logger.info("🔄 Запущен модуль проверки username")

    while True:
        now = datetime.now(moscow_tz)
        current_weekday = now.weekday()
        current_hour = now.hour
        current_minute = now.minute

        if current_weekday in CHECK_DAYS:
            is_in_window = (current_hour == 2 and current_minute >= 30) or (3 <= current_hour < 6)

            if is_in_window:
                logger.info(f"🔄 Проверка username (МСК {now.strftime('%H:%M')})")
                try:
                    await check_all_usernames(bot)
                    logger.info("✅ Проверка username завершена")
                except Exception as e:
                    logger.error(f"❌ Ошибка проверки username: {e}")

                await asyncio.sleep(3600)
                continue

            if current_hour < 2 or (current_hour == 2 and current_minute < 30):
                target = now.replace(hour=2, minute=30, second=0, microsecond=0)
                wait_seconds = (target - now).total_seconds()
                if wait_seconds > 0:
                    logger.info(f"⏳ Ждём до 2:30 МСК ({wait_seconds/60:.1f} мин.)")
                    await asyncio.sleep(wait_seconds)
                continue

            if current_hour >= 6:
                logger.info("⏳ Окно 2:30–6:00 прошло, ждём следующий день")

        # Ближайший день из CHECK_DAYS
        days_until_check = 7
        for day in CHECK_DAYS:
            if day > current_weekday:
                days_until_check = day - current_weekday
                break
        if days_until_check == 7:
            days_until_check = CHECK_DAYS[0] + (7 - current_weekday)

        next_check = (now + timedelta(days=days_until_check)).replace(
            hour=2, minute=30, second=0, microsecond=0
        )
        wait_seconds = (next_check - now).total_seconds()
        if wait_seconds > 0:
            logger.info(f"⏳ Следующая проверка: {next_check.strftime('%a %d.%m.%Y %H:%M')} МСК")
            await asyncio.sleep(wait_seconds)
