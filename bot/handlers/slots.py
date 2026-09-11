import logging, os, secrets, time, asyncio
from urllib.parse import quote
from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode
from bot.config import ADMIN_IDS, CHANNEL_ID, MANAGER_USERNAME, OTHER_JOBS_CHANNEL, SHEET_ID, SCREENSHOT_CHANNEL_ID, get_credentials_path, INSTRUCTION_PHOTO_ID, INSTRUCTION_PHOTO_PATH
from bot.database import is_registered, is_blocked, get_user, is_ga, is_moderator, get_user_by_username, add_review_take, count_review_takes_last_24h, get_limit
from bot.google_sheets import get_credentials
from bot.helpers import get_column_mapping, platform_from_sheet_name
from bot.state import active_slots, slot_requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pytz

router = Router()
logger = logging.getLogger(__name__)
moscow_tz = pytz.timezone("Europe/Moscow")

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

def get_sheet():
    path = get_credentials_path()
    if not os.path.exists(path):
        logger.error(f"Файл ключа не найден: {path}")
        return None
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(path, scope)
    client = gspread.authorize(creds)
    return client.open_by_key(SHEET_ID).sheet1

MESSAGE_TEMPLATE = (
    "Здравствуйте, меня интересует слот {slot_name} ({price}). "
    "Обязуюсь отправить скриншот/ы до 23:59 МСК, с правилами ознакомлен."
)

