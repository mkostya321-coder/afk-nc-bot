import logging, os, secrets
from urllib.parse import quote
from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode
from bot.config import ADMIN_IDS, CHANNEL_ID, MANAGER_USERNAME, OTHER_JOBS_CHANNEL, SHEET_ID, SCREENSHOT_CHANNEL_ID, get_credentials_path, INSTRUCTION_PHOTO_ID, INSTRUCTION_PHOTO_PATH
from bot.database import is_registered, is_blocked, get_user, is_ga, is_moderator, get_user_by_username, add_review_take, count_review_takes_last_24h, get_limit
from bot.google_sheets import get_column_mapping
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pytz

router = Router()
logger = logging.getLogger(__name__)
active_slots = {}
slot_requests = {}
cooldowns = {}
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
}

# ---------- Функция отправки инструкции ----------
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
            logger.info(f"📸 Отправка инструкции по ID: {INSTRUCTION_PHOTO_ID}")
            await bot.send_photo(
                chat_id=user_id,
                photo=INSTRUCTION_PHOTO_ID,
                caption=caption
            )
        elif INSTRUCTION_PHOTO_PATH and os.path.exists(INSTRUCTION_PHOTO_PATH):
            logger.info(f"📸 Отправка инструкции из файла: {INSTRUCTION_PHOTO_PATH}")
            with open(INSTRUCTION_PHOTO_PATH, 'rb') as photo:
                await bot.send_photo(
                    chat_id=user_id,
                    photo=photo,
                    caption=caption
                )
        else:
            logger.warning("❌ Нет ни ID, ни файла для инструкции. Отправляем только текст.")
            await bot.send_message(chat_id=user_id, text=caption)
    except Exception as e:
        logger.error(f"Ошибка отправки инструкции: {e}")
        try:
            await bot.send_message(chat_id=user_id, text="📸 Инструкция: сделайте скриншот отзыва и отправьте.")
        except:
            pass

# ---------- Проверка лимита ----------
async def check_limit(user_id: int, platform: str) -> bool:
    limit = get_limit(platform)
    count = count_review_takes_last_24h(user_id, platform)
    if count >= limit:
        return False
    return True

# ---------- Обработчик кнопки взять слот (из канала) ----------
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
        await callback.bot.send_message(user_id, "❌ Этот слот уже неактивен.")
        return

    if user_id in cooldowns and platform in cooldowns[user_id]:
        if datetime.now() < cooldowns[user_id][platform]:
            remaining = (cooldowns[user_id][platform] - datetime.now()).seconds // 3600
            await callback.bot.send_message(user_id, f"⏳ Вы уже брали {platform}. Повторно можно будет через {remaining} часов.")
            return

    if not await check_limit(user_id, platform):
        limit = get_limit(platform)
        await callback.bot.send_message(user_id, f"❌ Вы превысили лимит на {platform} – максимум {limit} отзывов за 24 часа.")
        return

    slot_requests[user_id] = {
        "platform": platform,
        "count": count,
        "date": date,
        "time": time,
        "slot_msg_id": slot_msg_id,
        "state": "waiting_quantity",
        "assigned_rows": [],
        "current_index": 0,
        "row_ids": slot_info["row_ids"],
        "from_menu": False,
        "mapping": slot_info.get("mapping", get_column_mapping(platform))
    }

    await callback.bot.send_message(
        chat_id=user_id,
        text=f"📊 Доступно отзывов: {count} шт.\nСколько вы готовы выполнить? (напишите число)"
    )

