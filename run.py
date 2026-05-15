import asyncio, logging, os, threading
from datetime import datetime, timedelta
from flask import Flask, Response
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
import pytz
from bot.config import BOT_TOKEN, CHANNEL_ID
from bot.database import init_db
from bot.google_sheets import monitor_schedule, update_stats_from_sheet
from bot.handlers import user, admin, slots, referral
from bot.middlewares import AutoMenuMiddleware

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)
@app.route('/')
def home(): return "Bot is running!"
@app.route('/health')
def health(): return Response(status=200)

def run_flask():
    port = int(os.environ.get("PORT", 80))
    app.run(host='0.0.0.0', port=port)

async def scheduler():
    moscow_tz = pytz.timezone("Europe/Moscow")
    bot = Bot(token=BOT_TOKEN)
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
        if now_after.hour == 8:
            await bot.send_message(CHANNEL_ID, "☀️ Доброе утро, друзья! ...")
        elif now_after.hour == 22 and now_after.minute == 30:
            await bot.send_message(CHANNEL_ID, "🌙 Рабочий день подошёл к концу...")

async def main():
    init_db()
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    async def close_session():
        await bot.session.close()
    dp.shutdown.register(close_session)

    dp.message.middleware(AutoMenuMiddleware())

    dp.include_router(user.router)
    dp.include_router(admin.router)
    dp.include_router(slots.router)
    dp.include_router(referral.router)

    asyncio.create_task(scheduler())
    asyncio.create_task(monitor_schedule(bot, slots.active_slots))
    asyncio.create_task(update_stats_from_sheet())

    await dp.start_polling(bot)

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    asyncio.run(main())
