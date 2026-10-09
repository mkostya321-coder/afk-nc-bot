from datetime import datetime
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from bot.config import OWNER_ID, LOG_CHANNEL_ID, DB_PATH
from bot.database import (
    get_user, get_user_by_username, toggle_block, update_user_field,
    get_admin_role, set_admin_role, remove_admin_role,
    is_owner, is_ga, is_admin_nc, is_stmoderator, is_moderator, is_comoderator, is_stpromonc,
    add_warning, get_warning_count, get_active_warnings, get_setting, set_setting,
    get_limit, set_limit, get_all_registered_users, get_all_users_with_payout,
    get_user_limit, set_user_limit, reset_user_limit, get_effective_limit,
)
from bot.helpers import match_platform, PRICES
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


def find_user_by_target(target: str):
    if not target:
        return None
    t = target.strip()
    if t.isdigit():
        return get_user(int(t))
    return get_user_by_username(t.lstrip("@"))


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
        )

    if is_ga(user_id):
        text += (
            "👑 /setrole <user> <role>\n"
            "   доступно: admin, stmoderator, moderator, comoderator, stpromonc, none\n"
            "👤 /userblock <user> — блок/разблок\n"
            "💰 /useredit <user> <поле> <знач> — правка данных\n"
            "💸 /pay <user> <сумма> — пополнить баланс\n"
            "➖ /subtract platform <user> <платформа> <N> [ШТ] [...] — списать N отзывов\n"
            "➖ /subtract many <user> <сумма> — списать N рублей\n"
            "ℹ️ /info <user> — профиль\n"
            "🔄 /update_stats — обновить статистику\n"
            "⚠️ /resetbalance — сбросить балансы ≥150₽\n"
            "🎬 /tiktok_pay <user> <просмотры> — начислить за TikTok\n"
            "⛔ /stop_tiktok — закрыть TikTok\n"
            "▶️ /start_tiktok — возобновить TikTok\n"
            "📨 /smsuser <user> <текст> — сообщение юзеру\n"
            "📊 /set_limit <platform> <N> — общий лимит\n"
            "👤 /user_limit <user> <platform> <N|reset> — персональный лимит\n"
            "🎖 /set_post <post> <user> — выдать должность\n"
            "🚫 /remove_post <user> — снять должность\n"
            "📋 /list_posts [post] — список сотрудников\n"
            "🏆 /infopromo <user> — карточка промоутера\n"
        )

    if is_admin_nc(user_id) and not is_ga(user_id):
        text += (
            "👤 /userblock <user> — блок/разблок\n"
            "ℹ️ /info <user> — профиль\n"
            "⚠️ /warn <user> <причина> — предупреждение\n"
            "📨 /smsuser <user> <текст> — сообщение\n"
            "💰 /useredit <user> <поле> <знач> — правка данных\n"
            "💸 /pay <user> <сумма> — пополнить баланс\n"
            "➖ /subtract platform <user> <платформа> <N> [ШТ] [...] — списать\n"
            "➖ /subtract many <user> <сумма> — списать рублей\n"
            "🔄 /update_stats — обновить статистику\n"
            "📊 /set_limit <platform> <N> — общий лимит\n"
            "👤 /user_limit <user> <platform> <N|reset> — персональный лимит\n"
            "📋 /list_posts [post] — список сотрудников\n"
        )

    if is_stmoderator(user_id) and not is_admin_nc(user_id):
        text += (
            "👤 /userblock <user> — блок/разблок\n"
            "ℹ️ /info <user> — профиль\n"
            "⚠️ /warn <user> <причина> — предупреждение\n"
            "📨 /smsuser <user> <текст> — сообщение\n"
        )

    if is_moderator(user_id) and not is_stmoderator(user_id):
        text += (
            "👤 /userblock <user> — блок/разблок\n"
            "ℹ️ /info <user> — профиль\n"
            "⚠️ /warn <user> <причина> — предупреждение\n"
            "📨 /smsuser <user> <текст> — сообщение\n"
        )

    if is_comoderator(user_id) and not is_moderator(user_id):
        text += (
            "ℹ️ /info <user> — профиль\n"
            "⚠️ /warn <user> <причина> — предупреждение\n"
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


@router.message(Command("warn"))
async def warn_user(message: Message):
    if not is_comoderator(message.from_user.id):
        return
    try:
        parts = message.text.split(maxsplit=2)
        if len(parts) < 3:
            await message.answer("Использование: /warn <user_id или username> <причина>")
            return
        target = parts[1]
        reason = parts[2]
        user = find_user_by_target(target)
        if not user:
            await message.answer("❌ Пользователь не найден")
            return

        add_warning(user["user_id"], reason, message.from_user.id)
        active_warnings = get_active_warnings(user["user_id"])
        warn_count = len(active_warnings)
        if warn_count >= 3:
            toggle_block(user["user_id"])
            await message.answer(f"✅ Пользователь @{user.get('username') or user['user_id']} получил третье предупреждение и заблокирован.")
            try:
                await message.bot.send_message(user["user_id"], f"⛔ Вы получили третье предупреждение и заблокированы.\nПричина: {reason}\nВы можете обратиться в поддержку через /support.")
            except:
                pass
        else:
            last_warn = active_warnings[-1]
            expires_str = datetime.fromisoformat(last_warn['expires_at']).strftime("%d.%m.%Y")
            await message.answer(f"✅ Предупреждение ({warn_count}/3) отправлено пользователю @{user.get('username') or user['user_id']}.\nДата снятия: {expires_str}")
            try:
                await message.bot.send_message(user["user_id"], f"⚠️ Предупреждение ({warn_count}/3): {reason}\nБудет снято: {expires_str}")
            except:
                pass
        log_action(message, f"Выдано предупреждение {warn_count}/3 пользователю {user['user_id']} ({reason})")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


@router.message(Command("smsuser"))
async def sms_user(message: Message):
    if not is_comoderator(message.from_user.id):
        return
    try:
        parts = message.text.split(maxsplit=2)
        if len(parts) < 3:
            await message.answer("Использование: /smsuser <username или user_id> <текст сообщения>")
            return
        target = parts[1]
        text = parts[2]
        user = find_user_by_target(target)
        if not user:
            await message.answer("❌ Пользователь не найден.")
            return
        try:
            await message.bot.send_message(
                user["user_id"],
                f"📩 Сообщение от Администрации проекта:\n\n{text}"
            )
            await message.answer("✅ Сообщение отправлено.")
            log_action(message, f"Отправлено SMS пользователю {user['user_id']}: {text}")
        except Exception as e:
            await message.answer(f"❌ Не удалось отправить сообщение: {e}")
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
        user = find_user_by_target(target)
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
    user = find_user_by_target(args[1])
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
    log_action(message, f"Запрошен профиль пользователя {args[1]}")


@router.message(Command("useredit"))
async def user_edit(message: Message):
    if not is_admin_nc(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) < 4:
        await message.answer("Использование: /useredit <user_id/username> <поле> <значение>\nПоля: payout, earned, phone, bank, myotz 1-13")
        return
    target = parts[1]
    user = find_user_by_target(target)
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
    log_action(message, f"Изменены данные пользователя {user_id}: {field}={value}")


@router.message(Command("pay"))
async def cmd_pay(message: Message):
    if not is_admin_nc(message.from_user.id):
        await message.answer("⛔ У вас нет доступа.")
        return

    parts = message.text.split()
    if len(parts) < 3:
        await message.answer(
            "❌ Использование: /pay <@username или user_id> <сумма>\n"
            "Пример: /pay @ivan 500\n"
            "Пример: /pay 8635115842 500"
        )
        return

    target = parts[1]
    try:
        amount = int(parts[2])
        if amount <= 0:
            await message.answer("❌ Сумма должна быть положительным числом.")
            return
    except ValueError:
        await message.answer("❌ Сумма должна быть числом.")
        return

    user = find_user_by_target(target)
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
        f"📊 Пополнение адм за неделю: {new_topup}₽"
    )
    log_action(message, f"Пополнение {amount}₽ пользователю {user_id} ({target})")