PLATFORM_TEMPLATES = {
    "яндекс": {
        "instruction": (
            "<b>⚠️ ПРИМЕР КАК ДОЛЖЕН ВЫГЛЯДЕТЬ СКРИНШОТ КОТОРЫЙ Я БУДУ ОТ ВАС ЖДАТЬ!</b>\n"
            "Скриншот в другом формате считается выполненным не по ТЗ и отзыв не будет оплачен, пожалуйста, будьте внимательны!"
        ),
        "extra_text": (
            "Чтобы повысить шанс прохода отзыва, рекомендуем просмотреть 5-10 фотографий и посидеть на карточке 1-2 минуты.\n"
            "Так же для повышения прохода можно переписать отзыв от руки, это значительно повысит шанс прохода и Вашу прибыль."
        ),
        "warning": (
            "<i>⚠️ Если не выполнить все взятые вами задачи до 23:30 и не успеть от них отказаться, "
            "все вами выполненное будет оплачено на 30% ниже!</i>"
        )
    },
    "google": {
        "instruction": (
            "<b>⚠️ ПРИМЕР КАК ДОЛЖЕН ВЫГЛЯДЕТЬ СКРИНШОТ КОТОРЫЙ Я БУДУ ОТ ВАС ЖДАТЬ!</b>\n"
            "Скриншот в другом формате считается выполненным не по ТЗ и отзыв не будет оплачен, пожалуйста, будьте внимательны!"
        ),
        "extra_text": (
            "Чтобы повысить шанс прохода отзыва, рекомендуем просмотреть 5-10 фотографий и посидеть на карточке 1-2 минуты.\n"
            "Так же для повышения прохода можно переписать отзыв от руки, это значительно повысит шанс прохода и Вашу прибыль."
        ),
        "warning": (
            "<i>⚠️ Если не выполнить все взятые вами задачи до 23:30 и не успеть от них отказаться, "
            "все вами выполненное будет оплачено на 30% ниже!</i>"
        )
    },
    "2гис": {
        "instruction": (
            "<b>⚠️ ПРИМЕР КАК ДОЛЖЕН ВЫГЛЯДЕТЬ СКРИНШОТ КОТОРЫЙ Я БУДУ ОТ ВАС ЖДАТЬ!</b>\n"
            "Скриншот в другом формате считается выполненным не по ТЗ и отзыв не будет оплачен, пожалуйста, будьте внимательны!"
        ),
        "extra_text": (
            "Чтобы повысить шанс прохода отзыва, рекомендуем просмотреть 5-10 фотографий и посидеть на карточке 1-2 минуты.\n"
            "Так же для повышения прохода можно переписать отзыв от руки, это значительно повысит шанс прохода и Вашу прибыль."
        ),
        "warning": (
            "<i>⚠️ Если не выполнить все взятые вами задачи до 23:30 и не успеть от них отказаться, "
            "все вами выполненное будет оплачено на 30% ниже!</i>"
        )
    },
    "вк": {
        "instruction": (
            "<b>⚠️ ПРИМЕР КАК ДОЛЖЕН ВЫГЛЯДЕТЬ СКРИНШОТ КОТОРЫЙ Я БУДУ ОТ ВАС ЖДАТЬ!</b>\n"
            "Скриншот в другом формате считается выполненным не по ТЗ и отзыв не будет оплачен, пожалуйста, будьте внимательны!"
        ),
        "extra_text": (
            "<b>- На данной платформе обязательно перепишите текст от руки, иначе отзыв может просто заблокироваться.</b>\n"
            "ДЛЯ 90% прохода:\n"
            "Оставьте отзыв несколько раз 3-4 раза, в этом случае он точно опубликуется, оставили 1 раз с другого устройства проверили появился ли он, если нет оставляете еще раз и так 3-4 раза."
        ),
        "warning": (
            "<i>⚠️ Если не выполнить все взятые вами задачи до 23:30 и не успеть от них отказаться, "
            "все вами выполненное будет оплачено на 30% ниже!</i>"
        )
    },
    "докдок": {
        "instruction": (
            "<b>⚠️ ПРИМЕР КАК ДОЛЖЕН ВЫГЛЯДЕТЬ СКРИНШОТ КОТОРЫЙ Я БУДУ ОТ ВАС ЖДАТЬ!</b>\n"
            "Скриншот в другом формате считается выполненным не по ТЗ и отзыв не будет оплачен, пожалуйста, будьте внимательны!"
        ),
        "extra_text": "",
        "warning": (
            "<i>⚠️ Если не выполнить все взятые вами задачи до 23:30 и не успеть от них отказаться, "
            "все вами выполненное будет оплачено на 30% ниже!</i>"
        )
    },
    "докту": {
        "instruction": (
            "<b>⚠️ ПРИМЕР КАК ДОЛЖЕН ВЫГЛЯДЕТЬ СКРИНШОТ КОТОРЫЙ Я БУДУ ОТ ВАС ЖДАТЬ!</b>\n"
            "Скриншот в другом формате считается выполненным не по ТЗ и отзыв не будет оплачен, пожалуйста, будьте внимательны!"
        ),
        "extra_text": "",
        "warning": (
            "<i>⚠️ Если не выполнить все взятые вами задачи до 23:30 и не успеть от них отказаться, "
            "все вами выполненное будет оплачено на 30% ниже!</i>"
        )
    },
    "32топ": {
        "instruction": (
            "<b>⚠️ ПРИМЕР КАК ДОЛЖЕН ВЫГЛЯДЕТЬ СКРИНШОТ КОТОРЫЙ Я БУДУ ОТ ВАС ЖДАТЬ!</b>\n"
            "Скриншот в другом формате считается выполненным не по ТЗ и отзыв не будет оплачен, пожалуйста, будьте внимательны!"
        ),
        "extra_text": "",
        "warning": (
            "<i>⚠️ Если не выполнить все взятые вами задачи до 23:30 и не успеть от них отказаться, "
            "все вами выполненное будет оплачено на 30% ниже!</i>"
        )
    },
    "авито": {
        "instruction": (
            "<b>⚠️ ПРИМЕР КАК ДОЛЖЕН ВЫГЛЯДЕТЬ СКРИНШОТ КОТОРЫЙ Я БУДУ ОТ ВАС ЖДАТЬ!</b>\n"
            "Скриншот в другом формате считается выполненным не по ТЗ и отзыв не будет оплачен, пожалуйста, будьте внимательны!"
        ),
        "extra_text": "",
        "warning": (
            "<i>⚠️ Если не выполнить все взятые вами задачи до 23:30 и не успеть от них отказаться, "
            "все вами выполненное будет оплачено на 30% ниже!</i>"
        )
    },
    "zoon": {
        "instruction": (
            "<b>⚠️ ПРИМЕР КАК ДОЛЖЕН ВЫГЛЯДЕТЬ СКРИНШОТ КОТОРЫЙ Я БУДУ ОТ ВАС ЖДАТЬ!</b>\n"
            "Скриншот в другом формате считается выполненным не по ТЗ и отзыв не будет оплачен, пожалуйста, будьте внимательны!"
        ),
        "extra_text": "",
        "warning": (
            "<i>⚠️ Если не выполнить все взятые вами задачи до 23:30 и не успеть от них отказаться, "
            "все вами выполненное будет оплачено на 30% ниже!</i>"
        )
    },
}

async def send_instruction(user_id: int, bot):
    try:
        caption = (
            "📸 Инструкция по отправке скриншотов:\n\n"
            "1. Сделайте скриншот экрана с опубликованным отзывом.\n"
            "2. Убедитесь, что видна платформа, текст и время публикации.\n"
            "3. Скриншот должен быть сделан в приложении (не в браузере), иначе шанс проходимости снижается, есть риск удаления отзыва.\n"
            "4. Отправьте скриншот в этот чат.\n"
            "5. Если скриншот не соответствует требованиям, отзыв НЕ БУДЕТ ОПЛАЧЕН."
        )
        if INSTRUCTION_PHOTO_ID:
            await bot.send_photo(chat_id=user_id, photo=INSTRUCTION_PHOTO_ID, caption=caption)
        elif INSTRUCTION_PHOTO_PATH and os.path.exists(INSTRUCTION_PHOTO_PATH):
            with open(INSTRUCTION_PHOTO_PATH, 'rb') as photo:
                await bot.send_photo(chat_id=user_id, photo=photo, caption=caption)
        else:
            await bot.send_message(chat_id=user_id, text=caption)
    except Exception as e:
        logger.error(f"Ошибка отправки инструкции: {e}")

