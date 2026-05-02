from aiogram.utils.keyboard import ReplyKeyboardBuilder
from aiogram.types import ReplyKeyboardMarkup

def main_menu_keyboard() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.button(text="📋 Профиль")
    builder.button(text="💼 Слоты")
    builder.button(text="❓ Помощь")
    builder.button(text="📝 Регистрация")
    builder.button(text="👥 Реферальная система")
    builder.button(text="👥 Мои рефералы")
    builder.adjust(2, 2, 2)
    return builder.as_markup(resize_keyboard=True)