@router.message(Command("subtract"))
async def cmd_subtract(message: Message):
    if not is_admin_nc(message.from_user.id):
        await message.answer("⛔ У вас нет доступа.")
        return

    parts = message.text.split()
    if len(parts) < 4:
        await message.answer(
            "❌ Использование:\n"
            "• /subtract platform <@username или user_id> <платформа> <N> [ШТ] [...]\n"
            "• /subtract many <@username или user_id> <сумма>\n\n"
            "Примеры:\n"
            "• /subtract platform @ivan 2ГИС 10 ШТ\n"
            "• /subtract platform 8635115842 2ГИС 10 ШТ Яндекс 5 ШТ\n"
            "• /subtract many @ivan 300\n"
            "• /subtract many 8635115842 300"
        )
        return

    mode = parts[1].lower()
    target = parts[2]

    user = find_user_by_target(target)
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
            await message.answer("❌ Сумма должна быть положительным числом.\nПример: /subtract many @ivan 300")
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
            f"💵 Заработано ЗВВ: {new_earned}₽\n"
            f"📊 Поправка баланса: {new_topup}₽"
        )
        log_action(message, f"Списано {amount}₽ (many) у {uid} ({target})")
        return

    if mode == "platform":
        tokens = parts[3:]
        ops = []
        i = 0
        while i < len(tokens):
            plat_raw = tokens[i]
            i += 1
            if i >= len(tokens):
                await message.answer(f"❌ После '{plat_raw}' ожидалось число.\nПример: /subtract platform @ivan 2ГИС 10 ШТ")
                return
            try:
                cnt = int(tokens[i])
                if cnt <= 0:
                    raise ValueError
            except ValueError:
                await message.answer(f"❌ Ожидалось положительное число после '{plat_raw}', получено '{tokens[i]}'.")
                return
            i += 1
            ops.append((plat_raw, cnt))
            if i < len(tokens) and tokens[i].lower() in ("шт", "штук", "штуки", "штука"):
                i += 1

        if not ops:
            await message.answer("❌ Не указаны платформы и количество.")
            return

        field_map = {
            "яндекс": "yandex", "яндекс негатив": "yandex_neg",
            "google": "google", "2гис": "gis",
            "авито": "avito", "вк": "vk", "отзовик": "otzovik",
            "доктору": "doctoru", "докдок": "dokdok",
            "про докторов": "prodoctors", "докту": "doctu",
            "32топ": "top32", "zoon": "zoon",
            "яу": "yau", "яб": "yab", "h": "hh",
            "yell": "yell",
        }

        user = get_user(uid)
        total_deducted = 0
        details = []
        updates = {}

        for plat_raw, cnt in ops:
            plat = match_platform(plat_raw)
            if not plat:
                await message.answer(
                    f"❌ Не распознал платформу '{plat_raw}'.\n"
                    f"Допустимые: Яндекс, Яндекс Негатив, Google, 2ГИС, Авито, ВК, Отзовик, Doctoru, "
                    f"ДокДок, Про Докторов, ДокТу, 32ТОП, ZOON, Yell, ЯУ, ЯБ, HH."
                )
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
            details.append(f"• {plat}: -{cnt} шт × {price}₽ = -{delta_rub}₽")

        new_payout = (user.get("payout") or 0) - total_deducted
        new_earned = (user.get("total_earned") or 0) - total_deducted

        for field, value in updates.items():
            update_user_field(uid, field, value)
        update_user_field(uid, "payout", new_payout)
        update_user_field(uid, "total_earned", new_earned)

        details_text = "\n".join(details)
        await message.answer(
            f"✅ Списано с @{username}:\n\n"
            f"{details_text}\n\n"
            f"💸 Итого списано: {total_deducted}₽\n"
            f"💰 К выплате: {new_payout}₽\n"
            f"💵 Заработано ЗВВ: {new_earned}₽"
        )
        log_action(message, f"Списано с {uid} ({target}): {details_text}")
        return

    await message.answer(
        "❌ Первый аргумент должен быть 'platform' или 'many'.\n"
        "Пример: /subtract platform @ivan 2ГИС 10 ШТ\n"
        "Или:    /subtract many @ivan 300"
    )


