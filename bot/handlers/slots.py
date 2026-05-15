import logging
import os
from urllib.parse import quote
from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode
from bot.config import ADMIN_IDS, CHANNEL_ID, MANAGER_USERNAME, OTHER_JOBS_CHANNEL, SHEET_ID
from bot.database import is_registered, is_blocked, get_user
import gspread
from oauth2client.service_account import ServiceAccountCredentials

router = Router()
logger = logging.getLogger(__name__)
active_slots = {}

class TakeSlotState(StatesGroup):
    waiting_for_quantity = State()
    sending_reviews = State()
    waiting_for_screenshot = State()

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

def get_sheet():
    creds_path = "/data/google_key.json"
    if not os.path.exists(creds_path):
        creds_path = "google_key.json"
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(creds_path, scope)
    client = gspread.authorize(creds)
    return client.open_by_key(SHEET_ID).sheet1

MESSAGE_TEMPLATE = (
    "Здравствуйте, меня интересует слот {slot_name} ({price}). "
    "Обязуюсь отправить скриншот/ы до 23:59 МСК, с правилами ознакомлен."
)

# ---------- Ручная публикация (старые команды) ----------
async def publish_slot(message: Message, slot_name: str, post_text: str, price: str):
    raw_text = MESSAGE_TEMPLATE.format(slot_name=slot_name, price=price)
    encoded_text = quote(raw_text, safe='')
    url = f"https://t.me/{MANAGER_USERNAME}?text={encoded_text}"
    builder = InlineKeyboardBuilder()
    builder.button(text="✋ Взять слот", url=url)
    builder.button(text="📋 Другие задания", url=OTHER_JOBS_CHANNEL)
    builder.adjust(1)
    sent_msg = await message.bot.send_message(
        chat_id=CHANNEL_ID, text=post_text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML
    )
    active_slots[sent_msg.message_id] = {"command": slot_name, "price": price, "post_text": post_text}
    await message.answer(f"✅ Слот «{slot_name}» опубликован в канале! ID: {sent_msg.message_id}")

@router.message(Command("yandex"))
async def yandex_slot(message: Message):
    if not is_admin(message.from_user.id): return
    text = (
        "🔥 Слот: Яндекс карты\nЗадача: Выполнить отзыв/ы Яндекс карты\n"
        "Оплата: 150 руб/шт\nДедлайн: Сегодня до 23:59 (МСК)\n"
        "Требуется человек: До закрытия слота.\nНажмите кнопку ниже, чтобы забрать слот."
    )
    await publish_slot(message, "Яндекс карты", text, "150₽")

@router.message(Command("google"))
async def google_slot(message: Message):
    if not is_admin(message.from_user.id): return
    text = (
        "🔥 Слот: GOOGLE\nЗадача: Выполнить отзыв/ы GOOGLE\nОплата: 50 руб/шт\n"
        "Дедлайн: Сегодня до 23:59 (МСК)\nТребуется человек: До закрытия слота.\n"
        "Нажмите кнопку ниже, чтобы забрать слот."
    )
    await publish_slot(message, "GOOGLE", text, "50₽")

@router.message(Command("gis"))
async def gis_slot(message: Message):
    if not is_admin(message.from_user.id): return
    text = (
        "🔥 Слот: 2ГИС\nЗадача: Выполнить отзыв/ы 2ГИС\nОплата: 50 руб/шт\n"
        "Дедлайн: Сегодня до 23:59 (МСК)\nТребуется человек: До закрытия слота.\n"
        "Нажмите кнопку ниже, чтобы забрать слот."
    )
    await publish_slot(message, "2ГИС", text, "50₽")

@router.message(Command("avito"))
async def avito_slot(message: Message):
    if not is_admin(message.from_user.id): return
    text = (
        "🔥 Слот: Авито\nЗадача: Выполнить отзыв/ы Авито\nОплата: 700 руб/шт\n"
        "Дедлайн: 2 суток с момента принятия слота\nТребуется человек: До закрытия слота.\n"
        "Нажмите кнопку ниже, чтобы забрать слот."
    )
    await publish_slot(message, "Авито", text, "700₽")

