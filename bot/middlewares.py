from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from bot.keyboards.reply import main_menu_keyboard
from bot.database import add_user
from bot.handlers.slots import slot_requests

class AutoMenuMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        if isinstance(event, CallbackQuery):
            return await handler(event, data)

        if isinstance(event, Message):
            # Пропускаем команды
            if event.text and event.text.startswith('/'):
                return await handler(event, data)
            # Пропускаем кнопки меню
            if event.text in ["📋 Профиль", "💼 Слоты", "❓ Помощь", "📝 Регистрация", "👥 Реферальная система", "👥 Мои рефералы"]:
                return await handler(event, data)
            # Если у пользователя активен запрос на взятие слота – пропускаем
            if event.from_user.id in slot_requests:
                return await handler(event, data)
            # Если есть активное FSM состояние (регистрация) – пропускаем
            state = data.get("state")
            if state and await state.get_state():
                return await handler(event, data)
            # Показываем меню
            add_user(event.from_user.id, event.from_user.username, event.from_user.full_name)
            await event.answer("👋 Главное меню", reply_markup=main_menu_keyboard())
            return

        return await handler(event, data)
