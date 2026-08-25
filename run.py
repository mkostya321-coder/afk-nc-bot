import asyncio, logging, os, threading
from flask import Flask, Response
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from bot.config import BOT_TOKEN
from bot.database import init_db
from bot.handlers import user, admin, slots, referral
from bot.middlewares import AutoMenuMiddleware
from bot.google_sheets import monitor_schedule, update_stats_from_sheet
from bot.run_scheduler import scheduler, weekly_payout_report  # если вынесли

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)
@app.route('/')
def home(): return "Bot is running!"
@app.route('/health')
def health(): return Response(status=200)

def run_flask():
    port = int(os.environ.get("PORT", 80))
    app.run(host='0.0.0.0', port=port)

async def main():
    init_db()
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    dp.message.middleware(AutoMenuMiddleware())
    dp.include_router(user.router)
    dp.include_router(admin.router)
    dp.include_router(slots.router)
    # dp.include_router(referral.router)  # закомментирован

    asyncio.create_task(scheduler(bot))
    asyncio.create_task(monitor_schedule(bot, slots.active_slots))
    asyncio.create_task(update_stats_from_sheet())
    asyncio.create_task(weekly_payout_report(bot))

    await dp.start_polling(bot)

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    asyncio.run(main())
