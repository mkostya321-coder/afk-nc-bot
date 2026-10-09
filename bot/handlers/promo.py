# bot/handlers/promo.py
import json
import logging
from datetime import datetime
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from bot.database import (
    get_user, get_user_by_username,
    is_ga, is_owner, is_admin_nc, is_stpromonc,
    get_admin_role,
    get_post, set_post, has_post, remove_post, list_posts,
    set_promo_table_link, get_promo_table_link,
    set_promo_schedule, get_promo_schedule,
)
from bot.config import (
    MANAGER_USERNAME,
    PROMO_REPORT_CHAT_ID, PROMO_REPORT_THREAD_ID,
    SUPPORT_CHAT_ID, SUPPORT_THREAD_ID,
)

logger = logging.getLogger(__name__)
router = Router()

# ============ ДОЛЖНОСТИ ============
POSTS = {
    "promonc": "Промоутер NC",
}


def post_display(code: str) -> str:
    return POSTS.get(code, code)


# ============ FSM ============
class PromoAdminEdit(StatesGroup):
    waiting_link = State()
    schedule_monday = State()
    schedule_tuesday = State()
    schedule_wednesday = State()
    schedule_thursday = State()
    schedule_friday = State()
    schedule_saturday = State()
    schedule_sunday = State()


class PromoReportForm(StatesGroup):
    waiting_photo_with_text = State()


DAY_FLOW = [
    ("schedule_monday",    "Понедельник", "schedule_tuesday"),
    ("schedule_tuesday",   "Вторник",     "schedule_wednesday"),
    ("schedule_wednesday", "Среда",       "schedule_thursday"),
    ("schedule_thursday",  "Четверг",     "schedule_friday"),
    ("schedule_friday",    "Пятница",     "schedule_saturday"),
    ("schedule_saturday",  "Суббота",     "schedule_sunday"),
    ("schedule_sunday",    "Воскресенье", None),
]
DAY_KEY_MAP = {
    "schedule_monday": "monday",
    "schedule_tuesday": "tuesday",
    "schedule_wednesday": "wednesday",
    "schedule_thursday": "thursday",
    "schedule_friday": "friday",
    "schedule_saturday": "saturday",
    "schedule_sunday": "sunday",
}
DAY_NAME_MAP = {
    "schedule_monday": "Понедельник",
    "schedule_tuesday": "Вторник",
    "schedule_wednesday": "Среда",
    "schedule_thursday": "Четверг",
    "schedule_friday": "Пятница",
    "schedule_saturday": "Суббота",
    "schedule_sunday": "Воскресенье",
}
SCHEDULE_DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
SCHEDULE_NAMES = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]


# ============ /set_post ============
@router.message(Command("set_post"))
async def cmd_set_post(message: Message):
    user_id = message.from_user.id
    if not (is_owner(user_id) or is_ga(user_id)):
        await message.answer("⛔ Команда доступна только владельцу и ГА.")
        return

    parts = message.text.split()
    if len(parts) < 3:
        await message.answer(
            "❌ Использование: /set_post <должность> <username>\n"
            f"Доступные должности: {', '.join(POSTS.keys())}\n"
            "Пример: /set_post promonc newchapter"
        )
        return

    post_code = parts[1].lower().strip()
    target = parts[2].lstrip("@").strip()

    if post_code not in POSTS:
        await message.answer(
            f"❌ Должность '{post_code}' не найдена.\n"
            f"Доступные: {', '.join(POSTS.keys())}"
        )
        return

    user = get_user_by_username(target)
    if not user:
        await message.answer(f"❌ Пользователь @{target} не найден.")
        return

    set_post(user["user_id"], post_code)
    await message.answer(
        f"✅ Пользователь @{user.get('tg_username') or user['user_id']} "
        f"назначен на должность «{post_display(post_code)}»."
    )
    logger.info(f"📌 {message.from_user.id} назначил @{target} должность {post_code}")


