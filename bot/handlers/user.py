import sqlite3, asyncio, logging, os
from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove, InlineKeyboardButton, FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from bot.config import (
    MANAGER_USERNAME, DB_PATH, LOG_CHANNEL_ID,
    TIKTOK_VIDEO_ID, TIKTOK_VIDEO_PATH,
    TIKTOK_REPORT_CHAT_ID, TIKTOK_REPORT_THREAD_ID,
    COLLABORATION_CHAT_ID, COLLABORATION_THREAD_ID,
    SUPPORT_CHAT_ID, SUPPORT_THREAD_ID
)
from bot.database import (
    add_user, get_user, get_user_by_username,
    is_registered, update_user_field, is_blocked,
    get_active_warnings, get_setting, set_setting
)
from bot.keyboards.reply import main_menu_keyboard
from bot.handlers.slots import active_slots

logger = logging.getLogger(__name__)
router = Router()

REFERRAL_DEADLINE_DAYS = 28

class RegForm(StatesGroup):
    name = State()
    timezone = State()
    city = State()
    referrer = State()
    phone_card = State()
    bank = State()

class IntroState(StatesGroup):
    first = State()
    second = State()

class TikTokReport(StatesGroup):
    account_name = State()
    screenshot_profile = State()
    video_link = State()
    screenshot_views = State()

class CollaborationForm(StatesGroup):
    platforms = State()
    counts = State()
    description = State()
    texts = State()

class SupportForm(StatesGroup):
    problem = State()

# ============= ПРАВИЛА (ОБНОВЛЕННАЯ ИНСТРУКЦИЯ) =============
RULES_1 = (
    "Информация о работе⚡️\n\n"
    "🔖Вы получаете\n"
    "Ссылки и текста куда нужно публиковать отзывы🗺\n\n"
    "💯Делать исключительно те текста которые вам отправили ❗️❗️❗️\n\n"
    "💎Лучше чтобы человек переписал текст, а не скопировал его это повышает на 20% проход отзыва\n\n"
    "Оплата раз в неделю Четверг до 23:59 (МСК) после выплат баланс сбрасывается до 0\n\n"
    "✨Ваша задача — просить своих знакомых или друзей опубликовать эти отзывы на разных платформах таких как Яндекс.Картах, Google Картах и др. строго по инструкции.\n\n"
    "1 человек с одного устройства может сделать = 1 отзыв в Яндекс + 1 в Google и дальше по 1 отзыву на каждой платформе. Нужно привлекать разных людей.🆕\n\n"
    "Контролируйте, чтобы текст соответствовал полу исполнителя (если указано «женский/мужской»).\n\n"
    "💲Еженедельная премия $35 — достанется сотруднику с самым высоким процентом опубликованных отзывов.\n\n"
    "График свободный, требуется 2-3 часа в день за телефоном👋\n\n"
    "🥰Можно совмещать с учёбой или основной работой."
)

RULES_2 = (
    "🙂Инструкция по работе с отзывами⚠️\n\n"
    "1. Кто может оставлять отзывы⁉️\n"
    "Привлекай только друзей и знакомых.\n"
    "Один человек может оставить только один отзыв в Яндекс Картах и один отзыв в Google Картах или 2ГИС и так на каждой платформе по разу, если человек сделал 2 и более отзыва эти отзывы НЕ ОПЛАЧИВАЮТСЯ.\n"
    "Повторно просить того же человека нельзя.‼️‼️\n\n"
    "2. Формат получения заданий\n"
    "Отзывы скидываются в формате:\n"
    "Ссылка\n"
    "Фотография к отзыву (если требуется) \n"
    "Текст\n"
    "Пол (указан при необходимости)📌\n\n"
    "4. Как учитывать пол💬\n"
    "🔴Бот в первом сообщение указывает нужно ли учесть пол данного отзыва.\n\n"
    "5. На каждый сделанный отзыв вы обязуетесь отправить скриншот боту который отправил вам отзывы.⚠️\n"
    "Скриншоты нужно отправлять в той форме в которой вам скажет бот, если скриншот будет не соответствовать ТЗ - ОТЗЫВ НЕ ОПЛАЧИВАЕТСЯ\n"
    "Если на скриншоте что-то другое не связанное с выполнением работы - выдается предупреждение 1/3.\n"
    "Если количество предупреждений достигнет 3/3 -> блокировка навсегда, с возможностью снять ее через 1 месяц.(на усмотрение администрации)\n\n"
    "6. ❗️Сотрудник, который берет 5 отзывов+- в определенный день, должен предоставить и отправить все подтверждающие скриншоты до 2️⃣3️⃣:5️⃣9️⃣ по московскому времени в день когда ему отправил отзывы бот. В случае несоблюдения этого срока, оплата за отзывы, полученные в этот день, будет снижена на 50%❗️\n\n"
    "Если бот пишет что пол не важен. ‼️То обязательно следи за текстом: если в тексте есть слова в женском роде, например покупала или ходила, а ты отправляешь задание парню, он должен изменить их на мужской род — покупал, ходил.‼️И наоборот. Отзыв должен соответствовать полу того, кто его пишет.✔️"
)

