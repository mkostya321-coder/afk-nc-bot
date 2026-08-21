import logging, os
from urllib.parse import quote
from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode
from bot.config import ADMIN_IDS, CHANNEL_ID, MANAGER_USERNAME, OTHER_JOBS_CHANNEL, SHEET_ID, SCREENSHOT_CHANNEL_ID, get_credentials_path
from bot.database import is_registered, is_blocked, get_user, is_ga
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

# ---------- Ручная публикация (обновлённые кнопки) ----------
async def publish_slot(message: Message, slot_name: str, post_text: str, price: str):
    raw_text = MESSAGE_TEMPLATE.format(slot_name=slot_name, price=price)
    encoded_text = quote(raw_text, safe='')
    url_to_bot = f"https://t.me/ncjobbot?start"  # или можно без start
    url_manager = f"https://t.me/{MANAGER_USERNAME}?text={encoded_text}"
    # Новая клавиатура: три кнопки
    builder = InlineKeyboardBuilder()
    builder.button(text="✋ Взять слот", callback_data="take_manual_slot")  # временный колбэк, но для ручных мы не используем callback, а ссылку на менеджера? Но по новому требованию, вероятно, нужно сделать callback как в автолотах. Но ручные команды созданы для админов, они могут остаться как есть с ссылкой на менеджера. Однако для единообразия я добавлю callback, но тогда нужно обрабатывать. Лучше оставить как было, но добавить кнопку "Перейти к задаче". Так как ручные слоты используются редко, я просто добавлю вторую кнопку.
    # Но чтобы не усложнять, я оставлю для ручных слотов: первая кнопка "Взять слот" (ссылка на менеджера), вторая "Перейти к задаче" (ссылка на бота), третья "Другие задания".
    builder.button(text="✋ Взять слот", url=url_manager)
    builder.button(text="🚀 Перейти к задаче", url=url_to_bot)
    builder.button(text="📋 Другие задания", url=OTHER_JOBS_CHANNEL)
    builder.adjust(1)  # все в столбик (можно adjust(1) или по 1)
    sent_msg = await message.bot.send_message(
        chat_id=CHANNEL_ID, text=post_text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML
    )
    active_slots[sent_msg.message_id] = {"command": slot_name, "price": price, "post_text": post_text}
    await message.answer(f"✅ Слот «{slot_name}» опубликован в канале! ID: {sent_msg.message_id}")

# Остальные команды без изменений, они вызывают publish_slot

@router.message(Command("yandex"))
async def yandex_slot(message: Message):
    if not is_ga(message.from_user.id): return
    text = (
        "🔥 Слот: Яндекс карты\nЗадача: Выполнить отзыв/ы Яндекс карты\n"
        "Оплата: 150 руб/шт\nДедлайн: Сегодня до 23:59 (МСК)\n"
        "Требуется человек: До закрытия слота.\n"
        "Чтобы забрать слот, нажмите кнопку «Взять слот», затем перейдите в бота по кнопке «Перейти к задаче»."
    )
    await publish_slot(message, "Яндекс карты", text, "150₽")

# Аналогично для остальных команд, просто меняем текст, добавляя фразу про кнопки.
# Я приведу все, но чтобы не дублировать, можно просто изменить шаблон publish_slot, чтобы он добавлял эту фразу автоматически.
# Но для ручных команд текст задаётся вручную, поэтому нужно изменить каждую.
# Давайте я напишу полный набор с обновлённым текстом.

@router.message(Command("google"))
async def google_slot(message: Message):
    if not is_ga(message.from_user.id): return
    text = (
        "🔥 Слот: GOOGLE\nЗадача: Выполнить отзыв/ы GOOGLE\nОплата: 50 руб/шт\n"
        "Дедлайн: Сегодня до 23:59 (МСК)\nТребуется человек: До закрытия слота.\n"
        "Чтобы забрать слот, нажмите кнопку «Взять слот», затем перейдите в бота по кнопке «Перейти к задаче»."
    )
    await publish_slot(message, "GOOGLE", text, "50₽")

