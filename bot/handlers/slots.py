import logging, os, secrets, time
from urllib.parse import quote
from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode
from bot.config import ADMIN_IDS, CHANNEL_ID, MANAGER_USERNAME, OTHER_JOBS_CHANNEL, SHEET_ID, SCREENSHOT_CHANNEL_ID, get_credentials_path, INSTRUCTION_PHOTO_ID, INSTRUCTION_PHOTO_PATH
from bot.database import is_registered, is_blocked, get_user, is_ga, is_moderator, get_user_by_username, add_review_take, count_review_takes_last_24h, get_limit
from bot.google_sheets import get_column_mapping, get_credentials
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

    # ---- ЗАПРЕТ НА ВЗЯТИЕ НОВОГО СЛОТА ПРИ НАЛИЧИИ АКТИВНОГО ----
    if user_id in slot_requests:
        active_platform = slot_requests[user_id]["platform"]
        await callback.bot.send_message(
            user_id,
            f"❌ У вас уже есть активный слот на платформе {active_platform}.\n"
            "Закончите его, чтобы взять новый."
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
        await callback.bot.send_message(user_id, "❌ Этот слот уже неактивен.")
        return

    # Проверка лимита
    if not await check_limit(user_id, platform):
        limit = get_limit(platform)
        await callback.bot.send_message(user_id, f"❌ Вы превысили лимит на {platform} – максимум {limit} отзывов за 24 часа (с 10:00 МСК).")
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
        "mapping": slot_info.get("mapping", get_column_mapping(platform)),
        "sheet_title": slot_info.get("sheet_title")
    }

    await callback.bot.send_message(
        chat_id=user_id,
        text=f"📊 Доступно отзывов: {count} шт.\nСколько вы готовы выполнить? (напишите число)"
    )

# ---------- Обработчик ввода количества ----------
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
    sheet_title = request.get("sheet_title")

    creds = get_credentials()
    if not creds:
        await message.answer("❌ Ошибка доступа к таблице.")
        del slot_requests[user_id]
        return
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(SHEET_ID)

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

        username = f"@{message.from_user.username}" if message.from_user.username else message.from_user.full_name
        for row_idx in assigned_rows:
            try:
                sheet.update_cell(row_idx, mapping["status_col"], "в работе")
                sheet.update_cell(row_idx, mapping["executor_col"], username)
                time.sleep(0.1)
            except Exception as e:
                logger.error(f"Ошибка обновления строки {row_idx}: {e}")

        for idx, row_idx in enumerate(assigned_rows, start=1):
            try:
                sheet.update_cell(row_idx, mapping["order_col"], idx)
            except Exception as e:
                logger.error(f"Не удалось записать номер для строки {row_idx}: {e}")

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
            "Нажмите кнопку «Активный слот», чтобы приступить к работе.",
            reply_markup=InlineKeyboardBuilder().button(text="🎯 Активный слот", callback_data=f"active_slot|{user_id}").as_markup()
        )
        return

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

        username = f"@{message.from_user.username}" if message.from_user.username else message.from_user.full_name
        for row_idx in assigned_rows:
            try:
                sheet.update_cell(row_idx, mapping["status_col"], "в работе")
                sheet.update_cell(row_idx, mapping["executor_col"], username)
                time.sleep(0.1)
            except Exception as e:
                logger.error(f"Ошибка обновления строки {row_idx}: {e}")

        for idx, row_idx in enumerate(assigned_rows, start=1):
            try:
                sheet.update_cell(row_idx, mapping["order_col"], idx)
            except Exception as e:
                logger.error(f"Не удалось записать номер для строки {row_idx}: {e}")

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
            "Нажмите кнопку «Активный слот», чтобы приступить к работе.",
            reply_markup=InlineKeyboardBuilder().button(text="🎯 Активный слот", callback_data=f"active_slot|{user_id}").as_markup()
        )

# ---------- Обработчик кнопки "Активный слот" ----------
@router.callback_query(F.data.startswith("active_slot|"))
async def active_slot(callback: CallbackQuery):
    user_id = int(callback.data.split("|")[1])
    if user_id != callback.from_user.id:
        await callback.answer("Это не ваша сессия.", show_alert=True)
        return
    if user_id not in slot_requests:
        await callback.answer("❌ Активная сессия не найдена.", show_alert=True)
        return
    request = slot_requests[user_id]
    if request["state"] != "slot_selection":
        await callback.answer("❌ Вы уже в процессе выполнения.", show_alert=True)
        return

    await callback.answer()
    await show_slot_buttons(callback.message, user_id)

