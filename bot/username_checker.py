# bot/username_checker.py
import asyncio
import logging
import sqlite3
from datetime import datetime, timedelta
import pytz
from bot.config import SHEET_ID, DB_PATH
from bot.database import get_user, update_user_field
from bot.helpers import platform_from_sheet_name, get_column_mapping

logger = logging.getLogger(__name__)
moscow_tz = pytz.timezone("Europe/Moscow")

CHECK_DAYS = [1, 4, 6]  # вт, пт, вс


async def check_all_usernames(bot):
    """
    Проходит по всем зарегистрированным юзерам с username в БД.
    Для каждого вызывает get_chat(user_id) — если в Telegram username изменился,
    обновляет в БД и синхронизирует в Google Sheets.
    """
    logger.info("🔄 check_all_usernames: старт проверки")

    # Берём всех юзеров с tg_username
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT user_id, tg_username FROM users WHERE tg_username IS NOT NULL AND tg_username != ''")
        users = [dict(r) for r in cur.fetchall()]

    if not users:
        logger.info("ℹ️ check_all_usernames: нет юзеров с username")
        return

    logger.info(f"🔄 check_all_usernames: проверяю {len(users)} юзеров")

    # Импортируем здесь, чтобы избежать цикличности
    from bot.google_sheets import sync_username_in_sheets

    updated_db = 0
    updated_sheets = 0
    errors = 0

    for u in users:
        uid = u["user_id"]
        old_username = (u["tg_username"] or "").strip().lower().lstrip("@")
        if not old_username:
            continue

        try:
            chat = await bot.get_chat(uid)
            new_username = (chat.username or "").strip().lower().lstrip("@")
        except Exception as e:
            err = str(e).lower()
            if "chat not found" in err or "user not found" in err or "bot was blocked" in err:
                # Юзер удалил аккаунт или заблокировал бота — пропускаем тихо
                pass
            else:
                logger.debug(f"⚠️ check_all_usernames: get_chat({uid}): {e}")
            errors += 1
            await asyncio.sleep(0.2)
            continue

        # Если username в TG совпадает или пустой — пропускаем
        if not new_username or new_username == old_username:
            await asyncio.sleep(0.2)
            continue

        # Username изменился
        logger.info(f"🔄 check_all_usernames: user {uid}: @{old_username} → @{new_username}")

        try:
            update_user_field(uid, "tg_username", new_username)
            updated_db += 1
        except Exception as e:
            logger.error(f"❌ check_all_usernames: не обновить БД для {uid}: {e}")
            await asyncio.sleep(0.2)
            continue

        # Синхронизируем в Google Sheets
        try:
            cnt = await sync_username_in_sheets(old_username, new_username)
            if cnt:
                updated_sheets += cnt
                logger.info(f"📊 check_all_usernames: обновлено {cnt} строк в таблице для @{old_username} → @{new_username}")
        except Exception as e:
            logger.error(f"❌ check_all_usernames: sync для {uid}: {e}")

        await asyncio.sleep(0.3)  # throttle на API

    logger.info(
        f"✅ check_all_usernames: готово. "
        f"Обновлено в БД: {updated_db}, строк в таблице: {updated_sheets}, ошибок: {errors}"
    )


async def username_checker(bot):
    """Планировщик проверки username: вт/пт/вс с 2:30 до 6:00 МСК."""
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
