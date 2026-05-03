from datetime import datetime
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from bot.config import ADMIN_IDS, CHANNEL_ID, MANAGER_USERNAME, OTHER_JOBS_CHANNEL, DB_PATH
from bot.database import toggle_block, update_user_field, get_user, get_user_by_username
from bot.keyboards.reply import main_menu_keyboard
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
        "/userblock <user_id> — Заблокировать/разблокировать\n"
        "/useredit <user_id> <поле> <значение>\n"
        "Поля: payout, earned, phone, bank, myotz 1/2/3/4/5/6/7 значение\n"
        "/info <username> — Показать профиль пользователя\n"
        "/update_stats — Принудительно обновить статистику из Google Таблиц\n\n"
        "⚠️ Осторожно! Сброс баланса:\n"
        "/resetbalance — Обнулить выплаты и периодические счётчики у ВСЕХ пользователей\n\n"
        "ℹ️ Для пользователей: /help"
    )
    await message.answer(text)

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

# ---------- /useredit ----------
@router.message(Command("useredit"))
async def user_edit(message: Message):
    if not is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) < 4:
        await message.answer(
            "Использование: /useredit <user_id> <поле> <значение>\n"
            "Поля: payout, earned, phone, bank, myotz (1-7) (значение)"
        )
        return
    try:
        user_id = int(parts[1])
    except:
        await message.answer("❌ Неверный user_id.")
        return

    field = parts[2].lower()
    value = parts[3]

    if field == "myotz":
        if len(parts) < 5:
            await message.answer("❌ Укажите номер платформы (1-7) и значение. Пример: /useredit 123456 myotz 1 10")
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
        await message.answer("Неизвестное поле.")
        return
    await message.answer(f"✅ Данные пользователя {user_id} обновлены.")

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

# Остальные админские команды (/userblock, /slots, /close, /closeall) оставьте без изменений (они уже есть в вашем admin.py)