async def show_intro(message: Message, state: FSMContext):
    await state.set_state(IntroState.first)
    kb = InlineKeyboardBuilder()
    kb.button(text="Далее", callback_data="intro_next")
    await message.answer(RULES_1, reply_markup=kb.as_markup())

@router.callback_query(F.data == "intro_next")
async def process_intro_next(callback: CallbackQuery, state: FSMContext):
    current_state = await state.get_state()
    if current_state == IntroState.first.state:
        await state.set_state(IntroState.second)
        kb = InlineKeyboardBuilder()
        kb.button(text="Далее", callback_data="intro_next")
        await callback.message.edit_text(RULES_2, reply_markup=kb.as_markup())
    elif current_state == IntroState.second.state:
        await state.clear()
        kb = InlineKeyboardBuilder()
        kb.button(text="Регистрация", callback_data="menu_reg")
        await callback.message.edit_text("Отлично! Теперь вы можете зарегистрироваться.", reply_markup=kb.as_markup())
    await callback.answer()

@router.callback_query(F.data == "menu_reg")
async def menu_reg_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.delete()
    await start_registration(callback.message, state)

# ---------- Старт ----------
@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    add_user(user_id, message.from_user.username, message.from_user.full_name)
    if is_registered(user_id):
        await message.answer("👋 Привет!\n\nЯ бот для работы со слотами и другими заданиями.", reply_markup=main_menu_keyboard(is_registered=True))
    else:
        await show_intro(message, state)

# ---------- Профиль ----------
@router.message(F.text == "📋 Профиль")
@router.message(Command("profile"))
async def menu_profile(message: Message):
    if is_blocked(message.from_user.id):
        await message.answer("⛔ Вы заблокированы.")
        return
    user = get_user(message.from_user.id)
    if not user or not user.get("name"):
        await message.answer("❌ Вы ещё не зарегистрированы. Используйте кнопку «📝 Регистрация».")
        return

    user_id = message.from_user.id
    reg_time = datetime.fromisoformat(user["registered_at"]) if user["registered_at"] else datetime.now()
    delta = datetime.now() - reg_time
    days = delta.days
    hours, rem = divmod(delta.seconds, 3600)
    minutes, _ = divmod(rem, 60)
    time_str = f"{days} дн. {hours} ч. {minutes} мин."

    referrer = user.get("referrer", "0")
    ref_status = "нет"
    if referrer != "0":
        yandex = user.get("yandex_total", 0) or 0
        google = user.get("google_total", 0) or 0
        gis = user.get("gis_total", 0) or 0
        if yandex >= 10 and (google + gis) >= 15:
            ref_status = "✅ выполнено"
        else:
            if user.get("registered_at"):
                try:
                    deadline = datetime.fromisoformat(user["registered_at"]) + timedelta(days=REFERRAL_DEADLINE_DAYS)
                    if datetime.now() > deadline:
                        ref_status = "❌ Не выполнен"
                    else:
                        ref_status = "🚀 в процессе"
                except:
                    ref_status = "🚀 в процессе"
            else:
                ref_status = "🚀 в процессе"

    # ---- Предупреждения ----
    active_warnings = get_active_warnings(user_id)
    warn_text = ""
    if active_warnings:
        warn_text = "⚠️ Предупреждения:\n"
        for i, w in enumerate(active_warnings, 1):
            created = datetime.fromisoformat(w['created_at']).strftime("%d.%m.%Y")
            expires = datetime.fromisoformat(w['expires_at']).strftime("%d.%m.%Y")
            warn_text += f"{i}/3 – {w['reason']}\n   Выдано: {created}, снимется: {expires}\n"
    else:
        warn_text = "⚠️ Предупреждений нет."

    text = (
        "🤖 Версия бота 1.0.0\n\n"
        f"📋 Профиль\n\n"
        f"Имя: {user['name']}\n"
        f"Время от МСК: {user['timezone']}\n"
        f"Город: {user['city']}\n\n"
        f"С нами уже: {time_str}\n"
        f"К выплате чт: {user['payout']}₽\n"
        f"Заработано за всё время: {user['total_earned']}₽\n\n"
        f"📊 Статистика (текущий период):\n"
        f"Яндекс: {user['yandex_passed']}\n"
        f"Google: {user['google_passed']}\n"
        f"2ГИС: {user['gis_passed']}\n"
        f"Авито: {user['avito_passed']}\n"
        f"ВК: {user['vk_passed']}\n"
        f"Отзовик: {user['otzovik_passed']}\n"
        f"Doctoru: {user['doctoru_passed']}\n"
        f"ДокДок: {user['dokdok_passed']}\n"
        f"Про Докторов: {user['prodoctors_passed']}\n"
        f"ДокТу: {user['doctu_passed']}\n"
        f"32ТОП: {user['top32_passed']}\n\n"
        f"ℹ️ Статистика обновляется каждый день в 10:00 и 20:00 МСК.\n\n"
        f"👥 Рефералка: {referrer if referrer != '0' else 'нет'} ({ref_status})\n\n"
        f"💳 Реквизиты\n"
        f"Номер телефона/карты: {user['phone_card']}\n"
        f"Банк: {user['bank']}\n\n"
        f"{warn_text}\n\n"
        f"Чтобы посмотреть общие отзывы за всё время, используйте /myotz"
    )
    await message.answer(text)