async def check_limit(user_id: int, platform: str) -> bool:
    limit = get_limit(platform)
    count = count_review_takes_last_24h(user_id, platform)
    return count < limit


# ============ КОМАНДА /cancel ============
@router.message(Command("cancel"))
@router.message(Command("отказ"))
async def cancel_task(message: Message):
    user_id = message.from_user.id
    if user_id not in slot_requests:
        await message.answer("❌ У вас нет активного задания.")
        return

    request = slot_requests[user_id]
    completed = request.get("completed_reviews", [])
    ordered_reviews = request.get("ordered_reviews", [])
    remaining_rows = [row_idx for row_idx, num in ordered_reviews if num not in completed]

    if not remaining_rows:
        await message.answer("✅ У вас нет невыполненных отзывов для отмены.")
        del slot_requests[user_id]
        return

    platform = request.get("platform", "неизвестно")
    mapping = request.get("mapping", get_column_mapping(platform))
    sheet_title = request.get("sheet_title")

    logger.info(f"🔄 Отмена: {user_id}, платформа {platform}, невыполненных: {len(remaining_rows)}")

    creds = get_credentials()
    if creds:
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key(SHEET_ID)

        sheet = None
        if sheet_title:
            try:
                sheet = spreadsheet.worksheet(sheet_title)
            except:
                pass
        if sheet is None:
            for s in spreadsheet.worksheets():
                try:
                    s.cell(remaining_rows[0], 1)
                    sheet = s
                    break
                except:
                    continue

        if sheet:
            batch_data = []
            for row_idx in remaining_rows:
                col_status = chr(64 + mapping["status_col"])
                batch_data.append({"range": f"{col_status}{row_idx}", "values": [["не принят в работу"]]})
                col_exec = chr(64 + mapping["executor_col"])
                batch_data.append({"range": f"{col_exec}{row_idx}", "values": [[""]]})
                col_o = chr(64 + mapping["flag_third_col"])
                batch_data.append({"range": f"{col_o}{row_idx}", "values": [[0]]})
                col_p = chr(64 + mapping["flag_second_col"])
                batch_data.append({"range": f"{col_p}{row_idx}", "values": [[0]]})
                col_q = chr(64 + mapping["flag_first_col"])
                batch_data.append({"range": f"{col_q}{row_idx}", "values": [[0]]})
                col_s = chr(64 + mapping["id_col"])
                batch_data.append({"range": f"{col_s}{row_idx}", "values": [[""]]})
                col_t = chr(64 + mapping["order_col"])
                batch_data.append({"range": f"{col_t}{row_idx}", "values": [[""]]})

            try:
                for i in range(0, len(batch_data), 50):
                    chunk = batch_data[i:i+50]
                    sheet.batch_update(chunk)
                    await asyncio.sleep(0.5)
                logger.info(f"✅ Все {len(remaining_rows)} строк очищены")
            except Exception as e:
                logger.error(f"❌ Ошибка пакетной очистки: {e}")

    del slot_requests[user_id]
    await message.answer(
        f"✅ Отказ принят.\n\n"
        f"• Выполненные: {len(completed)} – на модерацию\n"
        f"• Невыполненные: {len(remaining_rows)} – переопубликуются"
    )


