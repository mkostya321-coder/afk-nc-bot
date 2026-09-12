import logging, os, secrets, time, asyncio
from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode
from bot.config import (
    ADMIN_IDS, CHANNEL_ID, MANAGER_USERNAME, OTHER_JOBS_CHANNEL, SHEET_ID,
    SCREENSHOT_CHANNEL_ID, get_credentials_path, INSTRUCTION_PHOTO_ID, INSTRUCTION_PHOTO_PATH
)
from bot.database import (
    is_registered, is_blocked, get_user, is_ga, is_moderator, get_user_by_username,
    add_review_take, count_review_takes_last_24h, get_limit
)
from bot.google_sheets import get_client
from bot.helpers import get_column_mapping, platform_from_sheet_name
from bot.state import active_slots, slot_requests
import pytz

router = Router()
logger = logging.getLogger(__name__)
moscow_tz = pytz.timezone("Europe/Moscow")

SNIPPET_WARNING = (
    "⚠️ ПРИМЕР КАК ДОЛЖЕН ВЫГЛЯДЕТЬ СКРИНШОТ КОТОРЫЙ Я БУДУ ОТ ВАС ЖДАТЬ!\n"
    "Скриншот в другом формате считается выполненным не по ТЗ и отзыв не будет оплачен."
)

SNIPPET_REQ = (
    "📌 Требования к скриншоту:\n"
    "Скриншот должен быть сделан в свернутом приложении (не в браузере).\n"
    "На скриншоте видно: платформу, текст отзыва, время публикации."
)

WARNING = (
    "<i>⚠️ Если не выполнить все взятые вами задачи до 23:30 и не успеть от них отказаться, "
    "всё выполненное будет оплачено на 30% ниже!</i>"
)

PIN_REMINDER = "📸 Инструкция по скриншотам — закреплена выше ⬆️"

PLATFORM_TEMPLATES = {
    "яндекс": {
        "instruction": SNIPPET_WARNING + "\n\n🔥 Яндекс Карты\n\n1. Переходим по ссылке.\n2. Переписываем текст.",
        "extra_text": SNIPPET_REQ,
        "warning": WARNING
    },
    "google": {
        "instruction": SNIPPET_WARNING + "\n\n🔥 Google Карты\n\n1. Переходим по ссылке.\n2. Переписываем текст.",
        "extra_text": SNIPPET_REQ,
        "warning": WARNING
    },
    "2гис": {
        "instruction": SNIPPET_WARNING + "\n\n🔥 2ГИС\n\n1. Переходим по ссылке, просматриваем всю информацию, лайкаем положительные отзывы и прокладываем маршрут.\n2. Через 15–30 минут оставляем отзыв.",
        "extra_text": SNIPPET_REQ,
        "warning": WARNING
    },
    "авито": {
        "instruction": (
            SNIPPET_WARNING + "\n\n🔥 Авито\n\n"
            "1. Поиск объявлений.\n"
            "   – Найти и изучить похожие объявления (критерии уточнить у администратора).\n"
            "2. Диалог с продавцом.\n"
            "   – Задать 5–6 вопросов о товаре/услуге.\n"
            "   – Важно: без скриншотов переписки!\n"
            "3. Ожидание.\n"
            "   – Выждать 2–3 дня после диалога.\n"
            "4. Отзыв.\n"
            "   – Написать отзыв (согласовать текст с администратором).\n"
            "   – Нельзя: копировать текст, делать скриншоты.\n"
            "   – Дополнительно: оставить отзыв через «ждут оценки», если получится."
        ),
        "extra_text": SNIPPET_REQ,
        "warning": WARNING
    },
    "вк": {
        "instruction": (
            SNIPPET_WARNING + "\n\n🔥 ВКонтакте\n\n"
            "1. Переходим по ссылке.\n2. Переписываем текст.\n\n"
            "На данной платформе обязательно перепишите текст от руки, иначе отзыв может просто заблокироваться.\n"
            "ДЛЯ 90% прохода:\n"
            "Оставьте отзыв несколько раз 3-4 раза, в этом случае он точно опубликуется, оставили 1 раз с другого устройства проверили появился ли он, если нет оставляете еще раз и так 3-4 раза."
        ),
        "extra_text": SNIPPET_REQ,
        "warning": WARNING
    },
    "докдок": {
        "instruction": SNIPPET_WARNING + "\n\n🔥 ДокДок\n\n1. Переходим по ссылке.\n2. Переписываем текст.",
        "extra_text": SNIPPET_REQ,
        "warning": WARNING
    },
    "докту": {
        "instruction": SNIPPET_WARNING + "\n\n🔥 ДокТу\n\n1. Переходим по ссылке.\n2. Переписываем текст.",
        "extra_text": SNIPPET_REQ,
        "warning": WARNING
    },
    "32топ": {
        "instruction": SNIPPET_WARNING + "\n\n🔥 32ТОП\n\n1. Переходим по ссылке.\n2. Переписываем текст.",
        "extra_text": SNIPPET_REQ,
        "warning": WARNING
    },
    "zoon": {
        "instruction": (
            SNIPPET_WARNING + "\n\n🔥 ZOON\n\n"
            "1. Переходим по ссылке, прокладываем маршрут и просматриваем всю информацию.\n"
            "2. Через 30 минут оставляем отзыв."
        ),
        "extra_text": SNIPPET_REQ,
        "warning": WARNING
    },
    "яу": {
        "instruction": (
            SNIPPET_WARNING + "\n\n🔥 Яндекс Услуги\n\n"
            "1. Переходим по ссылке.\n"
            "2. Оставляем отзыв."
        ),
        "extra_text": SNIPPET_REQ,
        "warning": WARNING
    },
    "яб": {
        "instruction": (
            SNIPPET_WARNING + "\n\n🔥 Яндекс Браузер\n\n"
            "1. Переходим по ссылке.\n"
            "2. Открывается сайт компании — в нижнем или верхнем правом углу жмём 3 точки.\n"
            "3. Жмём на количество отзывов и оставляем отзыв с текстом."
        ),
        "extra_text": SNIPPET_REQ,
        "warning": WARNING
    },
    "h": {
        "instruction": (
            SNIPPET_WARNING + "\n\n🔥 HH.RU\n\n"
            "1. Зайти по ссылке.\n"
            "2. Просматриваем фото/видео, лайкаем хорошие отзывы.\n"
            "3. Оставить отзыв."
        ),
        "extra_text": SNIPPET_REQ,
        "warning": WARNING
    },
}

