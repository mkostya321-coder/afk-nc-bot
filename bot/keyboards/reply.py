from aiogram.utils.keyboard import ReplyKeyboardBuilder
from aiogram.types import ReplyKeyboardMarkup

def main_menu_keyboard(is_registered: bool = False) -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.button(text="📋 Профиль")
    builder.button(text="💼 Слоты")
    builder.button(text="❓ Помощь")
    if not is_registered:
        builder.button(text="📝 Регистрация")
    else:
        builder.button(text="🎯 Другие задания")
        builder.button(text="🤝 Сотрудничество с NC")
    builder.button(text="👥 Реферальная система")
    builder.button(text="👥 Мои рефералы")
    # делаем 2 колонки для компактности
    builder.adjust(2, 2, 2)
    return builder.as_markup(resize_keyboard=True)