# ============ КОМАНДА /resume ============
@router.message(Command("resume"))
@router.message(Command("слот"))
async def cmd_resume(message: Message):
    user_id = message.from_user.id
    if not is_registered(user_id):
        await message.answer("❌ Вы не зарегистрированы.")
        return
    if is_blocked(user_id):
        await message.answer("⛔ Вы заблокированы.")
        return

    if user_id in slot_requests:
        request = slot_requests[user_id]
        total = len(request.get("ordered_reviews", []))
        completed = len(request.get("completed_reviews", []))
        await message.answer(
            f"✅ У вас уже есть активный слот: {request['platform']}.\n"
            f"Осталось: {total - completed}",
            reply_markup=InlineKeyboardBuilder().button(
                text="🎯 Активный слот",
                callback_data=f"active_slot|{user_id}"
            ).as_markup()
        )
        return

    user = get_user(user_id)
    if not user or not user.get("tg_username"):
        await message.answer("❌ У вас не указан Telegram username.")
        return

    username = f"@{user['tg_username']}"

    creds = get_credentials()
    if not creds:
        await message.answer("❌ Ошибка доступа к таблице.")
        return

    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(SHEET_ID)

    found_rows = []
    for sheet in spreadsheet.worksheets():
        sheet_name = sheet.title
        platform = platform_from_sheet_name(sheet_name)
        if not platform:
            continue
        mapping = get_column_mapping(platform)
        records = sheet.get_all_values()
        if len(records) < 2:
            continue

        for row_idx, row in enumerate(records[1:], start=2):
            if len(row) < max(mapping["status_col"], mapping["executor_col"]):
                continue
            status = row[mapping["status_col"]-1].strip().lower()
            executor = row[mapping["executor_col"]-1].strip().lower()
            if status == "в работе" and executor == username.lower():
                found_rows.append({
                    "platform": platform,
                    "sheet_title": sheet_name,
                    "row_idx": row_idx,
                    "mapping": mapping
                })

    if not found_rows:
        await message.answer("❌ У вас нет активных слотов.")
        return

    platform = found_rows[0]["platform"]
    sheet_title = found_rows[0]["sheet_title"]
    mapping = found_rows[0]["mapping"]
    row_ids = [r["row_idx"] for r in found_rows if r["platform"] == platform]
    ordered_reviews = [(row_idx, idx) for idx, row_idx in enumerate(row_ids, start=1)]

    slot_requests[user_id] = {
        "platform": platform,
        "count": len(row_ids),
        "date": None, "time": None,
        "slot_msg_id": "resume",
        "state": "slot_selection",
        "assigned_rows": row_ids,
        "current_index": 0,
        "row_ids": [],
        "from_menu": False,
        "mapping": mapping,
        "sheet_title": sheet_title,
        "ordered_reviews": ordered_reviews,
        "completed_reviews": [],
        "active_review_row": None,
        "extra_messages": []
    }

    await message.answer(
        f"✅ Сессия восстановлена!\n\n"
        f"📋 Платформа: {platform}\n"
        f"📊 Отзывов: {len(row_ids)}",
        reply_markup=InlineKeyboardBuilder().button(
            text="🎯 Активный слот",
            callback_data=f"active_slot|{user_id}"
        ).as_markup()
    )


# ============ ОБРАБОТКА ВВОДА КОЛИЧЕСТВА ============
@router.message(F.text)
async def handle_quantity_input(message: Message):
    if message.text and message.text.startswith('/'):
        return

    user_id = message.from_user.id
    if user_id not in slot_requests:
        return
    request = slot_requests[user_id]
    if request["state"] != "waiting_quantity":
        return

    try:
        quantity = int(message.text.strip())
    except:
        await message.answer("Пожалуйста, введите число.")
        return

    if quantity <= 0 or quantity > request["count"]:
        await message.answer(f"❌ Можно взять от 1 до {request['count']} отзывов.")
        return

    platform = request["platform"]
    mapping = request["mapping"]
    sheet_title = request.get("sheet_title")

    creds = get_credentials()
    if not creds:
        await message.answer("❌ Ошибка доступа к таблице.")
        del slot_requests[user_id]
        return

    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(SHEET_ID)

    slot_msg_id = request["slot_msg_id"]
    slot_info = active_slots.get(slot_msg_id)

    # ФИКС: если слот потерян (после перезапуска) — восстанавливаем
    if not slot_info:
        logger.warning(f"⚠️ Слот {slot_msg_id} не найден, используем данные request")
        row_ids = request.get("row_ids", [])
        if not row_ids:
            await message.answer("❌ Не удалось получить список отзывов. Попробуйте заново через /resume.")
            del slot_requests[user_id]
            return
        slot_info = {
            "row_ids": row_ids,
            "count": len(row_ids),
            "mapping": mapping,
            "sheet_title": sheet_title,
            "platform": platform
        }

    row_ids = slot_info["row_ids"]
    if len(row_ids) < quantity:
        await message.answer("❌ Количество свободных отзывов изменилось. Попробуйте заново.")
        del slot_requests[user_id]
        return

    assigned_rows = row_ids[:quantity]
    slot_info["row_ids"] = row_ids[quantity:]
    slot_info["count"] = len(slot_info["row_ids"])

    if slot_info["count"] == 0 and slot_msg_id in active_slots:
        del active_slots[slot_msg_id]
        try:
            await message.bot.edit_message_text(
                chat_id=CHANNEL_ID, message_id=slot_msg_id,
                text="Все отзывы этого слота разобраны."
            )
        except:
            pass

    sheet = None
    if sheet_title:
        try:
            sheet = spreadsheet.worksheet(sheet_title)
        except:
            pass
    if sheet is None:
        for s in spreadsheet.worksheets():
            try:
                s.cell(assigned_rows[0], 1)
                sheet = s
                break
            except:
                continue

    if sheet is None:
        await message.answer("❌ Не удалось найти лист.")
        del slot_requests[user_id]
        return

    # ЗАПИСЬ K (username) и J (в работе)
    username = f"@{message.from_user.username}" if message.from_user.username else message.from_user.full_name
    logger.info(f"📝 Записываем @{message.from_user.username} в K (столбец {mapping['executor_col']}), строки: {assigned_rows}")

    for row_idx in assigned_rows:
        try:
            sheet.update_cell(row_idx, mapping["status_col"], "в работе")
            sheet.update_cell(row_idx, mapping["executor_col"], username)
            logger.info(f"✅ Строка {row_idx}: K={username}, J='в работе'")
            time.sleep(0.2)
        except Exception as e:
            logger.error(f"❌ Ошибка обновления строки {row_idx}: {e}")

    for idx, row_idx in enumerate(assigned_rows, start=1):
        try:
            sheet.update_cell(row_idx, mapping["order_col"], idx)
        except Exception as e:
            logger.error(f"Не удалось записать номер: {e}")

    ordered_reviews = [(row_idx, idx) for idx, row_idx in enumerate(assigned_rows, start=1)]
    request["ordered_reviews"] = ordered_reviews
    request["completed_reviews"] = []
    request["active_review_row"] = None
    request["state"] = "slot_selection"
    request["assigned_rows"] = assigned_rows
    request["extra_messages"] = []

    for _ in range(quantity):
        add_review_take(user_id, platform)

    await message.answer(
        f"🎯 Вы взяли {quantity} отзывов на платформе {platform}.\n"
        "Нажмите «Активный слот», чтобы приступить.",
        reply_markup=InlineKeyboardBuilder().button(
            text="🎯 Активный слот",
            callback_data=f"active_slot|{user_id}"
        ).as_markup()
    )