DEFAULT_MAPPING = {
    "status_col": 10, "executor_col": 11,
    "flag_third_col": 15, "flag_second_col": 16, "flag_first_col": 17,
    "id_col": 19, "order_col": 20,
}


def get_safe_mapping(request: dict, platform: str) -> dict:
    """Возвращает mapping с fallback, если его нет в request."""
    mapping = request.get("mapping")
    if not mapping or "status_col" not in mapping:
        mapping = get_column_mapping(platform)
        request["mapping"] = mapping
    return mapping


# ============ ИНСТРУКЦИЯ ============
async def send_instruction(user_id: int, bot):
    try:
        caption = (
            "📸 Инструкция по отправке скриншотов:\n\n"
            "1. Сделайте скриншот экрана с отправленным на модерацию отзывом.\n"
            "2. Убедитесь, что видна платформа, текст и время публикации.\n"
            "3. Скриншот должен быть сделан в свернутом приложении (не в браузере), иначе шанс проходимости снижается, есть риск удаления отзыва.\n"
            "4. Отправьте скриншот конкретно на отзыв, который вы сделали.\n"
            "5. Если скриншот не соответствует требованиям, отзыв НЕ БУДЕТ ОПЛАЧЕН."
        )
        sent = None
        if INSTRUCTION_PHOTO_ID:
            sent = await bot.send_photo(chat_id=user_id, photo=INSTRUCTION_PHOTO_ID, caption=caption)
        elif INSTRUCTION_PHOTO_PATH and os.path.exists(INSTRUCTION_PHOTO_PATH):
            photo = FSInputFile(INSTRUCTION_PHOTO_PATH)
            sent = await bot.send_photo(chat_id=user_id, photo=photo, caption=caption)
        else:
            sent = await bot.send_message(chat_id=user_id, text=caption)

        if sent:
            try:
                await bot.pin_chat_message(chat_id=user_id, message_id=sent.message_id, disable_notification=True)
                logger.info(f"📌 Инструкция закреплена для {user_id}")
            except Exception as e:
                logger.warning(f"⚠️ Не удалось закрепить инструкцию: {e}")
    except Exception as e:
        logger.error(f"Ошибка отправки инструкции: {e}")


async def unpin_instruction(user_id: int, bot):
    try:
        await bot.unpin_all_chat_messages(chat_id=user_id)
        logger.info(f"📌 Инструкция откреплена у {user_id}")
    except Exception as e:
        logger.warning(f"⚠️ Не удалось открепить: {e}")


