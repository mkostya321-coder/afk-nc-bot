from aiogram.utils.keyboard import ReplyKeyboardBuilder
from aiogram.types import ReplyKeyboardMarkup

def main_menu_keyboard(is_registered: bool = False) -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.button(text="📋 Профиль")
    builder.button(text="❓ Помощь")
    if not is_registered:
        # До регистрации — только «Регистрация» + рефералка
        builder.button(text="📝 Регистрация")
        builder.button(text="👥 Реферальная система")
        builder.adjust(2, 2)
    else:
        # После регистрации — все рабочие кнопки
        builder.button(text="🎯 Другие задания")
        builder.button(text="🤝 Сотрудничество с NC")
        builder.button(text="👥 Реферальная система")
        builder.button(text="👥 Мои рефералы")
        builder.adjust(2, 2, 2)
    return builder.as_markup(resize_keyboard=True)
