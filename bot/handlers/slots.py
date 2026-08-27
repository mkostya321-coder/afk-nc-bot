import logging, os, secrets
from urllib.parse import quote
from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode
from bot.config import ADMIN_IDS, CHANNEL_ID, MANAGER_USERNAME, OTHER_JOBS_CHANNEL, SHEET_ID, SCREENSHOT_CHANNEL_ID, get_credentials_path, INSTRUCTION_PHOTO_ID, INSTRUCTION_PHOTO_PATH
from bot.database import is_registered, is_blocked, get_user, is_ga, is_moderator, get_user_by_username
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
        "photo_required": False,
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
        "photo_required": False,
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
        "photo_required": False,
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
        "photo_required": False,
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
        "photo_required": False,
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
        "photo_required": False,
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
        "photo_required": False,
        "extra_text": "",
        "warning": (
            "<i>⚠️ Если не выполнить все взятые вами задачи до 23:30 и не успеть от них отказаться, "
            "все вами выполненное будет оплачено на 30% ниже!</i>"
        )
    },
    "про докторов": {
        "instruction": (
            "<b>⚠️ ПРИМЕР КАК ДОЛЖЕН ВЫГЛЯДЕТЬ СКРИНШОТ КОТОРЫЙ Я БУДУ ОТ ВАС ЖДАТЬ!</b>\n"
            "Скриншот в другом формате считается выполненным не по ТЗ и отзыв не будет оплачен, пожалуйста, будьте внимательны!"
        ),
        "photo_required": False,
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
        "photo_required": False,
        "extra_text": "",
        "warning": (
            "<i>⚠️ Если не выполнить все взятые вами задачи до 23:30 и не успеть от них отказаться, "
            "все вами выполненное будет оплачено на 30% ниже!</i>"
        )
    },
}