async def check_limit(user_id: int, platform: str) -> bool:
    return count_review_takes_last_24h(user_id, platform) < get_limit(platform)


# ============ CANCEL ============
@router.message(Command("cancel"))
@router.message(Command("отказ"))
async def cancel_task(message: Message):
    user_id = message.from_user.id
    if user_id not in slot_requests:
        await message.answer("❌ У вас нет активного задания.")
        return
    request = slot_requests[user_id]
    completed = request.get("completed_reviews", [])
    ordered = request.get("ordered_reviews", [])
    remaining = [r for r, n in ordered if n not in completed]
    if not remaining:
        await message.answer("✅ У вас нет невыполненных отзывов.")
        del slot_requests[user_id]
        return

    platform = request.get("platform", "яндекс")
    mapping = get_safe_mapping(request, platform)
    sheet_title = request.get("sheet_title")
    logger.info(f"🔄 Отмена: {user_id}, {platform}, невыполненных: {len(remaining)}")

    client = get_client()
    if client and sheet_title:
        try:
            sheet = client.open_by_key(SHEET_ID).worksheet(sheet_title)
            batch = []
            for row_idx in remaining:
                for key, val in [("status_col", "не принят в работу"), ("executor_col", ""),
                                 ("flag_third_col", 0), ("flag_second_col", 0), ("flag_first_col", 0),
                                 ("id_col", ""), ("order_col", "")]:
                    if key not in mapping:
                        continue
                    col = chr(64 + mapping[key])
                    batch.append({"range": f"{col}{row_idx}", "values": [[val]]})
            for i in range(0, len(batch), 50):
                sheet.batch_update(batch[i:i+50])
                await asyncio.sleep(0.5)
            logger.info(f"✅ Очищено {len(remaining)} строк")
        except Exception as e:
            logger.error(f"❌ Ошибка отмены: {e}")

    del slot_requests[user_id]
    await message.answer(
        f"✅ Отказ принят.\n\n"
        f"• Выполненные: {len(completed)} – на модерацию\n"
        f"• Невыполненные: {len(remaining)} – переопубликуются"
    )


# ============ RESUME ============
@router.message(Command("resume"))
@router.message(Command("слот"))
async def cmd_resume(message: Message):
    user_id = message.from_user.id
    if not is_registered(user_id):
        await message.answer("❌ Вы не зарегистрированы.")
        return
    if is_blocked(user_id):
        await message.answer("⛔ Вы заблокированы.")
        return

    if user_id in slot_requests:
        req = slot_requests[user_id]
        total = len(req.get("ordered_reviews", []))
        done = len(req.get("completed_reviews", []))
        await message.answer(
            f"✅ У вас уже есть активный слот: {req['platform']}.\n"
            f"Отзывов осталось: {total - done}",
            reply_markup=InlineKeyboardBuilder().button(
                text="🎯 Активный слот", callback_data=f"active_slot|{user_id}"
            ).as_markup()
        )
        return

    user = get_user(user_id)
    if not user or not user.get("tg_username"):
        await message.answer("❌ У вас не указан Telegram username.")
        return
    username = f"@{user['tg_username']}"

    client = get_client()
    if not client:
        await message.answer("❌ Ошибка доступа к таблице.")
        return
    spreadsheet = client.open_by_key(SHEET_ID)

    found = []
    for sheet in spreadsheet.worksheets():
        sheet_name = sheet.title
        platform = platform_from_sheet_name(sheet_name)
        if not platform:
            continue
        mapping = get_column_mapping(platform)
        try:
            records = sheet.get_all_values()
        except:
            continue
        for row_idx, row in enumerate(records[1:], start=2):
            if len(row) < max(mapping["status_col"], mapping["executor_col"]):
                continue
            status = row[mapping["status_col"]-1].strip().lower()
            executor = row[mapping["executor_col"]-1].strip().lower()
            if status == "в работе" and executor == username.lower():
                found.append({"platform": platform, "sheet_title": sheet_name, "row_idx": row_idx, "mapping": mapping})

    if not found:
        await message.answer("❌ У вас нет активных слотов.")
        return

    platform = found[0]["platform"]
    sheet_title = found[0]["sheet_title"]
    mapping = found[0]["mapping"]
    row_ids = [r["row_idx"] for r in found if r["platform"] == platform]
    ordered_reviews = [(r, i) for i, r in enumerate(row_ids, start=1)]

    slot_requests[user_id] = {
        "platform": platform, "count": len(row_ids),
        "date": None, "time": None, "slot_msg_id": "resume",
        "state": "slot_selection", "assigned_rows": row_ids, "current_index": 0,
        "row_ids": [], "from_menu": False, "mapping": mapping, "sheet_title": sheet_title,
        "ordered_reviews": ordered_reviews, "completed_reviews": [],
        "active_review_row": None, "extra_messages": []
    }
    await message.answer(
        f"✅ Сессия восстановлена!\n\n"
        f"📋 Платформа: {platform}\n"
        f"📊 Отзывов: {len(row_ids)}",
        reply_markup=InlineKeyboardBuilder().button(
            text="🎯 Активный слот", callback_data=f"active_slot|{user_id}"
        ).as_markup()
    )


