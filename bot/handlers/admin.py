from datetime import datetime
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from bot.config import OWNER_ID, LOG_CHANNEL_ID, DB_PATH
from bot.database import (
    get_user, get_user_by_username, toggle_block, update_user_field,
    get_admin_role, set_admin_role, is_owner, is_ga, is_moderator, is_comoderator,
    add_warning, get_warning_count, get_active_warnings, get_setting, set_setting
)
import sqlite3
import logging

logger = logging.getLogger(__name__)
router = Router()

def log_action(message: Message, action: str):
    try:
        text = f"👤 @{message.from_user.username or message.from_user.id} ({message.from_user.id})\n" \
               f"🕒 {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n" \
               f"⚙️ {action}"
        message.bot.send_message(LOG_CHANNEL_ID, text)
    except:
        pass

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

# ---------- Справка ----------
@router.message(Command("helpadm"))
async def cmd_helpadm(message: Message):
    user_id = message.from_user.id
    role = get_admin_role(user_id)
    if not role:
        await message.answer("⛔ У вас нет доступа.")
        return

    text = "🛠 Команды администратора:\n\n"
    if is_owner(user_id):
        text += "👑 /setrole <user_id или username> <owner|ga|moderator|comoderator> — назначить роль\n"
        text += "📊 /payout_report — запросить отчёт по выплатам (пользователи с балансом ≥150₽)\n"
    if is_ga(user_id):
        text += (
            "👤 /userblock <user_id или username> — блокировка/разблокировка\n"
            "💰 /useredit <user_id/username> <поле> <значение> — редактировать данные пользователя\n"
            "ℹ️ /info <username> — профиль пользователя\n"
            "🔄 /update_stats — обновить статистику\n"
            "⚠️ /resetbalance — сбросить балансы у пользователей с payout >= 150\n"
            "🎬 /tiktok_pay <user_id/username> <просмотры> — начислить выплату за Tik Tok\n"
            "⛔ /stop_tiktok — закрыть участие в Tik Tok\n"
            "📨 /smsuser <username> <текст> — отправить сообщение пользователю от администрации\n"
        )
    if is_moderator(user_id) and not is_ga(user_id):
        text += (
            "👤 /userblock <user_id/username> — блокировка/разблокировка\n"
            "ℹ️ /info <username> — профиль пользователя\n"
            "⚠️ /warn <user_id/username> <причина> — предупреждение (с датой снятия)\n"
            "📨 /smsuser <username> <текст> — отправить сообщение пользователю от администрации\n"
        )
    if is_comoderator(user_id) and not is_ga(user_id):
        text += (
            "👤 /userblock <user_id/username> — блокировка/разблокировка\n"
            "ℹ️ /info <username> — профиль пользователя\n"
            "⚠️ /warn <user_id/username> <причина> — предупреждение (с датой снятия)\n"
            "📨 /smsuser <username> <текст> — отправить сообщение пользователю от администрации\n"
        )
    await message.answer(text)

# ---------- /setrole ----------
@router.message(Command("setrole"))
async def set_role(message: Message):
    if not is_owner(message.from_user.id):
        return
    try:
        parts = message.text.split()
        if len(parts) < 3:
            await message.answer("❌ Использование: /setrole <user_id или username> <owner|ga|moderator|comoderator>")
            return
        target = parts[1]
        role = parts[2].lower()
        if role not in ['owner', 'ga', 'moderator', 'comoderator']:
            await message.answer("❌ Неверная роль. Допустимо: owner, ga, moderator, comoderator")
            return
        if target.isdigit():
            user_id = int(target)
        else:
            clean_username = target.lstrip('@')
            user = get_user_by_username(clean_username)
            if not user:
                await message.answer(f"❌ Пользователь с username '{target}' не найден.")
                return
            user_id = user["user_id"]
        set_admin_role(user_id, role)
        await message.answer(f"✅ Роль {role} назначена пользователю {user_id}")
        log_action(message, f"Назначена роль {role} пользователю {user_id}")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

# ---------- /warn (с датой снятия) ----------
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

# ---------- /smsuser ----------
@router.message(Command("smsuser"))
async def sms_user(message: Message):
    if not is_moderator(message.from_user.id):
        return
    try:
        parts = message.text.split(maxsplit=2)
        if len(parts) < 3:
            await message.answer("Использование: /smsuser <username> <текст сообщения>")
            return
        target = parts[1]
        text = parts[2]
        user = get_user_by_username(target)
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