# ============ /remove_post ============
@router.message(Command("remove_post"))
async def cmd_remove_post(message: Message):
    user_id = message.from_user.id
    if not (is_owner(user_id) or is_ga(user_id)):
        await message.answer("⛔ Команда доступна только владельцу и ГА.")
        return

    parts = message.text.split()
    if len(parts) < 2:
        await message.answer(
            "❌ Использование: /remove_post <username или user_id>\n"
            "Снимает должность с пользователя."
        )
        return

    target = parts[1]
    if target.isdigit():
        user = get_user(int(target))
    else:
        user = get_user_by_username(target.lstrip("@"))

    if not user:
        await message.answer(f"❌ Пользователь '{target}' не найден.")
        return

    post_code = get_post(user["user_id"])
    if not post_code:
        await message.answer(f"❌ У @{user.get('tg_username') or user['user_id']} нет должности.")
        return

    ok = remove_post(user["user_id"])
    if ok:
        await message.answer(
            f"✅ С @{user.get('tg_username') or user['user_id']} снята должность «{post_display(post_code)}»."
        )
        logger.info(f"📌 {message.from_user.id} снял должность {post_code} с {user['user_id']}")
    else:
        await message.answer("❌ Не удалось снять должность.")


# ============ /list_posts ============
@router.message(Command("list_posts"))
async def cmd_list_posts(message: Message):
    user_id = message.from_user.id
    admin_role = get_admin_role(user_id)

    if not (is_owner(user_id) or is_ga(user_id) or is_admin_nc(user_id) or is_stpromonc(user_id)):
        await message.answer("⛔ Команда доступна только владельцу, ГА, Админу и Старшему Промоутеру.")
        return

    parts = message.text.split()
    post_filter = parts[1].lower() if len(parts) > 1 else None

    # stpromonc видит только promonc
    if admin_role == "stpromonc":
        post_filter = "promonc"

    if post_filter and post_filter not in POSTS:
        await message.answer(
            f"❌ Должность '{post_filter}' не найдена.\n"
            f"Доступные: {', '.join(POSTS.keys())}"
        )
        return

    rows = list_posts(post_filter)
    if not rows:
        await message.answer("📭 Список пуст.")
        return

    lines = [f"📋 <b>Сотрудники с должностями</b>\n"]
    by_post = {}
    for r in rows:
        by_post.setdefault(r["post"], []).append(r["user_id"])

    for post_code, uids in by_post.items():
        lines.append(f"\n<b>{post_display(post_code)}</b> ({len(uids)}):")
        for uid in uids:
            u = get_user(uid)
            if not u:
                continue
            uname = u.get("tg_username") or "—"
            name = u.get("name") or "—"
            lines.append(f"• {name} (@{uname}, ID: {uid})")

    text = "\n".join(lines)
    if len(text) <= 4000:
        await message.answer(text, parse_mode="HTML")
    else:
        for i in range(0, len(text), 4000):
            await message.answer(text[i:i+4000], parse_mode="HTML")


# ============ /infopromo ============
@router.message(Command("infopromo"))
async def cmd_infopromo(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if not (is_owner(user_id) or is_ga(user_id) or is_stpromonc(user_id)):
        await message.answer("⛔ Команда доступна только владельцу, ГА и Старшему Промоутеру.")
        return

    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("❌ Использование: /infopromo <username или user_id>")
        return

    target = parts[1]
    if target.isdigit():
        user = get_user(int(target))
    else:
        user = get_user_by_username(target.lstrip("@"))

    if not user:
        await message.answer(f"❌ Пользователь '{target}' не найден.")
        return

    await state.update_data(promo_target=user["user_id"])
    await show_infopromo(message, user, is_new=True)


async def show_infopromo(target_message, user, is_new=True):
    try:
        reg_time = datetime.fromisoformat(user["registered_at"]) if user.get("registered_at") else datetime.now()
        delta = datetime.now() - reg_time
        time_str = f"{delta.days} дн."
    except Exception:
        time_str = "—"

    link = get_promo_table_link(user["user_id"])
    link_display = link if link else "ссылка еще не привязана"

    post_code = get_post(user["user_id"])
    post_str = post_display(post_code) if post_code else "—"

    text = (
        f"🏆 <b>Промоутер NC — инфо</b>\n\n"
        f"👤 Имя: {user.get('name') or '—'}\n"
        f"🎖 Должность: {post_str}\n"
        f"💰 К выплате: {user.get('payout') or 0}₽\n"
        f"📊 Пополнения адм: {user.get('admin_topup') or 0}₽\n"
        f"🏙 Город: {user.get('city') or '—'}\n"
        f"⏳ С нами: {time_str}\n"
        f"🕒 Время от МСК: {user.get('timezone') or '—'}\n"
        f"📛 Username: @{user.get('tg_username') or '—'}\n\n"
        f"🔗 Ссылка на таблицу: {link_display}"
    )

    kb = InlineKeyboardBuilder()
    kb.button(text="✏️ Изменить ссылку таблицы", callback_data="promo:edit_link")
    kb.button(text="📅 График", callback_data="promo:schedule")
    kb.adjust(1)

    if is_new:
        await target_message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())
    else:
        try:
            await target_message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
        except Exception:
            await target_message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())