# ============ ВВОД КОЛИЧЕСТВА ============
@router.message(F.text)
async def handle_quantity_input(message: Message):
    if message.text and message.text.startswith('/'):
        return
    user_id = message.from_user.id
    if user_id not in slot_requests:
        return
    request = slot_requests[user_id]
    if request.get("state") != "waiting_quantity":
        return
    try:
        quantity = int(message.text.strip())
    except:
        await message.answer("Пожалуйста, введите число.")
        return
    if quantity <= 0 or quantity > request["count"]:
        await message.answer(f"❌ Можно взять от 1 до {request['count']} отзывов.")
        return

    platform = request.get("platform", "яндекс")
    mapping = get_safe_mapping(request, platform)
    sheet_title = request.get("sheet_title")

    client = get_client()
    if not client:
        await message.answer("❌ Ошибка доступа к таблице.")
        del slot_requests[user_id]
        return
    spreadsheet = client.open_by_key(SHEET_ID)

    slot_msg_id = request["slot_msg_id"]
    slot_info = active_slots.get(slot_msg_id)
    if not slot_info:
        slot_info = {
            "row_ids": request.get("row_ids", []),
            "count": request.get("count", 0),
            "mapping": mapping, "sheet_title": sheet_title, "platform": platform
        }
        if not slot_info["row_ids"]:
            await message.answer("❌ Попробуйте /resume.")
            del slot_requests[user_id]
            return

    row_ids = slot_info["row_ids"]
    if len(row_ids) < quantity:
        await message.answer("❌ Свободных меньше. Попробуйте заново.")
        del slot_requests[user_id]
        return

    try:
        sheet = spreadsheet.worksheet(sheet_title)
        records = sheet.get_all_values()
    except Exception as e:
        await message.answer("❌ Ошибка доступа к листу.")
        del slot_requests[user_id]
        return

    free_rows = []
    for row_idx in row_ids:
        if row_idx - 1 >= len(records):
            continue
        row = records[row_idx - 1]
        status = row[mapping["status_col"]-1].strip().lower() if len(row) >= mapping["status_col"] else ""
        executor = row[mapping["executor_col"]-1].strip() if len(row) >= mapping["executor_col"] else ""
        if status in ("в работе", "на модерации", "на модерации с опз"):
            continue
        if executor:
            continue
        free_rows.append(row_idx)

    if len(free_rows) < quantity:
        await message.answer(f"⚠️ Свободно только {len(free_rows)}. Возьмите меньше или /resume.")
        del slot_requests[user_id]
        return

    assigned_rows = free_rows[:quantity]

    if slot_msg_id in active_slots:
        slot_info["row_ids"] = [r for r in row_ids if r not in assigned_rows]
        slot_info["count"] = len(slot_info["row_ids"])
        active_slots[slot_msg_id] = slot_info

        if slot_info["count"] == 0:
            try:
                await message.bot.edit_message_text(
                    chat_id=CHANNEL_ID,
                    message_id=slot_msg_id,
                    text="🔥 Слот полностью разобран. Ожидайте следующий."
                )
            except Exception as e:
                logger.warning(f"⚠️ Не удалось отредактировать: {e}")
            try:
                del active_slots[slot_msg_id]
            except KeyError:
                pass

    username = f"@{message.from_user.username}" if message.from_user.username else message.from_user.full_name
    logger.info(f"📝 Записываем {username} в K (столбец {mapping['executor_col']}), строки: {assigned_rows}")

    batch = []
    for row_idx in assigned_rows:
        col_j = chr(64 + mapping["status_col"])
        col_k = chr(64 + mapping["executor_col"])
        col_t = chr(64 + mapping["order_col"])
        idx = assigned_rows.index(row_idx) + 1
        batch.append({"range": f"{col_j}{row_idx}", "values": [["в работе"]]})
        batch.append({"range": f"{col_k}{row_idx}", "values": [[username]]})
        batch.append({"range": f"{col_t}{row_idx}", "values": [[idx]]})

    try:
        for i in range(0, len(batch), 50):
            sheet.batch_update(batch[i:i+50])
            await asyncio.sleep(0.5)
        logger.info(f"✅ Записано {len(assigned_rows)} строк")
    except Exception as e:
        logger.error(f"❌ Ошибка batch: {e}")

    ordered_reviews = [(r, i) for i, r in enumerate(assigned_rows, start=1)]
    request["ordered_reviews"] = ordered_reviews
    request["completed_reviews"] = []
    request["active_review_row"] = None
    request["state"] = "slot_selection"
    request["assigned_rows"] = assigned_rows
    request["extra_messages"] = []
    request["mapping"] = mapping
    slot_requests[user_id] = request

    for _ in range(quantity):
        add_review_take(user_id, platform)

    await message.answer(
        f"🎯 Вы взяли {quantity} отзывов на платформе {platform}.\n"
        "Нажмите «Активный слот», чтобы приступить.",
        reply_markup=InlineKeyboardBuilder().button(
            text="🎯 Активный слот", callback_data=f"active_slot|{user_id}"
        ).as_markup()
    )

    await send_instruction(user_id, message.bot)


