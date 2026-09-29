from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from aiogram.exceptions import TelegramBadRequest
from bot.keyboards.reply import main_menu_keyboard
from bot.database import add_user, get_admin_role
from bot.state import slot_requests
from bot.config import (
    REPORT_CHAT_ID,
    REQUIRED_CHANNEL_ID,
    TIKTOK_REPORT_CHAT_ID,
    TIKTOK_REPORT_THREAD_ID,
    COLLABORATION_CHAT_ID,
    COLLABORATION_THREAD_ID,
    LOG_CHANNEL_ID,
)
import logging

logger = logging.getLogger(__name__)


class AutoMenuMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        # ============ CALLBACK ============
        if isinstance(event, CallbackQuery):
            user_id = event.from_user.id
            cb_data = event.data or ""

            # Кнопка «Проверить подписку» — пропускаем всегда
            if cb_data == "check_sub":
                return await handler(event, data)

            role = get_admin_role(user_id)
            if role:
                return await handler(event, data)

            if not await is_subscribed(user_id, event.bot):
                try:
                    await event.answer(
                        f"⚠️ Для использования бота подпишитесь на канал {REQUIRED_CHANNEL_ID}",
                        show_alert=True
                    )
                except Exception:
                    pass
                return
            return await handler(event, data)

        # ============ MESSAGE ============
        if isinstance(event, Message):
            chat_id = event.chat.id
            thread_id = event.message_thread_id or 0

            # Бот работает ТОЛЬКО в личке
            if event.chat.type != "private":
                return

            if REPORT_CHAT_ID and chat_id == REPORT_CHAT_ID:
                return

            if TIKTOK_REPORT_CHAT_ID and chat_id == TIKTOK_REPORT_CHAT_ID:
                if TIKTOK_REPORT_THREAD_ID == 0 or thread_id == TIKTOK_REPORT_THREAD_ID:
                    return

            if COLLABORATION_CHAT_ID and chat_id == COLLABORATION_CHAT_ID:
                if COLLABORATION_THREAD_ID == 0 or thread_id == COLLABORATION_THREAD_ID:
                    return

            user_id = event.from_user.id
            role = get_admin_role(user_id)

            # /start пропускаем всегда — там сам обрабатываем подписку
            if event.text and event.text.startswith('/start'):
                add_user(event.from_user.id, event.from_user.username, event.from_user.full_name)
                return await handler(event, data)

            # Админы — свободный доступ
            if role:
                add_user(event.from_user.id, event.from_user.username, event.from_user.full_name)
                return await handler(event, data)

            # Всё остальное — сначала проверка подписки
            if not await is_subscribed(user_id, event.bot):
                await event.answer(
                    "⚠️ Для использования бота необходимо подписаться на наш канал:\n"
                    f"👉 {REQUIRED_CHANNEL_ID}\n\n"
                    "После подписки нажмите /start.",
                    reply_markup=main_menu_keyboard()
                )
                return

            add_user(event.from_user.id, event.from_user.username, event.from_user.full_name)
            return await handler(event, data)

        return await handler(event, data)


async def is_subscribed(user_id: int, bot) -> bool:
    """True = подписан. При любой ошибке — False (блокируем)."""
    try:
        chat_member = await bot.get_chat_member(chat_id=REQUIRED_CHANNEL_ID, user_id=user_id)
        return chat_member.status in ['member', 'administrator', 'creator']
    except TelegramBadRequest as e:
        logger.error(
            f"❌ is_subscribed: не удалось проверить {REQUIRED_CHANNEL_ID} для {user_id}: {e}. "
            f"Убедитесь, что бот добавлен в канал как администратор."
        )
        return False
    except Exception as e:
        logger.error(f"❌ is_subscribed: неожиданная ошибка для {user_id}: {e}")
        return False