@router.message(Command("update_stats"))
async def cmd_update_stats(message: Message):
    if not is_admin_nc(message.from_user.id):
        return
    await message.answer("⏳ Запускаю обновление статистики...")
    log_action(message, "Запущено обновление статистики")
    try:
        from bot.google_sheets import update_stats_from_sheet_once
        await update_stats_from_sheet_once(message.bot)
        await message.answer("✅ Статистика успешно обновлена!")
    except Exception as e:
        logger.error(f"Ошибка в /update_stats: {e}")
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
                await message.answer("Нет пользователей с балансом >= 150₽ для сброса.")
                return
            placeholders = ','.join(['?'] * len(user_ids))
            cur.execute(f"""
                UPDATE users SET payout = 0,
                admin_topup = 0,
                yandex_passed=0, yandex_neg_passed=0, yandex_neg_opz_passed=0,
                google_passed=0, gis_passed=0, avito_passed=0, vk_passed=0,
                otzovik_passed=0, doctoru_passed=0, dokdok_passed=0, prodoctors_passed=0,
                doctu_passed=0, top32_passed=0, zoon_passed=0, yell_passed=0,
                yau_passed=0, yab_passed=0, hh_passed=0
                WHERE user_id IN ({placeholders})
            """, user_ids)
            conn.commit()
        await message.answer(f"✅ Балансы сброшены у {len(user_ids)} пользователей (у кого было >=150₽).")
        log_action(message, f"Сброшены балансы у {len(user_ids)} пользователей (>=150₽)")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