@router.callback_query(F.data.startswith("take_slot|"))
async def take_slot_start(callback: CallbackQuery):
    try:
        await callback.answer()
    except Exception:
        pass

    user_id = callback.from_user.id
    if not is_registered(user_id):
        await callback.bot.send_message(user_id, "❌ Вы не зарегистрированы.")
        return
    if is_blocked(user_id):
        await callback.bot.send_message(user_id, "⛔ Вы заблокированы.")
        return

    if user_id in slot_requests:
        active_platform = slot_requests[user_id]["platform"]
        await callback.bot.send_message(
            user_id,
            f"❌ У вас уже есть активный слот: {active_platform}.\n"
            "Закончите его или отправьте /cancel."
        )
        return

    parts = callback.data.split("|")
    if len(parts) < 5:
        await callback.bot.send_message(user_id, "Некорректный запрос.")
        return

    _, platform, count_str, date, time_safe = parts
    try:
        count = int(count_str)
    except:
        await callback.bot.send_message(user_id, "Некорректное количество.")
        return

    time = time_safe.replace('-', ':')
    slot_msg_id = callback.message.message_id
    slot_info = active_slots.get(slot_msg_id)

    if not slot_info:
        # Ищем любой активный слот этой платформы
        platform_slots = [
            (mid, s) for mid, s in active_slots.items()
            if s.get("platform") == platform and s.get("count", 0) > 0
        ]
        if platform_slots:
            slot_msg_id, slot_info = platform_slots[0]
        else:
            await callback.bot.send_message(
                user_id,
                "❌ Слот не найден.\n\n"
                "Если вы уже брали отзывы — отправьте /resume."
            )
            return

    if not await check_limit(user_id, platform):
        limit = get_limit(platform)
        await callback.bot.send_message(user_id, f"❌ Лимит на {platform}: {limit} за 24ч.")
        return

    slot_requests[user_id] = {
        "platform": platform,
        "count": slot_info.get("count", count),
        "date": date, "time": time,
        "slot_msg_id": slot_msg_id,
        "state": "waiting_quantity",
        "assigned_rows": [],
        "current_index": 0,
        "row_ids": slot_info["row_ids"],
        "from_menu": False,
        "mapping": slot_info.get("mapping", get_column_mapping(platform)),
        "sheet_title": slot_info.get("sheet_title")
    }

    await callback.bot.send_message(
        chat_id=user_id,
        text=f"📊 Доступно отзывов: {slot_info.get('count', count)} шт.\nСколько вы готовы выполнить?"
    )