# ---------- Обработчик выбора платформы из меню "Слоты" ----------
@router.callback_query(F.data.startswith("choose_platform|"))
async def choose_platform(callback: CallbackQuery):
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

    platform = callback.data.split("|")[1]
    all_rows = []
    for msg_id, slot in active_slots.items():
        if slot.get("platform") == platform and slot.get("row_ids"):
            all_rows.extend(slot["row_ids"])

    if not all_rows:
        await callback.bot.send_message(user_id, "❌ Нет доступных отзывов для этой платформы.")
        return

    if user_id in cooldowns and platform in cooldowns[user_id]:
        if datetime.now() < cooldowns[user_id][platform]:
            remaining = (cooldowns[user_id][platform] - datetime.now()).seconds // 3600
            await callback.bot.send_message(user_id, f"⏳ Вы уже брали {platform}. Повторно можно будет через {remaining} часов.")
            return

    if not await check_limit(user_id, platform):
        limit = get_limit(platform)
        await callback.bot.send_message(user_id, f"❌ Вы превысили лимит на {platform} – максимум {limit} отзывов за 24 часа.")
        return

    slot_requests[user_id] = {
        "platform": platform,
        "count": len(all_rows),
        "date": None,
        "time": None,
        "slot_msg_id": "menu",
        "state": "waiting_quantity",
        "assigned_rows": [],
        "current_index": 0,
        "row_ids": all_rows,
        "from_menu": True,
        "mapping": get_column_mapping(platform)
    }

    await callback.bot.send_message(
        chat_id=user_id,
        text=f"📊 Доступно отзывов на платформе {platform}: {len(all_rows)} шт.\nСколько вы готовы выполнить? (напишите число)"
    )

# ---------- Обработчик ввода количества (общий) ----------
@router.message(F.text)
async def handle_quantity_input(message: Message):
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

    if request["from_menu"]:
        assigned_rows = request["row_ids"][:quantity]
        remaining_rows = request["row_ids"][quantity:]
        for msg_id, slot in list(active_slots.items()):
            if slot.get("platform") == platform:
                new_row_ids = [r for r in slot["row_ids"] if r not in assigned_rows]
                slot["row_ids"] = new_row_ids
                slot["count"] = len(new_row_ids)
                if slot["count"] == 0:
                    del active_slots[msg_id]
                    try:
                        await message.bot.edit_message_text(
                            chat_id=CHANNEL_ID, message_id=msg_id,
                            text="Все отзывы этого слота разобраны."
                        )
                    except:
                        pass
        # Обновляем строки
        username = f"@{message.from_user.username}" if message.from_user.username else message.from_user.full_name
        creds = get_credentials()
        if creds:
            client = gspread.authorize(creds)
            spreadsheet = client.open_by_key(SHEET_ID)
            for sheet in spreadsheet.worksheets():
                for row_idx in assigned_rows:
                    try:
                        sheet.cell(row_idx, 1)
                        sheet.update_cell(row_idx, mapping["status_col"], "в работе")
                        sheet.update_cell(row_idx, mapping["executor_col"], username)
                        logger.info(f"✅ Строка {row_idx} обновлена (статус 'в работе', исполнитель {username})")
                    except:
                        continue
        for _ in range(quantity):
            add_review_take(user_id, platform)
        request["assigned_rows"] = assigned_rows
        request["current_index"] = 0
        request["state"] = "sending_reviews"
        await send_next_review(message, request, sheet=None)
    else:
        slot_msg_id = request["slot_msg_id"]
        slot_info = active_slots.get(slot_msg_id)
        if not slot_info:
            await message.answer("❌ Этот слот уже неактивен.")
            del slot_requests[user_id]
            return
        row_ids = slot_info["row_ids"]
        if len(row_ids) < quantity:
            await message.answer("❌ Количество свободных отзывов изменилось. Попробуйте заново.")
            del slot_requests[user_id]
            return
        assigned_rows = row_ids[:quantity]
        slot_info["row_ids"] = row_ids[quantity:]
        slot_info["count"] -= quantity
        if slot_info["count"] == 0:
            del active_slots[slot_msg_id]
            try:
                await message.bot.edit_message_text(
                    chat_id=CHANNEL_ID, message_id=slot_msg_id,
                    text="Все отзывы этого слота разобраны."
                )
            except:
                pass
        username = f"@{message.from_user.username}" if message.from_user.username else message.from_user.full_name
        creds = get_credentials()
        if creds:
            client = gspread.authorize(creds)
            spreadsheet = client.open_by_key(SHEET_ID)
            for sheet in spreadsheet.worksheets():
                for row_idx in assigned_rows:
                    try:
                        sheet.cell(row_idx, 1)
                        sheet.update_cell(row_idx, mapping["status_col"], "в работе")
                        sheet.update_cell(row_idx, mapping["executor_col"], username)
                        logger.info(f"✅ Строка {row_idx} обновлена (статус 'в работе', исполнитель {username})")
                    except:
                        continue
        for _ in range(quantity):
            add_review_take(user_id, platform)
        request["assigned_rows"] = assigned_rows
        request["current_index"] = 0
        request["state"] = "sending_reviews"
        await send_next_review(message, request, sheet=None)