@router.callback_query(F.data == "promo:edit_link")
async def promo_edit_link(callback: CallbackQuery, state: FSMContext):
    if not (is_owner(callback.from_user.id) or is_ga(callback.from_user.id)):
        await callback.answer("⛔", show_alert=True)
        return
    data = await state.get_data()
    if not data.get("promo_target"):
        await callback.answer("Сначала откройте /infopromo <username>", show_alert=True)
        return
    await state.set_state(PromoAdminEdit.waiting_link)
    await callback.message.answer("🔗 Отправьте новую ссылку на таблицу:")
    await callback.answer()


@router.message(PromoAdminEdit.waiting_link, F.text)
async def promo_save_link(message: Message, state: FSMContext):
    if not (is_owner(message.from_user.id) or is_ga(message.from_user.id)):
        await state.clear()
        return
    data = await state.get_data()
    target_uid = data.get("promo_target")
    if not target_uid:
        await state.clear()
        return
    link = message.text.strip()
    set_promo_table_link(target_uid, link)
    user = get_user(target_uid)
    await message.answer("✅ Ссылка привязана.")
    await state.set_state(None)
    await show_infopromo(message, user, is_new=True)


@router.callback_query(F.data == "promo:schedule")
async def promo_view_schedule(callback: CallbackQuery, state: FSMContext):
    if not (is_owner(callback.from_user.id) or is_ga(callback.from_user.id)):
        await callback.answer("⛔", show_alert=True)
        return
    data = await state.get_data()
    target_uid = data.get("promo_target")
    if not target_uid:
        await callback.answer("Откройте /infopromo", show_alert=True)
        return
    sched = get_promo_schedule(target_uid) or {}
    lines = ["📅 <b>График работы</b>\n"]
    for d, n in zip(SCHEDULE_DAYS, SCHEDULE_NAMES):
        v = sched.get(d) or "не задано"
        lines.append(f"• {n}: {v}")
    kb = InlineKeyboardBuilder()
    kb.button(text="✏️ Изменить", callback_data="promo:schedule_edit")
    kb.button(text="⬅️ Назад", callback_data="promo:back")
    kb.adjust(1)
    try:
        await callback.message.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=kb.as_markup())
    except Exception:
        await callback.message.answer("\n".join(lines), parse_mode="HTML", reply_markup=kb.as_markup())
    await callback.answer()