# ---------- /myotz ----------
@router.message(Command("myotz"))
async def cmd_myotz(message: Message):
    if is_blocked(message.from_user.id):
        await message.answer("⛔ Вы заблокированы.")
        return
    user = get_user(message.from_user.id)
    if not user or not user.get("name"):
        await message.answer("❌ Вы не зарегистрированы.")
        return

    text = (
        f"📊 Ваши пройденные отзывы за всё время:\n\n"
        f"Яндекс: {user.get('yandex_total', 0)}\n"
        f"Google: {user.get('google_total', 0)}\n"
        f"2ГИС: {user.get('gis_total', 0)}\n"
        f"Авито: {user.get('avito_total', 0)}\n"
        f"ВК: {user.get('vk_total', 0)}\n"
        f"Отзовик: {user.get('otzovik_total', 0)}\n"
        f"Doctoru: {user.get('doctoru_total', 0)}\n"
        f"ДокДок: {user.get('dokdok_total', 0)}\n"
        f"Про Докторов: {user.get('prodoctors_total', 0)}\n"
        f"ДокТу: {user.get('doctu_total', 0)}\n"
        f"32ТОП: {user.get('top32_total', 0)}"
    )
    await message.answer(text)

# ---------- Помощь ----------
@router.message(F.text == "❓ Помощь")
@router.message(Command("help"))
async def menu_help(message: Message):
    text = (
        "🆘 Доступные команды:\n"
        "/start – Главное меню\n"
        "/reg – Регистрация\n"
        "/profile – Ваш профиль\n"
        "/job – Активные слоты\n"
        "/myotz – Общая статистика за всё время\n"
        "/help – Эта справка\n"
        "/manual – Инструкция по правильной публикации отзывов\n"
        "/money – Полная информация по системе выплат\n"
        "/tiktok – Справка по Tik Tok\n"
        "/support – Заявка в поддержку\n\n"
        f"По всем вопросам: @{MANAGER_USERNAME}"
    )
    user = get_user(message.from_user.id)
    is_reg = user and user.get("name") is not None
    await message.answer(text, reply_markup=main_menu_keyboard(is_registered=is_reg))

# ---------- /manual ----------
@router.message(Command("manual"))
async def cmd_manual(message: Message):
    text = RULES_1 + "\n\n" + RULES_2
    await message.answer(text)

# ---------- /money ----------
@router.message(Command("money"))
async def cmd_money(message: Message):
    text = (
        "💳 <b>Система выплат</b>\n\n"
        "Здравствуйте! Здесь вы можете ознакомиться с полной системой выплат, чтобы потом у вас не возникали вопросы.\n\n"
        "<b>💰 Расценки за отзывы (за 1 шт.):</b>\n"
        "• Яндекс — 150₽\n"
        "• Google — 50₽\n"
        "• 2ГИС — 50₽\n"
        "• Авито — 700₽\n"
        "• ВК — 50₽\n"
        "• Отзовик — 100₽\n"
        "• Doctoru — 100₽\n"
        "• ДокДок — 100₽\n"
        "• Про Докторов — 180₽\n"
        "• ДокТу — 110₽\n"
        "• 32ТОП — 100₽\n\n"
        "<b>📅 Когда выплата?</b>\n"
        "Все выплаты производятся <b>по четвергам</b>.\n"
        "В четверг вы получаете деньги за всё, что успели сделать <b>до понедельника (включительно)</b>.\n"
        "То есть отзывы, выполненные в понедельник, проходят модерацию во вторник, и за них вы получаете в ближайший четверг.\n"
        "Отзывы, выполненные во вторник, среду и т.д., переносятся на следующий четверг.\n"
        "В среду деньги начисляются на ваш баланс в четверг вечером или в пятницу.\n\n"
        "<b>⚠️ Важное правило:</b>\n"
        "Если вы не отказались от задания и не выполнили его до 23:30, то задания снимаются, а все выполненные отзывы из этого слота оплачиваются на <b>30% ниже</b>.\n"
        "Пожалуйста, будьте внимательны: либо доделывайте все отзывы, либо отказывайтесь заранее!\n\n"
        "Удачи в работе! 🚀"
    )
    await message.answer(text, parse_mode="HTML")

# ---------- /tiktok ----------
@router.message(Command("tiktok"))
async def cmd_tiktok(message: Message):
    text = (
        "🎬 <b>Справка по Tik Tok</b>\n\n"
        "В этой справке вы можете ознакомиться с выплатами по Tik Tok.\n\n"
        "Когда вы делаете отчёт, фиксируется последнее количество просмотров.\n"
        "Отчёт следует сделать <b>до вторника (включительно)</b>.\n\n"
        "💰 Максимальная выплата — <b>10 000 рублей</b>.\n"
        "Если у вас выходит до 15 000 рублей, администратор может внести сразу всю выплату в отчёт на ближайший четверг (на усмотрение Главного Администратора).\n"
        "Сумма зависит от количества людей, которым нужно выплатить.\n\n"
        "<b>📌 Важно!</b>\n"
        "Перед публикацией вашего рекламного ролика обязательно заходите в раздел «Другие задания» → «Tik Tok».\n"
        "Если в инструкции написано, что публикация роликов Tik Tok на сегодняшний день (дата) закрыта, то не выкладывайте ролик!\n"
        "Будьте внимательны: администрация при проверке отчёта будет смотреть, в какой день был опубликован ролик.\n"
        "Если публикация была в день, когда Tik Tok был закрыт, выплаты не будет.\n\n"
        "Удачи в творчестве! 🎥"
    )
    await message.answer(text, parse_mode="HTML")