@router.callback_query(F.data.startswith("active_slot|"))
async def active_slot(callback: CallbackQuery):
    user_id = int(callback.data.split("|")[1])
    if user_id != callback.from_user.id:
        await callback.answer("Это не ваша сессия.", show_alert=True)
        return
    if user_id not in slot_requests:
        await callback.answer("❌ Сессия не найдена. Отправьте /resume.", show_alert=True)
        return
    request = slot_requests[user_id]
    if request["state"] != "slot_selection":
        await callback.answer("❌ Вы уже в процессе.", show_alert=True)
        return

    await callback.answer()
    await show_slot_buttons(callback.message, user_id)


async def show_slot_buttons(message: Message, user_id: int):
    request = slot_requests[user_id]
    ordered_reviews = request.get("ordered_reviews", [])
    completed = request.get("completed_reviews", [])
    platform = request["platform"]
    platform_names = {
        "яндекс": "Яндекс", "google": "Google", "2гис": "2ГИС",
        "авито": "Авито", "вк": "ВК", "отзовик": "Отзовик",
        "доктору": "Doctoru", "докдок": "ДокДок",
        "про докторов": "Про Докторов", "докту": "ДокТу",
        "32топ": "32ТОП", "zoon": "ZOON"
    }
    platform_name = platform_names.get(platform, platform.capitalize())

    builder = InlineKeyboardBuilder()
    for row_idx, num in ordered_reviews:
        if num not in completed:
            builder.button(text=f"{platform_name} {num}", callback_data=f"select_review|{num}")
    builder.adjust(3)
    await message.edit_text(
        "📋 Выберите номер отзыва:",
        reply_markup=builder.as_markup()
    )


