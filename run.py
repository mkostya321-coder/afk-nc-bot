import sys
import os
import traceback
from datetime import datetime


# ============================================================
# 🔧 ЛОГ В ФАЙЛ: пишем в /data/, читаем через File Manager
# ============================================================
LOG_FILE = "/data/bot_startup.log"

def _log_to_file(msg: str):
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"[{ts}] {msg}\n")
    except Exception:
        pass

try:
    if os.path.exists(LOG_FILE):
        os.remove(LOG_FILE)
except Exception:
    pass

_log_to_file("=" * 60)
_log_to_file("🚀 STARTING BOT...")
_log_to_file(f"🐍 Python: {sys.version}")
_log_to_file(f"📂 CWD: {os.getcwd()}")
try:
    _log_to_file(f"📂 Файлы: {os.listdir('.')}")
except Exception as e:
    _log_to_file(f"❌ os.listdir: {e}")
_log_to_file("=" * 60)


try:
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr = sys.stdout
except Exception:
    pass


import asyncio, logging, threading
from datetime import timedelta

logging.basicConfig(
    level=logging.INFO,
    stream=sys.stdout,
    format='%(asctime)s %(levelname)s:%(name)s:%(message)s',
    force=True
)
logger = logging.getLogger(__name__)

print("🚀 STARTING BOT...", flush=True)
print(f"🐍 Python: {sys.version}", flush=True)


# ============================================================
# 🔧 ПОШАГОВЫЙ ИМПОРТ — увидим на каком шаге падает
# ============================================================
try:
    _log_to_file("Шаг 1: flask, aiogram, pytz")
    from flask import Flask, Response
    from aiogram import Bot, Dispatcher
    from aiogram.fsm.storage.memory import MemoryStorage
    from aiogram.exceptions import TelegramBadRequest
    import pytz
    _log_to_file("✅ Шаг 1 OK")

    _log_to_file("Шаг 2: bot.config")
    from bot.config import (
        BOT_TOKEN, CHANNEL_ID, REPORT_CHAT_ID, REPORT_THREAD_ID, DB_PATH,
        LOG_CHANNEL_ID, SCREENSHOT_CHANNEL_ID,
        TIKTOK_REPORT_CHAT_ID, COLLABORATION_CHAT_ID, SUPPORT_CHAT_ID,
        REQUIRED_CHANNEL_ID,
    )
    _log_to_file("✅ Шаг 2 OK")

    _log_to_file("Шаг 3: bot.database")
    from bot.database import (
        init_db, get_all_users_with_payout, save_channel_message,
        cleanup_old_review_takes,
    )
    _log_to_file("✅ Шаг 3 OK")

    _log_to_file("Шаг 4: bot.google_sheets")
    from bot.google_sheets import (
        monitor_schedule, update_stats_from_sheet,
        mark_as_paid_in_table, cleanup_channel
    )
    _log_to_file("✅ Шаг 4 OK")

    _log_to_file("Шаг 5: bot.handlers (user, admin, slots, promo)")
    from bot.handlers import user, admin, slots, promo
    _log_to_file("✅ Шаг 5 OK")

    _log_to_file("Шаг 6: admin_advanced")
    from bot.handlers.admin_advanced import router as admin_advanced_router
    _log_to_file("✅ Шаг 6 OK")

    _log_to_file("Шаг 7: bot.middlewares")
    from bot.middlewares import AutoMenuMiddleware, cleanup_subscription_cache
    _log_to_file("✅ Шаг 7 OK")

    _log_to_file("Шаг 8: bot.username_checker")
    from bot.username_checker import username_checker
    _log_to_file("✅ Шаг 8 OK")

    _log_to_file("Шаг 9: bot.state")
    from bot.state import active_slots
    _log_to_file("✅ Шаг 9 OK")

    _log_to_file("Шаг 10: sqlite3")
    import sqlite3
    _log_to_file("✅ Шаг 10 OK")

    _log_to_file("=" * 60)
    _log_to_file("✅✅✅ ВСЕ ИМПОРТЫ OK ✅✅✅")
    _log_to_file("=" * 60)
    print("✅ Все импорты OK", flush=True)

