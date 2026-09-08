# bot/handlers/admin_advanced.py
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from bot.database import get_user_by_username, get_user, update_user_field, get_admin_role, is_owner, is_ga, is_moderator
from bot.config import DB_PATH
import sqlite3
import logging

logger = logging.getLogger(__name__)
router = Router()

class EditUserStates(StatesGroup):
    menu = State()
    edit_name = State()
    edit_timezone = State()
    edit_city = State()
    edit_payout = State()
    edit_earned = State()
    edit_phone = State()
    edit_bank = State()

selected_user = {}

@router.message(Command("infoga"))
async def cmd_infoga(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if not is_moderator(user_id):
        await message.answer("⛔ У вас нет доступа.")
        return
    
    args = message.text.split()
    if len(args) < 2:
        await message.answer("❌ Использование: /infoga @username")
        return
    
    target = args[1].lstrip("@").lower()
    user = get_user_by_username(target)
    if not user:
        await message.answer(f"❌ Пользователь с username '{target}' не найден.")
        return
    
    selected_user[user_id] = user["user_id"]
    await state.set_state(EditUserStates.menu)
    await show_user_info(message, user)

async def show_user_info(message: Message, user: dict):
    from bot.database import get_active_warnings
    from datetime import datetime
    
    reg_time = datetime.fromisoformat(user["registered_at"]) if user.get("registered_at") else datetime.now()
    delta = datetime.now() - reg_time
    days, seconds = delta.days, delta.seconds
    hours, rem = divmod(seconds, 3600)
    minutes, _ = divmod(rem, 60)
    time_str = f"{days} дн. {hours} ч. {minutes} мин."
    
    active_warnings = get_active_warnings(user["user_id"])
    warn_text = "⚠️ Предупреждений нет."
    if active_warnings:
        warn_text = "⚠️ Предупреждения:\n"
        for i, w in enumerate(active_warnings, 1):
            created = datetime.fromisoformat(w['created_at']).strftime("%d.%m.%Y")
            expires = datetime.fromisoformat(w['expires_at']).strftime("%d.%m.%Y")
            warn_text += f"{i}/3 – {w['reason']}\n   Выдано: {created}, снимется: {expires}\n"
    
    text = (
        f"🕵️ <b>ПОЛНАЯ ИНФОРМАЦИЯ О ПОЛЬЗОВАТЕЛЕ</b>\n\n"
        f"👤 ID: {user['user_id']}\n"
        f"📛 Имя: {user['name']}\n"
        f"🆔 Username: @{user['tg_username']}\n"
        f"⏰ Время от МСК: {user['timezone']}\n"
        f"🏙️ Город: {user['city']}\n"
        f"📅 С нами: {time_str}\n"
        f"💰 К выплате чт: {user['payout']}₽\n"
        f"💵 Заработано ЗВВ: {user['total_earned']}₽\n\n"
        f"📊 Текущая статистика (passed):\n"
        f"  Яндекс: {user['yandex_passed']}, Google: {user['google_passed']}, 2ГИС: {user['gis_passed']}\n"
        f"  Авито: {user['avito_passed']}, ВК: {user['vk_passed']}, Отзовик: {user['otzovik_passed']}\n"
        f"  Doctoru: {user['doctoru_passed']}, ДокДок: {user['dokdok_passed']}\n"
        f"  Про Докторов: {user['prodoctors_passed']}, ДокТу: {user['doctu_passed']}\n"
        f"  32ТОП: {user['top32_passed']}, ZOON: {user.get('zoon_passed', 0)}\n\n"
        f"📊 Общая статистика (total):\n"
        f"  Яндекс: {user['yandex_total']}, Google: {user['google_total']}, 2ГИС: {user['gis_total']}\n"
        f"  Авито: {user['avito_total']}, ВК: {user['vk_total']}, Отзовик: {user['otzovik_total']}\n"
        f"  Doctoru: {user['doctoru_total']}, ДокДок: {user['dokdok_total']}\n"
        f"  Про Докторов: {user['prodoctors_total']}, ДокТу: {user['doctu_total']}\n"
        f"  32ТОП: {user['top32_total']}, ZOON: {user.get('zoon_total', 0)}\n\n"
        f"👥 Рефералка: {user['referrer'] if user['referrer'] != '0' else 'нет'}\n"
        f"💳 Телефон/карта: {user['phone_card']}\n"
        f"🏦 Банк: {user['bank']}\n"
        f"🔒 Статус: {'🔴 Заблокирован' if user['blocked'] else '🟢 Активен'}\n"
        f"{warn_text}"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Рефералы", callback_data="infoga:referrals"),
         InlineKeyboardButton(text="📊 Проход", callback_data="infoga:stats")],
        [InlineKeyboardButton(text="✏️ Изменить данные", callback_data="infoga:edit")],
        [InlineKeyboardButton(text="❌ Завершить просмотр", callback_data="infoga:exit")]
    ])
    
    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)