# ---------- Команда отказа ----------
@router.message(Command("cancel"))
@router.message(Command("отказ"))
async def cancel_task(message: Message):
    user_id = message.from_user.id
    if user_id not in slot_requests:
        await message.answer("❌ У вас нет активного задания.")
        return
    request = slot_requests[user_id]
    if request["state"] == "waiting_quantity":
        await message.answer("❌ Вы ещё не взяли отзывы. Сначала выберите количество.")
        return

    assigned_rows = request["assigned_rows"]
    current_index = request["current_index"]
    slot_msg_id = request["slot_msg_id"]
    slot_info = active_slots.get(slot_msg_id) if slot_msg_id != "menu" else None
    mapping = request["mapping"]

    remaining_rows = assigned_rows[current_index:]

    if remaining_rows:
        creds = get_credentials()
        if creds:
            client = gspread.authorize(creds)
            spreadsheet = client.open_by_key(SHEET_ID)
            for sheet in spreadsheet.worksheets():
                for row_idx in remaining_rows:
                    try:
                        sheet.cell(row_idx, 1)
                        sheet.update_cell(row_idx, mapping["status_col"], "")
                        sheet.update_cell(row_idx, mapping["executor_col"], "")
                        logger.info(f"✅ Строка {row_idx} очищена при отказе")
                    except:
                        continue
        if slot_info:
            slot_info["row_ids"].extend(remaining_rows)
            slot_info["count"] += len(remaining_rows)
            logger.info(f"Возвращено {len(remaining_rows)} отзывов в слот {slot_msg_id}")
        else:
            logger.info(f"Слот {slot_msg_id} неактивен, отзывы останутся свободными")

    del slot_requests[user_id]
    await message.answer(
        "✅ Отказ принят.\n"
        "Выполненные отзывы отправлены на модерацию.\n"
        "Остальные возвращены в слот и будут переопубликованы."
    )

# ---------- Обработка скриншотов ----------
@router.message(F.photo)
async def handle_screenshot(message: Message):
    user_id = message.from_user.id
    if user_id not in slot_requests:
        return
    request = slot_requests[user_id]
    if request["state"] != "waiting_screenshot":
        return

    mapping = request["mapping"]
    assigned_rows = request["assigned_rows"]
    current_row = assigned_rows[request["current_index"]]

    creds = get_credentials()
    if not creds:
        await message.answer("❌ Ошибка доступа к таблице.")
        return
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(SHEET_ID)
    sheet = None
    review_id = None
    for s in spreadsheet.worksheets():
        try:
            review_id = s.cell(current_row, mapping["id_col"]).value
            if review_id:
                sheet = s
                break
        except:
            continue
    if not review_id:
        review_id = secrets.token_hex(4)
        # ищем лист
        for s in spreadsheet.worksheets():
            try:
                s.cell(current_row, 1)
                sheet = s
                sheet.update_cell(current_row, mapping["id_col"], review_id)
                break
            except:
                continue
    if sheet:
        try:
            sheet.update_cell(current_row, mapping["status_col"], "на модерации")
            sheet.update_cell(current_row, mapping["flag_final_col"], 333)
            sheet.format(f"{chr(64+mapping['flag_final_col'])}{current_row}", {
                "backgroundColor": {"red": 0, "green": 0.8, "blue": 0}
            })
        except Exception as e:
            logger.error(f"Ошибка обновления статуса для строки {current_row}: {e}")

    # Пересылаем скриншот
    try:
        user = get_user(user_id)
        user_mention = f"@{user['tg_username']}" if user and user.get('tg_username') else f"@{message.from_user.username}"
        timestamp = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        caption = f"{user_mention} – {timestamp}\nID отзыва: {review_id or 'Unknown'}"
        await message.bot.send_photo(
            chat_id=SCREENSHOT_CHANNEL_ID,
            photo=message.photo[-1].file_id,
            caption=caption
        )
    except Exception as e:
        logger.error(f"Не удалось переслать скриншот в канал: {e}")

    request["current_index"] += 1
    request["state"] = "sending_reviews"
    await send_next_review(message, request, sheet)