@router.message(Command("payout_report"))
async def cmd_payout_report(message: Message):
    if not is_owner(message.from_user.id):
        return

    try:
        users = get_all_users_with_payout()
        if not users:
            await message.answer("📭 Нет пользователей с балансом >= 150₽.")
            return

        text_lines = ["<b>📋 Список на выплату (по запросу)</b>\n"]
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
        from bot.config import REPORT_CHAT_ID, REPORT_THREAD_ID

        if not REPORT_CHAT_ID:
            await message.answer("⚠️ REPORT_CHAT_ID не задан в переменных окружения — отчёт некуда отправить.")
        else:
            for i in range(0, len(full_text), max_len):
                chunk = full_text[i:i+max_len]
                await message.bot.send_message(
                    chat_id=REPORT_CHAT_ID,
                    text=chunk,
                    message_thread_id=REPORT_THREAD_ID or None,
                    parse_mode="HTML"
                )

        if user_ids:
            try:
                from bot.google_sheets import mark_as_paid_in_table
                await mark_as_paid_in_table(user_ids)
                await message.answer("✅ Строки с E=1 и статусом 'опубликовано' отмечены как 'В отчете ИСПЛ'.")
            except Exception as e:
                logger.error(f"Ошибка обновления статуса в таблице: {e}")
                await message.answer(f"⚠️ Ошибка при обновлении статуса: {e}")

            with sqlite3.connect(DB_PATH) as conn:
                cur = conn.cursor()
                placeholders = ','.join(['?'] * len(user_ids))
                cur.execute(f"""
                    UPDATE users SET
                        payout = 0,
                        admin_topup = 0,
                        yandex_passed = 0,
                        yandex_neg_passed = 0,
                        yandex_neg_opz_passed = 0,
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
                        zoon_passed = 0,
                        yell_passed = 0,
                        yau_passed = 0,
                        yab_passed = 0,
                        hh_passed = 0
                    WHERE user_id IN ({placeholders})
                """, user_ids)
                conn.commit()
            await message.answer(f"✅ Отчёт отправлен, балансы и текущая статистика обнулены у {len(user_ids)} пользователей.")

        log_action(message, f"Запрошен отчёт по выплатам (команда /payout_report), обнулено {len(user_ids)} пользователей")
    except Exception as e:
        await message.answer(f"❌ Ошибка при формировании отчёта: {e}")
        log_action(message, f"Ошибка в /payout_report: {e}")