# ---------- Показать кнопки с номерами ----------
async def show_slot_buttons(message: Message, user_id: int):
    request = slot_requests[user_id]
    ordered_reviews = request.get("ordered_reviews", [])
    completed = request.get("completed_reviews", [])
    platform = request["platform"]
    platform_names = {
        "яндекс": "Яндекс", "google": "Google", "2гис": "2ГИС",
        "авито": "Авито", "вк": "ВК", "отзовик": "Отзовик",
        "доктору": "Doctoru", "докдок": "ДокДок",
        "про докторов": "Про Докторов", "докту": "ДокТу", "32топ": "32ТОП"
    }
    platform_name = platform_names.get(platform, platform.capitalize())

    builder = InlineKeyboardBuilder()
    for row_idx, num in ordered_reviews:
        if num not in completed:
            builder.button(text=f"{platform_name} {num}", callback_data=f"select_review|{num}")
    builder.adjust(3)
    await message.edit_text(
        f"📋 Выберите номер отзыва, который хотите выполнить:",
        reply_markup=builder.as_markup()
    )

# ---------- Обработчик выбора номера отзыва ----------
@router.callback_query(F.data.startswith("select_review|"))
async def select_review(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in slot_requests:
        await callback.answer("❌ Сессия не найдена.", show_alert=True)
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
        await callback.answer("❌ Этот отзыв уже выполнен или не найден.", show_alert=True)
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

# ---------- ПОКАЗАТЬ ИНФОРМАЦИЮ ПО ОТЗЫВУ (ОСНОВНАЯ ФУНКЦИЯ) ----------
async def show_review_info(message: Message, user_id: int, row_idx: int, sheet, mapping, platform):
    request = slot_requests[user_id]
    row = sheet.row_values(row_idx)
    extra_ids = []

    if platform == "про докторов":
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
        await message.edit_text(full_msg, parse_mode="HTML", reply_markup=InlineKeyboardBuilder().button(text="🔙 Вернуться к слоту", callback_data=f"back_to_slot").as_markup())

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
        link = row[mapping["link_col"]-1] if len(row) >= mapping["link_col"] else ""
        text = row[mapping["text_col"]-1] if len(row) >= mapping["text_col"] else ""
        stars = row[mapping["stars_col"]-1] if len(row) >= mapping["stars_col"] else ""
        gender = row[mapping["gender_col"]-1] if len(row) >= mapping["gender_col"] else ""
        photo_link = row[17] if len(row) > 17 else ""  # столбец R (индекс 17)
        
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

        # Собираем основное сообщение
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
            "Если хотите отказаться от оставшихся заданий, отправьте команду /cancel.\n\n"
            f"{warning}"
        )
        
        # Отправляем основное сообщение
        await message.edit_text(final_msg, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardBuilder().button(text="🔙 Вернуться к слоту", callback_data=f"back_to_slot").as_markup())
        
        # Отправляем ссылку на карточку
        if link:
            sent = await message.answer(link)
            extra_ids.append(sent.message_id)
        
        # Отправляем текст отзыва
        if text:
            sent = await message.answer(text)
            extra_ids.append(sent.message_id)
        
        # ---- ОТПРАВКА ССЫЛКИ НА ФОТО ИЗ СТОЛБЦА R С ПРЕДУПРЕЖДЕНИЕМ О ШТРАФЕ ----
        if photo_link:
            sent = await message.answer(
                f"📸 <b>ФОТО обязательное к прикреплению к отзыву!</b>\n\n"
                f"{photo_link}\n\n"
                f"<b>⚠️ ШТРАФ: если вы не прикрепите это фото к отзыву, оплата будет снижена на 50%!</b>",
                parse_mode="HTML"
            )
            extra_ids.append(sent.message_id)
            logger.info(f"✅ Ссылка на фото из столбца R отправлена: {photo_link}")

    request["extra_messages"] = extra_ids
    request["active_review_row"] = row_idx