# ---------- Планирование автослота (используется из google_sheets.py) ----------
async def publish_scheduled_slot(bot, active_slots_dict, platform: str, count: int,
                                 date: str, time: str, row_ids: list, attempt: int = 1):
    platform_names = {
        "яндекс": "Яндекс", "google": "Google", "2гис": "2ГИС",
        "авито": "Авито", "вк": "ВК", "отзовик": "Otzovik", "доктору": "Doctoru",
        "докдок": "ДокДок", "про докторов": "Про Докторов", "докту": "ДокТу", "32топ": "32ТОП"
    }
    pretty_name = platform_names.get(platform, platform)
    post_text = (
        f"🔥 Слот: {pretty_name}\n"
        f"📅 Дата: {date}\n"
        f"⏰ Время: {time} (МСК)\n"
        f"📌 Доступно отзывов: {count} шт.\n"
        f"⏳ Дедлайн: Сегодня до 23:59 (МСК)\n\n"
        f"Чтобы забрать слот, нажмите кнопку «Взять слот», затем перейдите в бота по кнопке «Перейти к задаче»."
    )
    time_safe = time.replace(':', '-')
    callback_data = f"take_slot|{platform}|{count}|{date}|{time_safe}"
    url_to_bot = "https://t.me/ncjobbot?start"
    builder = InlineKeyboardBuilder()
    builder.button(text="✋ Взять слот", callback_data=callback_data)
    builder.button(text="🚀 Перейти к задаче", url=url_to_bot)
    builder.button(text="📋 Другие задания", url=OTHER_JOBS_CHANNEL)
    builder.adjust(1)
    sent_msg = await bot.send_message(
        chat_id=CHANNEL_ID, text=post_text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML
    )
    active_slots_dict[sent_msg.message_id] = {
        "platform": platform,
        "count": count,
        "initial_count": count,
        "row_ids": row_ids,
        "date": date,
        "time": time,
        "publish_time": datetime.now(moscow_tz),
        "attempt": attempt
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
        "from_menu": False
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
        "from_menu": True
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

    if request["from_menu"]:
        assigned_rows = request["row_ids"][:quantity]
        remaining_rows = request["row_ids"][quantity:]
        for msg_id, slot in list(active_slots.items()):
            if slot.get("platform") == request["platform"]:
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
        sheet = get_sheet()
        username = f"@{message.from_user.username}" if message.from_user.username else message.from_user.full_name
        for row_idx in assigned_rows:
            try:
                sheet.update_cell(row_idx, 11, username)
                sheet.update_cell(row_idx, 10, "в работе")
            except Exception as e:
                logger.error(f"Ошибка обновления строки {row_idx}: {e}")
        request["assigned_rows"] = assigned_rows
        request["current_index"] = 0
        request["state"] = "sending_reviews"
        await send_next_review(message, request, sheet)
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
        sheet = get_sheet()
        username = f"@{message.from_user.username}" if message.from_user.username else message.from_user.full_name
        for row_idx in assigned_rows:
            try:
                sheet.update_cell(row_idx, 11, username)
                sheet.update_cell(row_idx, 10, "в работе")
            except Exception as e:
                logger.error(f"Ошибка обновления строки {row_idx}: {e}")
        request["assigned_rows"] = assigned_rows
        request["current_index"] = 0
        request["state"] = "sending_reviews"
        await send_next_review(message, request, sheet)

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

    remaining_rows = assigned_rows[current_index:]

    if remaining_rows:
        sheet = get_sheet()
        if sheet:
            for row_idx in remaining_rows:
                try:
                    sheet.update_cell(row_idx, 10, "")
                    sheet.update_cell(row_idx, 11, "")
                except Exception as e:
                    logger.error(f"Ошибка очистки строки {row_idx} при отказе: {e}")
            if slot_info:
                slot_info["row_ids"].extend(remaining_rows)
                slot_info["count"] += len(remaining_rows)
                logger.info(f"Возвращено {len(remaining_rows)} отзывов в слот {slot_msg_id}")
            else:
                logger.info(f"Слот {slot_msg_id} неактивен, отзывы останутся свободными")
        else:
            await message.answer("❌ Ошибка доступа к таблице. Попробуйте позже.")
            return

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

    sheet = get_sheet()
    current_row = request["assigned_rows"][request["current_index"]]
    review_id = None
    if sheet:
        try:
            review_id = sheet.cell(current_row, 19).value
            if not review_id:
                review_id = secrets.token_hex(4)
                sheet.update_cell(current_row, 19, review_id)
        except Exception as e:
            logger.error(f"Не удалось получить/сгенерировать ID для строки {current_row}: {e}")
            review_id = "Unknown"

    try:
        user = get_user(user_id)
        user_mention = f"@{user['tg_username']}" if user and user.get('tg_username') else f"@{message.from_user.username}"
        timestamp = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        caption = f"{user_mention} – {timestamp}\nID отзыва: {review_id}"
        await message.bot.send_photo(
            chat_id=SCREENSHOT_CHANNEL_ID,
            photo=message.photo[-1].file_id,
            caption=caption
        )
    except Exception as e:
        logger.error(f"Не удалось переслать скриншот в канал: {e}")

    if sheet:
        try:
            sheet.update_cell(current_row, 10, "на модерации")
            sheet.update_cell(current_row, 9, 333)
            sheet.format(f"I{current_row}", {
                "backgroundColor": {"red": 0, "green": 0.8, "blue": 0}
            })
        except Exception as e:
            logger.error(f"Ошибка обновления статуса для строки {current_row}: {e}")

    request["current_index"] += 1
    request["state"] = "sending_reviews"
    await send_next_review(message, request, sheet)

# ---------- Отправка следующего отзыва ----------
async def send_next_review(message: Message, request: dict, sheet):
    assigned_rows = request["assigned_rows"]
    current_index = request["current_index"]
    if current_index >= len(assigned_rows):
        platform = request["platform"]
        if message.from_user.id not in cooldowns:
            cooldowns[message.from_user.id] = {}
        cooldowns[message.from_user.id][platform] = datetime.now() + timedelta(hours=24)
        await message.answer("✅ Все отзывы отправлены на модерацию. Спасибо за работу!")
        del slot_requests[message.from_user.id]
        return

    await send_instruction(message.from_user.id, message.bot)

    row_idx = assigned_rows[current_index]
    row = sheet.row_values(row_idx)
    if len(row) < 14:
        await message.answer("❌ Ошибка данных в таблице.")
        del slot_requests[message.from_user.id]
        return

    link = row[6]
    text = row[13]
    stars = row[2].strip() if len(row) > 2 else ""
    gender = row[12].strip().upper() if len(row) > 12 else ""
    platform = request["platform"]

    photo_link = row[17].strip() if len(row) > 17 else ""
    photo_warning = ""
    if photo_link:
        photo_warning = (
            "📸 <b>Фотография к ОБЯЗАТЕЛЬНОМУ прикреплению к отзыву!</b>\n"
            "Если вы не прикрепите фото, отзыв будет оплачен на 50% ниже.\n\n"
        )

    template = PLATFORM_TEMPLATES.get(platform, PLATFORM_TEMPLATES["яндекс"])
    instruction_text = template["instruction"]
    extra_text = template["extra_text"]
    warning = template["warning"]

    gender_text = ""
    if gender == "М":
        gender_text = "👨 Отзыв мужской. Его должен выполнить мужчина с мужским именем на картах."
    elif gender == "Ж":
        gender_text = "👩 Отзыв женский. Её должна выполнить женщина с женским именем на картах."
    else:
        gender_text = "👤 Отзыв без пола. Может выполнить и мужчина, и женщина. Главное – изменить род в тексте при отправке исполнителю (например, 'купил' → 'купила')."

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
