from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from aiogram.exceptions import TelegramBadRequest
from bot.keyboards.reply import main_menu_keyboard
from bot.database import add_user, get_admin_role
from bot.state import slot_requests   # <-- импорт из state
from bot.config import (
    REPORT_CHAT_ID,
    REQUIRED_CHANNEL_ID,
    TIKTOK_REPORT_CHAT_ID,
    TIKTOK_REPORT_THREAD_ID,
    COLLABORATION_CHAT_ID,
    COLLABORATION_THREAD_ID
)

class AutoMenuMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        if isinstance(event, Message):
            chat_id = event.chat.id
            thread_id = event.message_thread_id or 0

            # Пропускаем сообщения из служебных чатов
            if chat_id == REPORT_CHAT_ID:
                return

            if chat_id == TIKTOK_REPORT_CHAT_ID:
                if TIKTOK_REPORT_THREAD_ID == 0 or thread_id == TIKTOK_REPORT_THREAD_ID:
                    return

            if chat_id == COLLABORATION_CHAT_ID:
                if COLLABORATION_THREAD_ID == 0 or thread_id == COLLABORATION_THREAD_ID:
                    return

        if isinstance(event, CallbackQuery):
            return await handler(event, data)

        if isinstance(event, Message):
            # Пропускаем команды
            if event.text and event.text.startswith('/'):
                return await handler(event, data)

            # Пропускаем кнопки меню
            if event.text in ["📋 Профиль", "💼 Слоты", "❓ Помощь", "📝 Регистрация",
                              "👥 Реферальная система", "👥 Мои рефералы",
                              "🎯 Другие задания", "🤝 Сотрудничество с NC"]:
                return await handler(event, data)

            # Если у пользователя активная сессия слота – пропускаем
            if event.from_user.id in slot_requests:
                return await handler(event, data)

            # Если есть состояние FSM – пропускаем
            state = data.get("state")
            if state and await state.get_state():
                return await handler(event, data)

            # В остальных случаях – проверяем подписку и показываем меню
            user_id = event.from_user.id
            role = get_admin_role(user_id)
            if not role:
                if not await is_subscribed(user_id, event.bot):
                    await event.answer(
                        "⚠️ Для использования бота необходимо подписаться на наш канал:\n"
                        f"👉 {REQUIRED_CHANNEL_ID}\n\n"
                        "После подписки нажмите /start или любую кнопку.",
                        reply_markup=main_menu_keyboard()
                    )
                    return

            add_user(event.from_user.id, event.from_user.username, event.from_user.full_name)
            await event.answer("👋 Главное меню", reply_markup=main_menu_keyboard())
            return

        return await handler(event, data)

async def is_subscribed(user_id: int, bot) -> bool:
    try:
        chat_member = await bot.get_chat_member(chat_id=REQUIRED_CHANNEL_ID, user_id=user_id)
        return chat_member.status in ['member', 'administrator', 'creator']
    except TelegramBadRequest:
        return True