except Exception as e:
    err_text = f"❌ IMPORT ERROR: {type(e).__name__}: {e}\n" + traceback.format_exc()
    _log_to_file("=" * 60)
    _log_to_file(err_text)
    _log_to_file("=" * 60)
    print(err_text, flush=True)
    sys.exit(1)


# ============================================================
# Основной код
# ============================================================
moscow_tz = pytz.timezone("Europe/Moscow")

app = Flask(__name__)


@app.route('/')
def home():
    return "Bot is running!"


@app.route('/health')
def health():
    return Response(status=200)


def run_flask():
    port = int(os.environ.get("PORT", 80))
    app.run(host='0.0.0.0', port=port)


async def validate_chat_ids(bot):
    checks = {
        "CHANNEL_ID": CHANNEL_ID,
        "LOG_CHANNEL_ID": LOG_CHANNEL_ID,
        "SCREENSHOT_CHANNEL_ID": SCREENSHOT_CHANNEL_ID,
        "REPORT_CHAT_ID": REPORT_CHAT_ID,
        "TIKTOK_REPORT_CHAT_ID": TIKTOK_REPORT_CHAT_ID,
        "COLLABORATION_CHAT_ID": COLLABORATION_CHAT_ID,
        "SUPPORT_CHAT_ID": SUPPORT_CHAT_ID,
    }
    for name, cid in checks.items():
        if not cid:
            continue
        try:
            chat = await asyncio.wait_for(bot.get_chat(cid), timeout=10.0)
            logger.info(f"✅ {name} = {cid}")
        except Exception as e:
            logger.warning(f"⚠️ {name} = {cid} — {e}")


async def scheduler(bot):
    while True:
        now = datetime.now(moscow_tz)
        morning_target = now.replace(hour=8, minute=0, second=0, microsecond=0)
        if now >= morning_target:
            morning_target += timedelta(days=1)
        evening_target = now.replace(hour=22, minute=30, second=0, microsecond=0)
        if now >= evening_target:
            evening_target += timedelta(days=1)
        next_time = min(morning_target, evening_target)
        await asyncio.sleep((next_time - now).total_seconds())
        now_after = datetime.now(moscow_tz)
        try:
            if now_after.hour == 8:
                msg = await bot.send_message(CHANNEL_ID, "☀️ Доброе утро! Хорошего дня!")
                save_channel_message(msg.message_id, CHANNEL_ID)
            elif now_after.hour == 22 and now_after.minute >= 30:
                msg = await bot.send_message(CHANNEL_ID, "🌙 День закончен. Всем спасибо!")
                save_channel_message(msg.message_id, CHANNEL_ID)
        except Exception as e:
            logger.error(f"❌ scheduler: {e}")


async def weekly_payout_report(bot):
    while True:
        now = datetime.now(moscow_tz)
        days_ahead = (3 - now.weekday() + 7) % 7
        if days_ahead == 0 and now.hour >= 8:
            days_ahead = 7
        next_thursday = now.replace(hour=8, minute=0, second=0, microsecond=0) + timedelta(days=days_ahead)
        await asyncio.sleep((next_thursday - now).total_seconds())
        try:
            users = get_all_users_with_payout()
            if users:
                text_lines = ["<b>📋 Список на выплату</b>\n"]
                user_ids = []
                for u in users:
                    username = u.get('tg_username') or u.get('username') or str(u['user_id'])
                    phone = u.get('phone_card') or '—'
                    bank = u.get('bank') or '—'
                    line = f"👤 @{username} (ID: {u['user_id']})\n💰 {u['payout']}₽\n📞 {phone}\n🏦 {bank}\n────────"
                    text_lines.append(line)
                    user_ids.append(u['user_id'])
                full_text = "\n".join(text_lines)
                if REPORT_CHAT_ID:
                    for i in range(0, len(full_text), 4000):
                        await bot.send_message(
                            chat_id=REPORT_CHAT_ID, text=full_text[i:i+4000],
                            message_thread_id=REPORT_THREAD_ID or None,
                            parse_mode="HTML"
                        )
                if user_ids:
                    try:
                        await mark_as_paid_in_table(user_ids)
                    except Exception as e:
                        logging.error(f"mark_as_paid: {e}")
                    with sqlite3.connect(DB_PATH) as conn:
                        cur = conn.cursor()
                        ph = ','.join(['?'] * len(user_ids))
                        cur.execute(f"UPDATE users SET payout = 0, admin_topup = 0 WHERE user_id IN ({ph})", user_ids)
                        conn.commit()
        except Exception as e:
            logging.error(f"weekly_payout: {e}")