# ============ ВЗЯТЬ СЛОТ ============
@router.callback_query(F.data.startswith("take_slot|"))
async def take_slot_start(callback: CallbackQuery):
    try:
        await callback.answer()
    except Exception:
        pass
    user_id = callback.from_user.id
    if not is_registered(user_id):
        await callback.bot.send_message(user_id, "❌ Вы не зарегистрированы.")
        return
    if is_blocked(user_id):
        await callback.bot.send_message(user_id, "⛔ Вы заблокированы.")
        return
    if user_id in slot_requests:
        await callback.bot.send_message(user_id, f"❌ У вас уже есть активный слот: {slot_requests[user_id]['platform']}.")
        return

    parts = callback.data.split("|")
    if len(parts) < 5:
        await callback.bot.send_message(user_id, "Некорректный запрос.")
        return
    _, platform, count_str, date, time_safe = parts
    try:
        count = int(count_str)
    except:
        count = 0
    time = time_safe.replace('-', ':')
    slot_msg_id = callback.message.message_id
    slot_info = active_slots.get(slot_msg_id)
    if not slot_info:
        platform_slots = [(m, s) for m, s in active_slots.items() if s.get("platform") == platform and s.get("count", 0) > 0]
        if platform_slots:
            slot_msg_id, slot_info = platform_slots[0]
        else:
            await callback.bot.send_message(user_id, "❌ Слот не найден. /resume.")
            return
    if slot_info.get("count", 0) == 0:
        await callback.bot.send_message(user_id, "❌ Этот слот уже разобран. Ожидайте следующий.")
        return
    if not await check_limit(user_id, platform):
        await callback.bot.send_message(user_id, f"❌ Лимит на {platform}.")
        return

    mapping = slot_info.get("mapping") or get_column_mapping(platform)
    slot_requests[user_id] = {
        "platform": platform, "count": slot_info.get("count", count),
        "date": date, "time": time, "slot_msg_id": slot_msg_id,
        "state": "waiting_quantity", "assigned_rows": [], "current_index": 0,
        "row_ids": slot_info["row_ids"], "from_menu": False,
        "mapping": mapping,
        "sheet_title": slot_info.get("sheet_title")
    }
    await callback.bot.send_message(
        chat_id=user_id,
        text=(
            f"📊 Доступно: {slot_info.get('count', count)} шт.\n"
            f"Сколько выполните?\n\n"
            f"Если хотите отказаться пропишите команду /cancel."
        )
    )


@router.callback_query(F.data.startswith("active_slot|"))
async def active_slot(callback: CallbackQuery):
    user_id = int(callback.data.split("|")[1])
    if user_id != callback.from_user.id:
        await callback.answer("Это не ваша сессия.", show_alert=True)
        return
    if user_id not in slot_requests:
        await callback.answer("❌ Сессия не найдена. /resume.", show_alert=True)
        return
    if slot_requests[user_id].get("state") != "slot_selection":
        await callback.answer("❌ Уже в процессе.", show_alert=True)
        return
    await callback.answer()
    await show_slot_buttons(callback.message, user_id)