# ---------- Отправка следующего отзыва ----------
async def send_next_review(message: Message, request: dict, sheet):
    assigned_rows = request["assigned_rows"]
    current_index = request["current_index"]
    platform = request["platform"]
    mapping = request["mapping"]

    if current_index >= len(assigned_rows):
        if message.from_user.id not in cooldowns:
            cooldowns[message.from_user.id] = {}
        cooldowns[message.from_user.id][platform] = datetime.now() + timedelta(hours=24)
        await message.answer("✅ Все отзывы отправлены на модерацию. Спасибо за работу!")
        del slot_requests[message.from_user.id]
        return

    await send_instruction(message.from_user.id, message.bot)

    row_idx = assigned_rows[current_index]
    if sheet is None:
        creds = get_credentials()
        if creds:
            client = gspread.authorize(creds)
            spreadsheet = client.open_by_key(SHEET_ID)
            for s in spreadsheet.worksheets():
                try:
                    s.cell(row_idx, 1)
                    sheet = s
                    break
                except:
                    continue
    if sheet is None:
        await message.answer("❌ Ошибка: не удалось найти лист с отзывом.")
        del slot_requests[message.from_user.id]
        return

    row = sheet.row_values(row_idx)

    if platform == "про докторов":
        # 1. ТЗ
        tz_link = row[mapping["tz_col"]-1] if len(row) >= mapping["tz_col"] else ""
        if tz_link:
            await message.answer(f"📄 <b>Техническое задание (ТЗ)</b>\n\n{tz_link}", parse_mode="HTML")
        else:
            await message.answer("📄 Техническое задание отсутствует.")

        # 2. Информация по врачу
        doctor_name = row[mapping["doctor_name_col"]-1] if len(row) >= mapping["doctor_name_col"] else ""
        doctor_direction = row[mapping["doctor_direction_col"]-1] if len(row) >= mapping["doctor_direction_col"] else ""
        gender = row[mapping["gender_col"]-1] if len(row) >= mapping["gender_col"] else ""
        stars = row[mapping["stars_col"]-1] if len(row) >= mapping["stars_col"] else ""
        platform_name = row[mapping["platform_col"]-1] if len(row) >= mapping["platform_col"] else ""
        link = row[mapping["link_col"]-1] if len(row) >= mapping["link_col"] else ""

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
        await message.answer(info_msg, parse_mode="HTML")

        # 3. Документ (H)
        doc_link = row[mapping["photo_doc_col"]-1] if len(row) >= mapping["photo_doc_col"] else ""
        if doc_link:
            await message.answer(f"📎 <b>Документ с информацией для заполнения отзыва по ТЗ</b>\n\n{doc_link}", parse_mode="HTML")

        # 4-9. Части отзыва
        history = row[mapping["text_history_col"]-1] if len(row) >= mapping["text_history_col"] else ""
        like = row[mapping["text_like_col"]-1] if len(row) >= mapping["text_like_col"] else ""
        minus = row[mapping["text_minus_col"]-1] if len(row) >= mapping["text_minus_col"] else ""

        if history:
            await message.answer(f"1️⃣ <b>История:</b>\n\n{history}", parse_mode="HTML")
        if like:
            await message.answer(f"2️⃣ <b>Больше понравилось:</b>\n\n{like}", parse_mode="HTML")
        if minus:
            await message.answer(f"3️⃣ <b>Минусы:</b>\n\n{minus}", parse_mode="HTML")

        await message.answer("Ожидаю скриншот и продолжаем работу.")
        request["state"] = "waiting_screenshot"

    else:
        # Стандартная логика
        link = row[mapping["link_col"]-1] if len(row) >= mapping["link_col"] else ""
        text = row[mapping["text_col"]-1] if len(row) >= mapping["text_col"] else ""
        stars = row[mapping["stars_col"]-1] if len(row) >= mapping["stars_col"] else ""
        gender = row[mapping["gender_col"]-1] if len(row) >= mapping["gender_col"] else ""

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
            gender_text = "👤 Отзыв без пола. Может выполнить и мужчина, и женщина. Главное – изменить род в тексте при отправке исполнителю."

        photo_link = row[17] if len(row) > 17 else ""
        photo_warning = ""
        if photo_link:
            photo_warning = "📸 <b>Фотография к ОБЯЗАТЕЛЬНОМУ прикреплению к отзыву!</b>\nЕсли вы не прикрепите фото, отзыв будет оплачен на 50% ниже.\n\n"

        final_msg = (
            f"{instruction_text}\n\n"
            f"{photo_warning}"
            f"⭐ Количество звезд: {stars}\n"
            "👥 ОТЗЫВЫ ПУБЛИКУЮТ РАЗНЫЕ ЛЮДИ\n"
            "- 1 ЧЕЛОВЕК 1 ОТЗЫВ (на одной платформе)\n"
            f"{gender_text}\n"
        )
        if extra_text:
            final_msg += f"{extra_text}\n"
        final_msg += (
            "Пожалуйста, после выполнения пришлите скриншот отзыва.\n\n"
            "Если хотите отказаться от оставшихся заданий, отправьте команду /cancel.\n\n"
            f"{warning}"
        )

        await message.answer(final_msg, parse_mode=ParseMode.HTML)
        await message.answer(link)
        await message.answer(text)
        await message.answer("Ожидаю скриншот и продолжаем работу.")
        request["state"] = "waiting_screenshot"

