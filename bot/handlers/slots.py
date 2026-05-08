import logging
from urllib.parse import quote
from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode
from bot.config import ADMIN_IDS, CHANNEL_ID, MANAGER_USERNAME, OTHER_JOBS_CHANNEL, SHEET_ID
from bot.database import is_registered, is_blocked, get_user
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import asyncio

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

async def publish_scheduled_slot(bot, active_slots_dict, platform: str, count: int,
                                 date: str, time: str, row_ids: list):
    platform_names = {
        "яндекс": "Яндекс",
        "google": "Google",
        "2гис": "2ГИС",
        "авито": "Авито",
        "вк": "ВК",
        "отзовик": "Otzovik",
        "доктору": "Doctoru"
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

    builder = InlineKeyboardBuilder()
    # callback_data включает ID слота и количество
    builder.button(text="✋ Взять слот", callback_data=f"take_slot:{platform}:{count}:{date}:{time}")
    builder.button(text="📋 Другие задания", url=OTHER_JOBS_CHANNEL)
    builder.adjust(1)

    sent_msg = await bot.send_message(
        chat_id=CHANNEL_ID,
        text=post_text,
        reply_markup=builder.as_markup(),
        parse_mode=ParseMode.HTML
    )

    active_slots_dict[sent_msg.message_id] = {
        "platform": platform,
        "count": count,
        "row_ids": row_ids,
        "date": date,
        "time": time
    }

# ---------- Обработчик кнопки "Взять слот" ----------
@router.callback_query(F.data.startswith("take_slot:"))
async def take_slot_start(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    if not is_registered(user_id):
        await callback.answer("❌ Вы не зарегистрированы. Пройдите регистрацию.", show_alert=True)
        return
    if is_blocked(user_id):
        await callback.answer("⛔ Вы заблокированы.", show_alert=True)
        return

    # Разбираем callback_data: take_slot:platform:count:date:time
    parts = callback.data.split(":")
    if len(parts) < 6:
        await callback.answer("Некорректный запрос.", show_alert=True)
        return
    _, platform, count_str, date, time = parts
    count = int(count_str)

    # Сохраняем в состоянии
    await state.update_data(
        platform=platform, count=count, date=date, time=time,
        slot_msg_id=callback.message.message_id  # ID сообщения слота в канале
    )
    await state.set_state(TakeSlotState.waiting_for_quantity)
    await callback.message.answer(
        f"📊 Доступно отзывов: {count} шт.\n"
        f"Сколько вы готовы выполнить? (напишите число)"
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

    # Бронируем строки: берём первые quantity свободных строк из row_ids
    slot_msg_id = data["slot_msg_id"]
    slot_info = active_slots.get(slot_msg_id)
    if not slot_info:
        await message.answer("❌ Этот слот уже неактивен.")
        await state.clear()
        return

    row_ids = slot_info["row_ids"]
    if len(row_ids) < quantity:
        await message.answer("❌ К сожалению, количество свободных отзывов изменилось. Попробуйте заново.")
        await state.clear()
        return

    # Выделяем нужное количество строк (первые по порядку)
    assigned_rows = row_ids[:quantity]
    # Удаляем их из доступных у слота
    slot_info["row_ids"] = row_ids[quantity:]
    slot_info["count"] -= quantity
    # Если слот опустел – удалим его из active_slots (или пометим как закрытый)
    if slot_info["count"] == 0:
        del active_slots[slot_msg_id]
        # Обновим сообщение в канале (закроем)
        try:
            await message.bot.edit_message_text(
                chat_id=CHANNEL_ID,
                message_id=slot_msg_id,
                text="Все отзывы этого слота разобраны."
            )
        except:
            pass

    # Помечаем строки в таблице (E=5, K=username, J="в работе")
    sheet = get_sheet()
    username = f"@{message.from_user.username}" if message.from_user.username else message.from_user.full_name
    for row_idx in assigned_rows:
        try:
            sheet.update_cell(row_idx, 5, 5)          # E
            sheet.update_cell(row_idx, 11, username)   # K (исполнитель)
            sheet.update_cell(row_idx, 10, "в работе") # J
        except Exception as e:
            logger.error(f"Ошибка обновления строки {row_idx}: {e}")

    # Сохраняем список строк и текущий индекс в состоянии
    await state.update_data(assigned_rows=assigned_rows, current_index=0)
    await state.set_state(TakeSlotState.sending_reviews)

    # Начинаем отправку первого отзыва
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
    # Читаем данные из таблицы для этой строки
    row = sheet.row_values(row_idx)
    if len(row) < 14:
        await message.answer("❌ Ошибка данных в таблице.")
        await state.clear()
        return

    link = row[6]   # G
    text = row[13]  # N
    gender = row[12].strip().upper() if len(row) > 12 else ""  # M (столбец 13, индекс 12)

    # Формируем сообщение
    msg_text = f"{link}\n{text}\n{current_index+1}"
    if gender == "М":
        msg_text += "\n👨 Отзыв мужской. Его должен выполнить мужчина с мужским именем на картах."
    elif gender == "Ж":
        msg_text += "\n👩 Отзыв женский. Его должна выполнить женщина с женским именем на картах."
    else:
        msg_text += "\n👤 Отзыв без пола. Может выполнить мужчина или женщина, меняйте род в тексте (например, 'купил' на 'купила')."

    msg_text += "\n\nПожалуйста, пришлите скриншот подтверждения."

    await message.answer(msg_text)
    await state.set_state(TakeSlotState.waiting_for_screenshot)

@router.message(TakeSlotState.waiting_for_screenshot, F.photo)
async def receive_screenshot(message: Message, state: FSMContext):
    data = await state.get_data()
    current_index = data["current_index"]
    # Увеличиваем индекс и отправляем следующий
    await state.update_data(current_index=current_index + 1)
    await state.set_state(TakeSlotState.sending_reviews)
    sheet = get_sheet()
    await send_next_review(message, state, sheet)

@router.message(TakeSlotState.waiting_for_screenshot)
async def non_photo_in_screenshot_state(message: Message):
    await message.answer("Ожидается скриншот (фото). Пожалуйста, пришлите изображение.")

# ---------- Остальные команды (публикация вручную, /slots, /close, /closeall) без изменений ----------
# (оставьте их, как в вашем текущем файле)
