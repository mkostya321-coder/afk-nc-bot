from datetime import datetime
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from bot.config import (
    OWNER_ID, LOG_CHANNEL_ID, DB_PATH, SHEET_ID,
    LOG_USERS_CHAT_ID, LOG_USERS_THREAD_ID,
)
from bot.database import (
    get_user, get_user_by_username, toggle_block, update_user_field,
    get_admin_role, set_admin_role, remove_admin_role,
    is_owner, is_ga, is_admin_nc, is_stmoderator, is_moderator, is_comoderator, is_stpromonc,
    add_warning, get_warning_count, get_active_warnings, get_setting, set_setting,
    get_limit, set_limit, get_all_registered_users, get_all_users_with_payout,
    get_user_limit, set_user_limit, reset_user_limit, get_effective_limit,
    remove_last_warning, remove_all_warnings, get_all_users_with_active_warnings,
)
from bot.helpers import match_platform, PRICES, platform_from_sheet_name
from bot.logging_helpers import log_user_event
import sqlite3
import asyncio
import logging

logger = logging.getLogger(__name__)
router = Router()


HIDDEN_USERNAMES = {
    "new_chapterr24",
    "new_chapterr97",
    "molostovk",
}


def _norm(value) -> str:
    if value is None:
        return ""
    return str(value).strip().lower().replace("\xa0", " ").replace("\u200b", "")


def find_user_by_target(target: str):
    if not target:
        return None
    t = target.strip()
    if t.isdigit():
        return get_user(int(t))
    return get_user_by_username(t.lstrip("@"))


def find_user_extended(target: str):
    if not target:
        return None
    t = target.strip()
    if t.isdigit():
        return get_user(int(t))

    clean = t.lstrip("@").strip().lower()
    if not clean:
        return None

    user = get_user_by_username(clean)
    if user:
        return user

    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("SELECT * FROM users WHERE LOWER(name) = ? LIMIT 1", (clean,))
            row = cur.fetchone()
            if row:
                return dict(row)
            cur.execute("SELECT * FROM users WHERE LOWER(name) LIKE ? LIMIT 1", (f"%{clean}%",))
            row = cur.fetchone()
            if row:
                return dict(row)
    except Exception as e:
        logger.warning(f"⚠️ find_user_extended: {e}")

    return None


def log_action(message: Message, action: str):
    if not LOG_CHANNEL_ID:
        return
    try:
        text = f"👤 @{message.from_user.username or message.from_user.id} ({message.from_user.id})\n" \
               f"🕒 {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n" \
               f"⚙️ {action}"
        asyncio.create_task(message.bot.send_message(LOG_CHANNEL_ID, text))
    except Exception as e:
        logger.warning(f"Не удалось отправить лог в LOG_CHANNEL_ID: {e}")