@router.message(Command("gis"))
async def gis_slot(message: Message):
    if not is_ga(message.from_user.id): return
    text = (
        "🔥 Слот: 2ГИС\nЗадача: Выполнить отзыв/ы 2ГИС\nОплата: 50 руб/шт\n"
        "Дедлайн: Сегодня до 23:59 (МСК)\nТребуется человек: До закрытия слота.\n"
        "Чтобы забрать слот, нажмите кнопку «Взять слот», затем перейдите в бота по кнопке «Перейти к задаче»."
    )
    await publish_slot(message, "2ГИС", text, "50₽")

@router.message(Command("avito"))
async def avito_slot(message: Message):
    if not is_ga(message.from_user.id): return
    text = (
        "🔥 Слот: Авито\nЗадача: Выполнить отзыв/ы Авито\nОплата: 700 руб/шт\n"
        "Дедлайн: 2 суток с момента принятия слота\nТребуется человек: До закрытия слота.\n"
        "Чтобы забрать слот, нажмите кнопку «Взять слот», затем перейдите в бота по кнопке «Перейти к задаче»."
    )
    await publish_slot(message, "Авито", text, "700₽")

@router.message(Command("vk"))
async def vk_slot(message: Message):
    if not is_ga(message.from_user.id): return
    text = (
        "🔥 Слот: ВК\nЗадача: Выполнить отзыв/ы ВК\nОплата: 50 руб/шт\n"
        "Дедлайн: Сегодня до 23:59 (МСК)\nТребуется человек: До закрытия слота.\n"
        "Чтобы забрать слот, нажмите кнопку «Взять слот», затем перейдите в бота по кнопке «Перейти к задаче»."
    )
    await publish_slot(message, "ВК", text, "50₽")

@router.message(Command("otzovik"))
async def otzovik_slot(message: Message):
    if not is_ga(message.from_user.id): return
    text = (
        "🔥 Слот: Отзовик\nЗадача: Выполнить отзыв/ы ОТЗОВИК\nОплата: 100 руб/шт\n"
        "Дедлайн: Сегодня до 23:59 (МСК)\nТребуется человек: До закрытия слота.\n"
        "Чтобы забрать слот, нажмите кнопку «Взять слот», затем перейдите в бота по кнопке «Перейти к задаче»."
    )
    await publish_slot(message, "Отзовик", text, "100₽")

@router.message(Command("doctoru"))
async def doctoru_slot(message: Message):
    if not is_ga(message.from_user.id): return
    text = (
        "🔥 Слот: Doctoru\nЗадача: Выполнить отзыв/ы Doctoru\nОплата: 100 руб/шт\n"
        "Дедлайн: Сегодня до 23:59 (МСК)\nТребуется человек: До закрытия слота.\n"
        "Чтобы забрать слот, нажмите кнопку «Взять слот», затем перейдите в бота по кнопке «Перейти к задаче»."
    )
    await publish_slot(message, "Doctoru", text, "100₽")

@router.message(Command("dokdok"))
async def dokdok_slot(message: Message):
    if not is_ga(message.from_user.id): return
    text = (
        "🔥 Слот: ДокДок\nЗадача: Выполнить отзыв/ы ДокДок\nОплата: 100 руб/шт\n"
        "Дедлайн: Сегодня до 23:59 (МСК)\nТребуется человек: До закрытия слота.\n"
        "Чтобы забрать слот, нажмите кнопку «Взять слот», затем перейдите в бота по кнопке «Перейти к задаче»."
    )
    await publish_slot(message, "ДокДок", text, "100₽")

@router.message(Command("prodoctors"))
async def prodoctors_slot(message: Message):
    if not is_ga(message.from_user.id): return
    text = (
        "🔥 Слот: Про Докторов\nЗадача: Выполнить отзыв/ы Про Докторов\nОплата: 180 руб/шт\n"
        "Дедлайн: Сегодня до 23:59 (МСК)\nТребуется человек: До закрытия слота.\n"
        "Чтобы забрать слот, нажмите кнопку «Взять слот», затем перейдите в бота по кнопке «Перейти к задаче»."
    )
    await publish_slot(message, "Про Докторов", text, "180₽")

