# bot/handlers/admin_advanced.py
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from bot.database import (
    get_user_by_username, get_user, update_user_field, toggle_block,
    get_admin_role, is_owner, is_ga, is_moderator, get_active_warnings
)
from bot.config import DB_PATH
import sqlite3
import logging
from datetime import datetime

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


# ============ ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ============
async def delete_message_safe(message: Message):
    try:
        await message.delete()
    except Exception as e:
        logger.warning(f"Не удалось удалить сообщение: {e}")


# ============ ПОКАЗ ПРОФИЛЯ ============
async def show_user_info(message: Message, user: dict, is_new_message: bool = True):
    """
    is_new_message=True — отправляем новое сообщение
    is_new_message=False — редактируем существующее
    """
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

    ban_button = InlineKeyboardButton(
        text="🔓 UNBAN" if user['blocked'] else "🚫 BAN",
        callback_data="infoga:ban"
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Рефералы", callback_data="infoga:referrals"),
         InlineKeyboardButton(text="📊 Проход", callback_data="infoga:stats")],
        [InlineKeyboardButton(text="✏️ Изменить данные", callback_data="infoga:edit")],
        [ban_button],
        [InlineKeyboardButton(text="❌ Завершить просмотр", callback_data="infoga:exit")]
    ])

    if is_new_message:
        await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
    else:
        try:
            await message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
        except Exception as e:
            logger.warning(f"Не удалось отредактировать сообщение: {e}")
            await message.answer(text, parse_mode="HTML", reply_markup=keyboard)


# ============ КОМАНДА /infoga ============
@router.message(Command("infoga"))
async def cmd_infoga(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if not is_ga(user_id):
        await message.answer("⛔ У вас нет доступа. Команда доступна только GA и владельцу.")
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
    await show_user_info(message, user, is_new_message=True)


# ============ РЕФЕРАЛЫ ============
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


# ============ ПРОХОД (только те платформы, где > 0) ============
@router.callback_query(F.data == "infoga:stats")
async def infoga_stats(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in selected_user:
        await callback.answer("Ошибка", show_alert=True)
        return

    target_user_id = selected_user[user_id]
    user = get_user(target_user_id)

    platforms = [
        ("Яндекс", "yandex"),
        ("Google", "google"),
        ("2ГИС", "gis"),
        ("Авито", "avito"),
        ("ВК", "vk"),
        ("Отзовик", "otzovik"),
        ("Doctoru", "doctoru"),
        ("ДокДок", "dokdok"),
        ("Про Докторов", "prodoctors"),
        ("ДокТу", "doctu"),
        ("32ТОП", "top32"),
        ("ZOON", "zoon"),
    ]

    text = "📊 <b>Проход пользователя:</b>\n\n"
    total = 0
    has_any = False
    for name, field in platforms:
        count = user.get(f"{field}_total", 0) or 0
        if count > 0:
            text += f"• {name}: {count}\n"
            total += count
            has_any = True

    if not has_any:
        text += "Нет выполненных отзывов.\n"

    text += f"\n<b>Всего: {total}</b>"

    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()


# ============ BAN / UNBAN ============
@router.callback_query(F.data == "infoga:ban")
async def infoga_ban(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in selected_user:
        await callback.answer("Ошибка", show_alert=True)
        return

    target_user_id = selected_user[user_id]
    new_status = toggle_block(target_user_id)
    user = get_user(target_user_id)

    if new_status:
        await callback.answer("🚫 Пользователь заблокирован", show_alert=True)
    else:
        await callback.answer("🔓 Пользователь разблокирован", show_alert=True)

    # Обновляем профиль
    try:
        await show_user_info(callback.message, user, is_new_message=False)
    except Exception as e:
        logger.warning(f"Не удалось обновить профиль: {e}")


# ============ ЗАВЕРШИТЬ ПРОСМОТР ============
@router.callback_query(F.data == "infoga:exit")
async def infoga_exit(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    if user_id in selected_user:
        del selected_user[user_id]
    await state.clear()
    await delete_message_safe(callback.message)
    await callback.message.answer("✅ Просмотр завершён.")
    await callback.answer()


# ============ МЕНЮ РЕДАКТИРОВАНИЯ ============
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
    try:
        await callback.message.edit_text("Выберите, что хотите изменить:", reply_markup=keyboard)
    except Exception as e:
        logger.warning(f"edit_text не удался: {e}")
        await callback.message.answer("Выберите, что хотите изменить:", reply_markup=keyboard)
    await callback.answer()


# ============ ОБРАБОТКА КНОПОК edit:* ============
@router.callback_query(F.data.startswith("edit:"))
async def edit_menu(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    action = callback.data.split(":")[1]

    if action == "exit":
        await state.clear()
        await delete_message_safe(callback.message)
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
        try:
            await callback.message.edit_text("Выберите финансовые данные для изменения:", reply_markup=keyboard)
        except Exception as e:
            logger.warning(f"edit_text не удался: {e}")
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
        try:
            await callback.message.edit_text("Выберите, что хотите изменить:", reply_markup=keyboard)
        except Exception as e:
            logger.warning(f"edit_text не удался: {e}")
            await callback.message.answer("Выберите, что хотите изменить:", reply_markup=keyboard)
        await callback.answer()
        return

    if action == "view":
        if user_id not in selected_user:
            await callback.answer("Ошибка", show_alert=True)
            return
        target_user_id = selected_user[user_id]
        user = get_user(target_user_id)
        await state.clear()
        try:
            await show_user_info(callback.message, user, is_new_message=False)
        except Exception:
            await show_user_info(callback.message, user, is_new_message=True)
        await callback.answer()
        return

    if action == "name":
        await state.set_state(EditUserStates.edit_name)
        try:
            await callback.message.edit_text("Введите новое имя пользователя:", reply_markup=None)
        except Exception:
            await callback.message.answer("Введите новое имя пользователя:")
        await callback.answer()
        return

    if action == "city":
        await state.set_state(EditUserStates.edit_city)
        try:
            await callback.message.edit_text("Введите новый город:", reply_markup=None)
        except Exception:
            await callback.message.answer("Введите новый город:")
        await callback.answer()
        return

    if action == "timezone":
        await state.set_state(EditUserStates.edit_timezone)
        try:
            await callback.message.edit_text("Введите новое время от МСК (например, +3, -1):", reply_markup=None)
        except Exception:
            await callback.message.answer("Введите новое время от МСК (например, +3, -1):")
        await callback.answer()
        return

    if action == "payout":
        await state.set_state(EditUserStates.edit_payout)
        try:
            await callback.message.edit_text("Введите новую сумму 'К выплате':", reply_markup=None)
        except Exception:
            await callback.message.answer("Введите новую сумму 'К выплате':")
        await callback.answer()
        return

    if action == "earned":
        await state.set_state(EditUserStates.edit_earned)
        try:
            await callback.message.edit_text("Введите новую сумму 'Заработано ЗВВ':", reply_markup=None)
        except Exception:
            await callback.message.answer("Введите новую сумму 'Заработано ЗВВ':")
        await callback.answer()
        return


# ============ ОБРАБОТЧИКИ ВВОДА ============
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
    await show_user_info(message, user, is_new_message=True)


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
    await show_user_info(message, user, is_new_message=True)


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
    await show_user_info(message, user, is_new_message=True)


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
        await show_user_info(message, user, is_new_message=True)
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
        await show_user_info(message, user, is_new_message=True)
    except ValueError:
        await message.answer("❌ Введите число.")
