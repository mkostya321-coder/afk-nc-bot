# bot/logging_helpers.py
import logging
from datetime import datetime
from aiogram import Bot
from bot.config import LOG_USER_ID, LOG_USER_THREAD_ID

logger = logging.getLogger(__name__)

HEADERS = {
    "register": "🆕 <b>РЕГИСТРАЦИЯ</b>",
    "take_slot": "🎯 <b>ВЗЯЛ СЛОТ</b>",
    "cancel": "🚫 <b>ОТКАЗ ОТ СЛОТА</b>",
    "complete": "✅ <b>ВСЕ СКРИНЫ СДАНЫ</b>",
    "support": "🆘 <b>ПОДДЕРЖКА</b>",
    "tiktok": "🎬 <b>TIKTOK</b>",
    "collab": "🤝 <b>СОТРУДНИЧЕСТВО</b>",
    "blocked": "⛔ <b>ЮЗЕР ЗАБЛОКИРОВАЛ БОТА</b>",
    "unslot": "✂️ <b>СЛОТ СНЯТ АДМИНОМ</b>",
}


async def log_user_event(bot: Bot, event_type: str, text: str):
    """
    Отправляет событие пользователя в LOG_USER_ID беседу.
    event_type: register | take_slot | cancel | complete | support | tiktok | collab | blocked | unslot
    Не бросает исключений — если что-то упало, просто логирует warning.
    """
    if not LOG_USER_ID:
        return
    try:
        header = HEADERS.get(event_type, "📌 <b>СОБЫТИЕ</b>")
        ts = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        msg = f"{header}\n{text}\n🕒 {ts}"
        await bot.send_message(
            chat_id=LOG_USER_ID,
            text=msg,
            message_thread_id=LOG_USER_THREAD_ID or None,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    except Exception as e:
        logger.warning(f"⚠️ log_user_event[{event_type}]: {e}")