# ---------- /support ----------
@router.message(Command("support"))
async def cmd_support(message: Message, state: FSMContext):
    if is_blocked(message.from_user.id):
        await message.answer("⛔ Вы заблокированы, но можете оставить заявку в поддержку.")
    await state.set_state(SupportForm.problem)
    await message.answer(
        "📝 <b>Заявка в поддержку</b>\n\n"
        "Опишите вашу проблему подробно, и мы свяжемся с вами в ближайшее время.\n"
        "1. Подробно опишите вашу проблему:",
        parse_mode="HTML"
    )

@router.message(SupportForm.problem)
async def process_support(message: Message, state: FSMContext):
    problem = message.text.strip()
    await state.clear()

    report = (
        f"🆘 <b>Новая заявка в поддержку</b>\n"
        f"👤 Пользователь: @{message.from_user.username} (ID: {message.from_user.id})\n"
        f"📝 Проблема:\n{problem}"
    )

    try:
        await message.bot.send_message(
            chat_id=SUPPORT_CHAT_ID,
            text=report,
            message_thread_id=SUPPORT_THREAD_ID or None,
            parse_mode="HTML"
        )
        logger.info(f"✅ Заявка в поддержку отправлена в беседу {SUPPORT_CHAT_ID}")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки заявки в поддержку: {e}")

    await message.answer("✅ Ваша заявка принята! Мы свяжемся с вами в ближайшее время.")

# ---------- Реферальная система ----------
@router.message(F.text == "👥 Реферальная система")
async def referral_info(message: Message):
    logger.info(f"🔔 РЕФЕРАЛКА: пользователь {message.from_user.id} (@{message.from_user.username}) нажал на кнопку")
    try:
        text = (
            "📢 Реферальная система\n\n"
            "👥 Как участвовать?\n"
            "1️⃣ Приглашение. Зарегистрированный пользователь приглашает друга.\n"
            "2️⃣ Регистрация. При создании аккаунта друг в обязательном порядке указывает в вопросе №5 username того, кто его пригласил.\n"
            "3️⃣ Выполнение условий. Чтобы активировать выплату, приглашённый должен оставить одобренные отзывы в таком объёме:\n"
            "   • 10 отзывов на Яндекс.Картах\n"
            "   • 15 отзывов на Google Картах или на 2ГИС (можно комбинировать, например 7 Google + 8 2ГИС, но не менее 15 в сумме)\n\n"
            "⏳ На выполнение даётся 28 дней с момента регистрации. Если за это время условия не выполнены, реферал считается ❌ не выполненным, и вознаграждение уже не получить.\n\n"
            "✅ Отзывы должны пройти модерацию. Приглашённый может написать больше, но награда начисляется в момент, когда минимальные требования выполнены.\n\n"
            "💰 Вознаграждение:\n"
            "   • Пригласивший получает 450 рублей\n"
            "   • Приглашённый получает 200 рублей\n\n"
            "📅 Выплата производится в ближайшую среду или четверг (день зарплаты) после фиксации выполнения всех условий."
        )
        kb = InlineKeyboardBuilder()
        kb.button(text="🔙 Назад", callback_data="referral:back")
        kb.button(text="👥 Пригласить друга", callback_data="referral:invite")
        kb.adjust(2)
        await message.answer(text, reply_markup=kb.as_markup())
        logger.info(f"✅ РЕФЕРАЛКА: сообщение отправлено {message.from_user.id}")
    except Exception as e:
        logger.error(f"❌ РЕФЕРАЛКА ошибка: {e}")
        await message.answer("Произошла ошибка. Попробуйте позже.")

@router.callback_query(F.data == "referral:back")
async def referral_back(callback: CallbackQuery):
    logger.info(f"🔄 РЕФЕРАЛКА: назад {callback.from_user.id}")
    try:
        await callback.message.delete()
        user = get_user(callback.from_user.id)
        is_reg = user and user.get("name") is not None
        await callback.message.answer("👋 Главное меню", reply_markup=main_menu_keyboard(is_registered=is_reg))
        await callback.answer()
    except Exception as e:
        logger.error(f"❌ Ошибка referral_back: {e}")
        await callback.answer("Ошибка", show_alert=True)

