from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from bot.keyboards.reply import main_menu_keyboard

router = Router()

@router.message(F.text == "👥 Реферальная система")
async def referral_info(message: Message):
    if is_blocked(message.from_user.id):
    await message.answer("⛔ К сожалению, вы заблокированы. Если хотите обжаловать решение, напишите в поддержку @New_Chapterr24.")
    return
    text = (
        "📢 Реферальная система\n\n"
        "👥 Как участвовать?\n"
        "1️⃣ Приглашение. Зарегистрированный пользователь приглашает друга.\n"
        "2️⃣ Регистрация. При создании аккаунта друг в обязательном порядке указывает в вопросе №5 username того, кто его пригласил.\n"
        "3️⃣ Выполнение условий. Чтобы активировать выплату, приглашённый должен оставить одобренные отзывы в таком объёме:\n"
        "   • 10 отзывов на Яндекс.Картах\n"
        "   • 15 отзывов на Google Картах или на 2ГИС (можно комбинировать, например 7 Google + 8 2ГИС, но не менее 15 в сумме)\n\n"
        "⏳ На выполнение даётся <b>28 дней</b> с момента регистрации. Если за это время условия не выполнены, реферал считается ❌ не выполненным, и вознаграждение уже не получить.\n\n"
        "✅ Отзывы должны пройти модерацию. Приглашённый может написать больше, но награда начисляется в момент, когда минимальные требования выполнены.\n\n"
        "💰 Вознаграждение:\n"
        "   • Пригласивший получает 450 рублей\n"
        "   • Приглашённый получает 200 рублей\n\n"
        "📅 Выплата производится в ближайшую среду или четверг (день зарплаты) после фиксации выполнения всех условий."
    )

    # Инлайн‑кнопки
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 Назад", callback_data="referral:back")
    kb.button(text="👥 Пригласить друга", callback_data="referral:invite")
    kb.adjust(2)

    await message.answer(text, reply_markup=kb.as_markup())


# Обработчик нажатий на инлайн‑кнопки
@router.callback_query(F.data == "referral:back")
async def referral_back(callback: CallbackQuery):
    await callback.message.delete()   # убираем сообщение с кнопками
    await callback.message.answer(
        "👋 Главное меню",
        reply_markup=main_menu_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "referral:invite")
async def referral_invite(callback: CallbackQuery):
    user_id = callback.from_user.id
    # Получаем tg_username пользователя из базы
    from bot.database import get_user
    user = get_user(user_id)
    username = user.get("tg_username") if user else None
    if not username:
        await callback.answer("❌ У вас не указан Telegram username. Заполните профиль.", show_alert=True)
        return

    invite_text = (
        "Привет.\n"
        "Приглашаю в бот @ncjobbot. Схема такая:\n"
        "Ты регистрируешься, указываешь мой юзернейм: **" + username + "**.\n"
        "Получаешь бонус 200 рублей (один раз), когда сделаешь норму: 10 отзывов на Яндекс + 15 на Google или 2ГИС.\n"
        "Все что нужно делать просить знакомых оставлять отзывы. Ты сам просишь своих друзей писать отзывы. Даёшь им готовый текст и ссылку — они оставляют, а платят тебе.\n"
        "Всё просто. За каждого друга — свои деньги. Бот надёжный.\n\n"
        "Найди @ncjobbot в Telegram и вводи мой юзернейм при старте."
    )
    await callback.message.answer(invite_text)
    await callback.answer("Текст приглашения скопирован в чат.", show_alert=True)