@router.message(Command("tiktok_pay"))
async def cmd_tiktok_pay(message: Message):
    if not is_ga(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) < 3:
        await message.answer("❌ Использование: /tiktok_pay <user_id или username> <количество_просмотров>\nПример: /tiktok_pay 123456789 1500000")
        return
    target = parts[1]
    try:
        views = int(parts[2])
        if views <= 0:
            await message.answer("❌ Количество просмотров должно быть больше 0.")
            return
    except ValueError:
        await message.answer("❌ Количество просмотров должно быть числом.")
        return
    user = find_user_by_target(target)
    if not user:
        await message.answer(f"❌ Пользователь '{target}' не найден.")
        return
    user_id = user["user_id"]
    amount = calculate_tiktok_payout(views)
    if amount == 0:
        await message.answer("❌ Сумма выплаты равна 0. Проверьте количество просмотров.")
        return
    update_user_field(user_id, "payout", user["payout"] + amount)
    update_user_field(user_id, "total_earned", user["total_earned"] + amount)
    log_msg = (
        f"🎬 Начисление за Tik Tok\n"
        f"👤 Пользователь: @{user.get('tg_username', user_id)} (ID: {user_id})\n"
        f"📊 Просмотров: {views}\n"
        f"💰 Сумма: {amount}₽\n"
        f"🕒 Выполнил: @{message.from_user.username} (ID: {message.from_user.id})"
    )
    if LOG_CHANNEL_ID:
        try:
            await message.bot.send_message(LOG_CHANNEL_ID, log_msg)
        except Exception as e:
            logger.warning(f"Не удалось отправить лог Tik Tok: {e}")
    await message.answer(
        f"✅ Выплата за Tik Tok начислена!\n"
        f"Пользователь: @{user.get('tg_username', user_id)}\n"
        f"Просмотров: {views}\n"
        f"Сумма: {amount}₽\n"
        f"Новый баланс к выплате: {user['payout'] + amount}₽"
    )
    log_action(message, f"Начислено {amount}₽ за Tik Tok пользователю {user_id} (просмотров: {views})")


@router.message(Command("stop_tiktok"))
async def cmd_stop_tiktok(message: Message):
    if not is_ga(message.from_user.id):
        return
    try:
        from bot.google_sheets import moscow_tz
        now = datetime.now(moscow_tz)
        date_str = now.strftime("%d.%m.%Y")
        set_setting("tiktok_stop_date", date_str)
        await message.answer(f"✅ Участие в Tik Tok остановлено с {date_str}.\nВсе ролики, опубликованные после этой даты, не будут оплачиваться.")
        log_action(message, f"Установлена дата остановки Tik Tok: {date_str}")
        if LOG_CHANNEL_ID:
            try:
                await message.bot.send_message(
                    LOG_CHANNEL_ID,
                    f"⛔ Tik Tok остановлен с {date_str}. Все новые ролики не оплачиваются."
                )
            except Exception as e:
                logger.warning(f"Не удалось отправить лог: {e}")

        users = get_all_registered_users()
        if users:
            sent = 0
            for user in users:
                try:
                    await message.bot.send_message(
                        user["user_id"],
                        f"⛔ <b>Внимание!</b> Участие в Tik Tok приостановлено с <b>{date_str}</b>.\n"
                        "Все ролики, опубликованные после этой даты, <b>не оплачиваются</b>.\n"
                        "Пожалуйста, будьте внимательны!",
                        parse_mode="HTML"
                    )
                    sent += 1
                    await asyncio.sleep(0.1)
                except:
                    pass
            await message.answer(f"📨 Уведомление отправлено {sent} пользователям.")
        else:
            await message.answer("Нет зарегистрированных пользователей для уведомления.")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