@router.callback_query(F.data == "referral:invite")
async def referral_invite(callback: CallbackQuery):
    logger.info(f"📨 РЕФЕРАЛКА: пригласить {callback.from_user.id}")
    try:
        user_id = callback.from_user.id
        user = get_user(user_id)
        username = user.get("tg_username") if user else None
        if not username:
            await callback.answer("❌ У вас не указан Telegram username. Заполните профиль.", show_alert=True)
            return
        invite_text = (
            "Привет.\nПриглашаю в бот @ncjobbot. Схема такая:\n"
            "Ты регистрируешься, указываешь мой юзернейм: `" + username + "`\n"
            "Получаешь бонус 200 рублей и ещё 2 250 рублей за выполнение отзывов (10 Яндекс + 15 Google или 2ГИС).\n"
            "Все что нужно делать просить знакомых оставлять отзывы. Ты сам просишь своих друзей писать отзывы. Даёшь им готовый текст и ссылку — они оставляют, а платят тебе.\n"
            "Всё просто. За каждого друга — свои деньги. Бот надёжный.\n\n"
            "Найди @ncjobbot в Telegram и вводи мой юзернейм при старте."
        )
        await callback.message.answer(invite_text)
        await callback.answer("Текст приглашения отправлен в чат.", show_alert=True)
        logger.info(f"✅ РЕФЕРАЛКА: приглашение отправлено {user_id}")
    except Exception as e:
        logger.error(f"❌ Ошибка referral_invite: {e}")
        await callback.answer("Ошибка", show_alert=True)

# ---------- Регистрация ----------
@router.message(Command("reg"))
@router.message(F.text == "📝 Регистрация")
async def start_registration(message: Message, state: FSMContext):
    if is_blocked(message.from_user.id):
        await message.answer("⛔ Вы заблокированы.")
        return
    user_id = message.from_user.id
    add_user(user_id, message.from_user.username, message.from_user.full_name)
    if is_registered(user_id):
        await message.answer("✅ Вы уже зарегистрированы!", reply_markup=main_menu_keyboard(is_registered=True))
        return
    await state.set_state(RegForm.name)
    await message.answer("Отлично, задам вам пару вопросов.\n1. Ваше имя?", reply_markup=ReplyKeyboardRemove())

@router.message(RegForm.name)
async def process_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    tg_username = message.from_user.username
    if not tg_username:
        await message.answer("❌ У вас не установлен username в Telegram.\nПожалуйста, перейдите в Настройки Telegram → Изменить профиль и задайте имя пользователя (username).\nПосле этого вернитесь сюда и снова нажмите /reg или кнопку «📝 Регистрация».")
        await state.clear()
        return
    clean_username = tg_username.lstrip("@").lower()
    await state.update_data(tg_username=clean_username)
    await message.answer(f"✅ Ваш username: @{tg_username} — записан!")
    await state.set_state(RegForm.timezone)
    await message.answer("3. Ваше время от МСК +-?\n(Например: +4, -1, 0)")

@router.message(RegForm.timezone)
async def process_timezone(message: Message, state: FSMContext):
    await state.update_data(timezone=message.text.strip())
    await state.set_state(RegForm.city)
    await message.answer("4. В каком городе проживаете? (Для отправки ближайших отзывов)")

@router.message(RegForm.city)
async def process_city(message: Message, state: FSMContext):
    await state.update_data(city=message.text.strip())
    await state.set_state(RegForm.referrer)
    await message.answer(
        "5. Есть ли реферальное приглашение? Если да, напишите username человека, от которого вы пришли. "
        "Если нет, просто напишите 0.\n\n"
        "⚠️ Внимание: указание неверного username может привести к тому, что вы не получите реферальный бонус."
    )

@router.message(RegForm.referrer)
async def process_referrer(message: Message, state: FSMContext):
    referrer = message.text.strip().lstrip("@").lower()
    if referrer != "0":
        ref_user = get_user_by_username(referrer)
        if not ref_user:
            await message.answer("❌ Пользователь с таким username не найден. Проверьте правильность или напишите 0.")
            return
    await state.update_data(referrer=referrer)
    await state.set_state(RegForm.phone_card)
    await message.answer(
        "6. Номер телефона или карты? "
        "(Эти данные используются для автоматических выплат в день зарплаты. "
        "Если не хотите указывать сейчас, просто напишите 0)"
    )

@router.message(RegForm.phone_card)
async def process_phone_card(message: Message, state: FSMContext):
    await state.update_data(phone_card=message.text.strip())
    await state.set_state(RegForm.bank)
    await message.answer("7. Банк?")

@router.message(RegForm.bank)
async def process_bank(message: Message, state: FSMContext):
    data = await state.get_data()
    user_id = message.from_user.id
    update_user_field(user_id, "name", data["name"])
    update_user_field(user_id, "tg_username", data["tg_username"])
    update_user_field(user_id, "timezone", data["timezone"])
    update_user_field(user_id, "city", data["city"])
    update_user_field(user_id, "referrer", data["referrer"])
    update_user_field(user_id, "phone_card", data["phone_card"])
    update_user_field(user_id, "bank", message.text.strip())
    update_user_field(user_id, "registered_at", datetime.now().isoformat())
    await state.clear()
    await message.answer(
        "✅ Отлично, регистрация успешно пройдена! Используйте кнопки ниже для навигации.\n"
        "Хорошей работы и больших заработков!",
        reply_markup=main_menu_keyboard(is_registered=True)
    )