@router.message(Command("vk"))
async def vk_slot(message: Message):
    if not is_admin(message.from_user.id): return
    text = (
        "🔥 Слот: ВК\nЗадача: Выполнить отзыв/ы ВК\nОплата: 50 руб/шт\n"
        "Дедлайн: Сегодня до 23:59 (МСК)\nТребуется человек: До закрытия слота.\n"
        "Нажмите кнопку ниже, чтобы забрать слот."
    )
    await publish_slot(message, "ВК", text, "50₽")

@router.message(Command("otzovik"))
async def otzovik_slot(message: Message):
    if not is_admin(message.from_user.id): return
    text = (
        "🔥 Слот: Отзовик\nЗадача: Выполнить отзыв/ы ОТЗОВИК\nОплата: 100 руб/шт\n"
        "Дедлайн: Сегодня до 23:59 (МСК)\nТребуется человек: До закрытия слота.\n"
        "Нажмите кнопку ниже, чтобы забрать слот."
    )
    await publish_slot(message, "Отзовик", text, "100₽")

@router.message(Command("doctoru"))
async def doctoru_slot(message: Message):
    if not is_admin(message.from_user.id): return
    text = (
        "🔥 Слот: Doctoru\nЗадача: Выполнить отзыв/ы Doctoru\nОплата: 100 руб/шт\n"
        "Дедлайн: Сегодня до 23:59 (МСК)\nТребуется человек: До закрытия слота.\n"
        "Нажмите кнопку ниже, чтобы забрать слот."
    )
    await publish_slot(message, "Doctoru", text, "100₽")

# ---------- Планирование автослота ----------
async def publish_scheduled_slot(bot, active_slots_dict, platform: str, count: int,
                                 date: str, time: str, row_ids: list):
    platform_names = {
        "яндекс": "Яндекс", "google": "Google", "2гис": "2ГИС",
        "авито": "Авито", "вк": "ВК", "отзовик": "Otzovik", "доктору": "Doctoru"
    }
    pretty_name = platform_names.get(platform, platform)
    post_text = (
        f"🔥 Слот: {pretty_name}\n"
        f"📅 Дата: {date}\n"
        f"⏰ Время: {time} (МСК)\n"
        f"📌 Доступно отзывов: {count} шт.\n"
        f"⏳ Дедлайн: Сегодня до 23:59 (МСК)\n\n"
        f"Нажмите кнопку ниже, чтобы забрать слот."
    )
    time_safe = time.replace(':', '-')
    builder = InlineKeyboardBuilder()
    builder.button(
        text="✋ Взять слот",
        callback_data=f"take_slot|{platform}|{count}|{date}|{time_safe}"
    )
    builder.button(text="📋 Другие задания", url=OTHER_JOBS_CHANNEL)
    builder.adjust(1)
    sent_msg = await bot.send_message(
        chat_id=CHANNEL_ID, text=post_text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML
    )
    active_slots_dict[sent_msg.message_id] = {
        "platform": platform, "count": count, "row_ids": row_ids,
        "date": date, "time": time
    }

