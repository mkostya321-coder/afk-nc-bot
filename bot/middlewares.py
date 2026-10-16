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
import asyncio
import logging
import time

logger = logging.getLogger(__name__)


# ============ КЭШ ПОДПИСКИ (5 минут) ============
_subscription_cache = {}   # {user_id: (timestamp, bool)}
SUB_CACHE_TTL = 300        # 5 минут


async def is_subscribed(user_id: int, bot) -> bool:
    """True = подписан. При любой ошибке — False (блокируем). С таймаутом 5 сек."""
    try:
        chat_member = await asyncio.wait_for(
            bot.get_chat_member(chat_id=REQUIRED_CHANNEL_ID, user_id=user_id),
            timeout=5.0
        )
        return chat_member.status in ['member', 'administrator', 'creator']
    except asyncio.TimeoutError:
        logger.error(f"❌ is_subscribed: TIMEOUT для {user_id} — Telegram API не отвечает")
        return False
    except TelegramBadRequest as e:
        logger.error(
            f"❌ is_subscribed: не удалось проверить {REQUIRED_CHANNEL_ID} для {user_id}: {e}. "
            f"Убедитесь, что бот добавлен в канал как администратор."
        )
        return False
    except Exception as e:
        logger.error(f"❌ is_subscribed: неожиданная ошибка для {user_id}: {e}")
        return False


async def is_subscribed_cached(user_id: int, bot) -> bool:
    """Проверка подписки с кэшем на 5 минут. Снижает нагрузку на Telegram API в 10-20 раз."""
    now = time.time()
    cached = _subscription_cache.get(user_id)
    if cached and (now - cached[0]) < SUB_CACHE_TTL:
        return cached[1]
    result = await is_subscribed(user_id, bot)
    _subscription_cache[user_id] = (now, result)
    return result


def invalidate_subscription_cache(user_id: int):
    """Сбросить кэш подписки для юзера (например, после /start)."""
    _subscription_cache.pop(user_id, None)


def cleanup_subscription_cache():
    """Удаляет записи старше 10 минут. Вызывать периодически."""
    now = time.time()
    stale = [uid for uid, (ts, _) in _subscription_cache.items() if (now - ts) > 600]
    for uid in stale:
        _subscription_cache.pop(uid, None)
    return len(stale)


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

            # 🚀 Используем кэш — снижает нагрузку на API
            if not await is_subscribed_cached(user_id, event.bot):
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
                # 🔄 Сбрасываем кэш при /start — чтобы свежая проверка
                invalidate_subscription_cache(user_id)
                return await handler(event, data)

            # Админы — свободный доступ
            if role:
                add_user(event.from_user.id, event.from_user.username, event.from_user.full_name)
                return await handler(event, data)

            # 🚀 Используем кэш — снижает нагрузку на API
            if not await is_subscribed_cached(user_id, event.bot):
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
