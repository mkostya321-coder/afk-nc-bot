import logging
from urllib.parse import quote
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode
from bot.config import ADMIN_IDS, CHANNEL_ID, MANAGER_USERNAME, OTHER_JOBS_CHANNEL
from bot.database import is_registered, is_blocked

router = Router()
logger = logging.getLogger(__name__)
active_slots = {}

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

MESSAGE_TEMPLATE = (
    "Здравствуйте, меня интересует слот {slot_name} ({price}). "
    "Обязуюсь отправить скриншот/ы до 23:59 МСК, с правилами ознакомлен."
)

async def publish_slot(message: Message, slot_name: str, post_text: str, price: str):
    raw_text = MESSAGE_TEMPLATE.format(slot_name=slot_name, price=price)
    encoded_text = quote(raw_text, safe='')
    url = f"https://t.me/{MANAGER_USERNAME}?text={encoded_text}"

    builder = InlineKeyboardBuilder()
    builder.button(text="✋ Взять слот", url=url)
    builder.button(text="📋 Другие задания", url=OTHER_JOBS_CHANNEL)
    builder.adjust(1)

    sent_msg = await message.bot.send_message(
        chat_id=CHANNEL_ID,
        text=post_text,
        reply_markup=builder.as_markup(),
        parse_mode=ParseMode.HTML
    )
    active_slots[sent_msg.message_id] = {
        "command": slot_name,
        "price": price,
        "post_text": post_text
    }
    await message.answer(f"✅ Слот «{slot_name}» опубликован в канале! ID: {sent_msg.message_id}")


async def publish_scheduled_slot(bot, active_slots_dict, platform: str, count: int,
                                 date: str, time: str, row_ids: list):
    """Публикует автоматический слот в канале (без привязки к сообщению пользователя)."""
    # Красивое название платформы
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
    # Пока оставляем прямую ссылку на менеджера, позже заменим на callback
    url = f"https://t.me/{MANAGER_USERNAME}?text=Здравствуйте, хочу взять слот {pretty_name}"
    builder.button(text="✋ Взять слот", url=url)
    builder.button(text="📋 Другие задания", url=OTHER_JOBS_CHANNEL)
    builder.adjust(1)

    sent_msg = await bot.send_message(
        chat_id=CHANNEL_ID,
        text=post_text,
        reply_markup=builder.as_markup(),
        parse_mode=ParseMode.HTML
    )

    # Сохраняем слот с row_ids для дальнейшей раздачи
    active_slots_dict[sent_msg.message_id] = {
        "command": pretty_name,
        "price": f"{count} шт.",
        "post_text": post_text,
        "platform": platform,
        "available": count,
        "row_ids": row_ids,
        "date": date,
        "time": time
    }
    logger.info(f"Автослот {pretty_name} опубликован (ID: {sent_msg.message_id}), строк: {row_ids}")


# ---------- Команды публикации (вручную, только для админов) ----------
@router.message(Command("yandex"))
async def yandex_slot(message: Message):
    if not is_admin(message.from_user.id): return
    text = (
        "🔥 Слот: Яндекс карты\n"
        "Задача: Выполнить отзыв/ы Яндекс карты\n"
        "Оплата: 150 руб/шт\n"
        "Дедлайн: Сегодня до 23:59 (МСК)\n"
        "Требуется человек: До закрытия слота.\n"
        "Нажмите кнопку ниже, чтобы забрать слот."
    )
    await publish_slot(message, "Яндекс карты", text, "150₽")

# Остальные команды (/google, /gis, /avito, /vk, /otzovik, /doctoru) идентичны, я их опускаю для краткости.
# Обязательно оставьте их в вашем файле!

# ---------- Команды просмотра и закрытия слотов (админы) ----------
@router.message(Command("slots"))
async def list_slots(message: Message):
    if not is_admin(message.from_user.id): return
    if not active_slots:
        await message.answer("Нет активных слотов.")
        return
    lines = ["Активные слоты (ID):"]
    for msg_id, data in active_slots.items():
        lines.append(f"🔸 {data['command']} {data['price']} — ID: {msg_id}")
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
        chat_id=CHANNEL_ID,
        message_id=slot_id,
        text="Извините, данный слот устарел или был закрыт…"
    )
    await message.answer(f"✅ Слот «{data['command']}» закрыт.")

@router.message(Command("closeall"))
async def close_all_slots(message: Message):
    if not is_admin(message.from_user.id): return
    for slot_id in list(active_slots.keys()):
        try:
            await message.bot.edit_message_text(
                chat_id=CHANNEL_ID,
                message_id=slot_id,
                text="Извините, данный слот устарел или был закрыт…"
            )
        except:
            pass
        del active_slots[slot_id]
    await message.answer("✅ Все слоты закрыты.")