async def auto_close_slots_2330(bot):
    while True:
        try:
            now = datetime.now(moscow_tz)
            target = now.replace(hour=23, minute=30, second=0, microsecond=0)
            if now >= target:
                target += timedelta(days=1)
            await asyncio.sleep((target - now).total_seconds())
        except Exception as e:
            logger.error(f"❌ auto_close sleep: {e}")
            await asyncio.sleep(60)
            continue

        try:
            now = datetime.now(moscow_tz)
            slots_snapshot = list(active_slots.items())
            deleted = 0
            for msg_id, slot in slots_snapshot:
                try:
                    await bot.delete_message(chat_id=CHANNEL_ID, message_id=msg_id)
                    deleted += 1
                except Exception:
                    pass
                try:
                    del active_slots[msg_id]
                except KeyError:
                    pass
                await asyncio.sleep(0.3)
            logger.info(f"🌙 auto_close: удалено {deleted}")
        except Exception as e:
            logger.error(f"❌ auto_close: {e}")


async def review_takes_cleanup():
    while True:
        try:
            now = datetime.now(moscow_tz)
            target = now.replace(hour=5, minute=0, second=0, microsecond=0)
            if now >= target:
                target += timedelta(days=1)
            await asyncio.sleep((target - now).total_seconds())
            cnt = cleanup_old_review_takes(days=7)
            if cnt:
                logger.info(f"🧹 review_takes: {cnt}")
        except Exception as e:
            logger.error(f"❌ review_takes_cleanup: {e}")
            await asyncio.sleep(3600)


async def subscription_cache_cleanup():
    while True:
        try:
            await asyncio.sleep(600)
            cnt = cleanup_subscription_cache()
            if cnt:
                logger.info(f"🧹 Кэш подписок: {cnt}")
        except Exception as e:
            logger.error(f"❌ subscription_cache_cleanup: {e}")
            await asyncio.sleep(60)


async def main():
    _log_to_file("🔧 main() запущена")

    try:
        init_db()
        _log_to_file("✅ init_db() OK")
    except Exception as e:
        _log_to_file(f"❌ init_db() ERROR: {e}\n{traceback.format_exc()}")
        raise

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    async def close_session():
        await bot.session.close()
    dp.shutdown.register(close_session)

    dp.message.middleware(AutoMenuMiddleware())

    dp.include_router(user.router)
    dp.include_router(admin.router)
    dp.include_router(admin_advanced_router)
    dp.include_router(promo.router)
    dp.include_router(slots.router)

    _log_to_file("✅ Все роутеры подключены")

    asyncio.create_task(validate_chat_ids(bot))
    asyncio.create_task(scheduler(bot))
    asyncio.create_task(monitor_schedule(bot))
    asyncio.create_task(update_stats_from_sheet())
    asyncio.create_task(weekly_payout_report(bot))
    asyncio.create_task(username_checker(bot))
    asyncio.create_task(cleanup_channel(bot))
    asyncio.create_task(auto_close_slots_2330(bot))
    asyncio.create_task(review_takes_cleanup())
    asyncio.create_task(subscription_cache_cleanup())

    _log_to_file("🚀 Начинаю polling...")

    try:
        await dp.start_polling(bot)
    except Exception as e:
        _log_to_file(f"❌ POLLING ERROR: {e}\n{traceback.format_exc()}")
        raise


if __name__ == "__main__":
    _log_to_file("🎬 __main__ запущен")
    threading.Thread(target=run_flask, daemon=True).start()

    try:
        asyncio.run(main())
    except Exception as e:
        _log_to_file(f"❌ FATAL: {e}\n{traceback.format_exc()}")
        raise
