from datetime import datetime
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from bot.config import ADMIN_IDS, DB_PATH
from bot.database import (
    toggle_block, update_user_field, get_user, get_user_by_username
)
import sqlite3

router = Router()

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

@router.message(Command("helpadm"))
async def cmd_helpadm(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ У вас нет доступа к этой команде.")
        return
    text = (
        "🛠 Команды администратора:\n\n"
        "📢 Публикация слотов:\n"
        "/yandex — Яндекс карты (150₽)\n"
        "/google — GOOGLE (50₽)\n"
        "/gis — 2ГИС (50₽)\n"
        "/avito — Авито (700₽)\n"
        "/vk — ВК (50₽)\n"
        "/otzovik — Отзовик (100₽)\n"
        "/doctoru — Doctoru (100₽)\n\n"
        "📋 Управление слотами:\n"
        "/slots — Показать активные слоты (с ID)\n"
        "/close <ID> — Закрыть слот\n"
        "/closeall — Закрыть все слоты\n\n"
        "👤 Управление пользователями:\n"
        "/userblock <user_id или username> — Заблокировать/разблокировать\n"
        "/useredit <user_id или username> <поле> <значение>\n"
        "Поля: payout, earned, phone, bank, myotz 1/2/3/4/5/6/7 значение\n"
        "/info <username> — Показать профиль пользователя\n"
        "/update_stats — Принудительно обновить статистику из Google Таблиц\n\n"
        "⚠️ Осторожно! Сброс баланса:\n"
        "/resetbalance — Обнулить выплаты и периодические счётчики у ВСЕХ пользователей\n\n"
        "ℹ️ Для пользователей: /help"
    )
    await message.answer(text)

# ---------- /userblock ----------
@router.message(Command("userblock"))
async def user_block(message: Message):
    if not is_admin(message.from_user.id):
        return
    try:
        parts = message.text.split()
        target = parts[1]
        # Пытаемся интерпретировать как число, иначе ищем по username
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

# ---------- /useredit (поддержка username и myotz) ----------
@router.message(Command("useredit"))
async def user_edit(message: Message):
    if not is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) < 4:
        await message.answer(
            "Использование: /useredit <user_id или username> <поле> <значение>\n"
            "Поля: payout, earned, phone, bank, myotz (1-7) (значение)"
        )
        return

    target = parts[1]
    # Определяем user_id
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

    if field == "myotz":
        if len(parts) < 5:
            await message.answer("❌ Укажите номер платформы (1-7) и значение. Пример: /useredit new_chapterr24 myotz 1 5")
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
            7: "doctoru_total"
        }
        if platform_num not in platform_map:
            await message.answer("❌ Номер платформы должен быть от 1 до 7.")
            return
        update_user_field(user_id, platform_map[platform_num], new_value)
        await message.answer(f"✅ Общий счётчик платформы {platform_num} обновлён.")
        return

    if field == "payout":
        update_user_field(user_id, "payout", int(value))
    elif field == "earned":
        update_user_field(user_id, "total_earned", int(value))
    elif field == "phone":
        update_user_field(user_id, "phone_card", value)
    elif field == "bank":
        update_user_field(user_id, "bank", value)
    else:
        await message.answer("Неизвестное поле. Допустимые: payout, earned, phone, bank, myotz")
        return
    await message.answer(f"✅ Данные пользователя {user_id} обновлены.")

# ---------- /resetbalance ----------
@router.message(Command("resetbalance"))
async def reset_balance(message: Message):
    if not is_admin(message.from_user.id):
        return
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE users SET "
                "payout = 0, "
                "yandex_passed = 0, google_passed = 0, gis_passed = 0, "
                "avito_passed = 0, vk_passed = 0, otzovik_passed = 0, doctoru_passed = 0"
            )
            conn.commit()
        await message.answer("✅ Периодические счётчики и «к выплате» сброшены. Общие счётчики и заработано за всё время сохранены.")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

# ---------- /info <username> ----------
@router.message(Command("info"))
async def cmd_info(message: Message):
    if not is_admin(message.from_user.id):
        return
    args = message.text.split()
    if len(args) < 2:
        await message.answer("❌ Использование: /info <username>")
        return
    username = args[1]
    user = get_user_by_username(username)
    if not user:
        await message.answer(f"❌ Пользователь с username '{username}' не найден.")
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
        y = user.get("yandex_passed", 0) or 0
        g = user.get("google_passed", 0) or 0
        gi = user.get("gis_passed", 0) or 0
        if y >= 10 and (g + gi) >= 15:
            ref_status = "выполнено"
        else:
            ref_status = "в процессе"

    text = (
        f"🕵️ Профиль пользователя @{user.get('tg_username', username)}:\n\n"
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
        f"Doctoru: {user['doctoru_passed']}\n\n"
        f"Рефералка: {ref if ref != '0' else 'нет'} ({ref_status})\n"
        f"Реквизиты: {user['phone_card']} / {user['bank']}"
    )
    await message.answer(text)

# ---------- /update_stats ----------
@router.message(Command("update_stats"))
async def cmd_update_stats(message: Message):
    if not is_admin(message.from_user.id):
        return
    from bot.google_sheets import update_stats_from_sheet_once
    await message.answer("⏳ Запускаю обновление статистики из Google Таблицы...")
    try:
        await update_stats_from_sheet_once()
        await message.answer("✅ Статистика успешно обновлена! Проверьте профили.")
    except Exception as e:
        await message.answer(f"❌ Ошибка при обновлении: {e}")

# ---------- Остальные админские команды (/slots, /close, /closeall) должны быть здесь же (они есть в вашем admin.py) ----------
# Если они отсутствуют, скопируйте их из предыдущего полного файла slots.py (они висят на router'е slots, но можно оставить там)
