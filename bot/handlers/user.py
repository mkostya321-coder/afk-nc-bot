import sqlite3, asyncio
from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from bot.config import MANAGER_USERNAME, DB_PATH
from bot.database import (
    add_user, get_user, get_user_by_username,
    is_registered, update_user_field, is_blocked
)
from bot.keyboards.reply import main_menu_keyboard
from bot.handlers.slots import active_slots

router = Router()

REFERRAL_DEADLINE_DAYS = 28

class RegForm(StatesGroup):
    name = State()
    timezone = State()
    city = State()
    referrer = State()
    phone_card = State()
    bank = State()

class IntroState(StatesGroup):
    first = State()
    second = State()

RULES_1 = ( ... )  # тексты правил как раньше
RULES_2 = ( ... )

async def show_intro(message, state): ...
@router.callback_query(F.data == "intro_next") ...

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    add_user(user_id, message.from_user.username, message.from_user.full_name)
    if is_registered(user_id):
        await message.answer("👋 Привет!\n\nЯ бот для работы со слотами.\nВыберите нужный раздел на клавиатуре:", reply_markup=main_menu_keyboard())
    else:
        await show_intro(message, state)

@router.message(F.text == "📋 Профиль")
async def menu_profile(message: Message):
    if is_blocked(message.from_user.id):
        await message.answer("⛔ Вы заблокированы.")
        return
    user = get_user(message.from_user.id)
    if not user or not user.get("name"):
        await message.answer("❌ Вы ещё не зарегистрированы. Используйте кнопку «📝 Регистрация».")
        return

    reg_time = datetime.fromisoformat(user["registered_at"]) if user["registered_at"] else datetime.now()
    delta = datetime.now() - reg_time
    days = delta.days
    hours, rem = divmod(delta.seconds, 3600)
    minutes, _ = divmod(rem, 60)
    time_str = f"{days} дн. {hours} ч. {minutes} мин."

    referrer = user.get("referrer", "0")
    ref_status = "нет"
    if referrer != "0":
        yandex = user.get("yandex_total", 0) or 0
        google = user.get("google_total", 0) or 0
        gis = user.get("gis_total", 0) or 0
        if yandex >= 10 and (google + gis) >= 15:
            ref_status = "✅ выполнено"
        else:
            if user.get("registered_at"):
                try:
                    deadline = datetime.fromisoformat(user["registered_at"]) + timedelta(days=REFERRAL_DEADLINE_DAYS)
                    if datetime.now() > deadline:
                        ref_status = "❌ Не выполнен"
                    else:
                        ref_status = "🚀 в процессе"
                except:
                    ref_status = "🚀 в процессе"
            else:
                ref_status = "🚀 в процессе"

    text = (
        f"📋 Профиль\n\n"
        f"Имя: {user['name']}\n"
        f"Время от МСК: {user['timezone']}\n"
        f"Город: {user['city']}\n\n"
        f"С нами уже: {time_str}\n"
        f"К выплате ср/чт: {user['payout']}₽\n"
        f"Заработано за всё время: {user['total_earned']}₽\n\n"
        f"📊 Статистика (текущий период):\n"
        f"Яндекс: {user['yandex_passed']}\n"
        f"Google: {user['google_passed']}\n"
        f"2ГИС: {user['gis_passed']}\n"
        f"Авито: {user['avito_passed']}\n"
        f"ВК: {user['vk_passed']}\n"
        f"Отзовик: {user['otzovik_passed']}\n"
        f"Doctoru: {user['doctoru_passed']}\n"
        f"ДокДок: {user['dokdok_passed']}\n"
        f"Про Докторов: {user['prodoctors_passed']}\n"
        f"ДокТу: {user['doctu_passed']}\n"
        f"32ТОП: {user['top32_passed']}\n\n"
        f"ℹ️ Статистика обновляется каждый день в 10:00 и 20:00 МСК.\n\n"
        f"👥 Рефералка: {referrer if referrer != '0' else 'нет'} ({ref_status})\n\n"
        f"💳 Реквизиты\n"
        f"Номер телефона/карты: {user['phone_card']}\n"
        f"Банк: {user['bank']}\n\n"
        f"Чтобы посмотреть общие отзывы за всё время, используйте /myotz"
    )
    await message.answer(text)

@router.message(Command("myotz"))
async def cmd_myotz(message: Message):
    if is_blocked(message.from_user.id):
        await message.answer("⛔ Вы заблокированы.")
        return
    user = get_user(message.from_user.id)
    if not user or not user.get("name"):
        await message.answer("❌ Вы не зарегистрированы.")
        return

    text = (
        f"📊 Ваши пройденные отзывы за всё время:\n\n"
        f"Яндекс: {user.get('yandex_total', 0)}\n"
        f"Google: {user.get('google_total', 0)}\n"
        f"2ГИС: {user.get('gis_total', 0)}\n"
        f"Авито: {user.get('avito_total', 0)}\n"
        f"ВК: {user.get('vk_total', 0)}\n"
        f"Отзовик: {user.get('otzovik_total', 0)}\n"
        f"Doctoru: {user.get('doctoru_total', 0)}\n"
        f"ДокДок: {user.get('dokdok_total', 0)}\n"
        f"Про Докторов: {user.get('prodoctors_total', 0)}\n"
        f"ДокТу: {user.get('doctu_total', 0)}\n"
        f"32ТОП: {user.get('top32_total', 0)}"
    )
    await message.answer(text)

# Остальные функции (регистрация, /job, рефералы) остаются без изменений
# ... (весь прежний код, который был в user.py)
