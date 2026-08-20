from datetime import datetime
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from bot.config import OWNER_ID, LOG_CHANNEL_ID, DB_PATH
from bot.database import (
    get_user, get_user_by_username, toggle_block, update_user_field,
    get_admin_role, set_admin_role, is_owner, is_ga, is_moderator, is_comoderator,
    add_warning, get_warning_count
)
import sqlite3

router = Router()

def log_action(message: Message, action: str):
    try:
        text = f"👤 @{message.from_user.username or message.from_user.id} ({message.from_user.id})\n" \
               f"🕒 {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n" \
               f"⚙️ {action}"
        message.bot.send_message(LOG_CHANNEL_ID, text)
    except:
        pass

# ---------- Справка в зависимости от роли ----------
@router.message(Command("helpadm"))
async def cmd_helpadm(message: Message):
    user_id = message.from_user.id
    role = get_admin_role(user_id)
    if not role:
        await message.answer("⛔ У вас нет доступа.")
        return

    text = "🛠 Команды администратора:\n\n"
    if is_owner(user_id):
        text += "👑 /setrole <user_id> <owner|ga|moderator|comoderator> — назначить роль\n"
    if is_ga(user_id):
        text += (
            "📢 Публикация слотов:\n"
            "/yandex, /google, /gis, /avito, /vk, /otzovik, /doctoru, /dokdok, /prodoctors, /doctu, /32top\n"
            "📋 /slots — активные слоты\n"
            "🔒 /close <ID> — закрыть слот\n"
            "🔒 /closeall — закрыть все слоты\n"
            "👤 /userblock <user_id/username> — блокировка\n"
            "💰 /useredit <...> — изменить payout, earned, phone, bank, myotz 1-11\n"
            "ℹ️ /info <username> — профиль пользователя\n"
            "🔄 /update_stats — обновить статистику\n"
            "⚠️ /resetbalance — сбросить выплаты\n"
        )
    if is_moderator(user_id):
        text += (
            "/slots, /info <username>, /userblock <user_id/username>\n"
            "/warn <user_id/username> <причина> — предупреждение\n"
        )
    if is_comoderator(user_id):
        text += (
            "/slots, /info <username>, /userblock <user_id/username>\n"
            "/warn <user_id/username> <причина> — предупреждение\n"
        )
    await message.answer(text)

# ---------- /setrole (только владелец) ----------
@router.message(Command("setrole"))
async def set_role(message: Message):
    if not is_owner(message.from_user.id):
        return
    try:
        parts = message.text.split()
        target_id = int(parts[1])
        role = parts[2].lower()
        if role not in ['owner', 'ga', 'moderator', 'comoderator']:
            await message.answer("❌ Неверная роль. Допустимо: owner, ga, moderator, comoderator")
            return
        set_admin_role(target_id, role)
        await message.answer(f"✅ Роль {role} назначена пользователю {target_id}")
        log_action(message, f"Назначена роль {role} пользователю {target_id}")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

# ---------- /warn (модератор и выше) ----------
@router.message(Command("warn"))
async def warn_user(message: Message):
    if not is_moderator(message.from_user.id):
        return
    try:
        parts = message.text.split(maxsplit=2)
        if len(parts) < 3:
            await message.answer("Использование: /warn <user_id или username> <причина>")
            return
        target = parts[1]
        reason = parts[2]
        if target.isdigit():
            user = get_user(int(target))
        else:
            user = get_user_by_username(target)
        if not user:
            await message.answer("❌ Пользователь не найден")
            return

        add_warning(user["user_id"], reason, message.from_user.id)
        warn_count = get_warning_count(user["user_id"])
        if warn_count >= 3:
            toggle_block(user["user_id"])
            await message.answer(f"✅ Пользователь @{user.get('username') or user['user_id']} получил третье предупреждение и заблокирован.")
            try:
                await message.bot.send_message(user["user_id"], f"⛔ Вы получили третье предупреждение и заблокированы.\nПричина: {reason}")
            except:
                pass
        else:
            await message.answer(f"✅ Предупреждение ({warn_count}/3) отправлено пользователю @{user.get('username') or user['user_id']}.")
            try:
                await message.bot.send_message(user["user_id"], f"⚠️ Предупреждение ({warn_count}/3): {reason}")
            except:
                pass
        log_action(message, f"Выдано предупреждение {warn_count}/3 пользователю {user['user_id']}")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

# ---------- /slots, /close, /closeall ----------
@router.message(Command("slots"))
async def list_slots(message: Message):
    if not is_moderator(message.from_user.id):
        return
    from bot.handlers.slots import active_slots
    if not active_slots:
        await message.answer("Нет активных слотов.")
        return
    lines = ["Активные слоты (ID):"]
    for msg_id, data in active_slots.items():
        lines.append(f"🔸 {data.get('command', data.get('platform', '?'))} {data.get('price', data.get('count', '?'))} — ID: {msg_id}")
    await message.answer("\n".join(lines))