@router.message(Command("start_tiktok"))
async def cmd_start_tiktok(message: Message):
    if not is_ga(message.from_user.id):
        return
    try:
        set_setting("tiktok_stop_date", "")
        await message.answer("✅ Участие в Tik Tok возобновлено.\nТеперь вы можете публиковать ролики и получать выплаты.")
        log_action(message, "Возобновлено участие в Tik Tok")
        if LOG_CHANNEL_ID:
            try:
                await message.bot.send_message(
                    LOG_CHANNEL_ID,
                    "▶️ Tik Tok открыт для публикаций. Все новые ролики оплачиваются."
                )
            except Exception as e:
                logger.warning(f"Не удалось отправить лог: {e}")

        users = get_all_registered_users()
        if users:
            sent = 0
            for user in users:
                try:
                    await message.bot.send_message(
                        user["user_id"],
                        "▶️ <b>Хорошие новости!</b> Участие в Tik Tok возобновлено!\n"
                        "Теперь вы можете публиковать рекламные ролики и получать выплаты.\n"
                        "Удачи в творчестве! 🚀",
                        parse_mode="HTML"
                    )
                    sent += 1
                    await asyncio.sleep(0.1)
                except:
                    pass
            await message.answer(f"📨 Уведомление отправлено {sent} пользователям.")
        else:
            await message.answer("Нет зарегистрированных пользователей для уведомления.")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


@router.message(Command("set_limit"))
async def cmd_set_limit(message: Message):
    if not is_admin_nc(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) < 3:
        await message.answer("❌ Использование: /set_limit <platform> <limit>\n"
                             "Пример: /set_limit яндекс 15")
        return
    platform = parts[1].lower()
    try:
        limit = int(parts[2])
        if limit < 1:
            await message.answer("❌ Лимит должен быть положительным числом.")
            return
        set_limit(platform, limit)
        await message.answer(f"✅ Лимит для платформы '{platform}' установлен на {limit} отзывов за 24 часа.")
        log_action(message, f"Установлен лимит {limit} для платформы {platform}")
    except ValueError:
        await message.answer("❌ Лимит должен быть числом.")


@router.message(Command("user_limit"))
async def cmd_user_limit(message: Message):
    if not is_admin_nc(message.from_user.id):
        await message.answer("⛔ У вас нет доступа.")
        return

    parts = message.text.split()
    if len(parts) < 3:
        await message.answer(
            "❌ Использование:\n"
            "• /user_limit <@username или user_id> <platform> <limit>\n"
            "• /user_limit <@username или user_id> <platform> reset\n"
            "• /user_limit <@username или user_id> reset\n\n"
            "Примеры:\n"
            "• /user_limit @ivan яндекс 20\n"
            "• /user_limit 8635115842 2ГИС 50\n"
            "• /user_limit @ivan яндекс reset\n"
            "• /user_limit @ivan reset"
        )
        return

    target = parts[1]
    user = find_user_by_target(target)
    if not user:
        await message.answer(f"❌ Пользователь '{target}' не найден.")
        return

    uid = user["user_id"]

    if len(parts) == 3 and parts[2].lower() == "reset":
        reset_user_limit(uid)
        await message.answer(
            f"✅ Все персональные лимиты @{user.get('tg_username') or uid} сброшены.\n"
            f"Теперь действуют общие лимиты (по платформам)."
        )
        log_action(message, f"Сброшены все персональные лимиты у {uid}")
        return

    if len(parts) < 4:
        await message.answer("❌ Укажите платформу и значение (или reset).\nПример: /user_limit @ivan яндекс 20")
        return

    platform = parts[2].lower()
    value = parts[3].lower()

    if value == "reset":
        reset_user_limit(uid, platform)
        await message.answer(
            f"✅ Персональный лимит на '{platform}' для @{user.get('tg_username') or uid} сброшен.\n"
            f"Теперь действует общий лимит: {get_limit(platform)} отзывов в день."
        )
        log_action(message, f"Сброшен персональный лимит '{platform}' у {uid}")
        return

    try:
        limit = int(value)
        if limit < 1:
            await message.answer("❌ Лимит должен быть положительным числом.")
            return
    except ValueError:
        await message.answer("❌ Лимит должен быть числом или 'reset'.")
        return

    set_user_limit(uid, platform, limit)
    await message.answer(
        f"✅ Для @{user.get('tg_username') or uid} установлен персональный лимит:\n"
        f"• Платформа: <b>{platform}</b>\n"
        f"• Лимит: <b>{limit} отзывов в день</b>\n\n"
        f"<i>Общий лимит на эту платформу: {get_limit(platform)}</i>",
        parse_mode="HTML"
    )
    log_action(message, f"Установлен персональный лимит {limit} '{platform}' для {uid}")
