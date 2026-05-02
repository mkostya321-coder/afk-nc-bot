from datetime import datetime   # ← обязательный импорт
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from bot.config import ADMIN_IDS, CHANNEL_ID, MANAGER_USERNAME, OTHER_JOBS_CHANNEL, DB_PATH
from bot.database import toggle_block, update_user_field, get_user, get_user_by_username
from bot.keyboards.reply import main_menu_keyboard
import sqlite3

router = Router()

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

@router.message(Command("helpadm"))
async def cmd_helpadm(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ У вас нет доступа к этой команде.")
        return
    text = (
        "🛠 Команды администратора:\n\n"
        "📢 Публикация слотов:\n"
        "/yandex — Яндекс карты (150₽)\n"
        "/google — GOOGLE (50₽)\n"
        "/gis — 2ГИС (50₽)\n"
        "/avito — Авито (700₽)\n"
        "/vk — ВК (50₽)\n"
        "/otzovik — Отзовик (100₽)\n"
        "/doctoru — Doctoru (100₽)\n\n"
        "📋 Управление слотами:\n"
        "/slots — Показать активные слоты (с ID)\n"
        "/close <ID> — Закрыть слот\n"
        "/closeall — Закрыть все слоты\n\n"
        "👤 Управление пользователями:\n"
        "/userblock <user_id> — Заблокировать/разблокировать\n"
        "/useredit <user_id> <поле> <значение>\n"
        "Поля: payout, earned, phone, bank\n"
        "/info <username> — Показать профиль пользователя\n\n"
        "⚠️ Осторожно! Сброс баланса:\n"
        "/resetbalance — Обнулить выплаты и счётчики у ВСЕХ пользователей\n\n"
        "ℹ️ Для пользователей: /help"
    )
    await message.answer(text)

# ---------- /info <username> ----------
@router.message(Command("info"))
async def cmd_info(message: Message):
    if not is_admin(message.from_user.id):
        return

    args = message.text.split()
    if len(args) < 2:
        await message.answer("❌ Использование: /info <username>")
        return

    username = args[1]
    user = get_user_by_username(username)
    if not user:
        await message.answer(f"❌ Пользователь с username '{username}' не найден.")
        return

    reg_time = datetime.fromisoformat(user["registered_at"]) if user.get("registered_at") else datetime.now()
    delta = datetime.now() - reg_time
    days, seconds = delta.days, delta.seconds
    hours, rem = divmod(seconds, 3600)
    minutes, _ = divmod(rem, 60)
    time_str = f"{days} дн. {hours} ч. {minutes} мин."

    ref = user.get("referrer", "0")
    ref_status = "нет"
    if ref != "0":
        y = user.get("yandex_passed", 0) or 0
        g = user.get("google_passed", 0) or 0
        gi = user.get("gis_passed", 0) or 0
        if y >= 10 and (g + gi) >= 15:
            ref_status = "выполнено"
        else:
            ref_status = "в процессе"

    text = (
        f"🕵️ Профиль пользователя @{user.get('tg_username', username)}:\n\n"
        f"Имя: {user['name']}\n"
        f"Время от МСК: {user['timezone']}\n"
        f"Город: {user['city']}\n"
        f"С нами уже: {time_str}\n"
        f"К выплате ср/чт: {user['payout']}₽\n"
        f"Заработано за всё время: {user['total_earned']}₽\n\n"
        f"📊 Статистика по слотам:\n"
        f"Яндекс: {user['yandex_passed']}\n"
        f"Google: {user['google_passed']}\n"
        f"2ГИС: {user['gis_passed']}\n"
        f"Авито: {user['avito_passed']}\n"
        f"ВК: {user['vk_passed']}\n"
        f"Отзовик: {user['otzovik_passed']}\n"
        f"Doctoru: {user['doctoru_passed']}\n\n"
        f"Рефералка: {ref if ref != '0' else 'нет'} ({ref_status})\n"
        f"Реквизиты: {user['phone_card']} / {user['bank']}"
    )
    await message.answer(text)

# ---------- Остальные админские команды ----------
# Здесь должны быть /userblock, /useredit, /slots, /close, /closeall, /resetbalance
# Если их нет в вашем admin.py, скопируйте их из предыдущих версий.
