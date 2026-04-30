from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, ReplyKeyboardRemove
from datetime import datetime

from bot.config import MANAGER_USERNAME
from bot.database import (
    add_user, get_user, get_user_by_username,
    is_registered, update_user_field
)
from bot.keyboards.reply import main_menu_keyboard

router = Router()

class RegForm(StatesGroup):
    name = State()
    tg_username = State()
    timezone = State()
    city = State()
    referrer = State()
    phone_card = State()
    bank = State()

@router.message(Command("start"))
async def cmd_start(message: Message):
    user_id = message.from_user.id
    add_user(user_id, message.from_user.username, message.from_user.full_name)
    await message.answer(
        "👋 Привет!\n\nЯ бот для работы со слотами.\nВыберите нужный раздел на клавиатуре:",
        reply_markup=main_menu_keyboard()
    )

@router.message(F.text == "📋 Профиль")
async def menu_profile(message: Message):
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
    if referrer == "0":
        ref_status = "нет"
    else:
        yandex = user.get("yandex_passed", 0) or 0
        google = user.get("google_passed", 0) or 0
        gis = user.get("gis_passed", 0) or 0
        ref_status = "выполнено" if (yandex >= 10 and (google + gis) >= 15) else "в процессе"

    text = (
        f"📋 Профиль\n\n"
        f"Имя: {user['name']}\n"
        f"Время от МСК: {user['timezone']}\n"
        f"Город: {user['city']}\n\n"
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
        f"ℹ️ Статистика обновляется ежедневно в 15:00 МСК.\n\n"
        f"👥 Рефералка: {referrer if referrer != '0' else 'нет'} ({ref_status})\n\n"
        f"💳 Реквизиты\n"
        f"Номер телефона/карты: {user['phone_card']}\n"
        f"Банк: {user['bank']}"
    )
    await message.answer(text)

@router.message(F.text == "❓ Помощь")
async def menu_help(message: Message):
    text = (
        "🆘 Доступные команды:\n"
        "/start – Главное меню\n"
        "/reg – Регистрация\n"
        "/profile – Ваш профиль\n"
        "/job – Активные слоты\n"
        "/help – Эта справка\n\n"
        f"По всем вопросам: @{MANAGER_USERNAME}"
    )
    await message.answer(text, reply_markup=main_menu_keyboard())

@router.message(Command("reg"))
@router.message(F.text == "📝 Регистрация")
async def start_registration(message: Message, state: FSMContext):
    user_id = message.from_user.id
    add_user(user_id, message.from_user.username, message.from_user.full_name)
    if is_registered(user_id):
        await message.answer("✅ Вы уже зарегистрированы! Используйте кнопку «📋 Профиль».")
        return
    await state.set_state(RegForm.name)
    await message.answer("Отлично, задам вам пару вопросов.\n1. Ваше имя?", reply_markup=ReplyKeyboardRemove())

@router.message(RegForm.name)
async def process_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await state.set_state(RegForm.tg_username)
    await message.answer("2. Ваш User в TG?\n(Напишите ваш username, например @durov)")

@router.message(RegForm.tg_username)
async def process_tg_username(message: Message, state: FSMContext):
    raw = message.text.strip()
# Убираем @ в начале и приводим к нижнему регистру
clean = raw.lstrip("@").lower()
await state.update_data(tg_username=clean)
    await state.set_state(RegForm.timezone)
    await message.answer("3. Ваше время от МСК +-?\n(Например: +4, -1, 0)")

@router.message(RegForm.timezone)
async def process_timezone(message: Message, state: FSMContext):
    await state.update_data(timezone=message.text.strip())
    await state.set_state(RegForm.city)
    await message.answer("4. В каком городе проживаете? (Для отправки ближайших отзывов)")

@router.message(RegForm.city)
async def process_city(message: Message, state: FSMContext):
    await state.update_data(city=message.text.strip())
    await state.set_state(RegForm.referrer)
    await message.answer(
        "5. Есть ли реферальное приглашение? Если да, напишите username человека, от которого вы пришли. "
        "Если нет, просто напишите 0.\n\n"
        "⚠️ Внимание: указание неверного username может привести к тому, что вы не получите реферальный бонус."
    )

@router.message(RegForm.referrer)
async def process_referrer(message: Message, state: FSMContext):
    referrer = message.text.strip()
    if referrer != "0":
        ref_user = get_user_by_username(referrer)
        if not ref_user:
            await message.answer("❌ Пользователь с таким username не найден. Проверьте правильность или напишите 0.")
            return
    await state.update_data(referrer=referrer)
    await state.set_state(RegForm.phone_card)
    await message.answer(
        "6. Номер телефона или карты? "
        "(Эти данные используются для автоматических выплат в день зарплаты. "
        "Если не хотите указывать сейчас, просто напишите 0)"
    )

@router.message(RegForm.phone_card)
async def process_phone_card(message: Message, state: FSMContext):
    await state.update_data(phone_card=message.text.strip())
    await state.set_state(RegForm.bank)
    await message.answer("7. Банк?")

@router.message(RegForm.bank)
async def process_bank(message: Message, state: FSMContext):
    data = await state.get_data()
    user_id = message.from_user.id
    update_user_field(user_id, "name", data["name"])
    update_user_field(user_id, "tg_username", data["tg_username"])
    update_user_field(user_id, "timezone", data["timezone"])
    update_user_field(user_id, "city", data["city"])
    update_user_field(user_id, "referrer", data["referrer"])
    update_user_field(user_id, "phone_card", data["phone_card"])
    update_user_field(user_id, "bank", message.text.strip())
    update_user_field(user_id, "registered_at", datetime.now())
    await state.clear()
    await message.answer(
        "✅ Отлично, регистрация успешно пройдена! Используйте кнопки ниже для навигации.\n"
        "Хорошей работы и больших заработков!",
        reply_markup=main_menu_keyboard()
    )
