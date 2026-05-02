from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from bot.config import ADMIN_IDS, CHANNEL_ID, MANAGER_USERNAME, OTHER_JOBS_CHANNEL
from bot.database import toggle_block, update_user_field, get_user
from bot.keyboards.reply import main_menu_keyboard

router = Router()

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

@router.message(Command("helpadm"))
async def cmd_helpadm(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ У вас нет доступа к этой команде.")
        return
    text = (
        "🛠 <b>Команды администратора:</b>\n\n"
        "📢 <b>Публикация слотов:</b>\n"
        "/yandex — Яндекс карты (150₽)\n"
        "/google — GOOGLE (50₽)\n"
        "/gis — 2ГИС (50₽)\n"
        "/avito — Авито (700₽)\n"
        "/vk — ВК (50₽)\n"
        "/otzovik — Отзовик (100₽)\n"
        "/doctoru — Doctoru (100₽)\n\n"
        "📋 <b>Управление слотами:</b>\n"
        "/slots — Показать активные слоты (с ID)\n"
        "/close <ID> — Закрыть слот\n"
        "/closeall — Закрыть все слоты\n\n"
        "👤 <b>Управление пользователями:</b>\n"
        "/userblock <user_id> — Заблокировать/разблокировать\n"
        "/useredit <user_id> <поле> <значение>\n"
        "Поля: payout, earned, phone, bank\n\n"
        "⚠️ <b>Осторожно! Сброс баланса:</b>\n"
        "/resetbalance — Обнулить выплаты и счётчики у ВСЕХ пользователей\n\n"
        "ℹ️ <b>Для пользователей:</b> /help"
    )
    await message.answer(text)

@router.message(Command("resetbalance"))
async def reset_balance(message: Message):
    if not is_admin(message.from_user.id):
        return
    import sqlite3
    from bot.config import DB_PATH
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE users SET
                    payout = 0,
                    yandex_passed = 0,
                    google_passed = 0,
                    gis_passed = 0,
                    avito_passed = 0,
                    vk_passed = 0,
                    otzovik_passed = 0,
                    doctoru_passed = 0
            """)
            conn.commit()
        await message.answer("✅ Баланс и счётчики всех пользователей сброшены.")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

# Остальные админские команды (/userblock, /useredit, /slots, /close, /closeall) оставьте без изменений (они уже были в вашем admin.py)