@router.callback_query(F.data.startswith("select_review|"))
async def select_review(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in slot_requests:
        await callback.answer("❌ Сессия не найдена. Отправьте /resume.", show_alert=True)
        return
    request = slot_requests[user_id]
    if request["state"] != "slot_selection":
        await callback.answer("❌ Вы уже работаете над отзывом.", show_alert=True)
        return

    selected_num = int(callback.data.split("|")[1])
    ordered_reviews = request.get("ordered_reviews", [])
    target_row = None
    for row_idx, num in ordered_reviews:
        if num == selected_num and num not in request.get("completed_reviews", []):
            target_row = row_idx
            break
    if target_row is None:
        await callback.answer("❌ Отзыв уже выполнен или не найден.", show_alert=True)
        return

    request["active_review_row"] = target_row
    request["state"] = "working_on_review"

    sheet = None
    creds = get_credentials()
    if creds:
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key(SHEET_ID)
        sheet_title = request.get("sheet_title")
        if sheet_title:
            try:
                sheet = spreadsheet.worksheet(sheet_title)
            except:
                pass
        if sheet is None:
            for s in spreadsheet.worksheets():
                try:
                    s.cell(target_row, 1)
                    sheet = s
                    break
                except:
                    continue
    if sheet is None:
        await callback.answer("❌ Ошибка доступа к таблице.", show_alert=True)
        return

    mapping = request["mapping"]
    platform = request["platform"]
    await show_review_info(callback.message, user_id, target_row, sheet, mapping, platform)
    await callback.answer()


async def show_review_info(message: Message, user_id: int, row_idx: int, sheet, mapping, platform):
    request = slot_requests[user_id]
    row = sheet.row_values(row_idx)
    extra_ids = []

    logger.info(f"📄 Показ отзыва строка {row_idx}, платформа {platform}, mapping: {mapping}")

    if platform == "про докторов":
        # ... (Продокторов код без изменений)
        tz_link = row[mapping["tz_col"]-1] if len(row) >= mapping["tz_col"] else ""
        doctor_name = row[mapping["doctor_name_col"]-1] if len(row) >= mapping["doctor_name_col"] else ""
        doctor_direction = row[mapping["doctor_direction_col"]-1] if len(row) >= mapping["doctor_direction_col"] else ""
        gender = row[mapping["gender_col"]-1] if len(row) >= mapping["gender_col"] else ""
        stars = row[mapping["stars_col"]-1] if len(row) >= mapping["stars_col"] else ""
        platform_name = row[mapping["platform_col"]-1] if len(row) >= mapping["platform_col"] else ""
        link = row[mapping["link_col"]-1] if len(row) >= mapping["link_col"] else ""
        doc_link = row[mapping["photo_doc_col"]-1] if len(row) >= mapping["photo_doc_col"] else ""
        history = row[mapping["text_history_col"]-1] if len(row) >= mapping["text_history_col"] else ""
        like = row[mapping["text_like_col"]-1] if len(row) >= mapping["text_like_col"] else ""
        minus = row[mapping["text_minus_col"]-1] if len(row) >= mapping["text_minus_col"] else ""

        gender_text = "Без пола" if not gender else ("Мужской" if gender.upper() == "М" else "Женский")
        info_msg = (
            f"👨‍⚕️ <b>Информация по врачу:</b>\n"
            f"Имя врача: {doctor_name}\n"
            f"Направление: {doctor_direction}\n\n"
            f"<b>Информация по отзыву:</b>\n"
            f"Пол: {gender_text}\n"
            f"Кол-во звезд: {stars}\n"
            f"Платформа: {platform_name}\n"
            f"Ссылка на платформу: {link}"
        )
        date_info = (
            "\n\n<b>❗ Важно!</b>\n"
            "Если в документе нет даты рождения, укажите возраст от 20 лет.\n"
            "Если нет даты посещения, укажите в течение последних 7 дней."
        )
        full_msg = info_msg + date_info
        await message.edit_text(full_msg, parse_mode="HTML",
            reply_markup=InlineKeyboardBuilder().button(text="🔙 Вернуться к слоту", callback_data="back_to_slot").as_markup())

        if tz_link:
            sent = await message.answer(f"📄 <b>ТЗ</b>\n\n{tz_link}", parse_mode="HTML")
            extra_ids.append(sent.message_id)
        if doc_link:
            sent = await message.answer(f"📎 <b>Документ</b> (обязательно прикрепить)\n\n{doc_link}", parse_mode="HTML")
            extra_ids.append(sent.message_id)
        if history:
            sent = await message.answer(f"1️⃣ <b>История</b>\n\n{history}", parse_mode="HTML")
            extra_ids.append(sent.message_id)
        if like:
            sent = await message.answer(f"2️⃣ <b>Больше понравилось</b>\n\n{like}", parse_mode="HTML")
            extra_ids.append(sent.message_id)
        if minus:
            sent = await message.answer(f"3️⃣ <b>Минусы</b>\n\n{minus}", parse_mode="HTML")
            extra_ids.append(sent.message_id)

    else:
        # === ОБЫЧНЫЕ ПЛАТФОРМЫ ===
        link = row[mapping["link_col"]-1] if len(row) >= mapping["link_col"] else ""
        stars = row[mapping["stars_col"]-1] if len(row) >= mapping["stars_col"] else ""
        gender = row[mapping["gender_col"]-1] if len(row) >= mapping["gender_col"] else ""

        # ТЕКСТ ОТЗЫВА — ФИКС с проверкой нескольких столбцов
        text = row[mapping["text_col"]-1] if len(row) >= mapping["text_col"] else ""
        logger.info(f"📝 text_col = {mapping['text_col']}, len(row) = {len(row)}, text = '{text[:50]}'")

        if not text:
            # Фоллбэк: ищем текст в столбцах N, O, P, Q, M
            for col_idx in [14, 15, 16, 17, 13]:
                if len(row) >= col_idx and row[col_idx-1].strip():
                    candidate = row[col_idx-1].strip()
                    if not candidate.startswith("http") and candidate not in ("0", "1"):
                        text = candidate
                        logger.info(f"✅ Текст найден в столбце {col_idx}: '{candidate[:50]}...'")
                        break

        photo_link = row[17] if len(row) > 17 else ""

        template = PLATFORM_TEMPLATES.get(platform, PLATFORM_TEMPLATES["яндекс"])
        instruction_text = template["instruction"]
        extra_text = template["extra_text"]
        warning = template["warning"]

        gender_text = ""
        if gender.upper() == "М":
            gender_text = "👨 Отзыв мужской. Его должен выполнить мужчина с мужским именем на картах."
        elif gender.upper() == "Ж":
            gender_text = "👩 Отзыв женский. Её должна выполнить женщина с женским именем на картах."
        else:
            gender_text = "👤 Отзыв без пола. Может выполнить и мужчина, и женщина."

        final_msg = (
            f"{instruction_text}\n\n"
            f"⭐ Количество звезд: {stars}\n"
            "👥 ОТЗЫВЫ ПУБЛИКУЮТ РАЗНЫЕ ЛЮДИ\n"
            "- 1 ЧЕЛОВЕК 1 ОТЗЫВ (на одной платформе)\n"
            f"{gender_text}\n"
        )
        if extra_text:
            final_msg += f"{extra_text}\n"
        final_msg += (
            "Пожалуйста, после выполнения пришлите скриншот отзыва.\n\n"
            "Если хотите отказаться — /cancel.\n\n"
            f"{warning}"
        )

        await message.edit_text(final_msg, parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardBuilder().button(text="🔙 Вернуться к слоту", callback_data="back_to_slot").as_markup())

        if link:
            sent = await message.answer(link)
            extra_ids.append(sent.message_id)

        # ФИКС: если текст не найден — сообщаем
        if text:
            sent = await message.answer(f"📝 <b>Текст отзыва:</b>\n\n{text}", parse_mode="HTML")
            extra_ids.append(sent.message_id)
            logger.info(f"✅ Текст отправлен пользователю {user_id}")
        else:
            sent = await message.answer("⚠️ <b>Внимание!</b> Текст отзыва не найден в таблице. Обратитесь к администратору.")
            extra_ids.append(sent.message_id)
            logger.warning(f"⚠️ Текст отзыва пустой для строки {row_idx}")

        if photo_link:
            sent = await message.answer(
                f"📸 <b>ФОТО обязательное к прикреплению!</b>\n\n{photo_link}\n\n"
                f"<b>⚠️ ШТРАФ 50% если не прикрепить!</b>",
                parse_mode="HTML"
            )
            extra_ids.append(sent.message_id)

    request["extra_messages"] = extra_ids
    request["active_review_row"] = row_idx


@router.callback_query(F.data == "back_to_slot")
async def back_to_slot(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in slot_requests:
        await callback.answer("❌ Сессия не найдена.", show_alert=True)
        return
    request = slot_requests[user_id]
    if request["state"] != "working_on_review":
        await callback.answer("❌ Вы не в просмотре отзыва.", show_alert=True)
        return

    chat_id = callback.message.chat.id
    for msg_id in request.get("extra_messages", []):
        try:
            await callback.bot.delete_message(chat_id=chat_id, message_id=msg_id)
        except:
            pass
    request["extra_messages"] = []
    request["state"] = "slot_selection"
    request["active_review_row"] = None
    await callback.answer()
    await show_slot_buttons(callback.message, user_id)


@router.message(F.photo)
async def handle_screenshot(message: Message):
    user_id = message.from_user.id
    if user_id not in slot_requests:
        return
    request = slot_requests[user_id]
    if request["state"] != "working_on_review":
        await message.answer("❌ Сначала выберите отзыв.")
        return

    active_row = request.get("active_review_row")
    if active_row is None:
        await message.answer("❌ Активный отзыв не найден.")
        return

    chat_id = message.chat.id
    for msg_id in request.get("extra_messages", []):
        try:
            await message.bot.delete_message(chat_id=chat_id, message_id=msg_id)
        except:
            pass
    request["extra_messages"] = []

    mapping = request["mapping"]
    sheet_title = request.get("sheet_title")

    creds = get_credentials()
    if not creds:
        await message.answer("❌ Ошибка доступа к таблице.")
        return
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(SHEET_ID)
    sheet = None
    if sheet_title:
        try:
            sheet = spreadsheet.worksheet(sheet_title)
        except:
            pass
    if sheet is None:
        for s in spreadsheet.worksheets():
            try:
                s.cell(active_row, 1)
                sheet = s
                break
            except:
                continue
    if sheet is None:
        await message.answer("❌ Не удалось найти лист.")
        return

    review_id = sheet.cell(active_row, mapping["id_col"]).value
    if not review_id:
        review_id = secrets.token_hex(4)
        sheet.update_cell(active_row, mapping["id_col"], review_id)

    try:
        sheet.update_cell(active_row, mapping["status_col"], "на модерации")
        sheet.update_cell(active_row, mapping["flag_final_col"], 333)
        sheet.format(f"{chr(64+mapping['flag_final_col'])}{active_row}", {
            "backgroundColor": {"red": 0, "green": 0.8, "blue": 0}
        })
        logger.info(f"✅ Строка {active_row} → 'на модерации'")
    except Exception as e:
        logger.error(f"Ошибка обновления: {e}")
        await message.answer("❌ Ошибка при сохранении. Попробуйте позже.")
        return

    try:
        user = get_user(user_id)
        user_mention = f"@{user['tg_username']}" if user and user.get('tg_username') else f"@{message.from_user.username}"
        timestamp = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        caption = f"{user_mention} – {timestamp}\nID: {review_id or 'Unknown'}"
        await message.bot.send_photo(
            chat_id=SCREENSHOT_CHANNEL_ID,
            photo=message.photo[-1].file_id,
            caption=caption
        )
    except Exception as e:
        logger.error(f"Не удалось переслать скриншот: {e}")

    ordered_reviews = request.get("ordered_reviews", [])
    completed = request.get("completed_reviews", [])
    for row_idx, num in ordered_reviews:
        if row_idx == active_row:
            completed.append(num)
            break
    request["completed_reviews"] = completed
    request["active_review_row"] = None
    request["state"] = "slot_selection"

    total = len(ordered_reviews)
    if len(completed) == total:
        await message.answer("✅ Все отзывы отправлены на модерацию!")
        del slot_requests[user_id]
        return

    await message.answer(
        f"✅ Отзыв выполнен! Осталось {total - len(completed)}.",
        reply_markup=InlineKeyboardBuilder().button(
            text="🎯 Активный слот",
            callback_data=f"active_slot|{user_id}"
        ).as_markup()
    )