@router.callback_query(F.data == "infoga:referrals")
async def infoga_referrals(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in selected_user:
        await callback.answer("Ошибка", show_alert=True)
        return
    
    target_user_id = selected_user[user_id]
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        "SELECT name, tg_username, registered_at, yandex_total, google_total, gis_total "
        "FROM users WHERE LOWER(REPLACE(referrer, '@', '')) = ?",
        (get_user(target_user_id)['tg_username'].lower(),)
    )
    referrals = cur.fetchall()
    conn.close()
    
    if not referrals:
        await callback.message.answer("👥 У пользователя нет рефералов.")
        await callback.answer()
        return
    
    text = "👥 <b>Рефералы пользователя:</b>\n\n"
    for ref in referrals:
        name = ref["name"] or "Без имени"
        username = ref["tg_username"] or "unknown"
        yandex = ref["yandex_total"] or 0
        google = ref["google_total"] or 0
        gis = ref["gis_total"] or 0
        status = "✅" if yandex >= 10 and (google + gis) >= 15 else "🚀"
        text += f"{name} (@{username}) – {status}\n"
    
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "infoga:stats")
async def infoga_stats(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in selected_user:
        await callback.answer("Ошибка", show_alert=True)
        return
    
    target_user_id = selected_user[user_id]
    user = get_user(target_user_id)
    
    total = (user.get('yandex_total', 0) + user.get('google_total', 0) + user.get('gis_total', 0) +
             user.get('avito_total', 0) + user.get('vk_total', 0) + user.get('otzovik_total', 0) +
             user.get('doctoru_total', 0) + user.get('dokdok_total', 0) + user.get('prodoctors_total', 0) +
             user.get('doctu_total', 0) + user.get('top32_total', 0) + user.get('zoon_total', 0))
    
    await callback.message.answer(f"📊 <b>Общий проход пользователя:</b>\n\nВсего отзывов: {total}", parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "infoga:exit")
async def infoga_exit(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    if user_id in selected_user:
        del selected_user[user_id]
    await state.clear()
    await callback.message.answer("✅ Просмотр завершён.")
    await callback.answer()

@router.callback_query(F.data == "infoga:edit")
async def infoga_edit(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    if user_id not in selected_user:
        await callback.answer("Ошибка", show_alert=True)
        return
    
    await state.set_state(EditUserStates.edit_name)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Изменить имя", callback_data="edit:name"),
         InlineKeyboardButton(text="✏️ Изменить город", callback_data="edit:city")],
        [InlineKeyboardButton(text="✏️ Изменить время от МСК", callback_data="edit:timezone")],
        [InlineKeyboardButton(text="➡️ Далее", callback_data="edit:next")],
        [InlineKeyboardButton(text="❌ Выйти", callback_data="edit:exit")]
    ])
    await callback.message.answer("Выберите, что хотите изменить:", reply_markup=keyboard)
    await callback.answer()