# ---------- Мои рефералы ----------
@router.message(F.text == "👥 Мои рефералы")
async def show_my_referrals(message: Message, state: FSMContext):
    if is_blocked(message.from_user.id):
        await message.answer("⛔ Вы заблокированы.")
        return
    user_id = message.from_user.id
    user = get_user(user_id)
    if not user or not user.get("name"):
        await message.answer("❌ Вы не зарегистрированы.")
        return
    tg_username = user.get("tg_username")
    if not tg_username:
        await message.answer("❌ У вас не указан Telegram username. Заполните профиль.")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        "SELECT name, tg_username, registered_at, yandex_total, google_total, gis_total "
        "FROM users WHERE LOWER(REPLACE(referrer, '@', '')) = ?",
        (tg_username.lower(),)
    )
    referrals = cur.fetchall()
    conn.close()

    if not referrals:
        await message.answer("👥 У вас пока нет рефералов.")
        return

    now = datetime.now()
    data = []
    for ref in referrals:
        name = ref["name"] or "Без имени"
        username = ref["tg_username"] or "unknown"
        reg_time_str = ref["registered_at"]
        if reg_time_str:
            try:
                reg_time = datetime.fromisoformat(reg_time_str)
            except:
                reg_time = now
            deadline = reg_time + timedelta(days=REFERRAL_DEADLINE_DAYS)
            remaining = (deadline - now).days
        else:
            remaining = 0

        yandex = ref["yandex_total"] or 0
        google = ref["google_total"] or 0
        gis = ref["gis_total"] or 0

        if yandex >= 10 and (google + gis) >= 15:
            status = "✅ Выполнен"
        elif remaining <= 0:
            status = "❌ Не выполнен"
        else:
            status = "🚀 В процессе"

        data.append((name, username, status))

    PAGE_SIZE = 10
    total_pages = (len(data) + PAGE_SIZE - 1) // PAGE_SIZE
    await state.update_data(ref_page=0, ref_data=data, ref_total_pages=total_pages)

    kb = InlineKeyboardBuilder()
    kb.button(text="Страница 1", callback_data="ignore")
    if total_pages > 1:
        kb.button(text="Страница 2 →", callback_data="ref_nav:2")
    kb.adjust(1)

    text = build_page_text(data, 0, PAGE_SIZE)
    await message.answer(text, reply_markup=kb.as_markup())

def build_page_text(data, page, page_size):
    start = page * page_size
    end = start + page_size
    page_items = data[start:end]
    lines = [f"👥 Мои рефералы (стр. {page+1})"]
    for name, username, status in page_items:
        lines.append(f"{name} (@{username}) – {status}")
    return "\n".join(lines)

@router.callback_query(F.data.startswith("ref_nav:"))
async def ref_page_navigate(callback: CallbackQuery, state: FSMContext):
    page = int(callback.data.split(":")[1]) - 1
    data_state = await state.get_data()
    ref_data = data_state.get("ref_data", [])
    total_pages = data_state.get("ref_total_pages", 1)

    if not ref_data:
        await callback.answer("Нет данных.", show_alert=True)
        return

    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton(text=f"← Страница {page}", callback_data=f"ref_nav:{page}"))
    buttons.append(InlineKeyboardButton(text=f"Страница {page+1}", callback_data="ignore"))
    if page < total_pages - 1:
        buttons.append(InlineKeyboardButton(text=f"Страница {page+2} →", callback_data=f"ref_nav:{page+2}"))

    keyboard = InlineKeyboardBuilder()
    keyboard.row(*buttons)

    text = build_page_text(ref_data, page, 10)
    await callback.message.edit_text(text, reply_markup=keyboard.as_markup())
    await callback.answer()

# ============ ДРУГИЕ ЗАДАНИЯ ============

@router.message(F.text == "🎯 Другие задания")
async def other_tasks(message: Message):
    kb = InlineKeyboardBuilder()
    kb.button(text="🎬 Tik Tok", callback_data="task_tiktok")
    kb.button(text="📊 Отчет Tik Tok", callback_data="report_tiktok")
    kb.adjust(1)
    await message.answer("Выберите задание:", reply_markup=kb.as_markup())