# ---------- Обработчик "Вернуться к слоту" ----------
@router.callback_query(F.data == "back_to_slot")
async def back_to_slot(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in slot_requests:
        await callback.answer("❌ Сессия не найдена.", show_alert=True)
        return
    request = slot_requests[user_id]
    if request["state"] != "working_on_review":
        await callback.answer("❌ Вы не находитесь в режиме просмотра отзыва.", show_alert=True)
        return

    chat_id = callback.message.chat.id
    for msg_id in request.get("extra_messages", []):
        try:
            await callback.bot.delete_message(chat_id=chat_id, message_id=msg_id)
        except Exception as e:
            logger.error(f"Не удалось удалить сообщение {msg_id}: {e}")
    request["extra_messages"] = []

    request["state"] = "slot_selection"
    request["active_review_row"] = None
    await callback.answer()
    await show_slot_buttons(callback.message, user_id)

# ---------- Обработка скриншотов ----------
@router.message(F.photo)
async def handle_screenshot(message: Message):
    user_id = message.from_user.id
    if user_id not in slot_requests:
        return
    request = slot_requests[user_id]
    if request["state"] != "working_on_review":
        await message.answer("❌ Сначала выберите отзыв из списка.")
        return

    active_row = request.get("active_review_row")
    if active_row is None:
        await message.answer("❌ Активный отзыв не найден.")
        return

    chat_id = message.chat.id
    for msg_id in request.get("extra_messages", []):
        try:
            await message.bot.delete_message(chat_id=chat_id, message_id=msg_id)
        except Exception as e:
            logger.error(f"Не удалось удалить сообщение {msg_id}: {e}")
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
        logger.info(f"✅ Строка {active_row} обновлена (статус 'на модерации')")
    except Exception as e:
        logger.error(f"Ошибка обновления статуса: {e}")
        await message.answer("❌ Ошибка при сохранении скриншота. Попробуйте позже.")
        return

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
        await message.answer("✅ Все отзывы отправлены на модерацию. Спасибо за работу!")
        del slot_requests[user_id]
        return

    await message.answer(
        f"✅ Отзыв выполнен! Осталось {total - len(completed)} отзывов.",
        reply_markup=InlineKeyboardBuilder().button(text="🎯 Активный слот", callback_data=f"active_slot|{user_id}").as_markup()
    )

# ---------- Команда отказа ----------
@router.message(Command("cancel"))
@router.message(Command("отказ"))
async def cancel_task(message: Message):
    user_id = message.from_user.id
    if user_id not in slot_requests:
        await message.answer("❌ У вас нет активного задания.")
        return
    request = slot_requests[user_id]
    assigned_rows = request.get("assigned_rows", [])
    completed = request.get("completed_reviews", [])
    ordered_reviews = request.get("ordered_reviews", [])
    remaining_rows = [row_idx for row_idx, num in ordered_reviews if num not in completed]
    if remaining_rows:
        creds = get_credentials()
        if creds:
            client = gspread.authorize(creds)
            spreadsheet = client.open_by_key(SHEET_ID)
            sheet_title = request.get("sheet_title")
            mapping = request["mapping"]
            if sheet_title:
                try:
                    sheet = spreadsheet.worksheet(sheet_title)
                except:
                    sheet = None
            if sheet is None:
                for s in spreadsheet.worksheets():
                    try:
                        s.cell(remaining_rows[0], 1)
                        sheet = s
                        break
                    except:
                        continue
            if sheet:
                for row_idx in remaining_rows:
                    try:
                        sheet.update_cell(row_idx, mapping["status_col"], "")
                        sheet.update_cell(row_idx, mapping["executor_col"], "")
                        sheet.update_cell(row_idx, mapping["order_col"], "")
                        time.sleep(0.1)
                    except Exception as e:
                        logger.error(f"Ошибка очистки строки {row_idx}: {e}")
        slot_msg_id = request.get("slot_msg_id")
        if slot_msg_id and slot_msg_id != "menu":
            slot_info = active_slots.get(slot_msg_id)
            if slot_info:
                slot_info["row_ids"].extend(remaining_rows)
                slot_info["count"] += len(remaining_rows)
    del slot_requests[user_id]
    await message.answer(
        "✅ Отказ принят.\n"
        "Выполненные отзывы отправлены на модерацию.\n"
        "Остальные возвращены в слот и будут переопубликованы."
    )