@router.message(Command("doctu"))
async def doctu_slot(message: Message):
    if not is_ga(message.from_user.id): return
    text = (
        "🔥 Слот: ДокТу\nЗадача: Выполнить отзыв/ы ДокТу\nОплата: 110 руб/шт\n"
        "Дедлайн: Сегодня до 23:59 (МСК)\nТребуется человек: До закрытия слота.\n"
        "Чтобы забрать слот, нажмите кнопку «Взять слот», затем перейдите в бота по кнопке «Перейти к задаче»."
    )
    await publish_slot(message, "ДокТу", text, "110₽")

@router.message(Command("32top"))
async def top32_slot(message: Message):
    if not is_ga(message.from_user.id): return
    text = (
        "🔥 Слот: 32ТОП\nЗадача: Выполнить отзыв/ы 32ТОП\nОплата: 100 руб/шт\n"
        "Дедлайн: Сегодня до 23:59 (МСК)\nТребуется человек: До закрытия слота.\n"
        "Чтобы забрать слот, нажмите кнопку «Взять слот», затем перейдите в бота по кнопке «Перейти к задаче»."
    )
    await publish_slot(message, "32ТОП", text, "100₽")

# ---------- Планирование автослота (обновлённая клавиатура) ----------
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
    url_to_bot = "https://t.me/ncjobbot?start"  # ссылка на бота
    builder = InlineKeyboardBuilder()
    builder.button(text="✋ Взять слот", callback_data=callback_data)
    builder.button(text="🚀 Перейти к задаче", url=url_to_bot)
    builder.button(text="📋 Другие задания", url=OTHER_JOBS_CHANNEL)
    builder.adjust(1)  # все в столбик
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

# ---------- Обработчик кнопки взять слот (без изменений) ----------
@router.callback_query(F.data.startswith("take_slot|"))
async def take_slot_start(callback: CallbackQuery):
    user_id = callback.from_user.id
    if not is_registered(user_id):
        await callback.answer("❌ Вы не зарегистрированы.", show_alert=True)
        return
    if is_blocked(user_id):
        await callback.answer("⛔ Вы заблокированы.", show_alert=True)
        return
    parts = callback.data.split("|")
    if len(parts) < 5:
        await callback.answer("Некорректный запрос.", show_alert=True)
        return
    _, platform, count_str, date, time_safe = parts
    count = int(count_str)
    time = time_safe.replace('-', ':')
    slot_msg_id = callback.message.message_id
    slot_info = active_slots.get(slot_msg_id)
    if not slot_info:
        await callback.answer("❌ Этот слот уже неактивен.", show_alert=True)
        return
    if user_id in cooldowns and platform in cooldowns[user_id]:
        if datetime.now() < cooldowns[user_id][platform]:
            await callback.answer(f"⏳ Вы уже брали {platform}. Повторно можно будет через 24 часа.", show_alert=True)
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
        "row_ids": slot_info["row_ids"]
    }
    await callback.bot.send_message(
        chat_id=user_id,
        text=f"📊 Доступно отзывов: {count} шт.\nСколько вы готовы выполнить? (напишите число)"
    )
    await callback.answer()

# ---------- Обработчик ввода количества (без изменений) ----------
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
            sheet.update_cell(row_idx, 11, username)   # K
            sheet.update_cell(row_idx, 10, "в работе") # J
        except Exception as e:
            logger.error(f"Ошибка обновления строки {row_idx}: {e}")
    request["assigned_rows"] = assigned_rows
    request["current_index"] = 0
    request["state"] = "sending_reviews"
    await send_next_review(message, request, sheet)