# ---------- Команда для пользователя "Слоты" (кнопка в меню) ----------
@router.message(Command("job"))
@router.message(F.text == "💼 Слоты")
async def cmd_job(message: Message):
    if is_blocked(message.from_user.id):
        await message.answer("⛔ Вы заблокированы.")
        return
    if not active_slots:
        await message.answer("😔 К сожалению, на данный момент все слоты закрыты. Ожидайте нового слота.\nС уважением, команда New Chapter.")
        return

    platforms = set()
    for slot in active_slots.values():
        p = slot.get("platform")
        if p:
            platforms.add(p)

    if not platforms:
        await message.answer("Нет доступных платформ.")
        return

    builder = InlineKeyboardBuilder()
    platform_names = {
        "яндекс": "Яндекс", "google": "Google", "2гис": "2ГИС",
        "авито": "Авито", "вк": "ВК", "отзовик": "Отзовик",
        "доктору": "Doctoru", "докдок": "ДокДок",
        "про докторов": "Про Докторов", "докту": "ДокТу", "32топ": "32ТОП"
    }
    for p in platforms:
        display_name = platform_names.get(p, p.capitalize())
        builder.button(text=display_name, callback_data=f"choose_platform|{p}")
    builder.adjust(2)
    await message.answer(
        "Выберите платформу, с которой хотите взять отзывы:",
        reply_markup=builder.as_markup()
    )
