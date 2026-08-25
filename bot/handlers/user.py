import sqlite3, asyncio, logging, os
from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove, InlineKeyboardButton, FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from bot.config import MANAGER_USERNAME, DB_PATH, LOG_CHANNEL_ID, TIKTOK_VIDEO_ID, TIKTOK_VIDEO_PATH
from bot.database import (
    add_user, get_user, get_user_by_username,
    is_registered, update_user_field, is_blocked
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

# ---------- Новые состояния для Tik Tok и Сотрудничества ----------
class TikTokReport(StatesGroup):
    account_name = State()
    screenshot_profile = State()
    video_link = State()
    screenshot_views = State()

class CollaborationForm(StatesGroup):
    company_name = State()
    reviews_count = State()
    platforms = State()
    links = State()
    contact = State()

# ============= ПРАВИЛА (оставляем как есть) =============
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
    "Один человек может оставить только один отзыв в Яндекс Картах и один отзыв в Google Картах или 2ГИС и так на каждой платформе по разу, (ВСЕ ЧТО СПЕРЕДИ ДО НЕ ОПЛАЧИВАЮТСЯ СДЕЛАЙ ЖИРНЫМ ТЕКСТОМ) если человек сделал 2 и более отзыва эти отзывы НЕ ОПЛАЧИВАЮТСЯ.\n"
    "Повторно просить того же человека нельзя.‼️‼️\n\n"
    "2. Формат получения заданий\n"
    "Отзывы скидываются в формате:\n"
    "Ссылка\n"
    "Текст\n"
    "Пол (указан при необходимости)📌\n\n"
    "4. Как учитывать пол💬\n"
    "🔴Бот в первом сообщение указывает нужно ли учесть пол данного отзыва.\n\n"
    "5. На каждый сделанный отзыв вы обязуетесь отправить скриншот боту который отправил вам отзывы.⚠️\n"
    "Скриншоты нужно отправлять в той форме в которой вам скажет бот, если скриншот будет не соответствовать - ОТЗЫВ НЕ ОПЛАЧИВАЕТСЯ\n"
    "Если на скриншоте что-то другое - ПРЕД 1/3 если количество предупреждений дойдет до 3/3 блокировка навсегда, с шансом снять ее через 1 месяц.\n\n"
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
        # показываем меню без "Регистрация"
        await message.answer("👋 Привет!\n\nЯ бот для работы со слотами и другими заданиями.", reply_markup=main_menu_keyboard(is_registered=True))
    else:
        await show_intro(message, state)

# ---------- Профиль ----------
@router.message(F.text == "📋 Профиль")
async def menu_profile(message: Message):
    if is_blocked(message.from_user.id):
        await message.answer("⛔ Вы заблокированы.")
        return
    user = get_user(message.from_user.id)
    if not user or not user.get("name"):
        await message.answer("❌ Вы ещё не зарегистрированы. Используйте кнопку «📝 Регистрация».")
        return

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

    text = (
        f"📋 Профиль\n\n"
        f"Имя: {user['name']}\n"
        f"Время от МСК: {user['timezone']}\n"
        f"Город: {user['city']}\n\n"
        f"С нами уже: {time_str}\n"
        f"К выплате ср/чт: {user['payout']}₽\n"
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
async def menu_help(message: Message):
    text = (
        "🆘 Доступные команды:\n"
        "/start – Главное меню\n"
        "/reg – Регистрация\n"
        "/profile – Ваш профиль\n"
        "/job – Активные слоты\n"
        "/myotz – Общая статистика за всё время\n"
        "/help – Эта справка\n\n"
        f"По всем вопросам: @{MANAGER_USERNAME}"
    )
    # Меню с учётом регистрации
    user = get_user(message.from_user.id)
    is_reg = user and user.get("name") is not None
    await message.answer(text, reply_markup=main_menu_keyboard(is_registered=is_reg))

# ---------- Реферальная система (оставляем без изменений) ----------
# ... (код рефералки уже есть, я не повторяю его для краткости)

# ---------- РЕГИСТРАЦИЯ ----------
@router.message(Command("reg"))
@router.message(F.text == "📝 Регистрация")
async def start_registration(message: Message, state: FSMContext):
    if is_blocked(message.from_user.id):
        await message.answer("⛔ Вы заблокированы.")
        return
    user_id = message.from_user.id
    add_user(user_id, message.from_user.username, message.from_user.full_name)
    if is_registered(user_id):
        # после регистрации показываем меню без кнопки "Регистрация"
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

# ============ НОВЫЙ РАЗДЕЛ: ДРУГИЕ ЗАДАНИЯ ============

@router.message(F.text == "🎯 Другие задания")
async def other_tasks(message: Message):
    kb = InlineKeyboardBuilder()
    kb.button(text="🎬 Tik Tok", callback_data="task_tiktok")
    kb.button(text="📊 Отчет Tik Tok", callback_data="report_tiktok")
    kb.adjust(1)
    await message.answer("Выберите задание:", reply_markup=kb.as_markup())

# ---------- Tik Tok: показ видео и правил ----------
@router.callback_query(F.data == "task_tiktok")
async def tiktok_task(callback: CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id
    if not is_registered(user_id):
        await callback.message.answer("❌ Сначала зарегистрируйтесь.")
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

    # Отправляем видео
    try:
        if TIKTOK_VIDEO_ID:
            await callback.message.answer_video(video=TIKTOK_VIDEO_ID, caption=rules, parse_mode="HTML")
        elif TIKTOK_VIDEO_PATH and os.path.exists(TIKTOK_VIDEO_PATH):
            video_file = FSInputFile(TIKTOK_VIDEO_PATH)
            await callback.message.answer_video(video=video_file, caption=rules, parse_mode="HTML")
        else:
            # если нет видео, отправляем только текст
            await callback.message.answer(rules, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Ошибка отправки видео Tik Tok: {e}")
        await callback.message.answer(rules, parse_mode="HTML")

# ---------- Отчет Tik Tok (опросник) ----------
@router.callback_query(F.data == "report_tiktok")
async def report_tiktok_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id
    if not is_registered(user_id):
        await callback.message.answer("❌ Сначала зарегистрируйтесь.")
        return

    await state.set_state(TikTokReport.account_name)
    await callback.message.answer(
        "📝 <b>Отчет по Tik Tok</b>\n\n"
        "Ответьте на несколько вопросов для отправки отчета.\n"
        "1. Название вашего аккаунта Tik Tok:",
        parse_mode="HTML"
    )

@router.message(TikTokReport.account_name)
async def process_tiktok_account(message: Message, state: FSMContext):
    await state.update_data(account_name=message.text.strip())
    await state.set_state(TikTokReport.screenshot_profile)
    await message.answer(
        "2. Отправьте скриншот внутри профиля, где видно:\n"
        "2.1) Ваши последние ролики\n"
        "2.2) Возможность изменять профиль\n"
        "2.3) Что-то добавлять и т.д.\n"
        "На скриншоте ничего нельзя замазывать."
    )

@router.message(TikTokReport.screenshot_profile, F.photo)
async def process_tiktok_screenshot_profile(message: Message, state: FSMContext):
    # сохраняем file_id
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

    # Формируем отчёт
    report = (
        f"📊 <b>Новый отчет Tik Tok</b>\n"
        f"👤 Пользователь: @{message.from_user.username} (ID: {message.from_user.id})\n"
        f"📱 Аккаунт: {data.get('account_name')}\n"
        f"🔗 Ссылка на ролик: {data.get('video_link')}\n"
        f"📸 Скриншот профиля: (см. ниже)\n"
        f"📸 Скриншот просмотров: (см. ниже)"
    )

    # Отправляем в канал логов
    try:
        # сначала текст
        await message.bot.send_message(LOG_CHANNEL_ID, report, parse_mode="HTML")
        # затем два скриншота
        if data.get('screenshot_profile'):
            await message.bot.send_photo(LOG_CHANNEL_ID, data['screenshot_profile'])
        if data.get('screenshot_views'):
            await message.bot.send_photo(LOG_CHANNEL_ID, data['screenshot_views'])
    except Exception as e:
        logger.error(f"Ошибка отправки отчета Tik Tok: {e}")

    await message.answer("✅ Отчет отправлен! Менеджер проверит его в ближайшее время.")

@router.message(TikTokReport.screenshot_views)
async def process_tiktok_screenshot_views_invalid(message: Message):
    await message.answer("Пожалуйста, отправьте фото скриншота с просмотрами.")

# ---------- Кнопка "Сотрудничество с NC" ----------
@router.message(F.text == "🤝 Сотрудничество с NC")
async def collaboration_start(message: Message, state: FSMContext):
    if is_blocked(message.from_user.id):
        await message.answer("⛔ Вы заблокированы.")
        return
    await state.set_state(CollaborationForm.company_name)
    await message.answer(
        "🤝 <b>Сотрудничество с NC</b>\n\n"
        "Заполните форму для передачи ваших отзывов под работу NC.\n"
        "Вы должны быть осведомлены, что перед началом работы вы выплачиваете 60% от зарплаты людям (по ставкам NC).\n"
        "NC берет 20% от чистой прибыли за использование сервиса (минимум 60₽ за отзыв).\n\n"
        "Введите название вашей компании/проекта:",
        parse_mode="HTML"
    )

@router.message(CollaborationForm.company_name)
async def collaboration_company(message: Message, state: FSMContext):
    await state.update_data(company_name=message.text.strip())
    await state.set_state(CollaborationForm.reviews_count)
    await message.answer("Сколько отзывов вы готовы передать? (укажите число)")

@router.message(CollaborationForm.reviews_count)
async def collaboration_count(message: Message, state: FSMContext):
    try:
        count = int(message.text.strip())
        await state.update_data(reviews_count=count)
    except:
        await message.answer("Пожалуйста, введите число.")
        return
    await state.set_state(CollaborationForm.platforms)
    await message.answer("На каких платформах ваши отзывы? (Яндекс, Google, 2ГИС и т.д.)")

@router.message(CollaborationForm.platforms)
async def collaboration_platforms(message: Message, state: FSMContext):
    await state.update_data(platforms=message.text.strip())
    await state.set_state(CollaborationForm.links)
    await message.answer("Предоставьте ссылки на ваши отзывы (можно несколько, каждую с новой строки):")

@router.message(CollaborationForm.links)
async def collaboration_links(message: Message, state: FSMContext):
    await state.update_data(links=message.text.strip())
    await state.set_state(CollaborationForm.contact)
    await message.answer("Ваши контактные данные (Telegram username или телефон):")

@router.message(CollaborationForm.contact)
async def collaboration_contact(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()

    report = (
        f"🤝 <b>Новая заявка на сотрудничество</b>\n"
        f"👤 От: @{message.from_user.username} (ID: {message.from_user.id})\n"
        f"🏢 Компания: {data.get('company_name')}\n"
        f"📊 Кол-во отзывов: {data.get('reviews_count')}\n"
        f"📌 Платформы: {data.get('platforms')}\n"
        f"🔗 Ссылки:\n{data.get('links')}\n"
        f"📞 Контакты: {data.get('contact')}"
    )

    try:
        await message.bot.send_message(LOG_CHANNEL_ID, report, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Ошибка отправки заявки на сотрудничество: {e}")

    await message.answer("✅ Ваша заявка отправлена! Менеджер свяжется с вами в ближайшее время.")

# ---------- 👥 Мои рефералы (без изменений) ----------
# ... (код рефералов уже есть, я не повторяю для краткости)
