# bot/username_checker.py
import asyncio
import logging
import gspread
import sqlite3
from datetime import datetime, timedelta
from oauth2client.service_account import ServiceAccountCredentials
from bot.config import SHEET_ID, DB_PATH, get_credentials_path
from bot.database import get_user_by_username, update_user_field, get_user
from bot.helpers import platform_from_sheet_name, get_column_mapping  # <-- импорт из helpers

logger = logging.getLogger(__name__)

# Дни недели для проверки: вторник (1), пятница (4), воскресенье (6)
CHECK_DAYS = [1, 4, 6]

async def username_checker(bot):
    """Проверка username каждый вторник, пятницу, воскресенье с 2:30 до 6:00 МСК"""
    logger.info("🔄 Запущен модуль проверки username")
    
    while True:
        now = datetime.now()
        current_weekday = now.weekday()
        current_hour = now.hour
        current_minute = now.minute
        
        if current_weekday in CHECK_DAYS:
            is_in_window = (current_hour == 2 and current_minute >= 30) or (3 <= current_hour < 6)
            
            if is_in_window:
                logger.info(f"🔄 Начинаем проверку username пользователей (текущее время: {now.strftime('%H:%M')})")
                try:
                    await check_all_usernames(bot)
                    logger.info("✅ Проверка username завершена")
                except Exception as e:
                    logger.error(f"❌ Ошибка при проверке username: {e}")
                
                await asyncio.sleep(3600)
                continue
            
            if current_hour < 2 or (current_hour == 2 and current_minute < 30):
                target = now.replace(hour=2, minute=30, second=0, microsecond=0)
                wait_seconds = (target - now).total_seconds()
                if wait_seconds > 0:
                    logger.info(f"⏳ Ждём до 2:30 МСК для проверки username ({wait_seconds/60:.1f} мин.)")
                    await asyncio.sleep(wait_seconds)
                continue
            
            if current_hour >= 6:
                logger.info(f"⏳ Время проверки (2:30-6:00) прошло, ждём следующий день")
        
        days_until_check = 7
        for day in CHECK_DAYS:
            if day > current_weekday:
                days_until_check = day - current_weekday
                break
        
        if days_until_check == 7:
            days_until_check = CHECK_DAYS[0] + (7 - current_weekday)
        
        next_check = datetime.now().replace(hour=2, minute=30, second=0, microsecond=0) + timedelta(days=days_until_check)
        wait_seconds = (next_check - datetime.now()).total_seconds()
        
        if wait_seconds > 0:
            logger.info(f"⏳ Следующая проверка username в {next_check.strftime('%A %d.%m.%Y %H:%M')} МСК, ждём {wait_seconds/3600:.1f} ч.")
            await asyncio.sleep(wait_seconds)

async def check_all_usernames(bot):
    """Проверяет всех пользователей и обновляет username в таблице"""
    try:
        logger.info("🔍 Получаем всех зарегистрированных пользователей")
        
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("SELECT user_id, tg_username FROM users WHERE tg_username IS NOT NULL")
            users = cur.fetchall()
        
        logger.info(f"👥 Найдено {len(users)} пользователей для проверки")
        
        updated_count = 0
        error_count = 0
        checked_count = 0
        
        for user in users:
            user_id = user['user_id']
            old_username = user['tg_username']
            checked_count += 1
            
            try:
                chat = await bot.get_chat(user_id)
                new_username = chat.username.lower() if chat.username else None
                
                if new_username and new_username != old_username:
                    logger.info(f"🔄 У пользователя {user_id} изменился username: {old_username} -> {new_username}")
                    
                    update_user_field(user_id, "tg_username", new_username)
                    await update_username_in_sheets(old_username, new_username)
                    
                    updated_count += 1
                elif not new_username and old_username:
                    logger.warning(f"⚠️ У пользователя {user_id} удалён username (был @{old_username})")
                
                await asyncio.sleep(0.2)
                
            except Exception as e:
                logger.error(f"❌ Ошибка при проверке пользователя {user_id}: {e}")
                error_count += 1
        
        logger.info(f"✅ Проверка username завершена: проверено {checked_count} пользователей, обновлено {updated_count}, ошибок {error_count}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка в check_all_usernames: {e}")

async def update_username_in_sheets(old_username: str, new_username: str):
    """Обновляет username во всех строках Google Sheets"""
    try:
        from bot.google_sheets import get_credentials  # <-- импорт внутри функции
        
        creds = get_credentials()
        if not creds:
            logger.error("❌ Нет credentials для обновления username")
            return
        
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key(SHEET_ID)
        
        updated_rows = 0
        
        for sheet in spreadsheet.worksheets():
            records = sheet.get_all_values()
            if len(records) < 2:
                continue
            
            platform = platform_from_sheet_name(sheet.title)
            mapping = get_column_mapping(platform) if platform else get_column_mapping("яндекс")
            
            old_username_lower = old_username.lower()
            new_username_lower = new_username.lower()
            
            for row_idx, row in enumerate(records[1:], start=2):
                if len(row) < mapping["executor_col"]:
                    continue
                
                executor = row[mapping["executor_col"]-1].strip().lstrip("@").lower()
                
                if executor == old_username_lower:
                    try:
                        sheet.update_cell(row_idx, mapping["executor_col"], f"@{new_username_lower}")
                        updated_rows += 1
                        await asyncio.sleep(0.05)
                        logger.info(f"✅ Обновлён username в строке {row_idx} (лист {sheet.title})")
                    except Exception as e:
                        logger.error(f"❌ Не удалось обновить строку {row_idx}: {e}")
        
        logger.info(f"✅ Обновлено {updated_rows} строк с username {old_username} -> {new_username}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка в update_username_in_sheets: {e}")