# ---------- Обработчик кнопки "Взять слот" ----------
@router.callback_query(F.data.startswith("take_slot|"))
async def take_slot_start(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    if not is_registered(user_id):
        await callback.answer("❌ Вы не зарегистрированы.", show_alert=True)
        return
    if is_blocked(user_id):
        await callback.answer("⛔ Вы заблокированы.", show_alert=True)
        return

    parts = callback.data.split("|")
    # Ожидаем ровно 5 частей: take_slot, platform, count, date, time_safe
    if len(parts) != 5:
        await callback.answer("Некорректный запрос.", show_alert=True)
        return

    _, platform, count_str, date, time_safe = parts
    count = int(count_str)
    time = time_safe.replace('-', ':')

    await state.update_data(
        platform=platform, count=count, date=date, time=time,
        slot_msg_id=callback.message.message_id
    )
    await state.set_state(TakeSlotState.waiting_for_quantity)
  await callback.bot.send_message(
    chat_id=user_id,
    text=f"📊 Доступно отзывов: {count} шт.\nСколько вы готовы выполнить? (напишите число)"
)
    await callback.answer()

@router.message(TakeSlotState.waiting_for_quantity)
async def process_quantity(message: Message, state: FSMContext):
    try:
        quantity = int(message.text.strip())
    except:
        await message.answer("Пожалуйста, введите число.")
        return

    data = await state.get_data()
    available = data["count"]
    if quantity > available or quantity <= 0:
        await message.answer(f"❌ Можно взять от 1 до {available} отзывов.")
        return

    slot_msg_id = data["slot_msg_id"]
    slot_info = active_slots.get(slot_msg_id)
    if not slot_info:
        await message.answer("❌ Этот слот уже неактивен.")
        await state.clear()
        return

    row_ids = slot_info["row_ids"]
    if len(row_ids) < quantity:
        await message.answer("❌ Количество свободных отзывов изменилось. Попробуйте заново.")
        await state.clear()
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
            sheet.update_cell(row_idx, 5, 5)          # E = 5
            sheet.update_cell(row_idx, 11, username)   # K
            sheet.update_cell(row_idx, 10, "в работе") # J
        except Exception as e:
            logger.error(f"Ошибка обновления строки {row_idx}: {e}")

    await state.update_data(assigned_rows=assigned_rows, current_index=0)
    await state.set_state(TakeSlotState.sending_reviews)
    await send_next_review(message, state, sheet)

async def send_next_review(message: Message, state: FSMContext, sheet):
    data = await state.get_data()
    assigned_rows = data["assigned_rows"]
    current_index = data["current_index"]

    if current_index >= len(assigned_rows):
        await message.answer("✅ Все отзывы отправлены. Спасибо за работу!")
        await state.clear()
        return

    row_idx = assigned_rows[current_index]
    row = sheet.row_values(row_idx)
    if len(row) < 14:
        await message.answer("❌ Ошибка данных в таблице.")
        await state.clear()
        return

    link = row[6]   # G
    text = row[13]  # N
    gender = row[12].strip().upper() if len(row) > 12 else ""

    msg_text = f"{link}\n{text}\n{current_index+1}"
    if gender == "М":
        msg_text += "\n👨 Отзыв мужской. Его должен выполнить мужчина с мужским именем на картах."
    elif gender == "Ж":
        msg_text += "\n👩 Отзыв женский. Её должна выполнить женщина с женским именем на картах."
    else:
        msg_text += "\n👤 Отзыв без пола. Может выполнить мужчина или женщина, меняйте род в тексте (например, 'купил' на 'купила')."

    msg_text += "\n\nПожалуйста, пришлите скриншот подтверждения."
    await message.answer(msg_text)
    await state.set_state(TakeSlotState.waiting_for_screenshot)

@router.message(TakeSlotState.waiting_for_screenshot, F.photo)
async def receive_screenshot(message: Message, state: FSMContext):
    data = await state.get_data()
    current_index = data["current_index"]
    await state.update_data(current_index=current_index + 1)
    await state.set_state(TakeSlotState.sending_reviews)
    sheet = get_sheet()
    await send_next_review(message, state, sheet)

@router.message(TakeSlotState.waiting_for_screenshot)
async def non_photo_in_screenshot_state(message: Message):
    await message.answer("Ожидается скриншот (фото). Пожалуйста, пришлите изображение.")

# ---------- Команды просмотра/закрытия ----------
@router.message(Command("slots"))
async def list_slots(message: Message):
    if not is_admin(message.from_user.id): return
    if not active_slots:
        await message.answer("Нет активных слотов.")
        return
    lines = ["Активные слоты (ID):"]
    for msg_id, data in active_slots.items():
        lines.append(f"🔸 {data.get('command', data.get('platform', '?'))} {data.get('price', data.get('count', '?'))} — ID: {msg_id}")
    await message.answer("\n".join(lines))

@router.message(Command("close"))
async def close_slot(message: Message):
    if not is_admin(message.from_user.id): return
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
    if not is_admin(message.from_user.id): return
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