@router.callback_query(F.data == "promo:back")
async def promo_back(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    target_uid = data.get("promo_target")
    if not target_uid:
        await callback.answer()
        return
    user = get_user(target_uid)
    await show_infopromo(callback.message, user, is_new=False)
    await callback.answer()


@router.callback_query(F.data == "promo:schedule_edit")
async def promo_schedule_edit(callback: CallbackQuery, state: FSMContext):
    if not (is_owner(callback.from_user.id) or is_ga(callback.from_user.id)):
        await callback.answer("⛔", show_alert=True)
        return
    await state.update_data(promo_schedule_draft={})
    await state.set_state(PromoAdminEdit.schedule_monday)
    await callback.message.answer(
        "📅 Введите график на <b>Понедельник</b>:\n"
        "(например: с 16:00-20:00+ или выходной)",
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(PromoAdminEdit.schedule_monday)
@router.message(PromoAdminEdit.schedule_tuesday)
@router.message(PromoAdminEdit.schedule_wednesday)
@router.message(PromoAdminEdit.schedule_thursday)
@router.message(PromoAdminEdit.schedule_friday)
@router.message(PromoAdminEdit.schedule_saturday)
@router.message(PromoAdminEdit.schedule_sunday)
async def promo_schedule_input(message: Message, state: FSMContext):
    if not (is_owner(message.from_user.id) or is_ga(message.from_user.id)):
        await state.clear()
        return
    if not message.text:
        return

    current = await state.get_state()
    current_key = current.split(":")[-1] if current else None
    if not current_key or current_key not in DAY_KEY_MAP:
        await state.clear()
        return

    value = message.text.strip()
    data = await state.get_data()
    sched = data.get("promo_schedule_draft") or {}
    sched[DAY_KEY_MAP[current_key]] = value
    await state.update_data(promo_schedule_draft=sched)

    next_state = None
    for key, name, nxt in DAY_FLOW:
        if key == current_key:
            next_state = nxt
            break

    if next_state:
        next_name = DAY_NAME_MAP[next_state]
        await state.set_state(getattr(PromoAdminEdit, next_state))
        await message.answer(f"📅 Введите график на <b>{next_name}</b>:", parse_mode="HTML")
    else:
        target_uid = data.get("promo_target")
        if target_uid:
            set_promo_schedule(target_uid, sched)
        await state.update_data(promo_schedule_draft=None)
        await state.set_state(None)
        user = get_user(target_uid) if target_uid else None
        await message.answer("✅ График сохранён.")
        if user:
            await show_infopromo(message, user, is_new=True)


# ============ МЕНЮ ПРОМОУТЕРА (для юзера) ============
@router.callback_query(F.data == "promo_menu")
async def promo_menu_cb(callback: CallbackQuery):
    user_id = callback.from_user.id
    if not has_post(user_id, "promonc"):
        await callback.answer("⛔ У вас нет доступа.", show_alert=True)
        return
    kb = InlineKeyboardBuilder()
    kb.button(text="📊 Моя таблица", callback_data="promo_user:table")
    kb.button(text="📅 График работы", callback_data="promo_user:schedule")
    kb.button(text="📤 Отправить отчёт", callback_data="promo_user:report")
    kb.button(text="❓ Справка по таблице", callback_data="promo_user:help")
    kb.adjust(1)
    try:
        await callback.message.edit_text(
            "🏆 <b>Промоутер NC</b>\n\nВыберите раздел:",
            reply_markup=kb.as_markup(),
            parse_mode="HTML"
        )
    except Exception:
        await callback.message.answer(
            "🏆 <b>Промоутер NC</b>\n\nВыберите раздел:",
            reply_markup=kb.as_markup(),
            parse_mode="HTML"
        )
    await callback.answer()


@router.callback_query(F.data == "promo_user:table")
async def promo_user_table(callback: CallbackQuery):
    user_id = callback.from_user.id
    if not has_post(user_id, "promonc"):
        await callback.answer("⛔", show_alert=True)
        return
    user = get_user(user_id)
    link = get_promo_table_link(user_id)
    name = (user.get("name") if user else None) or "друг"
    if link:
        text = (
            f"Рады вас снова приветствовать, <b>{name}</b>!\n"
            f"Ваша таблица ниже, хорошей работы. С уважением, команда NC.\n\n"
            f"{link}"
        )
    else:
        text = (
            f"Рады вас снова приветствовать, <b>{name}</b>!\n"
            f"Ваша таблица ещё не привязана. Обратитесь к администрации.\n\n"
            f"С уважением, команда NC."
        )
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "promo_user:schedule")
async def promo_user_schedule(callback: CallbackQuery):
    user_id = callback.from_user.id
    if not has_post(user_id, "promonc"):
        await callback.answer("⛔", show_alert=True)
        return
    sched = get_promo_schedule(user_id) or {}
    lines = ["📅 <b>Ваш график работы</b>\n"]
    for d, n in zip(SCHEDULE_DAYS, SCHEDULE_NAMES):
        v = sched.get(d) or "не задано"
        lines.append(f"• {n}: {v}")
    await callback.message.answer("\n".join(lines), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "promo_user:report")
async def promo_user_report(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    if not has_post(user_id, "promonc"):
        await callback.answer("⛔", show_alert=True)
        return
    await state.set_state(PromoReportForm.waiting_photo_with_text)
    await callback.message.answer(
        "📤 <b>Отправка отчёта</b>\n\n"
        "Пришлите <b>фото</b> с <b>подписью</b> (не отдельным сообщением!).\n\n"
        "В подписи укажите:\n"
        "1. На каком месте по горизонтали находится отзыв в таблице?\n"
        "   <i>(слева в таблице номера строк, пример: 67)</i>\n"
        "2. Какие-то уточнения? <i>(другой текст или изменения — не обязательно)</i>\n\n"
        "<b>Пример подписи:</b>\n"
        "<code>67 — текст изменён на новый, фото обновлено</code>\n"
        "или просто:\n"
        "<code>67</code>\n\n"
        "⚠️ <b>Фото без подписи не принимается!</b>",
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(PromoReportForm.waiting_photo_with_text, F.photo)
async def promo_report_photo(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if not has_post(user_id, "promonc"):
        await state.clear()
        return

    caption = (message.caption or "").strip()
    if not caption:
        await message.answer(
            "⚠️ <b>Фото без подписи не принимается!</b>\n\n"
            "Пришлите фото ещё раз, указав в подписи номер строки (например, <code>67</code>).",
            parse_mode="HTML"
        )
        return

    user = get_user(user_id)
    username = (user.get("tg_username") if user else None) or message.from_user.username or "unknown"
    name = (user.get("name") if user else None) or "—"

    report_chat = PROMO_REPORT_CHAT_ID or SUPPORT_CHAT_ID
    report_thread = PROMO_REPORT_THREAD_ID or SUPPORT_THREAD_ID or None

    header = (
        f"🏆 <b>Отчёт Промоутера NC</b>\n"
        f"👤 {name} (@{username}, ID: {user_id})\n"
        f"📝 Подпись:\n{caption}"
    )

    if not report_chat:
        logger.warning("⚠️ PROMO_REPORT_CHAT_ID/SUPPORT_CHAT_ID не заданы — отчёт не отправлен.")
        await message.answer("⚠️ Техническая ошибка: чат для отчётов не настроен. Обратитесь к администрации.")
        return

    try:
        await message.bot.send_photo(
            chat_id=report_chat,
            photo=message.photo[-1].file_id,
            caption=header,
            message_thread_id=report_thread,
            parse_mode="HTML"
        )
        logger.info(f"✅ Промо-отчёт от {user_id} (@{username}) отправлен")
    except Exception as e:
        logger.error(f"❌ Не удалось отправить промо-отчёт: {e}")
        await message.answer("❌ Ошибка отправки. Попробуйте позже.")
        return

    await message.answer(
        "✅ <b>Отчёт принят!</b>\n\n"
        "Можете отправить следующий отчёт или выйти в меню через /start.",
        parse_mode="HTML"
    )


@router.message(PromoReportForm.waiting_photo_with_text, F.text)
async def promo_report_wrong_format(message: Message, state: FSMContext):
    await message.answer(
        "⚠️ Отправьте именно <b>фото</b> с подписью. Текстом отчёт не принимается.",
        parse_mode="HTML"
    )


@router.callback_query(F.data == "promo_user:help")
async def promo_user_help(callback: CallbackQuery):
    user_id = callback.from_user.id
    if not has_post(user_id, "promonc"):
        await callback.answer("⛔", show_alert=True)
        return
    text = (
        "❓ <b>Справка по таблице Промоутера</b>\n\n"
        "В вашей таблице отображается:\n"
        "• Ссылки на объекты для продвижения\n"
        "• Тексты для публикации\n"
        "• Статус выполнения заданий\n"
        "• Начисления за проделанную работу\n\n"
        "📤 <b>Как отправлять отчёты:</b>\n"
        "Нажмите «Отправить отчёт» и пришлите фото с подписью, где указан номер строки из таблицы.\n\n"
        f"По всем вопросам: @{MANAGER_USERNAME}"
    )
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()
