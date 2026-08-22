from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from aiogram.exceptions import TelegramBadRequest
from bot.keyboards.reply import main_menu_keyboard
from bot.database import add_user
from bot.handlers.slots import slot_requests
from bot.config import REPORT_CHAT_ID, REQUIRED_CHANNEL_ID, ADMIN_IDS, OWNER_ID
from bot.database import is_registered, is_blocked, get_admin_role

class AutoMenuMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        # Игнорируем беседу отчета
        if isinstance(event, Message) and event.chat.id == REPORT_CHAT_ID:
            return

        if isinstance(event, CallbackQuery):
            return await handler(event, data)

        if isinstance(event, Message):
            # Пропускаем команды /start, /help, /reg и админ-команды
            if event.text and event.text.startswith('/'):
                return await handler(event, data)
            if event.text in ["📋 Профиль", "💼 Слоты", "❓ Помощь", "📝 Регистрация", "👥 Реферальная система", "👥 Мои рефералы"]:
                return await handler(event, data)
            if event.from_user.id in slot_requests:
                return await handler(event, data)
            state = data.get("state")
            if state and await state.get_state():
                return await handler(event, data)

            # Проверка подписки (кроме админов)
            user_id = event.from_user.id
            role = get_admin_role(user_id)
            if not role:  # если не админ
                if not await is_subscribed(user_id, event.bot):
                    await event.answer(
                        "⚠️ Для использования бота необходимо подписаться на наш канал:\n"
                        f"👉 {REQUIRED_CHANNEL_ID}\n\n"
                        "После подписки нажмите /start или любую кнопку.",
                        reply_markup=main_menu_keyboard()
                    )
                    return  # блокируем дальнейшую обработку

            add_user(event.from_user.id, event.from_user.username, event.from_user.full_name)
            await event.answer("👋 Главное меню", reply_markup=main_menu_keyboard())
            return

        return await handler(event, data)

async def is_subscribed(user_id: int, bot) -> bool:
    try:
        chat_member = await bot.get_chat_member(chat_id=REQUIRED_CHANNEL_ID, user_id=user_id)
        return chat_member.status in ['member', 'administrator', 'creator']
    except TelegramBadRequest:
        # Если бот не может получить информацию (не админ канала), считаем что подписка не требуется
        return True