# ---------- Tik Tok: показ видео и правил (с проверкой остановки) ----------
@router.callback_query(F.data == "task_tiktok")
async def tiktok_task(callback: CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id
    if not is_registered(user_id):
        await callback.message.answer("❌ Сначала зарегистрируйтесь.")
        return

    # Проверка на остановку Tik Tok
    stop_date = get_setting("tiktok_stop_date")
    if stop_date:
        await callback.message.answer(
            f"⛔ <b>Внимание!</b> Участие в Tik Tok приостановлено с <b>{stop_date}</b>.\n"
            "Все ролики, опубликованные после этой даты, <b>не оплачиваются</b>.\n"
            "Пожалуйста, будьте внимательны! Это правило прописано в справке /tiktok.",
            parse_mode="HTML"
        )
        return

    rules = (
        "🎬 <b>Задание Tik Tok</b>\n\n"
        "📌 Над данным текстом находится рекламный ролик New Chapter, который вы должны будете вставить в свое видео.\n"
        "Видео вы можете делать на любую тему, кроме тех, что входят в запрещающий список.\n\n"
        "<b>🚫 В ролике ЗАПРЕЩАЕТСЯ:</b>\n"
        "❌ Содержание порнографического контента\n"
        "❌ Пропаганда запрещенных веществ\n"
        "❌ <b>Содержание другой ЛЮБОЙ рекламы</b>\n"
        "❌ Видео на политические темы\n"
        "❌ Оскорбительный контент\n"
        "❌ Содержание запрещенного контента в РФ\n\n"
        "<b>💰 Ваш доход:</b>\n"
        "📊 За 1000 просмотров вы получаете <b>10 рублей</b>.\n"
        "🔥 1.000.000 просмотров → <b>10.000 рублей</b>\n"
        "📉 После 1 млн просмотров, последующие 1000 просмотров оплачиваются по <b>5 рублей</b> (до 500.000 просмотров).\n"
        "📉 Далее <b>2 рубля</b> за 1000 просмотров.\n"
        "💰 Максимальная выплата в неделю за ролик в Tik Tok — <b>10.000 рублей</b>.\n"
        "💳 Выплата через кошелек в @ncjobbot.\n\n"
        "Удачи! 🚀"
    )

    try:
        if TIKTOK_VIDEO_ID:
            await callback.message.answer_video(video=TIKTOK_VIDEO_ID, caption=rules, parse_mode="HTML")
        elif TIKTOK_VIDEO_PATH and os.path.exists(TIKTOK_VIDEO_PATH):
            video_file = FSInputFile(TIKTOK_VIDEO_PATH)
            await callback.message.answer_video(video=video_file, caption=rules, parse_mode="HTML")
        else:
            await callback.message.answer(rules, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Ошибка отправки видео Tik Tok: {e}")
        await callback.message.answer(rules, parse_mode="HTML")

# ---------- Отчет Tik Tok (сначала описание и кнопка) ----------
@router.callback_query(F.data == "report_tiktok")
async def report_tiktok_intro(callback: CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id
    if not is_registered(user_id):
        await callback.message.answer("❌ Сначала зарегистрируйтесь.")
        return

    text = (
        "📊 <b>Отчет по Tik Tok</b>\n\n"
        "Для предоставления отчета вам необходимо ответить на несколько вопросов и приложить скриншоты.\n\n"
        "Вам нужно будет указать:\n"
        "• Название вашего аккаунта Tik Tok\n"
        "• Скриншот профиля (с последними роликами и возможностью редактирования)\n"
        "• Ссылку на ролик\n"
        "• Скриншот с количеством просмотров\n\n"
        "Нажмите кнопку ниже, чтобы начать заполнение отчета."
    )
    kb = InlineKeyboardBuilder()
    kb.button(text="📝 Перейти к заполнению формы", callback_data="report_tiktok_form")
    await callback.message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")

@router.callback_query(F.data == "report_tiktok_form")
async def report_tiktok_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(TikTokReport.account_name)
    await callback.message.answer(
        "1. Название вашего аккаунта Tik Tok:"
    )

@router.message(TikTokReport.account_name)
async def process_tiktok_account(message: Message, state: FSMContext):
    await state.update_data(account_name=message.text.strip())
    await state.set_state(TikTokReport.screenshot_profile)
    await message.answer(
        "2. Отправьте скриншот внутри профиля, где видно:\n"
        "• Ваши последние ролики\n"
        "• Возможность изменять профиль\n"
        "• Что-то добавлять и т.д.\n"
        "На скриншоте ничего нельзя замазывать."
    )

@router.message(TikTokReport.screenshot_profile, F.photo)
async def process_tiktok_screenshot_profile(message: Message, state: FSMContext):
    await state.update_data(screenshot_profile=message.photo[-1].file_id)
    await state.set_state(TikTokReport.video_link)
    await message.answer("3. Отправьте ссылку на ролик, за который хотите получить выплату:")

@router.message(TikTokReport.screenshot_profile)
async def process_tiktok_screenshot_profile_invalid(message: Message):
    await message.answer("Пожалуйста, отправьте фото скриншота профиля.")

@router.message(TikTokReport.video_link)
async def process_tiktok_video_link(message: Message, state: FSMContext):
    await state.update_data(video_link=message.text.strip())
    await state.set_state(TikTokReport.screenshot_views)
    await message.answer("4. Отправьте скриншот ролика, где видно количество просмотров.")

@router.message(TikTokReport.screenshot_views, F.photo)
async def process_tiktok_screenshot_views(message: Message, state: FSMContext):
    await state.update_data(screenshot_views=message.photo[-1].file_id)
    data = await state.get_data()
    await state.clear()

    report = (
        f"📊 <b>Новый отчет Tik Tok</b>\n"
        f"👤 Пользователь: @{message.from_user.username} (ID: {message.from_user.id})\n"
        f"📱 Аккаунт: {data.get('account_name')}\n"
        f"🔗 Ссылка на ролик: {data.get('video_link')}\n"
        f"📸 Скриншот профиля: (см. ниже)\n"
        f"📸 Скриншот просмотров: (см. ниже)"
    )

    try:
        await message.bot.send_message(
            chat_id=TIKTOK_REPORT_CHAT_ID,
            text=report,
            message_thread_id=TIKTOK_REPORT_THREAD_ID or None,
            parse_mode="HTML"
        )
        if data.get('screenshot_profile'):
            await message.bot.send_photo(
                chat_id=TIKTOK_REPORT_CHAT_ID,
                photo=data['screenshot_profile'],
                message_thread_id=TIKTOK_REPORT_THREAD_ID or None
            )
        if data.get('screenshot_views'):
            await message.bot.send_photo(
                chat_id=TIKTOK_REPORT_CHAT_ID,
                photo=data['screenshot_views'],
                message_thread_id=TIKTOK_REPORT_THREAD_ID or None
            )
        logger.info(f"✅ Отчет Tik Tok отправлен в беседу {TIKTOK_REPORT_CHAT_ID}")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки отчета Tik Tok: {e}")

    await message.answer("✅ Отчет отправлен! Менеджер проверит его в ближайшее время.")

@router.message(TikTokReport.screenshot_views)
async def process_tiktok_screenshot_views_invalid(message: Message):
    await message.answer("Пожалуйста, отправьте фото скриншота с просмотрами.")

# ---------- СОТРУДНИЧЕСТВО ----------
@router.message(F.text == "🤝 Сотрудничество с NC")
async def collaboration_start(message: Message):
    if is_blocked(message.from_user.id):
        await message.answer("⛔ Вы заблокированы.")
        return
    text = (
        "🤝 <b>Сотрудничество с NC</b>\n\n"
        "Вы хотите передать свои отзывы под работу нашей команде.\n"
        "Мы берём на себя организацию выполнения отзывов, выплаты исполнителям и контроль качества.\n\n"
        "<b>Условия сотрудничества:</b>\n"
        "• Вы выплачиваете <b>60%</b> от зарплаты исполнителей (по нашим ставкам).\n"
        "• За использование сервиса NC берёт <b>20%</b> от чистой прибыли (минимум 60₽ за отзыв).\n"
        "• Если вы заказываете текста для отзывов у нас – стоимость составляет <b>35₽</b> за один отзыв.\n\n"
        "Заполните форму, и мы свяжемся с вами для деталей."
    )
    kb = InlineKeyboardBuilder()
    kb.button(text="📝 Перейти к заполнению формы", callback_data="collaboration_form")
    await message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")

@router.callback_query(F.data == "collaboration_form")
async def collaboration_form_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(CollaborationForm.platforms)
    await callback.message.answer(
        "📝 <b>Форма сотрудничества</b>\n\n"
        "Ответьте на вопросы для отправки заявки.\n"
        "1. Какие платформы вы хотите передать к нам в работу? (Яндекс, Google, 2ГИС, Авито, и т.д.)",
        parse_mode="HTML"
    )

@router.message(CollaborationForm.platforms)
async def collaboration_platforms(message: Message, state: FSMContext):
    await state.update_data(platforms=message.text.strip())
    await state.set_state(CollaborationForm.counts)
    await message.answer(
        "2. Какое количество отзывов требуется на каждую платформу?\n"
        "Укажите в формате: Яндекс – 50, Google – 30, и т.д."
    )

@router.message(CollaborationForm.counts)
async def collaboration_counts(message: Message, state: FSMContext):
    await state.update_data(counts=message.text.strip())
    await state.set_state(CollaborationForm.description)
    await message.answer(
        "3. Подробно распишите каждый заказ:\n"
        "Например: какие именно объекты, какие требования, есть ли фото для прикрепления, и т.д."
    )

@router.message(CollaborationForm.description)
async def collaboration_description(message: Message, state: FSMContext):
    await state.update_data(description=message.text.strip())
    await state.set_state(CollaborationForm.texts)
    await message.answer(
        "4. Текста на отзывы вы заказываете у нас или отправляете сами?\n"
        "Если заказываете у нас – стоимость 35₽ за отзыв.\n"
        "Напишите: 'Заказываем у NC' или 'Отправляем сами'."
    )

@router.message(CollaborationForm.texts)
async def collaboration_texts(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()

    report = (
        f"🤝 <b>Новая заявка на сотрудничество</b>\n"
        f"👤 От: @{message.from_user.username} (ID: {message.from_user.id})\n"
        f"📌 Платформы: {data.get('platforms')}\n"
        f"📊 Количество по платформам:\n{data.get('counts')}\n"
        f"📝 Описание заказов:\n{data.get('description')}\n"
        f"✍️ Текста: {message.text.strip()}"
    )

    try:
        await message.bot.send_message(
            chat_id=COLLABORATION_CHAT_ID,
            text=report,
            message_thread_id=COLLABORATION_THREAD_ID or None,
            parse_mode="HTML"
        )
        logger.info(f"✅ Заявка на сотрудничество отправлена в беседу {COLLABORATION_CHAT_ID}")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки заявки на сотрудничество: {e}")

    await message.answer("✅ Ваша заявка отправлена! Менеджер свяжется с вами в ближайшее время.")
