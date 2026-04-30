from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from bot.keyboards.reply import main_menu_keyboard
from bot.database import add_user

class AutoMenuMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        if isinstance(event, CallbackQuery):
            return await handler(event, data)

        if isinstance(event, Message):
            if event.text and event.text.startswith('/'):
                return await handler(event, data)
            if event.text in ["📋 Профиль", "💼 Слоты", "❓ Помощь", "📝 Регистрация", "👥 Реферальная система", "👥 Мои рефералы"]:
                return await handler(event, data)
            state = data.get("state")
            if state and await state.get_state():
                return await handler(event, data)
            add_user(event.from_user.id, event.from_user.username, event.from_user.full_name)
            await event.answer("👋 Главное меню", reply_markup=main_menu_keyboard())
            return

        return await handler(event, data)