def calculate_tiktok_payout(views: int) -> int:
    if views <= 0:
        return 0
    if views <= 1_000_000:
        return (views // 1000) * 10
    elif views <= 1_500_000:
        first_part = 1_000_000
        second_part = views - first_part
        return (first_part // 1000) * 10 + (second_part // 1000) * 5
    else:
        first_part = 1_000_000
        second_part = 500_000
        third_part = views - first_part - second_part
        return (first_part // 1000) * 10 + (second_part // 1000) * 5 + (third_part // 1000) * 2


@router.message(Command("helpadm"))
async def cmd_helpadm(message: Message):
    user_id = message.from_user.id
    role = get_admin_role(user_id)
    if not role:
        await message.answer("⛔ У вас нет доступа.")
        return

    text = "🛠 Команды администратора:\n\n"

    if is_owner(user_id):
        text += (
            "👑 /setrole <user> <role>\n"
            "   доступно: ga, admin, stmoderator, moderator, comoderator, stpromonc, none\n"
            "📊 /payout_report — отчёт по выплатам (≥150₽) + обнуление\n"
            "🔍 /infoga <@username или user_id> — полная информация + редактирование\n"
            "📋 /admlist — список всех ролей (без owner)\n"
            "👤 /userblock <user> — блок/разблок\n"
            "ℹ️ /info <user> — профиль\n"
            "⚠️ /warn <user> <7-30 дней> <причина> — предупреждение на N дней\n"
            "✅ /unwarn <user> — снять 1 предупреждение\n"
            "🧹 /clearwarns <user> — снять ВСЕ предупреждения\n"
            "📋 /warnlist — список юзеров с активными W\n"
            "📨 /smsuser <user> <текст> — сообщение\n"
            "🎯 /unslot <user> — снять активный слот\n"
            "🧹 /cleanflags — сбросить неправильные флаги I\n"
            "🔧 /resetflags <платформа> — сбросить Q/P/O/I/S у висящих строк\n"
            "📢 /smsall <текст> — рассылка всем зарегистрированным\n"
            "👥 /users — список всех зарегистрированных\n"
        )

    if is_ga(user_id):
        text += (
            "👑 /setrole <user> <role>\n"
            "   доступно: admin, stmoderator, moderator, comoderator, stpromonc, none\n"
            "📋 /admlist — список всех ролей (без owner)\n"
            "👤 /userblock <user> — блок/разблок\n"
            "💰 /useredit <user> <поле> <знач> — правка данных\n"
            "💸 /pay <user> <сумма> — пополнить баланс\n"
            "➖ /subtract platform <user> <платформа> <N> [ШТ] [...] — списать N отзывов\n"
            "➖ /subtract many <user> <сумма> — списать N рублей\n"
            "ℹ️ /info <user> — профиль\n"
            "⚠️ /warn <user> <7-30 дней> <причина> — предупреждение\n"
            "✅ /unwarn <user> — снять 1 предупреждение\n"
            "🧹 /clearwarns <user> — снять ВСЕ предупреждения\n"
            "📋 /warnlist — список юзеров с W\n"
            "📨 /smsuser <user> <текст> — сообщение юзеру\n"
            "🔄 /update_stats — обновить статистику\n"
            "⚠️ /resetbalance — сбросить балансы ≥150₽\n"
            "🎬 /tiktok_pay <user> <просмотры> — начислить за TikTok\n"
            "⛔ /stop_tiktok — закрыть TikTok\n"
            "▶️ /start_tiktok — возобновить TikTok\n"
            "📊 /set_limit <platform> <N> — общий лимит\n"
            "👤 /user_limit <user> <platform> <N|reset> — персональный лимит\n"
            "🎖 /set_post <post> <user> — выдать должность\n"
            "🚫 /remove_post <user> — снять должность\n"
            "📋 /list_posts [post] — список сотрудников\n"
            "🏆 /infopromo <user> — карточка промоутера\n"
            "🎯 /unslot <user> — снять активный слот\n"
            "🧹 /cleanflags — сбросить неправильные флаги I\n"
            "🔧 /resetflags <платформа> — сбросить Q/P/O/I/S у висящих строк\n"
            "📢 /smsall <текст> — рассылка всем зарегистрированным\n"
            "👥 /users — список всех зарегистрированных\n"
        )

    if is_admin_nc(user_id) and not is_ga(user_id):
        text += (
            "👤 /userblock <user> — блок/разблок\n"
            "ℹ️ /info <user> — профиль\n"
            "⚠️ /warn <user> <7-30 дней> <причина> — предупреждение\n"
            "✅ /unwarn <user> — снять 1 предупреждение\n"
            "📋 /warnlist — список юзеров с W\n"
            "📨 /smsuser <user> <текст> — сообщение\n"
            "💰 /useredit <user> <поле> <знач> — правка данных\n"
            "💸 /pay <user> <сумма> — пополнить баланс\n"
            "➖ /subtract platform <user> <платформа> <N> [ШТ] [...] — списать\n"
            "➖ /subtract many <user> <сумма> — списать рублей\n"
            "🔄 /update_stats — обновить статистику\n"
            "📊 /set_limit <platform> <N> — общий лимит\n"
            "👤 /user_limit <user> <platform> <N|reset> — персональный лимит\n"
            "📋 /list_posts [post] — список сотрудников\n"
            "🎯 /unslot <user> — снять активный слот\n"
            "🧹 /cleanflags — сбросить неправильные флаги I\n"
            "🔧 /resetflags <платформа> — сбросить Q/P/O/I/S у висящих строк\n"
        )

    if is_stmoderator(user_id) and not is_admin_nc(user_id):
        text += (
            "👤 /userblock <user> — блок/разблок\n"
            "ℹ️ /info <user> — профиль\n"
            "⚠️ /warn <user> <7-30 дней> <причина> — предупреждение\n"
            "✅ /unwarn <user> — снять 1 предупреждение\n"
            "📋 /warnlist — список юзеров с W\n"
            "📨 /smsuser <user> <текст> — сообщение\n"
        )

    if is_moderator(user_id) and not is_stmoderator(user_id):
        text += (
            "👤 /userblock <user> — блок/разблок\n"
            "ℹ️ /info <user> — профиль\n"
            "⚠️ /warn <user> <7-30 дней> <причина> — предупреждение\n"
            "✅ /unwarn <user> — снять 1 предупреждение\n"
            "📋 /warnlist — список юзеров с W\n"
            "📨 /smsuser <user> <текст> — сообщение\n"
        )

    if is_comoderator(user_id) and not is_moderator(user_id):
        text += (
            "ℹ️ /info <user> — профиль\n"
            "⚠️ /warn <user> <7-30 дней> <причина> — предупреждение\n"
            "📋 /warnlist — список юзеров с W\n"
            "📨 /smsuser <user> <текст> — сообщение\n"
        )

    if is_stpromonc(user_id) and not is_comoderator(user_id) and not is_admin_nc(user_id):
        text += (
            "📋 /list_posts [promonc] — список промоутеров\n"
            "🏆 /infopromo <user> — карточка промоутера\n"
        )

    text += "\nПо всем вопросам: /support"
    await message.answer(text)
    log_action(message, "Просмотр списка админ-команд")


@router.message(Command("setrole"))
async def set_role(message: Message):
    caller_id = message.from_user.id
    if not (is_owner(caller_id) or is_ga(caller_id)):
        return

    try:
        parts = message.text.split()
        if len(parts) < 3:
            await message.answer(
                "❌ Использование: /setrole <user_id или username> <role>\n"
                "Доступные роли: ga, admin, stmoderator, moderator, comoderator, stpromonc, none"
            )
            return

        target = parts[1]
        role = parts[2].lower()

        if is_owner(caller_id):
            allowed = {'ga', 'admin', 'stmoderator', 'moderator', 'comoderator', 'stpromonc', 'none'}
        elif is_ga(caller_id):
            allowed = {'admin', 'stmoderator', 'moderator', 'comoderator', 'stpromonc', 'none'}
        else:
            allowed = set()

        if role not in allowed:
            await message.answer(
                f"❌ Неверная роль. Вам доступно: {', '.join(sorted(allowed))}\n"
                f"<i>Роль owner назначается только через БД.</i>",
                parse_mode="HTML"
            )
            return

        user = find_user_by_target(target)
        if not user:
            await message.answer(f"❌ Пользователь '{target}' не найден.")
            return

        target_current_role = get_admin_role(user["user_id"])
        if target_current_role == "owner":
            await message.answer("❌ Нельзя изменить роль владельца.")
            return

        if role == "none":
            remove_admin_role(user["user_id"])
            await message.answer(f"✅ С пользователя {user['user_id']} снята роль.")
            log_action(message, f"Снята роль с {user['user_id']}")
            return

        set_admin_role(user["user_id"], role)
        await message.answer(f"✅ Роль «{role}» назначена пользователю {user['user_id']}")
        log_action(message, f"Назначена роль {role} пользователю {user['user_id']}")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


# ============ /warn — предупреждение на N дней (7..30) ============
@router.message(Command("warn"))
async def warn_user(message: Message):
    caller_id = message.from_user.id
    if not is_comoderator(caller_id):
        return

    parts = message.text.split(maxsplit=3)
    if len(parts) < 4:
        await message.answer(
            "❌ <b>Использование:</b>\n"
            "<code>/warn &lt;username или user_id&gt; &lt;дни 7-30&gt; &lt;причина&gt;</code>\n\n"
            "<b>Примеры:</b>\n"
            "<code>/warn @ivan 9 спам в чате</code>\n"
            "<code>/warn 8635115842 14 не доделывает слоты</code>",
            parse_mode="HTML"
        )
        return

    target_raw = parts[1].strip()
    days_raw = parts[2].strip()
    reason = parts[3].strip()

    try:
        days = int(days_raw)
    except ValueError:
        await message.answer("❌ Количество дней должно быть числом от 7 до 30.")
        return

    if days < 7 or days > 30:
        await message.answer("❌ Количество дней должно быть от <b>7 до 30</b>.", parse_mode="HTML")
        return

    logger.info(f"⚠️ /warn: caller={caller_id}, target='{target_raw}', days={days}, reason='{reason}'")

    user = find_user_extended(target_raw)

    if not user:
        hint = ""
        try:
            with sqlite3.connect(DB_PATH) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                clean = target_raw.lstrip("@").strip().lower()
                cur.execute(
                    "SELECT user_id, tg_username, name FROM users "
                    "WHERE LOWER(tg_username) LIKE ? OR LOWER(username) LIKE ? OR LOWER(name) LIKE ? "
                    "LIMIT 5",
                    (f"%{clean}%", f"%{clean}%", f"%{clean}%")
                )
                similar = cur.fetchall()
                if similar:
                    lines = ["\n\n💡 <b>Похожие пользователи в БД:</b>"]
                    for s in similar:
                        lines.append(f"• {s['name'] or '—'} (@{s['tg_username'] or '—'}, ID: {s['user_id']})")
                    hint = "\n".join(lines)
        except Exception:
            pass

        await message.answer(
            f"❌ Пользователь <code>{target_raw}</code> не найден в БД.{hint}\n\n"
            f"<i>Подсказка: проверьте @username точно как в профиле юзера.</i>",
            parse_mode="HTML"
        )
        return

    user_id = user["user_id"]
    logger.info(f"⚠️ /warn: user найден → id={user_id}")

    try:
        add_warning(user_id, reason, caller_id, days=days)
        active_warnings = get_active_warnings(user_id)
        warn_count = len(active_warnings)

        if warn_count >= 3:
            toggle_block(user_id)
            await message.answer(
                f"✅ Пользователь @{user.get('tg_username') or user_id} "
                f"получил <b>третье предупреждение</b> и заблокирован.\n"
                f"📅 Варн выдан на {days} дней.",
                parse_mode="HTML"
            )
            try:
                await message.bot.send_message(
                    user_id,
                    f"⛔ Вы получили третье предупреждение и заблокированы.\n"
                    f"Причина: {reason}\n"
                    f"Срок: {days} дней\n"
                    f"Обратитесь в /support."
                )
            except Exception as e:
                logger.warning(f"⚠️ /warn: уведомление: {e}")
        else:
            last_warn = active_warnings[-1]
            expires_str = datetime.fromisoformat(last_warn['expires_at']).strftime("%d.%m.%Y")
            await message.answer(
                f"✅ Предупреждение <b>{warn_count}/3</b> выдано "
                f"@{user.get('tg_username') or user_id}.\n"
                f"📅 Срок: <b>{days} дней</b> (снимется {expires_str})",
                parse_mode="HTML"
            )
            try:
                await message.bot.send_message(
                    user_id,
                    f"⚠️ Предупреждение ({warn_count}/3): {reason}\n"
                    f"Срок: {days} дней\n"
                    f"Будет снято: {expires_str}"
                )
            except Exception as e:
                logger.warning(f"⚠️ /warn: уведомление: {e}")

        log_action(message, f"Выдано W {warn_count}/3 на {days}дн. пользователю {user_id} ({reason})")
    except Exception as e:
        logger.error(f"❌ /warn: {e}", exc_info=True)
        await message.answer(f"❌ Ошибка: {e}")


# ============ /unwarn — снять 1 предупреждение ============
@router.message(Command("unwarn"))
async def cmd_unwarn(message: Message):
    caller_id = message.from_user.id
    if not is_moderator(caller_id):
        return

    parts = message.text.split()
    if len(parts) < 2:
        await message.answer(
            "❌ <b>Использование:</b>\n"
            "<code>/unwarn &lt;@username или user_id&gt;</code>",
            parse_mode="HTML"
        )
        return

    target = parts[1]
    user = find_user_extended(target)
    if not user:
        await message.answer(f"❌ Пользователь '{target}' не найден.")
        return

    uid = user["user_id"]
    uname = user.get("tg_username") or uid

    active = get_active_warnings(uid)
    if not active:
        await message.answer(f"❌ У @{uname} нет активных предупреждений.")
        return

    ok = remove_last_warning(uid)
    if not ok:
        await message.answer("❌ Не удалось снять предупреждение.")
        return

    try:
        await message.bot.send_message(uid, "✅ С вас снято одно предупреждение администрацией проекта.")
    except Exception:
        pass

    remaining = len(get_active_warnings(uid))
    await message.answer(
        f"✅ <b>Снято 1 предупреждение</b>\n\n"
        f"👤 @{uname} (ID: {uid})\n"
        f"📊 Осталось активных: <b>{remaining}/3</b>",
        parse_mode="HTML"
    )
    log_action(message, f"/unwarn: снято 1 W с {uid} (@{uname}), осталось {remaining}")


# ============ /clearwarns — снять ВСЕ предупреждения ============
@router.message(Command("clearwarns"))
async def cmd_clearwarns(message: Message):
    caller_id = message.from_user.id
    if not (is_owner(caller_id) or is_ga(caller_id)):
        await message.answer("⛔ Доступно только владельцу и ГА.")
        return

    parts = message.text.split()
    if len(parts) < 2:
        await message.answer(
            "❌ <b>Использование:</b>\n"
            "<code>/clearwarns &lt;@username или user_id&gt;</code>",
            parse_mode="HTML"
        )
        return

    target = parts[1]
    user = find_user_extended(target)
    if not user:
        await message.answer(f"❌ Пользователь '{target}' не найден.")
        return

    uid = user["user_id"]
    uname = user.get("tg_username") or uid

    removed = remove_all_warnings(uid)
    if removed == 0:
        await message.answer(f"❌ У @{uname} нет активных предупреждений.")
        return

    try:
        await message.bot.send_message(
            uid,
            f"✅ С вас сняты все предупреждения администрацией проекта.\nСнято: {removed}."
        )
    except Exception:
        pass

    await message.answer(
        f"✅ <b>Снято предупреждений: {removed}</b>\n\n"
        f"👤 @{uname} (ID: {uid})",
        parse_mode="HTML"
    )
    log_action(message, f"/clearwarns: снято {removed} W с {uid} (@{uname})")


# ============ /warnlist — список юзеров с активными W ============
@router.message(Command("warnlist"))
async def cmd_warnlist(message: Message):
    if not is_comoderator(message.from_user.id):
        return

    data = get_all_users_with_active_warnings()
    if not data:
        await message.answer("📭 Активных предупреждений ни у кого нет.")
        return

    total_warns = sum(len(u["warnings"]) for u in data)
    lines = [
        f"⚠️ <b>Активные предупреждения</b>",
        f"<i>Юзеров: {len(data)} · Всего варнов: {total_warns}</i>\n",
    ]

    for u in data:
        uname = u["tg_username"]
        name = u["name"]
        cnt = len(u["warnings"])
        lines.append(f"\n<b>{name}</b> (@{uname}, ID: {u['user_id']}) — <b>{cnt}/3</b>")
        for i, w in enumerate(u["warnings"], 1):
            try:
                created = datetime.fromisoformat(w["created_at"]).strftime("%d.%m.%Y")
            except Exception:
                created = "—"
            try:
                expires = datetime.fromisoformat(w["expires_at"]).strftime("%d.%m.%Y")
            except Exception:
                expires = "—"
            lines.append(f"  {i}. {w['reason']}")
            lines.append(f"     📅 Выдан: {created} → снимется: {expires}")

    text = "\n".join(lines)
    max_len = 4000

    if len(text) <= max_len:
        await message.answer(text, parse_mode="HTML")
    else:
        total_parts = (len(text) + max_len - 1) // max_len
        for i in range(0, len(text), max_len):
            part_num = i // max_len + 1
            chunk = text[i:i+max_len]
            if part_num > 1:
                chunk = f"<i>(часть {part_num}/{total_parts})</i>\n\n" + chunk
            await message.answer(chunk, parse_mode="HTML")

    log_action(message, f"/warnlist: показано {len(data)} юзеров")


@router.message(Command("smsuser"))
async def sms_user(message: Message):
    if not is_comoderator(message.from_user.id):
        return
    try:
        parts = message.text.split(maxsplit=2)
        if len(parts) < 3:
            await message.answer("Использование: /smsuser <username или user_id> <текст>")
            return
        target = parts[1]
        text = parts[2]
        user = find_user_extended(target)
        if not user:
            await message.answer("❌ Пользователь не найден.")
            return
        try:
            await message.bot.send_message(
                user["user_id"],
                f"📩 Сообщение от Администрации проекта:\n\n{text}"
            )
            await message.answer("✅ Сообщение отправлено.")
            log_action(message, f"SMS пользователю {user['user_id']}: {text}")
        except Exception as e:
            await message.answer(f"❌ Не удалось отправить: {e}")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


@router.message(Command("userblock"))
async def user_block(message: Message):
    if not is_moderator(message.from_user.id):
        return
    try:
        parts = message.text.split()
        if len(parts) < 2:
            await message.answer("Использование: /userblock <user_id или username>")
            return
        target = parts[1]
        user = find_user_extended(target)
        if not user:
            await message.answer("❌ Пользователь не найден.")
            return
        new_status = toggle_block(user["user_id"])
        if new_status is None:
            await message.answer("❌ Пользователь не найден.")
        else:
            status_text = "заблокирован" if new_status else "разблокирован"
            await message.answer(f"✅ Пользователь {user['user_id']} {status_text}.")
            log_action(message, f"Пользователь {user['user_id']} {status_text}")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


@router.message(Command("info"))
async def cmd_info(message: Message):
    if not is_comoderator(message.from_user.id):
        return
    args = message.text.split()
    if len(args) < 2:
        await message.answer("❌ Использование: /info <username или user_id>")
        return
    user = find_user_extended(args[1])
    if not user:
        await message.answer(f"❌ Пользователь '{args[1]}' не найден.")
        return
    target_username = (user.get("tg_username") or "").lower().lstrip("@")
    if target_username in HIDDEN_USERNAMES:
        await message.answer(f"❌ Пользователь '{args[1]}' не найден.")
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
        y = user.get("yandex_total", 0) or 0
        g = user.get("google_total", 0) or 0
        gi = user.get("gis_total", 0) or 0
        if y >= 10 and (g + gi) >= 15:
            ref_status = "выполнено"
        else:
            ref_status = "в процессе"
    active_warnings = get_active_warnings(user["user_id"])
    warn_text = ""
    if active_warnings:
        warn_text = "\n⚠️ Предупреждения:\n"
        for i, w in enumerate(active_warnings, 1):
            created = datetime.fromisoformat(w['created_at']).strftime("%d.%m.%Y")
            expires = datetime.fromisoformat(w['expires_at']).strftime("%d.%m.%Y")
            warn_text += f"{i}/3 – {w['reason']}\n   Выдано: {created}, снимется: {expires}\n"
    else:
        warn_text = "\n⚠️ Предупреждений нет."

    text = (
        f"🕵️ Профиль пользователя @{user.get('tg_username', user['user_id'])}:\n\n"
        f"ID: {user['user_id']}\n"
        f"Имя: {user['name']}\n"
        f"Время от МСК: {user['timezone']}\n"
        f"Город: {user['city']}\n"
        f"С нами уже: {time_str}\n"
        f"К выплате чт: {user['payout']}₽\n"
        f"Заработано за всё время: {user['total_earned']}₽\n"
        f"Пополнение адм: {user.get('admin_topup', 0)}₽\n\n"
        f"📊 Статистика по слотам:\n"
        f"Яндекс: {user['yandex_passed']}\n"
        f"Яндекс Негатив: {user.get('yandex_neg_passed', 0)}\n"
        f"Google: {user['google_passed']}\n"
        f"2ГИС: {user['gis_passed']}\n"
        f"Авито: {user['avito_passed']}\n"
        f"ВК: {user['vk_passed']}\n"
        f"Отзовик: {user['otzovik_passed']}\n"
        f"Doctoru: {user['doctoru_passed']}\n"
        f"ДокДок: {user['dokdok_passed']}\n"
        f"Про Докторов: {user['prodoctors_passed']}\n"
        f"ДокТу: {user['doctu_passed']}\n"
        f"32ТОП: {user['top32_passed']}\n"
        f"ZOON: {user.get('zoon_passed', 0)}\n"
        f"Yell: {user.get('yell_passed', 0)}\n\n"
        f"Рефералка: {ref if ref != '0' else 'нет'} ({ref_status})\n"
        f"Реквизиты: {user['phone_card']} / {user['bank']}\n"
        f"{warn_text}"
    )
    await message.answer(text)
    log_action(message, f"/info: {args[1]}")


@router.message(Command("useredit"))
async def user_edit(message: Message):
    if not is_admin_nc(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) < 4:
        await message.answer("Использование: /useredit <user_id/username> <поле> <значение>\nПоля: payout, earned, phone, bank, myotz 1-13")
        return
    target = parts[1]
    user = find_user_extended(target)
    if not user:
        await message.answer("❌ Пользователь не найден.")
        return
    user_id = user["user_id"]

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
    elif field == "myotz":
        if len(parts) < 5:
            await message.answer("❌ Укажите номер платформы (1-13) и значение.")
            return
        platform_num = int(parts[3])
        new_value = int(parts[4])
        platform_map = {
            1: "yandex_total", 2: "google_total", 3: "gis_total", 4: "avito_total",
            5: "vk_total", 6: "otzovik_total", 7: "doctoru_total", 8: "dokdok_total",
            9: "prodoctors_total", 10: "doctu_total", 11: "top32_total",
            12: "zoon_total", 13: "yell_total"
        }
        if platform_num not in platform_map:
            await message.answer("❌ Номер платформы от 1 до 13.")
            return
        update_user_field(user_id, platform_map[platform_num], new_value)
        await message.answer(f"✅ Общий счётчик платформы {platform_num} обновлён.")
        return
    else:
        await message.answer("Неизвестное поле.")
        return
    await message.answer(f"✅ Данные пользователя {user_id} обновлены.")
    log_action(message, f"/useredit {user_id}: {field}={value}")


@router.message(Command("pay"))
async def cmd_pay(message: Message):
    if not is_admin_nc(message.from_user.id):
        await message.answer("⛔ У вас нет доступа.")
        return

    parts = message.text.split()
    if len(parts) < 3:
        await message.answer("❌ Использование: /pay <@username или user_id> <сумма>")
        return

    target = parts[1]
    try:
        amount = int(parts[2])
        if amount <= 0:
            await message.answer("❌ Сумма > 0.")
            return
    except ValueError:
        await message.answer("❌ Сумма — число.")
        return

    user = find_user_extended(target)
    if not user:
        await message.answer(f"❌ Пользователь '{target}' не найден.")
        return

    user_id = user["user_id"]
    new_payout = (user.get("payout") or 0) + amount
    new_earned = (user.get("total_earned") or 0) + amount
    new_topup = (user.get("admin_topup") or 0) + amount

    update_user_field(user_id, "payout", new_payout)
    update_user_field(user_id, "total_earned", new_earned)
    update_user_field(user_id, "admin_topup", new_topup)

    await message.answer(
        f"✅ Пользователю @{user.get('tg_username') or user_id} начислено {amount}₽\n\n"
        f"💰 К выплате: {new_payout}₽\n"
        f"💵 Заработано ЗВВ: {new_earned}₽\n"
        f"📊 Пополнение адм: {new_topup}₽"
    )
    log_action(message, f"/pay {amount}₽ → {user_id}")


@router.message(Command("subtract"))
async def cmd_subtract(message: Message):
    if not is_admin_nc(message.from_user.id):
        await message.answer("⛔ У вас нет доступа.")
        return

    parts = message.text.split()
    if len(parts) < 4:
        await message.answer(
            "❌ Использование:\n"
            "• /subtract platform <user> <платформа> <N> [ШТ] [...]\n"
            "• /subtract many <user> <сумма>"
        )
        return

    mode = parts[1].lower()
    target = parts[2]

    user = find_user_extended(target)
    if not user:
        await message.answer(f"❌ Пользователь '{target}' не найден.")
        return

    uid = user["user_id"]
    username = user.get("tg_username") or str(uid)

    if mode == "many":
        try:
            amount = int(parts[3])
            if amount <= 0:
                raise ValueError
        except (ValueError, IndexError):
            await message.answer("❌ Сумма > 0. Пример: /subtract many @ivan 300")
            return

        new_payout = (user.get("payout") or 0) - amount
        new_earned = (user.get("total_earned") or 0) - amount
        new_topup = (user.get("admin_topup") or 0) - amount

        update_user_field(uid, "payout", new_payout)
        update_user_field(uid, "total_earned", new_earned)
        update_user_field(uid, "admin_topup", new_topup)

        await message.answer(
            f"✅ Списано {amount}₽ с @{username}\n\n"
            f"💰 К выплате: {new_payout}₽\n"
            f"💵 Заработано: {new_earned}₽"
        )
        log_action(message, f"/subtract many {amount}₽ {uid}")
        return

    if mode == "platform":
        tokens = parts[3:]
        ops = []
        i = 0
        while i < len(tokens):
            plat_raw = tokens[i]
            i += 1
            if i >= len(tokens):
                await message.answer(f"❌ После '{plat_raw}' ожидалось число.")
                return
            try:
                cnt = int(tokens[i])
                if cnt <= 0:
                    raise ValueError
            except ValueError:
                await message.answer(f"❌ После '{plat_raw}' — положительное число.")
                return
            i += 1
            ops.append((plat_raw, cnt))
            if i < len(tokens) and tokens[i].lower() in ("шт", "штук", "штуки", "штука"):
                i += 1

        if not ops:
            await message.answer("❌ Не указаны платформы.")
            return

        field_map = {
            "яндекс": "yandex", "яндекс негатив": "yandex_neg",
            "google": "google", "2гис": "gis", "авито": "avito",
            "вк": "vk", "отзовик": "otzovik", "доктору": "doctoru",
            "докдок": "dokdok", "про докторов": "prodoctors", "докту": "doctu",
            "32топ": "top32", "zoon": "zoon", "яу": "yau",
            "яб": "yab", "h": "hh", "yell": "yell",
        }

        user = get_user(uid)
        total_deducted = 0
        details = []
        updates = {}

        for plat_raw, cnt in ops:
            plat = match_platform(plat_raw)
            if not plat:
                await message.answer(f"❌ Не распознал '{plat_raw}'.")
                return
            fp = field_map[plat]
            price = PRICES.get(plat, 0)
            delta_rub = cnt * price

            cur_passed = user.get(f"{fp}_passed") or 0
            cur_total = user.get(f"{fp}_total") or 0

            new_passed = max(0, cur_passed - cnt)
            new_total = max(0, cur_total - cnt)

            updates[f"{fp}_passed"] = new_passed
            updates[f"{fp}_total"] = new_total
            user[f"{fp}_passed"] = new_passed
            user[f"{fp}_total"] = new_total

            total_deducted += delta_rub
            details.append(f"• {plat}: -{cnt} × {price}₽ = -{delta_rub}₽")

        new_payout = (user.get("payout") or 0) - total_deducted
        new_earned = (user.get("total_earned") or 0) - total_deducted

        for field, value in updates.items():
            update_user_field(uid, field, value)
        update_user_field(uid, "payout", new_payout)
        update_user_field(uid, "total_earned", new_earned)

        details_text = "\n".join(details)
        await message.answer(
            f"✅ Списано с @{username}:\n\n{details_text}\n\n"
            f"💸 Итого: {total_deducted}₽\n"
            f"💰 К выплате: {new_payout}₽"
        )
        log_action(message, f"/subtract {uid}: {details_text}")
        return

    await message.answer("❌ Первый аргумент: 'platform' или 'many'.")


@router.message(Command("update_stats"))
async def cmd_update_stats(message: Message):
    if not is_admin_nc(message.from_user.id):
        return
    await message.answer("⏳ Запускаю обновление статистики...")
    log_action(message, "Запущено обновление статистики")
    try:
        from bot.google_sheets import update_stats_from_sheet_once
        await update_stats_from_sheet_once(message.bot)
        await message.answer("✅ Статистика обновлена!")
    except Exception as e:
        logger.error(f"/update_stats: {e}")
        await message.answer(f"❌ Ошибка: {e}")


@router.message(Command("resetbalance"))
async def reset_balance(message: Message):
    if not is_ga(message.from_user.id):
        return
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.cursor()
            cur.execute("SELECT user_id FROM users WHERE payout >= 150")
            rows = cur.fetchall()
            user_ids = [row[0] for row in rows]
            if not user_ids:
                await message.answer("Нет юзеров с балансом >= 150₽.")
                return
            placeholders = ','.join(['?'] * len(user_ids))
            cur.execute(f"""
                UPDATE users SET payout = 0, admin_topup = 0,
                yandex_passed=0, yandex_neg_passed=0, yandex_neg_opz_passed=0,
                google_passed=0, gis_passed=0, avito_passed=0, vk_passed=0,
                otzovik_passed=0, doctoru_passed=0, dokdok_passed=0, prodoctors_passed=0,
                doctu_passed=0, top32_passed=0, zoon_passed=0, yell_passed=0,
                yau_passed=0, yab_passed=0, hh_passed=0
                WHERE user_id IN ({placeholders})
            """, user_ids)
            conn.commit()
        await message.answer(f"✅ Балансы сброшены у {len(user_ids)} юзеров.")
        log_action(message, f"resetbalance: {len(user_ids)}")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


@router.message(Command("payout_report"))
async def cmd_payout_report(message: Message):
    if not is_owner(message.from_user.id):
        return

    try:
        users = get_all_users_with_payout()
        if not users:
            await message.answer("📭 Нет юзеров с балансом >= 150₽.")
            return

        text_lines = ["<b>📋 Список на выплату</b>\n"]
        user_ids = []
        for u in users:
            username = u.get('tg_username') or u.get('username') or str(u['user_id'])
            phone = u.get('phone_card') or '—'
            bank = u.get('bank') or '—'
            line = f"👤 @{username} (ID: {u['user_id']})\n💰 {u['payout']}₽\n📞 {phone}\n🏦 {bank}\n──────────────"
            text_lines.append(line)
            user_ids.append(u['user_id'])
        full_text = "\n".join(text_lines)
        max_len = 4000
        from bot.config import REPORT_CHAT_ID, REPORT_THREAD_ID

        if not REPORT_CHAT_ID:
            await message.answer("⚠️ REPORT_CHAT_ID не задан.")
        else:
            for i in range(0, len(full_text), max_len):
                chunk = full_text[i:i+max_len]
                await message.bot.send_message(
                    chat_id=REPORT_CHAT_ID, text=chunk,
                    message_thread_id=REPORT_THREAD_ID or None,
                    parse_mode="HTML"
                )

        if user_ids:
            try:
                from bot.google_sheets import mark_as_paid_in_table
                await mark_as_paid_in_table(user_ids)
                await message.answer("✅ Строки → 'В отчете ИСПЛ'.")
            except Exception as e:
                logger.error(f"mark_as_paid: {e}")
                await message.answer(f"⚠️ Ошибка: {e}")

            with sqlite3.connect(DB_PATH) as conn:
                cur = conn.cursor()
                placeholders = ','.join(['?'] * len(user_ids))
                cur.execute(f"""
                    UPDATE users SET
                        payout = 0, admin_topup = 0,
                        yandex_passed = 0, yandex_neg_passed = 0, yandex_neg_opz_passed = 0,
                        google_passed = 0, gis_passed = 0, avito_passed = 0, vk_passed = 0,
                        otzovik_passed = 0, doctoru_passed = 0, dokdok_passed = 0,
                        prodoctors_passed = 0, doctu_passed = 0, top32_passed = 0,
                        zoon_passed = 0, yell_passed = 0, yau_passed = 0, yab_passed = 0, hh_passed = 0
                    WHERE user_id IN ({placeholders})
                """, user_ids)
                conn.commit()
            await message.answer(f"✅ Обнулено у {len(user_ids)} юзеров.")

        log_action(message, f"/payout_report: {len(user_ids)}")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")
        log_action(message, f"/payout_report: {e}")


@router.message(Command("tiktok_pay"))
async def cmd_tiktok_pay(message: Message):
    if not is_ga(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) < 3:
        await message.answer("❌ /tiktok_pay <user> <просмотры>")
        return
    target = parts[1]
    try:
        views = int(parts[2])
        if views <= 0:
            await message.answer("❌ Просмотры > 0.")
            return
    except ValueError:
        await message.answer("❌ Просмотры — число.")
        return
    user = find_user_extended(target)
    if not user:
        await message.answer(f"❌ '{target}' не найден.")
        return
    user_id = user["user_id"]
    amount = calculate_tiktok_payout(views)
    if amount == 0:
        await message.answer("❌ Сумма = 0.")
        return
    update_user_field(user_id, "payout", user["payout"] + amount)
    update_user_field(user_id, "total_earned", user["total_earned"] + amount)
    if LOG_CHANNEL_ID:
        try:
            await message.bot.send_message(
                LOG_CHANNEL_ID,
                f"🎬 TikTok: @{user.get('tg_username', user_id)} ({user_id})\n"
                f"📊 {views} просмотров\n💰 {amount}₽\n🕒 @{message.from_user.username}"
            )
        except Exception:
            pass
    await message.answer(
        f"✅ Начислено {amount}₽ за TikTok.\n"
        f"Просмотров: {views}\n"
        f"Новый баланс: {user['payout'] + amount}₽"
    )
    log_action(message, f"TikTok +{amount}₽ → {user_id}")


@router.message(Command("stop_tiktok"))
async def cmd_stop_tiktok(message: Message):
    if not is_ga(message.from_user.id):
        return
    try:
        from bot.google_sheets import moscow_tz
        now = datetime.now(moscow_tz)
        date_str = now.strftime("%d.%m.%Y")
        set_setting("tiktok_stop_date", date_str)
        await message.answer(f"✅ TikTok остановлен с {date_str}.")
        log_action(message, f"TikTok stop: {date_str}")
        users = get_all_registered_users()
        if users:
            sent = 0
            for user in users:
                try:
                    await message.bot.send_message(
                        user["user_id"],
                        f"⛔ <b>Внимание!</b> TikTok приостановлен с <b>{date_str}</b>.",
                        parse_mode="HTML"
                    )
                    sent += 1
                    await asyncio.sleep(0.1)
                except:
                    pass
            await message.answer(f"📨 Уведомлено: {sent}.")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


@router.message(Command("start_tiktok"))
async def cmd_start_tiktok(message: Message):
    if not is_ga(message.from_user.id):
        return
    try:
        set_setting("tiktok_stop_date", "")
        await message.answer("✅ TikTok возобновлён.")
        log_action(message, "TikTok start")
        users = get_all_registered_users()
        if users:
            sent = 0
            for user in users:
                try:
                    await message.bot.send_message(
                        user["user_id"],
                        "▶️ <b>Хорошие новости!</b> TikTok возобновлён!",
                        parse_mode="HTML"
                    )
                    sent += 1
                    await asyncio.sleep(0.1)
                except:
                    pass
            await message.answer(f"📨 Уведомлено: {sent}.")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


@router.message(Command("set_limit"))
async def cmd_set_limit(message: Message):
    if not is_admin_nc(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) < 3:
        await message.answer("❌ /set_limit <platform> <limit>")
        return
    platform = parts[1].lower()
    try:
        limit = int(parts[2])
        if limit < 1:
            await message.answer("❌ Лимит > 0.")
            return
        set_limit(platform, limit)
        await message.answer(f"✅ Лимит '{platform}' = {limit} / 24ч.")
        log_action(message, f"Лимит {limit} для {platform}")
    except ValueError:
        await message.answer("❌ Лимит — число.")


@router.message(Command("user_limit"))
async def cmd_user_limit(message: Message):
    if not is_admin_nc(message.from_user.id):
        await message.answer("⛔ Нет доступа.")
        return

    parts = message.text.split()
    if len(parts) < 3:
        await message.answer(
            "❌ /user_limit <user> <platform> <limit|reset>\n"
            "или /user_limit <user> reset"
        )
        return

    target = parts[1]
    user = find_user_extended(target)
    if not user:
        await message.answer(f"❌ '{target}' не найден.")
        return

    uid = user["user_id"]

    if len(parts) == 3 and parts[2].lower() == "reset":
        reset_user_limit(uid)
        await message.answer(f"✅ Все персональные лимиты @{user.get('tg_username') or uid} сброшены.")
        log_action(message, f"reset user_limit {uid}")
        return

    if len(parts) < 4:
        await message.answer("❌ Укажите платформу и значение.")
        return

    platform = parts[2].lower()
    value = parts[3].lower()

    if value == "reset":
        reset_user_limit(uid, platform)
        await message.answer(
            f"✅ Персональный лимит '{platform}' для @{user.get('tg_username') or uid} сброшен.\n"
            f"Общий: {get_limit(platform)}."
        )
        log_action(message, f"reset user_limit {uid} {platform}")
        return

    try:
        limit = int(value)
        if limit < 1:
            await message.answer("❌ Лимит > 0.")
            return
    except ValueError:
        await message.answer("❌ Лимит — число или 'reset'.")
        return

    set_user_limit(uid, platform, limit)
    await message.answer(
        f"✅ @{user.get('tg_username') or uid}: лимит '{platform}' = <b>{limit}</b>.\n"
        f"<i>Общий: {get_limit(platform)}</i>",
        parse_mode="HTML"
    )
    log_action(message, f"user_limit {limit} '{platform}' {uid}")


# ============ /unslot ============
@router.message(Command("unslot"))
async def cmd_unslot(message: Message):
    if not is_admin_nc(message.from_user.id):
        await message.answer("⛔ Только для владельца, ГА и Админа NC.")
        return

    parts = message.text.split()
    if len(parts) < 2:
        await message.answer(
            "❌ <b>Использование:</b>\n"
            "<code>/unslot &lt;@username или user_id&gt;</code>",
            parse_mode="HTML"
        )
        return

    target = parts[1]
    user = find_user_extended(target)
    if not user:
        await message.answer(f"❌ '{target}' не найден.")
        return

    uid = user["user_id"]

    from bot.state import slot_requests
    if uid not in slot_requests:
        await message.answer(f"❌ У @{user.get('tg_username') or uid} нет активного слота.")
        return

    req = slot_requests[uid]
    platform = req.get("platform", "?")
    assigned_rows = req.get("assigned_rows", [])
    sheet_title = req.get("sheet_title")
    mapping = req.get("mapping")
    completed = len(req.get("completed_reviews", []))
    state = req.get("state")

    cleaned_ok = False
    if sheet_title and assigned_rows:
        try:
            from bot.google_sheets import get_client, retry_api_call
            from bot.helpers import get_column_mapping

            if not mapping or "status_col" not in mapping:
                mapping = get_column_mapping(platform)

            client = get_client()
            if client:
                spreadsheet = await asyncio.to_thread(client.open_by_key, SHEET_ID)
                sheet = await asyncio.to_thread(spreadsheet.worksheet, sheet_title)

                batch = []
                for row_idx in assigned_rows:
                    for key, val in [
                        ("status_col", "не принят в работу"),
                        ("executor_col", ""),
                        ("flag_final_col", 0),
                        ("flag_third_col", 0),
                        ("flag_second_col", 0),
                        ("flag_first_col", 0),
                        ("id_col", ""),
                        ("order_col", ""),
                    ]:
                        if key not in mapping:
                            continue
                        col = chr(64 + mapping[key])
                        batch.append({"range": f"{col}{row_idx}", "values": [[val]]})

                for i in range(0, len(batch), 20):
                    await retry_api_call(sheet.batch_update, batch[i:i+20])
                    await asyncio.sleep(0.4)
                cleaned_ok = True
                logger.info(f"/unslot: {uid} — очищено {len(assigned_rows)}")
        except Exception as e:
            logger.error(f"/unslot: {e}")
    else:
        cleaned_ok = True

    try:
        del slot_requests[uid]
    except KeyError:
        pass

    try:
        msg = (
            f"⚠️ <b>Ваш слот снят администратором.</b>\n\n"
            f"📋 Платформа: {platform}\n"
            f"📊 Строк было: {len(assigned_rows)}\n"
            f"✅ Выполнено: {completed}"
        )
        await message.bot.send_message(uid, msg, parse_mode="HTML")
    except Exception as e:
        logger.warning(f"/unslot notify: {e}")

    await message.answer(
        f"✅ <b>Слот снят</b>\n\n"
        f"👤 @{user.get('tg_username') or uid}\n"
        f"📋 Платформа: {platform}\n"
        f"📊 Строк: {len(assigned_rows)}\n"
        f"✅ Выполнено: {completed}\n"
        f"🧹 Таблица: {'✅' if cleaned_ok else '⚠️ ошибка'}",
        parse_mode="HTML"
    )
    log_action(message, f"/unslot {uid} ({platform})")


# ============ /cleanflags ============
@router.message(Command("cleanflags"))
async def cmd_cleanflags(message: Message):
    if not is_admin_nc(message.from_user.id):
        await message.answer("⛔ Только для владельца, ГА и Админа NC.")
        return

    await message.answer("⏳ Прохожу по всем листам...")

    try:
        from bot.google_sheets import get_client, retry_api_call
        from bot.helpers import get_column_mapping

        client = get_client()
        if not client:
            await message.answer("❌ Нет доступа к Sheets.")
            return

        spreadsheet = await asyncio.to_thread(client.open_by_key, SHEET_ID)
        worksheets = await asyncio.to_thread(spreadsheet.worksheets)

        VALID_FOR_333 = (
            "на модерации", "на модерации с опз",
            "опубликован", "опубликовано", "опубликован опз", "опубликовано опз",
            "удален", "в отчете испол",
        )

        total_cleaned = 0
        details = []

        for sheet in worksheets:
            sheet_name = sheet.title
            platform = platform_from_sheet_name(sheet_name)
            if not platform:
                continue

            try:
                records = await retry_api_call(sheet.get_all_values)
            except Exception as e:
                logger.warning(f"cleanflags '{sheet_name}': {e}")
                continue
            if len(records) < 2:
                continue

            headers_row = records[0] if records else None
            mapping = get_column_mapping(platform, headers_row)
            col_i = chr(64 + mapping["flag_final_col"])

            batch = []
            for row_idx, row in enumerate(records[1:], start=2):
                if len(row) < max(mapping["status_col"], mapping["flag_final_col"]):
                    continue
                i_val = (row[mapping["flag_final_col"]-1] or "").strip()
                j_val = (row[mapping["status_col"]-1] or "").strip().lower() if len(row) >= mapping["status_col"] else ""

                if i_val in ("", "0"):
                    continue

                if i_val == "333":
                    if not any(j_val.startswith(s) for s in VALID_FOR_333):
                        batch.append({"range": f"{col_i}{row_idx}", "values": [[0]]})

            if batch:
                try:
                    for i in range(0, len(batch), 50):
                        await retry_api_call(sheet.batch_update, batch[i:i+50])
                        await asyncio.sleep(0.6)
                    total_cleaned += len(batch)
                    details.append(f"• {sheet_name}: {len(batch)}")
                except Exception as e:
                    logger.error(f"cleanflags '{sheet_name}': {e}")
                    details.append(f"• {sheet_name}: ⚠️ {e}")

        if total_cleaned == 0:
            await message.answer("✅ Всё чисто.")
        else:
            text = f"✅ <b>Готово</b>\n\nСброшено: <b>{total_cleaned}</b>\n\n" + "\n".join(details)
            await message.answer(text, parse_mode="HTML")

        log_action(message, f"/cleanflags: {total_cleaned}")
    except Exception as e:
        logger.error(f"cleanflags: {e}", exc_info=True)
        await message.answer(f"❌ Ошибка: {e}")


# ============ /resetflags — сброс Q/P/O/I/S у "висящих" строк ============
@router.message(Command("resetflags"))
async def cmd_resetflags(message: Message):
    if not is_admin_nc(message.from_user.id):
        await message.answer("⛔ Только для владельца, ГА и Админа NC.")
        return

    parts = message.text.split()
    if len(parts) < 2:
        await message.answer(
            "❌ <b>Использование:</b>\n"
            "<code>/resetflags &lt;платформа&gt;</code>\n\n"
            "Сбрасывает Q, P, O, I, S у всех строк, где:\n"
            "• статус пустой или «не принят в работу»\n"
            "• исполнитель пустой\n\n"
            "Примеры: <code>/resetflags 2гис</code>, <code>/resetflags яндекс</code>",
            parse_mode="HTML"
        )
        return

    platform_raw = parts[1].lower()
    platform = match_platform(platform_raw)
    if not platform:
        await message.answer(f"❌ Не распознал платформу '{platform_raw}'.")
        return

    await message.answer(f"⏳ Ищу зависшие строки на «{platform}»...", parse_mode="HTML")

    try:
        from bot.google_sheets import get_client, retry_api_call
        from bot.helpers import get_column_mapping

        client = get_client()
        if not client:
            await message.answer("❌ Нет доступа к Sheets.")
            return

        spreadsheet = await asyncio.to_thread(client.open_by_key, SHEET_ID)
        worksheets = await asyncio.to_thread(spreadsheet.worksheets)

        target_sheets = []
        for sheet in worksheets:
            if platform_from_sheet_name(sheet.title) == platform:
                target_sheets.append(sheet)

        if not target_sheets:
            await message.answer(f"❌ Не нашёл лист для «{platform}».")
            return

        total_reset = 0
        details = []

        for sheet in target_sheets:
            sheet_name = sheet.title
            try:
                records = await retry_api_call(sheet.get_all_values)
            except Exception as e:
                logger.error(f"resetflags '{sheet_name}': {e}")
                continue
            if len(records) < 2:
                continue

            headers_row = records[0] if records else None
            mapping = get_column_mapping(platform, headers_row)

            batch = []
            for row_idx, row in enumerate(records[1:], start=2):
                if len(row) < max(
                    mapping["status_col"],
                    mapping["executor_col"],
                    mapping["flag_first_col"],
                    mapping["flag_second_col"],
                    mapping["flag_third_col"],
                    mapping["flag_final_col"],
                ):
                    continue

                status = _norm(row[mapping["status_col"]-1])
                executor = row[mapping["executor_col"]-1].strip()

                if executor:
                    continue
                if status and status not in ("не принят в работу",):
                    continue

                q = row[mapping["flag_first_col"]-1].strip()
                p = row[mapping["flag_second_col"]-1].strip()
                o = row[mapping["flag_third_col"]-1].strip()
                i = row[mapping["flag_final_col"]-1].strip()

                if q in ("1", "999"):
                    batch.append({"range": f"{chr(64+mapping['flag_first_col'])}{row_idx}", "values": [[0]]})
                    s_val = row[mapping["id_col"]-1].strip() if len(row) >= mapping["id_col"] else ""
                    if s_val:
                        batch.append({"range": f"{chr(64+mapping['id_col'])}{row_idx}", "values": [[""]]})
                if p == "1":
                    batch.append({"range": f"{chr(64+mapping['flag_second_col'])}{row_idx}", "values": [[0]]})
                if o == "1":
                    batch.append({"range": f"{chr(64+mapping['flag_third_col'])}{row_idx}", "values": [[0]]})
                if i in ("1", "888", "222"):
                    batch.append({"range": f"{chr(64+mapping['flag_final_col'])}{row_idx}", "values": [[0]]})

            if batch:
                try:
                    for i in range(0, len(batch), 50):
                        await retry_api_call(sheet.batch_update, batch[i:i+50])
                        await asyncio.sleep(0.6)
                    total_reset += len(batch)
                    details.append(f"• {sheet_name}: сброшено {len(batch)} ячеек")
                except Exception as e:
                    logger.error(f"resetflags '{sheet_name}': {e}")
                    details.append(f"• {sheet_name}: ⚠️ {e}")

        if total_reset == 0:
            await message.answer(f"✅ Зависших строк на «{platform}» не найдено.")
        else:
            text = (
                f"✅ <b>Готово</b>\n\n"
                f"Сброшено флагов: <b>{total_reset}</b> ячеек\n\n" +
                "\n".join(details) +
                f"\n\n<i>Через 5 минут монитор соберёт их в слот.</i>"
            )
            await message.answer(text, parse_mode="HTML")

        log_action(message, f"/resetflags {platform}: {total_reset}")
    except Exception as e:
        logger.error(f"resetflags: {e}", exc_info=True)
        await message.answer(f"❌ Ошибка: {e}")


# ============ /admlist — список всех ролей кроме owner ============
@router.message(Command("admlist"))
async def cmd_admlist(message: Message):
    caller_id = message.from_user.id
    if not (is_owner(caller_id) or is_ga(caller_id)):
        await message.answer("⛔ Команда доступна только владельцу и ГА.")
        return

    ROLE_ORDER = {
        "ga": 1,
        "admin": 2,
        "stmoderator": 3,
        "moderator": 4,
        "comoderator": 5,
        "stpromonc": 6,
    }

    ROLE_DISPLAY = {
        "ga": "🛡️ ГА (Главный администратор)",
        "admin": "🎩 Администратор NC",
        "stmoderator": "⭐ Старший модератор",
        "moderator": "🔨 Модератор",
        "comoderator": "🧰 Комодер",
        "stpromonc": "🏆 Старший промоутер",
    }

    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("""
                SELECT a.user_id, a.role, u.tg_username, u.name, u.blocked
                FROM admins a
                LEFT JOIN users u ON u.user_id = a.user_id
                WHERE a.role != 'owner'
            """)
            rows = [dict(r) for r in cur.fetchall()]
    except Exception as e:
        await message.answer(f"❌ Ошибка БД: {e}")
        return

    if not rows:
        await message.answer("📭 Список пуст — нет ни одного сотрудника с ролью.")
        return

    grouped = {}
    for r in rows:
        grouped.setdefault(r["role"], []).append(r)

    lines = [
        f"👥 <b>Список сотрудников с ролями</b>",
        f"<i>Без владельца · Всего: {len(rows)}</i>\n",
    ]

    for role in sorted(grouped.keys(), key=lambda x: ROLE_ORDER.get(x, 99)):
        items = grouped[role]
        lines.append(f"\n<b>{ROLE_DISPLAY.get(role, role)}</b> ({len(items)}):")
        for u in sorted(items, key=lambda x: (x.get("name") or "").lower()):
            name = u.get("name") or "—"
            uname = u.get("tg_username") or "—"
            uid = u["user_id"]
            blocked_mark = " ⛔" if u.get("blocked") else ""
            lines.append(f"• {name} (@{uname}, ID: {uid}){blocked_mark}")

    text = "\n".join(lines)
    max_len = 4000

    if len(text) <= max_len:
        await message.answer(text, parse_mode="HTML")
    else:
        total_parts = (len(text) + max_len - 1) // max_len
        for i in range(0, len(text), max_len):
            part_num = i // max_len + 1
            chunk = text[i:i+max_len]
            if part_num > 1:
                chunk = f"<i>(часть {part_num}/{total_parts})</i>\n\n" + chunk
            await message.answer(chunk, parse_mode="HTML")

    log_action(message, f"/admlist: показано {len(rows)} сотрудников")


# ============ /smsall — рассылка всем зарегистрированным ============
@router.message(Command("smsall"))
async def cmd_smsall(message: Message):
    caller_id = message.from_user.id
    if not (is_owner(caller_id) or is_ga(caller_id)):
        await message.answer("⛔ Только для владельца и ГА.")
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("❌ <code>/smsall &lt;текст&gt;</code>", parse_mode="HTML")
        return

    text = parts[1].strip()
    if len(text) < 3:
        await message.answer("❌ Текст короткий.")
        return

    users = get_all_registered_users()
    if not users:
        await message.answer("📭 Нет зарегистрированных.")
        return

    await message.answer(f"📤 Рассылка на {len(users)} юзеров...", parse_mode="HTML")
    log_action(message, f"/smsall на {len(users)}")

    sent = 0
    blocked = 0
    failed = 0

    for u in users:
        uid = u["user_id"]
        try:
            await message.bot.send_message(
                uid,
                f"📢 <b>Сообщение от администрации NC:</b>\n\n{text}",
                parse_mode="HTML"
            )
            sent += 1
        except Exception as e:
            err = str(e).lower()
            if "blocked" in err or "deactivated" in err or "chat not found" in err:
                blocked += 1
            else:
                failed += 1
                logger.warning(f"/smsall {uid}: {e}")
        await asyncio.sleep(0.05)

    summary = (
        f"✅ <b>Рассылка завершена</b>\n\n"
        f"📤 Отправлено: <b>{sent}</b>\n"
        f"🚫 Заблокировали бота: <b>{blocked}</b>\n"
        f"❌ Ошибок: <b>{failed}</b>\n"
        f"📊 Всего: <b>{len(users)}</b>"
    )
    await message.answer(summary, parse_mode="HTML")
    log_action(message, f"/smsall: sent={sent}, blocked={blocked}, failed={failed}")


# ============ /users — список зарегистрированных ============
@router.message(Command("users"))
async def cmd_users(message: Message):
    caller_id = message.from_user.id
    if not (is_owner(caller_id) or is_ga(caller_id)):
        await message.answer("⛔ Только для владельца и ГА.")
        return

    users = get_all_registered_users()
    if not users:
        await message.answer("📭 Нет зарегистрированных.")
        return

    lines = [
        f"👥 <b>Зарегистрированные пользователи</b> ({len(users)}):",
        f"<i>Обновлено: {datetime.now().strftime('%d.%m.%Y %H:%M')}</i>\n",
    ]
    for i, u in enumerate(users, 1):
        uname = u.get("tg_username") or "—"
        lines.append(f"{i}. @{uname} (ID: {u['user_id']})")

    text = "\n".join(lines)
    max_len = 4000

    if LOG_USERS_CHAT_ID:
        try:
            total_parts = (len(text) + max_len - 1) // max_len
            for i in range(0, len(text), max_len):
                part_num = i // max_len + 1
                chunk = text[i:i+max_len]
                if part_num > 1:
                    chunk = f"<i>(часть {part_num}/{total_parts})</i>\n\n" + chunk
                await message.bot.send_message(
                    chat_id=LOG_USERS_CHAT_ID,
                    text=chunk,
                    message_thread_id=LOG_USERS_THREAD_ID or None,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )
                await asyncio.sleep(0.4)

            await message.answer(
                f"✅ Список из <b>{len(users)}</b> пользователей отправлен в беседу.",
                parse_mode="HTML"
            )
            log_action(message, f"/users: {len(users)} → LOG_USERS_CHAT_ID")
        except Exception as e:
            logger.error(f"/users: {e}")
            await message.answer(f"⚠️ Не удалось в беседу: {e}\nОтправляю в личку.")
            if len(text) <= max_len:
                await message.answer(text, parse_mode="HTML")
            else:
                total_parts = (len(text) + max_len - 1) // max_len
                for i in range(0, len(text), max_len):
                    part_num = i // max_len + 1
                    chunk = text[i:i+max_len]
                    if part_num > 1:
                        chunk = f"<i>(часть {part_num}/{total_parts})</i>\n\n" + chunk
                    await message.answer(chunk, parse_mode="HTML")
    else:
        if len(text) <= max_len:
            await message.answer(text, parse_mode="HTML")
        else:
            total_parts = (len(text) + max_len - 1) // max_len
            for i in range(0, len(text), max_len):
                part_num = i // max_len + 1
                chunk = text[i:i+max_len]
                if part_num > 1:
                    chunk = f"<i>(часть {part_num}/{total_parts})</i>\n\n" + chunk
                await message.answer(chunk, parse_mode="HTML")

        log_action(message, f"/users: показано {len(users)}")
