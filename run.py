import asyncio
import logging
import os
import threading
from datetime import datetime, timedelta

from flask import Flask, Response
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
import pytz

from bot.config import BOT_TOKEN, CHANNEL_ID
from bot.database import init_db
from bot.google_sheets import update_stats_from_sheet
from bot.handlers import user, admin, slots, referral
from bot.middlewares import AutoMenuMiddleware

logging.basicConfig(level=logging.INFO)

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
        sleep_seconds = (next_time - now).total_seconds()
        await asyncio.sleep(sleep_seconds)

        now_after = datetime.now(moscow_tz)
        if now_after.hour == 8 and now_after.minute == 0:
            try:
                await bot.send_message(
                    CHANNEL_ID,
                    "☀️ Доброе утро, друзья!\n"
                    "Вот и ещё один прекрасный рабочий день. Скоро появятся новые слоты.\n"
                    "Всем хорошего дня! С уважением, команда New Chapter!"
                )
            except Exception as e:
                logging.error(f"Ошибка утреннего сообщения: {e}")
        elif now_after.hour == 22 and now_after.minute == 30:
            try:
                await bot.send_message(
                    CHANNEL_ID,
                    "🌙 Рабочий день подошёл к концу.\n"
                    "Т.к. работаем с 8 до 22 МСК, рабочий день вышел. Всем спасибо за выполненную работу!\n"
                    "У кого ещё есть задания — ожидаем скриншоты до 23:59 МСК.\n"
                    "Всем спокойной ночи! С уважением, команда New Chapter!"
                )
            except Exception as e:
                logging.error(f"Ошибка вечернего сообщения: {e}")

async def main():
    init_db()
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    # Закрываем сессию при остановке
    dp.shutdown.register(lambda: bot.session.close())

    dp.message.middleware(AutoMenuMiddleware())

    dp.include_router(user.router)
    dp.include_router(admin.router)
    dp.include_router(slots.router)
    dp.include_router(referral.router)

    asyncio.create_task(scheduler())
    asyncio.create_task(update_stats_from_sheet())

    await dp.start_polling(bot)

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    asyncio.run(main())
