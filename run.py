import asyncio, logging, os, threading
from datetime import datetime, timedelta
from flask import Flask, Response
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
import pytz
from bot.config import BOT_TOKEN, CHANNEL_ID, REPORT_CHAT_ID, REPORT_THREAD_ID
from bot.database import init_db, get_all_users_with_payout
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

async def scheduler(bot):
    moscow_tz = pytz.timezone("Europe/Moscow")
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
            await bot.send_message(CHANNEL_ID, "☀️ Доброе утро! Вот и ещё один прекрасный рабочий день. Всем хорошего дня! Ожидайте сегодняшние слоты. С уважением, команда NC 🤝")
        elif now_after.hour == 22 and now_after.minute == 30:
            await bot.send_message(CHANNEL_ID, "🌙 Сегодняшний рабочий день подошёл к концу. Всем спасибо за работу! Кто ещё не отправил скриншоты — успевайте до 23:59 МСК. Всем доброй ночи! С уважением, команда NC 😴🌟")

async def weekly_payout_report(bot):
    moscow_tz = pytz.timezone("Europe/Moscow")
    while True:
        now = datetime.now(moscow_tz)
        days_ahead = (3 - now.weekday() + 7) % 7
        if days_ahead == 0 and now.hour >= 10 and now.minute >= 30:
            days_ahead = 7
        next_thursday = now.replace(hour=10, minute=30, second=0, microsecond=0) + timedelta(days=days_ahead)
        await asyncio.sleep((next_thursday - now).total_seconds())

        try:
            users = get_all_users_with_payout()
            if users:
                text_lines = ["<b>📋 Список на выплату (четверг)</b>\n"]
                for u in users:
                    username = u.get('tg_username') or u.get('username') or str(u['user_id'])
                    phone = u.get('phone_card') or '—'
                    bank = u.get('bank') or '—'
                    line = f"👤 @{username} (ID: {u['user_id']})\n💰 Сумма: {u['payout']}₽\n📞 {phone}\n🏦 {bank}\n──────────────"
                    text_lines.append(line)
                full_text = "\n".join(text_lines)
                max_len = 4000
                for i in range(0, len(full_text), max_len):
                    chunk = full_text[i:i+max_len]
                    await bot.send_message(
                        chat_id=REPORT_CHAT_ID,
                        text=chunk,
                        message_thread_id=REPORT_THREAD_ID or None,
                        parse_mode="HTML"
                    )
            else:
                await bot.send_message(
                    chat_id=REPORT_CHAT_ID,
                    text="Сегодня нет пользователей, которым нужно выплатить вознаграждение.",
                    message_thread_id=REPORT_THREAD_ID or None
                )
        except Exception as e:
            logging.error(f"Ошибка еженедельного отчета: {e}")

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
    # dp.include_router(referral.router)   # закомментирован

    asyncio.create_task(scheduler(bot))
    asyncio.create_task(monitor_schedule(bot, slots.active_slots))
    asyncio.create_task(update_stats_from_sheet())
    asyncio.create_task(weekly_payout_report(bot))

    await dp.start_polling(bot)

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    asyncio.run(main())