async def show_slot_buttons(message: Message, user_id: int):
    request = slot_requests[user_id]
    ordered = request.get("ordered_reviews", [])
    completed = request.get("completed_reviews", [])
    platform = request.get("platform", "яндекс")
    if not request.get("mapping"):
        request["mapping"] = get_column_mapping(platform)
        slot_requests[user_id] = request
    names = {
        "яндекс": "Яндекс", "google": "Google", "2гис": "2ГИС", "авито": "Авито",
        "вк": "ВК", "отзовик": "Отзовик", "доктору": "Doctoru", "докдок": "ДокДок",
        "про докторов": "Про Докторов", "докту": "ДокТу", "32топ": "32ТОП",
        "zoon": "ZOON", "яу": "ЯУ", "яб": "ЯБ", "h": "HH"
    }
    name = names.get(platform, platform.capitalize())
    builder = InlineKeyboardBuilder()
    for row_idx, num in ordered:
        if num not in completed:
            builder.button(text=f"{name} {num}", callback_data=f"select_review|{num}")
    builder.adjust(3)
    await message.edit_text("📋 Выберите номер отзыва:", reply_markup=builder.as_markup())


# ============ ВЫБОР ОТЗЫВА ============
@router.callback_query(F.data.startswith("select_review|"))
async def select_review(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in slot_requests:
        await callback.answer("❌ /resume.", show_alert=True)
        return
    request = slot_requests[user_id]
    if request.get("state") != "slot_selection":
        await callback.answer("❌ Уже работаете.", show_alert=True)
        return

    # ФИКС: mapping с fallback
    platform = request.get("platform", "яндекс")
    mapping = get_safe_mapping(request, platform)
    slot_requests[user_id] = request

    selected_num = int(callback.data.split("|")[1])
    ordered = request.get("ordered_reviews", [])
    target_row = None
    for row_idx, num in ordered:
        if num == selected_num and num not in request.get("completed_reviews", []):
            target_row = row_idx
            break
    if target_row is None:
        await callback.answer("❌ Уже выполнен.", show_alert=True)
        return
    request["active_review_row"] = target_row
    request["state"] = "working_on_review"
    slot_requests[user_id] = request

    client = get_client()
    if not client:
        await callback.answer("❌ Ошибка доступа.", show_alert=True)
        return
    spreadsheet = client.open_by_key(SHEET_ID)
    sheet = None
    sheet_title = request.get("sheet_title")
    if sheet_title:
        try:
            sheet = spreadsheet.worksheet(sheet_title)
        except:
            pass
    if sheet is None:
        for s in spreadsheet.worksheets():
            try:
                s.cell(target_row, 1)
                sheet = s
                break
            except:
                continue
    if sheet is None:
        await callback.answer("❌ Ошибка таблицы.", show_alert=True)
        return
    await show_review_info(callback.message, user_id, target_row, sheet, mapping, platform)
    await callback.answer()


# ============ ПОКАЗ ОТЗЫВА ============
async def show_review_info(message: Message, user_id: int, row_idx: int, sheet, mapping, platform):
    request = slot_requests[user_id]

    # ФИКС: fallback mapping
    if not mapping or "status_col" not in mapping:
        mapping = get_column_mapping(platform)
        request["mapping"] = mapping
        slot_requests[user_id] = request

    row = sheet.row_values(row_idx)
    extra_ids = []

    logger.info(f"📄 Показ отзыва строка {row_idx}, платформа {platform}")

    if platform == "про докторов":
        tz_link = row[mapping["tz_col"]-1] if len(row) >= mapping["tz_col"] else ""
        doctor_name = row[mapping["doctor_name_col"]-1] if len(row) >= mapping["doctor_name_col"] else ""
        doctor_direction = row[mapping["doctor_direction_col"]-1] if len(row) >= mapping["doctor_direction_col"] else ""
        gender = row[mapping["gender_col"]-1] if len(row) >= mapping["gender_col"] else ""
        stars = row[mapping["stars_col"]-1] if len(row) >= mapping["stars_col"] else ""
        platform_name = row[mapping["platform_col"]-1] if len(row) >= mapping["platform_col"] else ""
        link = row[mapping["link_col"]-1] if len(row) >= mapping["link_col"] else ""
        doc_link = row[mapping["photo_doc_col"]-1] if len(row) >= mapping["photo_doc_col"] else ""
        history = row[mapping["text_history_col"]-1] if len(row) >= mapping["text_history_col"] else ""
        like = row[mapping["text_like_col"]-1] if len(row) >= mapping["text_like_col"] else ""
        minus = row[mapping["text_minus_col"]-1] if len(row) >= mapping["text_minus_col"] else ""

        gender_text = "Без пола" if not gender else ("Мужской" if gender.upper() == "М" else "Женский")
        info_msg = (
            f"{SNIPPET_WARNING}\n\n"
            f"👨‍⚕️ <b>Информация по врачу:</b>\n"
            f"Имя врача: {doctor_name}\n"
            f"Направление: {doctor_direction}\n\n"
            f"<b>Информация по отзыву:</b>\n"
            f"Пол: {gender_text}\n"
            f"Кол-во звезд: {stars}\n"
            f"Платформа: {platform_name}\n"
            f"Ссылка на платформу: {link}\n\n"
            f"{SNIPPET_REQ}\n\n"
            f"<b>❗ Важно!</b>\n"
            f"Если в документе нет даты рождения, укажите возраст от 20 лет.\n"
            f"Если нет даты посещения, укажите в течение последних 7 дней.\n\n"
            f"{PIN_REMINDER}"
        )
        await message.edit_text(info_msg, parse_mode="HTML",
            reply_markup=InlineKeyboardBuilder().button(text="🔙 Вернуться к слоту", callback_data="back_to_slot").as_markup())

        if tz_link:
            sent = await message.answer(f"📄 <b>ТЗ</b>\n\n{tz_link}", parse_mode="HTML")
            extra_ids.append(sent.message_id)
        if doc_link:
            sent = await message.answer(f"📎 <b>Документ</b> (обязательно прикрепить)\n\n{doc_link}", parse_mode="HTML")
            extra_ids.append(sent.message_id)
        if history:
            sent = await message.answer(f"1️⃣ <b>История</b>\n\n{history}", parse_mode="HTML")
            extra_ids.append(sent.message_id)
        if like:
            sent = await message.answer(f"2️⃣ <b>Больше понравилось</b>\n\n{like}", parse_mode="HTML")
            extra_ids.append(sent.message_id)
        if minus:
            sent = await message.answer(f"3️⃣ <b>Не понравилось</b>\n\n{minus}", parse_mode="HTML")
            extra_ids.append(sent.message_id)

    else:
        link = row[mapping["link_col"]-1] if len(row) >= mapping["link_col"] else ""
        stars = row[mapping["stars_col"]-1] if len(row) >= mapping["stars_col"] else ""
        gender = row[mapping["gender_col"]-1] if len(row) >= mapping["gender_col"] else ""
        text = row[mapping["text_col"]-1] if len(row) >= mapping["text_col"] else ""
        photo_link = row[17] if len(row) > 17 else ""

        template = PLATFORM_TEMPLATES.get(platform, PLATFORM_TEMPLATES["яндекс"])
        instruction_text = template["instruction"]
        extra_text = template["extra_text"]
        warning = template["warning"]

        gender_text = ""
        if gender.upper() == "М":
            gender_text = "👨 Отзыв мужской. Его должен выполнить мужчина с мужским именем на картах."
        elif gender.upper() == "Ж":
            gender_text = "👩 Отзыв женский. Её должна выполнить женщина с женским именем на картах."
        else:
            gender_text = "👤 Отзыв без пола. Может выполнить и мужчина, и женщина."

        final_msg = (
            f"{instruction_text}\n\n"
            f"{extra_text}\n\n"
            f"⭐ Количество звёзд: {stars}\n"
            f"👥 1 ЧЕЛОВЕК 1 ОТЗЫВ (на одной платформе)\n"
            f"{gender_text}\n\n"
            f"{PIN_REMINDER}\n\n"
            "Пожалуйста, после выполнения пришлите скриншот отзыва.\n\n"
            "Если хотите отказаться от оставшихся заданий — /cancel.\n\n"
            f"{warning}"
        )

        await message.edit_text(final_msg, parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardBuilder().button(text="🔙 Вернуться к слоту", callback_data="back_to_slot").as_markup())

        if link:
            sent = await message.answer(link)
            extra_ids.append(sent.message_id)

        if text:
            sent = await message.answer(f"📝 <b>Текст отзыва:</b>\n\n{text}", parse_mode="HTML")
            extra_ids.append(sent.message_id)
        else:
            sent = await message.answer("⚠️ <b>Текст отзыва не найден.</b>")
            extra_ids.append(sent.message_id)

        if photo_link:
            sent = await message.answer(
                f"📸 <b>ФОТО обязательное к прикреплению к отзыву!</b>\n\n{photo_link}\n\n"
                f"<b>⚠️ ШТРАФ 50% если не прикрепить!</b>",
                parse_mode="HTML"
            )
            extra_ids.append(sent.message_id)

    request["extra_messages"] = extra_ids
    request["active_review_row"] = row_idx
    slot_requests[user_id] = request


# ============ ВЕРНУТЬСЯ К СЛОТУ ============
@router.callback_query(F.data == "back_to_slot")
async def back_to_slot(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in slot_requests:
        await callback.answer("❌ Сессия не найдена.", show_alert=True)
        return
    request = slot_requests[user_id]
    if request.get("state") != "working_on_review":
        await callback.answer("❌ Не в просмотре.", show_alert=True)
        return
    chat_id = callback.message.chat.id
    for msg_id in request.get("extra_messages", []):
        try:
            await callback.bot.delete_message(chat_id=chat_id, message_id=msg_id)
        except:
            pass
    request["extra_messages"] = []
    request["state"] = "slot_selection"
    request["active_review_row"] = None
    slot_requests[user_id] = request
    await callback.answer()
    await show_slot_buttons(callback.message, user_id)


# ============ СКРИНШОТ ============
@router.message(F.photo)
async def handle_screenshot(message: Message):
    user_id = message.from_user.id
    if user_id not in slot_requests:
        return
    request = slot_requests[user_id]
    if request.get("state") != "working_on_review":
        await message.answer("❌ Сначала выберите отзыв.")
        return
    active_row = request.get("active_review_row")
    if active_row is None:
        await message.answer("❌ Активный отзыв не найден.")
        return
    chat_id = message.chat.id
    for msg_id in request.get("extra_messages", []):
        try:
            await message.bot.delete_message(chat_id=chat_id, message_id=msg_id)
        except:
            pass
    request["extra_messages"] = []

    platform = request.get("platform", "яндекс")
    mapping = get_safe_mapping(request, platform)
    sheet_title = request.get("sheet_title")

    client = get_client()
    if not client:
        await message.answer("❌ Ошибка доступа.")
        return
    spreadsheet = client.open_by_key(SHEET_ID)
    sheet = None
    if sheet_title:
        try:
            sheet = spreadsheet.worksheet(sheet_title)
        except:
            pass
    if sheet is None:
        for s in spreadsheet.worksheets():
            try:
                s.cell(active_row, 1)
                sheet = s
                break
            except:
                continue
    if sheet is None:
        await message.answer("❌ Лист не найден.")
        return

    review_id = sheet.cell(active_row, mapping["id_col"]).value
    if not review_id:
        review_id = secrets.token_hex(4)
        sheet.update_cell(active_row, mapping["id_col"], review_id)

    try:
        sheet.update_cell(active_row, mapping["status_col"], "на модерации")
        sheet.update_cell(active_row, mapping["flag_final_col"], 333)
        sheet.format(f"{chr(64+mapping['flag_final_col'])}{active_row}", {
            "backgroundColor": {"red": 0, "green": 0.8, "blue": 0}
        })
        logger.info(f"✅ Строка {active_row} → 'на модерации'")
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await message.answer("❌ Ошибка сохранения.")
        return

    try:
        user = get_user(user_id)
        user_mention = f"@{user['tg_username']}" if user and user.get('tg_username') else f"@{message.from_user.username}"
        timestamp = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        caption = f"{user_mention} – {timestamp}\nID: {review_id or 'Unknown'}"
        await message.bot.send_photo(chat_id=SCREENSHOT_CHANNEL_ID, photo=message.photo[-1].file_id, caption=caption)
    except Exception as e:
        logger.error(f"Ошибка скриншота: {e}")

    ordered = request.get("ordered_reviews", [])
    completed = request.get("completed_reviews", [])
    for row_idx, num in ordered:
        if row_idx == active_row:
            completed.append(num)
            break
    request["completed_reviews"] = completed
    request["active_review_row"] = None
    request["state"] = "slot_selection"
    slot_requests[user_id] = request

    total = len(ordered)
    if len(completed) == total:
        await unpin_instruction(user_id, message.bot)
        await message.answer("✅ Все отзывы отправлены на модерацию!")
        del slot_requests[user_id]
        return
    await message.answer(
        f"✅ Отзыв выполнен! Осталось {total - len(completed)}.",
        reply_markup=InlineKeyboardBuilder().button(
            text="🎯 Активный слот", callback_data=f"active_slot|{user_id}"
        ).as_markup()
    )