@router.message(Command("close"))
async def close_slot(message: Message):
    if not is_moderator(message.from_user.id):
        return
    try:
        _, slot_id = message.text.split()
        slot_id = int(slot_id)
    except:
        await message.answer("Использование: /close <ID>")
        return
    from bot.handlers.slots import active_slots, CHANNEL_ID
    if slot_id not in active_slots:
        await message.answer("❌ Слот не найден.")
        return
    data = active_slots.pop(slot_id)
    await message.bot.edit_message_text(
        chat_id=CHANNEL_ID, message_id=slot_id,
        text="Извините, данный слот устарел или был закрыт…"
    )
    await message.answer(f"✅ Слот «{data.get('command', data.get('platform', '?'))}» закрыт.")
    log_action(message, f"Закрыт слот {slot_id}")

@router.message(Command("closeall"))
async def close_all_slots(message: Message):
    if not is_moderator(message.from_user.id):
        return
    from bot.handlers.slots import active_slots, CHANNEL_ID
    for slot_id in list(active_slots.keys()):
        try:
            await message.bot.edit_message_text(
                chat_id=CHANNEL_ID, message_id=slot_id,
                text="Извините, данный слот устарел или был закрыт…"
            )
        except:
            pass
        del active_slots[slot_id]
    await message.answer("✅ Все слоты закрыты.")
    log_action(message, "Закрыты все слоты")

# ---------- /userblock ----------
@router.message(Command("userblock"))
async def user_block(message: Message):
    if not is_moderator(message.from_user.id):
        return
    try:
        parts = message.text.split()
        target = parts[1]
        if target.isdigit():
            user_id = int(target)
        else:
            user = get_user_by_username(target)
            if not user:
                await message.answer("❌ Пользователь не найден.")
                return
            user_id = user["user_id"]
    except:
        await message.answer("Использование: /userblock <user_id или username>")
        return
    new_status = toggle_block(user_id)
    if new_status is None:
        await message.answer("❌ Пользователь не найден.")
    else:
        status_text = "заблокирован" if new_status else "разблокирован"
        await message.answer(f"✅ Пользователь {user_id} {status_text}.")
        log_action(message, f"Пользователь {user_id} {status_text}")

# ---------- /info ----------
@router.message(Command("info"))
async def cmd_info(message: Message):
    if not is_moderator(message.from_user.id):
        return
    args = message.text.split()
    if len(args) < 2:
        await message.answer("❌ Использование: /info <username>")
        return
    user = get_user_by_username(args[1])
    if not user:
        await message.answer(f"❌ Пользователь с username '{args[1]}' не найден.")
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
    text = (
        f"🕵️ Профиль пользователя @{user.get('tg_username', args[1])}:\n\n"
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
        f"Doctoru: {user['doctoru_passed']}\n"
        f"ДокДок: {user['dokdok_passed']}\n"
        f"Про Докторов: {user['prodoctors_passed']}\n"
        f"ДокТу: {user['doctu_passed']}\n"
        f"32ТОП: {user['top32_passed']}\n\n"
        f"Рефералка: {ref if ref != '0' else 'нет'} ({ref_status})\n"
        f"Реквизиты: {user['phone_card']} / {user['bank']}"
    )
    await message.answer(text)

# ---------- /useredit (ГА и владелец) ----------
@router.message(Command("useredit"))
async def user_edit(message: Message):
    if not is_ga(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) < 4:
        await message.answer("Использование: /useredit <user_id/username> <поле> <значение>\nПоля: payout, earned, phone, bank, myotz 1-11")
        return
    target = parts[1]
    if target.isdigit():
        user_id = int(target)
    else:
        user = get_user_by_username(target)
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
            await message.answer("❌ Укажите номер платформы (1-11) и значение.")
            return
        platform_num = int(parts[3])
        new_value = int(parts[4])
        platform_map = {
            1: "yandex_total",
            2: "google_total",
            3: "gis_total",
            4: "avito_total",
            5: "vk_total",
            6: "otzovik_total",
            7: "doctoru_total",
            8: "dokdok_total",
            9: "prodoctors_total",
            10: "doctu_total",
            11: "top32_total"
        }
        if platform_num not in platform_map:
            await message.answer("❌ Номер платформы от 1 до 11.")
            return
        update_user_field(user_id, platform_map[platform_num], new_value)
        await message.answer(f"✅ Общий счётчик платформы {platform_num} обновлён.")
        return
    else:
        await message.answer("Неизвестное поле.")
        return
    await message.answer(f"✅ Данные пользователя {user_id} обновлены.")
    log_action(message, f"Изменены данные пользователя {user_id}: {field}={value}")

# ---------- /update_stats (ГА и владелец) ----------
@router.message(Command("update_stats"))
async def cmd_update_stats(message: Message):
    if not is_ga(message.from_user.id):
        return
    from bot.google_sheets import update_stats_from_sheet_once
    await message.answer("⏳ Запускаю обновление статистики...")
    try:
        await update_stats_from_sheet_once()
        await message.answer("✅ Статистика успешно обновлена!")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

# ---------- /resetbalance (ГА и владелец) ----------
@router.message(Command("resetbalance"))
async def reset_balance(message: Message):
    if not is_ga(message.from_user.id):
        return
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE users SET payout = 0,
                yandex_passed=0, google_passed=0, gis_passed=0, avito_passed=0, vk_passed=0,
                otzovik_passed=0, doctoru_passed=0, dokdok_passed=0, prodoctors_passed=0,
                doctu_passed=0, top32_passed=0
            """)
            conn.commit()
        await message.answer("✅ Периодические счётчики и «к выплате» сброшены.")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")