# ---------- /userblock ----------
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
        if target.isdigit():
            user_id = int(target)
        else:
            user = get_user_by_username(target)
            if not user:
                await message.answer("❌ Пользователь не найден.")
                return
            user_id = user["user_id"]
        new_status = toggle_block(user_id)
        if new_status is None:
            await message.answer("❌ Пользователь не найден.")
        else:
            status_text = "заблокирован" if new_status else "разблокирован"
            await message.answer(f"✅ Пользователь {user_id} {status_text}.")
            log_action(message, f"Пользователь {user_id} {status_text}")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

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
    # Предупреждения
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
        f"🕵️ Профиль пользователя @{user.get('tg_username', args[1])}:\n\n"
        f"Имя: {user['name']}\n"
        f"Время от МСК: {user['timezone']}\n"
        f"Город: {user['city']}\n"
        f"С нами уже: {time_str}\n"
        f"К выплате чт: {user['payout']}₽\n"
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
        f"Реквизиты: {user['phone_card']} / {user['bank']}\n"
        f"{warn_text}"
    )
    await message.answer(text)

# ---------- /useredit ----------
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

# ---------- /update_stats ----------
@router.message(Command("update_stats"))
async def cmd_update_stats(message: Message):
    if not is_ga(message.from_user.id):
        return
    await message.answer("⏳ Запускаю обновление статистики...")
    try:
        from bot.google_sheets import update_stats_from_sheet_once
        await update_stats_from_sheet_once()
        await message.answer("✅ Статистика успешно обновлена!")
    except Exception as e:
        logger.error(f"Ошибка в /update_stats: {e}")
        await message.answer(f"❌ Ошибка: {e}")

# ---------- /resetbalance ----------
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
                yandex_passed=0, google_passed=0, gis_passed=0, avito_passed=0, vk_passed=0,
                otzovik_passed=0, doctoru_passed=0, dokdok_passed=0, prodoctors_passed=0,
                doctu_passed=0, top32_passed=0
                WHERE user_id IN ({placeholders})
            """, user_ids)
            conn.commit()
        await message.answer(f"✅ Балансы сброшены у {len(user_ids)} пользователей (у кого было >=150₽).")
        log_action(message, f"Сброшены балансы у {len(user_ids)} пользователей (>=150₽)")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

# ---------- /payout_report ----------
@router.message(Command("payout_report"))
async def cmd_payout_report(message: Message):
    if not is_owner(message.from_user.id):
        return
    try:
        from bot.database import get_all_users_with_payout
        users = get_all_users_with_payout()
        if not users:
            await message.answer("📭 Нет пользователей с балансом >= 150₽.")
            return
        text_lines = ["<b>📋 Список на выплату (по запросу)</b>\n"]
        for u in users:
            username = u.get('tg_username') or u.get('username') or str(u['user_id'])
            phone = u.get('phone_card') or '—'
            bank = u.get('bank') or '—'
            line = f"👤 @{username} (ID: {u['user_id']})\n💰 Сумма: {u['payout']}₽\n📞 {phone}\n🏦 {bank}\n──────────────"
            text_lines.append(line)
        full_text = "\n".join(text_lines)
        max_len = 4000
        from bot.config import REPORT_CHAT_ID, REPORT_THREAD_ID
        for i in range(0, len(full_text), max_len):
            chunk = full_text[i:i+max_len]
            await message.bot.send_message(
                chat_id=REPORT_CHAT_ID,
                text=chunk,
                message_thread_id=REPORT_THREAD_ID or None,
                parse_mode="HTML"
            )
        await message.answer("✅ Отчёт по выплатам отправлен в беседу.")
        log_action(message, "Запрошен отчёт по выплатам (команда /payout_report)")
    except Exception as e:
        await message.answer(f"❌ Ошибка при формировании отчёта: {e}")
        log_action(message, f"Ошибка в /payout_report: {e}")

# ---------- /tiktok_pay ----------
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
    if target.isdigit():
        user_id = int(target)
        user = get_user(user_id)
    else:
        user = get_user_by_username(target)
    if not user:
        await message.answer(f"❌ Пользователь с идентификатором '{target}' не найден.")
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
    await message.bot.send_message(LOG_CHANNEL_ID, log_msg)
    await message.answer(
        f"✅ Выплата за Tik Tok начислена!\n"
        f"Пользователь: @{user.get('tg_username', user_id)}\n"
        f"Просмотров: {views}\n"
        f"Сумма: {amount}₽\n"
        f"Новый баланс к выплате: {user['payout'] + amount}₽"
    )
    log_action(message, f"Начислено {amount}₽ за Tik Tok пользователю {user_id} (просмотров: {views})")

# ---------- /stop_tiktok ----------
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
        await message.bot.send_message(
            LOG_CHANNEL_ID,
            f"⛔ Tik Tok остановлен с {date_str}. Все новые ролики не оплачиваются."
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")