# ---------- Обработка скриншотов (без изменений) ----------
@router.message(F.photo)
async def handle_screenshot(message: Message):
    user_id = message.from_user.id
    if user_id not in slot_requests:
        return
    request = slot_requests[user_id]
    if request["state"] != "waiting_screenshot":
        return
    try:
        user = get_user(user_id)
        user_mention = f"@{user['tg_username']}" if user and user.get('tg_username') else f"@{message.from_user.username}"
        timestamp = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        caption = f"{user_mention} – {timestamp}"
        await message.bot.send_photo(
            chat_id=SCREENSHOT_CHANNEL_ID,
            photo=message.photo[-1].file_id,
            caption=caption
        )
    except Exception as e:
        logger.error(f"Не удалось переслать скриншот в канал: {e}")
    request["current_index"] += 1
    request["state"] = "sending_reviews"
    sheet = get_sheet()
    await send_next_review(message, request, sheet)

async def send_next_review(message: Message, request: dict, sheet):
    assigned_rows = request["assigned_rows"]
    current_index = request["current_index"]
    if current_index >= len(assigned_rows):
        for row_idx in assigned_rows:
            try:
                sheet.update_cell(row_idx, 10, "на модерации")  # J
            except Exception as e:
                logger.error(f"Не удалось обновить статус для строки {row_idx}: {e}")
        platform = request["platform"]
        if message.from_user.id not in cooldowns:
            cooldowns[message.from_user.id] = {}
        cooldowns[message.from_user.id][platform] = datetime.now() + timedelta(hours=24)
        await message.answer("✅ Все отзывы отправлены на модерацию. Спасибо за работу!")
        del slot_requests[message.from_user.id]
        return
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
    info_msg = (
        f"⭐ Количество звезд: {stars}\n"
        "👥 ОТЗЫВЫ ПУБЛИКУЮТ РАЗНЫЕ ЛЮДИ – 1 ЧЕЛОВЕК 1 ОТЗЫВ\n"
    )
    if gender == "М":
        info_msg += "👨 Отзыв мужской. Его должен выполнить мужчина с мужским именем на картах.\n"
    elif gender == "Ж":
        info_msg += "👩 Отзыв женский. Её должна выполнить женщина с женским именем на картах.\n"
    else:
        info_msg += "👤 Отзыв без пола. Может выполнить и мужчина, и женщина. Главное – изменить род в тексте при отправке исполнителю (например, 'купил' → 'купила').\n"
    info_msg += "💡 Чтобы повысить шанс прохода отзыва, рекомендуем просмотреть 5-10 фотографий и посидеть на карточке 1-2 минуты.\n\nПожалуйста, после выполнения пришлите скриншот отзыва."
    await message.answer(info_msg)
    await message.answer(link)
    await message.answer(text)
    await message.answer("Ожидаю скриншот и продолжаем работу.")
    request["state"] = "waiting_screenshot"

# ---------- Команды просмотра/закрытия (без изменений) ----------
@router.message(Command("slots"))
async def list_slots(message: Message):
    if not is_ga(message.from_user.id): return
    if not active_slots:
        await message.answer("Нет активных слотов.")
        return
    lines = ["Активные слоты (ID):"]
    for msg_id, data in active_slots.items():
        lines.append(f"🔸 {data.get('command', data.get('platform', '?'))} {data.get('price', data.get('count', '?'))} — ID: {msg_id}")
    await message.answer("\n".join(lines))

@router.message(Command("close"))
async def close_slot(message: Message):
    if not is_ga(message.from_user.id): return
    try:
        _, slot_id = message.text.split()
        slot_id = int(slot_id)
    except:
        await message.answer("Использование: /close <ID>")
        return
    if slot_id not in active_slots:
        await message.answer("❌ Слот не найден.")
        return
    data = active_slots.pop(slot_id)
    await message.bot.edit_message_text(
        chat_id=CHANNEL_ID, message_id=slot_id,
        text="Извините, данный слот устарел или был закрыт…"
    )
    await message.answer(f"✅ Слот «{data.get('command', data.get('platform', '?'))}» закрыт.")

@router.message(Command("closeall"))
async def close_all_slots(message: Message):
    if not is_ga(message.from_user.id): return
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
