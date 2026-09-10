import asyncio, logging, os, threading
from datetime import datetime, timedelta
from flask import Flask, Response
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
import pytz
from bot.config import BOT_TOKEN, CHANNEL_ID, REPORT_CHAT_ID, REPORT_THREAD_ID, DB_PATH
from bot.database import init_db, get_all_users_with_payout, save_channel_message
from bot.google_sheets import (
    monitor_schedule, update_stats_from_sheet,
    mark_as_paid_in_table, cleanup_channel
)
from bot.handlers import user, admin, slots, referral
from bot.handlers.admin_advanced import router as admin_advanced_router
from bot.middlewares import AutoMenuMiddleware
from bot.username_checker import username_checker
import sqlite3

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
            msg = await bot.send_message(CHANNEL_ID, "☀️ Доброе утро! Вот и ещё один прекрасный рабочий день. Всем хорошего дня! Ожидайте сегодняшние слоты. С уважением, команда NC 🤝")
            save_channel_message(msg.message_id, CHANNEL_ID)
        elif now_after.hour == 22 and now_after.minute == 30:
            msg = await bot.send_message(CHANNEL_ID, "🌙 Сегодняшний рабочий день подошёл к концу. Всем спасибо за работу! Кто ещё не отправил скриншоты — успевайте до 23:59 МСК. Всем доброй ночи! С уважением, команда NC 😴🌟")
            save_channel_message(msg.message_id, CHANNEL_ID)


async def weekly_payout_report(bot):
    moscow_tz = pytz.timezone("Europe/Moscow")
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
                text_lines = ["<b>📋 Список на выплату (четверг)</b>\n"]
                user_ids = []
                for u in users:
                    username = u.get('tg_username') or u.get('username') or str(u['user_id'])
                    phone = u.get('phone_card') or '—'
                    bank = u.get('bank') or '—'
                    line = f"👤 @{username} (ID: {u['user_id']})\n💰 Сумма: {u['payout']}₽\n📞 {phone}\n🏦 {bank}\n──────────────"
                    text_lines.append(line)
                    user_ids.append(u['user_id'])
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
                if user_ids:
                    try:
                        await mark_as_paid_in_table(user_ids)
                    except Exception as e:
                        logging.error(f"Ошибка обновления статуса в таблице: {e}")

                    with sqlite3.connect(DB_PATH) as conn:
                        cur = conn.cursor()
                        placeholders = ','.join(['?'] * len(user_ids))
                        cur.execute(f"""
                            UPDATE users SET 
                                payout = 0,
                                yandex_passed = 0,
                                google_passed = 0,
                                gis_passed = 0,
                                avito_passed = 0,
                                vk_passed = 0,
                                otzovik_passed = 0,
                                doctoru_passed = 0,
                                dokdok_passed = 0,
                                prodoctors_passed = 0,
                                doctu_passed = 0,
                                top32_passed = 0,
                                zoon_passed = 0
                            WHERE user_id IN ({placeholders})
                        """, user_ids)
                        conn.commit()
                    logging.info(f"✅ Обнулены балансы и passed-поля у {len(user_ids)} пользователей")
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

    # === ПОРЯДОК ВАЖЕН! admin_advanced ДО slots ===
    dp.include_router(user.router)
    dp.include_router(admin.router)
    dp.include_router(admin_advanced_router)
    dp.include_router(slots.router)

    asyncio.create_task(scheduler(bot))
    asyncio.create_task(monitor_schedule(bot))
    asyncio.create_task(update_stats_from_sheet())
    asyncio.create_task(weekly_payout_report(bot))
    asyncio.create_task(username_checker(bot))
    asyncio.create_task(cleanup_channel(bot))  # <-- Автоочистка в 4:30 МСК

    await dp.start_polling(bot)


if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    asyncio.run(main())
