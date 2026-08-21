import sqlite3, asyncio, logging
from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from bot.config import MANAGER_USERNAME, DB_PATH
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

# ============= ОБНОВЛЁННЫЕ ПРАВИЛА =============
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
        await message.answer("👋 Привет!\n\nЯ бот для работы со слотами.\nВыберите нужный раздел на клавиатуре:", reply_markup=main_menu_keyboard())
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
    await message.answer(text, reply_markup=main_menu_keyboard())

# ---------- РЕФЕРАЛЬНАЯ СИСТЕМА (добавлено сюда для надёжности) ----------
@router.message(F.text == "👥 Реферальная система")
async def referral_info(message: Message):
    logger.info(f"🔔 Пользователь {message.from_user.id} (@{message.from_user.username}) нажал на 'Реферальная система' (обработчик из user.py)")
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
        logger.info(f"✅ Сообщение о реферальной системе отправлено пользователю {message.from_user.id}")
    except Exception as e:
        logger.error(f"❌ Ошибка при отправке реферальной информации: {e}")
        await message.answer("Произошла ошибка. Попробуйте позже.")

# ---------- Колбэки для рефералки ----------
@router.callback_query(F.data == "referral:back")
async def referral_back(callback: CallbackQuery):
    logger.info(f"🔄 Пользователь {callback.from_user.id} вернулся в главное меню из рефералки")
    try:
        await callback.message.delete()
        await callback.message.answer("👋 Главное меню", reply_markup=main_menu_keyboard())
        await callback.answer()
    except Exception as e:
        logger.error(f"❌ Ошибка в referral_back: {e}")
        await callback.answer("Ошибка, попробуйте снова", show_alert=True)

@router.callback_query(F.data == "referral:invite")
async def referral_invite(callback: CallbackQuery):
    logger.info(f"📨 Пользователь {callback.from_user.id} запросил приглашение")
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
        logger.info(f"✅ Приглашение отправлено пользователю {user_id}")
    except Exception as e:
        logger.error(f"❌ Ошибка в referral_invite: {e}")
        await callback.answer("Ошибка, попробуйте снова", show_alert=True)

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
        await message.answer("✅ Вы уже зарегистрированы! Используйте кнопку «📋 Профиль».")
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
        reply_markup=main_menu_keyboard()
    )

# ---------- /job (слоты) ----------
@router.message(Command("job"))
@router.message(F.text == "💼 Слоты")
async def cmd_job(message: Message):
    if is_blocked(message.from_user.id):
        await message.answer("⛔ Вы заблокированы.")
        return
    if not active_slots:
        await message.answer("😔 К сожалению на данный момент все слоты закрыты, ожидайте нового слота.\nС уважением команда New Chapter.")
        return
    lines = ["Открытые слоты:"]
    for msg_id, data in active_slots.items():
        lines.append(f"🔸 {data.get('command', data.get('platform', '?'))} {data.get('price', data.get('count', '?'))} (ID: {msg_id})")
    lines.append(f"\nДля получения слота напишите менеджеру @{MANAGER_USERNAME}")
    await message.answer("\n".join(lines))

# ---------- 👥 Мои рефералы ----------
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
            deadline = now

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