@router.callback_query(F.data.startswith("edit:"))
async def edit_menu(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    action = callback.data.split(":")[1]
    
    if action == "exit":
        await state.clear()
        await callback.message.answer("✅ Редактирование завершено.")
        await callback.answer()
        return
    
    if action == "next":
        await state.set_state(EditUserStates.edit_payout)
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Изменить 'К выплате'", callback_data="edit:payout")],
            [InlineKeyboardButton(text="✏️ Изменить 'Заработано ЗВВ'", callback_data="edit:earned")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="edit:back")],
            [InlineKeyboardButton(text="👤 Вернуться к просмотру", callback_data="edit:view")]
        ])
        await callback.message.answer("Выберите финансовые данные для изменения:", reply_markup=keyboard)
        await callback.answer()
        return
    
    if action == "back":
        await state.set_state(EditUserStates.edit_name)
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Изменить имя", callback_data="edit:name"),
             InlineKeyboardButton(text="✏️ Изменить город", callback_data="edit:city")],
            [InlineKeyboardButton(text="✏️ Изменить время от МСК", callback_data="edit:timezone")],
            [InlineKeyboardButton(text="➡️ Далее", callback_data="edit:next")],
            [InlineKeyboardButton(text="❌ Выйти", callback_data="edit:exit")]
        ])
        await callback.message.answer("Выберите, что хотите изменить:", reply_markup=keyboard)
        await callback.answer()
        return
    
    if action == "view":
        user_id_owner = callback.from_user.id
        if user_id_owner not in selected_user:
            await callback.answer("Ошибка", show_alert=True)
            return
        target_user_id = selected_user[user_id_owner]
        user = get_user(target_user_id)
        await state.clear()
        await show_user_info(callback.message, user)
        await callback.answer()
        return
    
    if action == "name":
        await state.set_state(EditUserStates.edit_name)
        await callback.message.answer("Введите новое имя пользователя:")
        await callback.answer()
        return
    elif action == "city":
        await state.set_state(EditUserStates.edit_city)
        await callback.message.answer("Введите новый город:")
        await callback.answer()
        return
    elif action == "timezone":
        await state.set_state(EditUserStates.edit_timezone)
        await callback.message.answer("Введите новое время от МСК (например, +3, -1):")
        await callback.answer()
        return
    elif action == "payout":
        await state.set_state(EditUserStates.edit_payout)
        await callback.message.answer("Введите новую сумму 'К выплате':")
        await callback.answer()
        return
    elif action == "earned":
        await state.set_state(EditUserStates.edit_earned)
        await callback.message.answer("Введите новую сумму 'Заработано ЗВВ':")
        await callback.answer()
        return

@router.message(EditUserStates.edit_name)
async def edit_name(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id not in selected_user:
        await message.answer("❌ Ошибка сессии.")
        await state.clear()
        return
    target_user_id = selected_user[user_id]
    update_user_field(target_user_id, "name", message.text.strip())
    await message.answer(f"✅ Имя изменено на '{message.text.strip()}'")
    await state.set_state(EditUserStates.edit_name)
    user = get_user(target_user_id)
    await show_user_info(message, user)

@router.message(EditUserStates.edit_timezone)
async def edit_timezone(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id not in selected_user:
        await message.answer("❌ Ошибка сессии.")
        await state.clear()
        return
    target_user_id = selected_user[user_id]
    update_user_field(target_user_id, "timezone", message.text.strip())
    await message.answer(f"✅ Время от МСК изменено на '{message.text.strip()}'")
    await state.set_state(EditUserStates.edit_name)
    user = get_user(target_user_id)
    await show_user_info(message, user)

@router.message(EditUserStates.edit_city)
async def edit_city(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id not in selected_user:
        await message.answer("❌ Ошибка сессии.")
        await state.clear()
        return
    target_user_id = selected_user[user_id]
    update_user_field(target_user_id, "city", message.text.strip())
    await message.answer(f"✅ Город изменён на '{message.text.strip()}'")
    await state.set_state(EditUserStates.edit_name)
    user = get_user(target_user_id)
    await show_user_info(message, user)

@router.message(EditUserStates.edit_payout)
async def edit_payout(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id not in selected_user:
        await message.answer("❌ Ошибка сессии.")
        await state.clear()
        return
    try:
        value = int(message.text.strip())
        target_user_id = selected_user[user_id]
        update_user_field(target_user_id, "payout", value)
        await message.answer(f"✅ 'К выплате' изменено на {value}₽")
        await state.set_state(EditUserStates.edit_name)
        user = get_user(target_user_id)
        await show_user_info(message, user)
    except ValueError:
        await message.answer("❌ Введите число.")

@router.message(EditUserStates.edit_earned)
async def edit_earned(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id not in selected_user:
        await message.answer("❌ Ошибка сессии.")
        await state.clear()
        return
    try:
        value = int(message.text.strip())
        target_user_id = selected_user[user_id]
        update_user_field(target_user_id, "total_earned", value)
        await message.answer(f"✅ 'Заработано ЗВВ' изменено на {value}₽")
        await state.set_state(EditUserStates.edit_name)
        user = get_user(target_user_id)
        await show_user_info(message, user)
    except ValueError:
        await message.answer("❌ Введите число.")
