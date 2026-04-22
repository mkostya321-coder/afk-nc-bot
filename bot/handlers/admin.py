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
        "ℹ️ <b>Для пользователей:</b> /help"
    )
    await message.answer(text)

@router.message(Command("userblock"))
async def user_block(message: Message):
    if not is_admin(message.from_user.id):
        return
    try:
        _, user_id = message.text.split()
        user_id = int(user_id)
    except:
        await message.answer("Использование: /userblock <user_id>")
        return
    new_status = toggle_block(user_id)
    if new_status is None:
        await message.answer("❌ Пользователь не найден.")
    else:
        status_text = "заблокирован" if new_status else "разблокирован"
        await message.answer(f"✅ Пользователь {user_id} {status_text}.")

@router.message(Command("useredit"))
async def user_edit(message: Message):
    if not is_admin(message.from_user.id):
        return
    parts = message.text.split(maxsplit=3)
    if len(parts) < 4:
        await message.answer(
            "Использование: /useredit <user_id> <field> <value>\n"
            "Поля: payout, earned, phone, bank"
        )
        return
    try:
        user_id = int(parts[1])
    except:
        await message.answer("❌ Неверный user_id.")
        return
    field = parts[2].lower()
    value = parts[3]

    if field == "payout":
        update_user_field(user_id, "payout", int(value))
    elif field == "earned":
        update_user_field(user_id, "total_earned", int(value))
    elif field == "phone":
        update_user_field(user_id, "phone_card", value)
    elif field == "bank":
        update_user_field(user_id, "bank", value)
    else:
        await message.answer("Неизвестное поле. Допустимые: payout, earned, phone, bank")
        return
    await message.answer(f"✅ Данные пользователя {user_id} обновлены.")