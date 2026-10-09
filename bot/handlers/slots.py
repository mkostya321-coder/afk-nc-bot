import logging, os, secrets, time, asyncio
from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode
from bot.config import (
    ADMIN_IDS, CHANNEL_ID, MANAGER_USERNAME, OTHER_JOBS_CHANNEL, SHEET_ID,
    SCREENSHOT_CHANNEL_ID, get_credentials_path, INSTRUCTION_PHOTO_ID, INSTRUCTION_PHOTO_PATH,
    REQUIRED_CHANNEL_ID,
)
from bot.database import (
    is_registered, is_blocked, get_user, is_ga, is_moderator, get_user_by_username,
    add_review_take, count_review_takes_last_24h, get_limit, get_effective_limit
)
from bot.google_sheets import get_client, build_slot_message
from bot.helpers import get_column_mapping, platform_from_sheet_name, business_day_key
from bot.state import active_slots, slot_requests
import pytz

router = Router()
logger = logging.getLogger(__name__)
moscow_tz = pytz.timezone("Europe/Moscow")


async def _safe_send(bot, chat_id: int, text: str, **kwargs):
    try:
        return await bot.send_message(chat_id=chat_id, text=text, **kwargs)
    except Exception as e:
        logger.warning(f"⚠️ _safe_send для {chat_id}: {e}")
        return None


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
        "instruction": "🔥 Яндекс Карты\n\n1. Переходим по ссылке.\n2. Переписываем текст.",
        "extra_text": SNIPPET_REQ, "warning": WARNING
    },
    "яндекс негатив": {
        "instruction": "🔥 Яндекс Негатив\n\n1. Переходим по ссылке.\n2. Переписываем текст.",
        "extra_text": SNIPPET_REQ, "warning": WARNING
    },
    "google": {
        "instruction": "🔥 Google Карты\n\n1. Переходим по ссылке.\n2. Переписываем текст.",
        "extra_text": SNIPPET_REQ, "warning": WARNING
    },
    "2гис": {
        "instruction": "🔥 2ГИС\n\n1. Переходим по ссылке, просматриваем всю информацию, лайкаем положительные отзывы и прокладываем маршрут.\n2. Через 15–30 минут оставляем отзыв.",
        "extra_text": SNIPPET_REQ, "warning": WARNING
    },
    "авито": {
        "instruction": (
            "🔥 Авито\n\n"
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
        "extra_text": SNIPPET_REQ, "warning": WARNING
    },
    "вк": {
        "instruction": (
            "🔥 ВКонтакте\n\n"
            "1. Переходим по ссылке.\n2. Переписываем текст.\n\n"
            "На данной платформе обязательно перепишите текст от руки, иначе отзыв может просто заблокироваться.\n"
            "ДЛЯ 90% прохода:\n"
            "Оставьте отзыв несколько раз 3-4 раза, в этом случае он точно опубликуется, оставили 1 раз с другого устройства проверили появился ли он, если нет оставляете еще раз и так 3-4 раза."
        ),
        "extra_text": SNIPPET_REQ, "warning": WARNING
    },
    "отзовик": {
        "instruction": "🔥 Отзовик\n\n1. Переходим по ссылке.\n2. Переписываем текст.",
        "extra_text": SNIPPET_REQ, "warning": WARNING
    },
    "докдок": {
        "instruction": "🔥 ДокДок\n\n1. Переходим по ссылке.\n2. Переписываем текст.",
        "extra_text": SNIPPET_REQ, "warning": WARNING
    },
    "докту": {
        "instruction": "🔥 ДокТу\n\n1. Переходим по ссылке.\n2. Переписываем текст.",
        "extra_text": SNIPPET_REQ, "warning": WARNING
    },
    "32топ": {
        "instruction": "🔥 32ТОП\n\n1. Переходим по ссылке.\n2. Переписываем текст.",
        "extra_text": SNIPPET_REQ, "warning": WARNING
    },
    "zoon": {
        "instruction": (
            "🔥 ZOON\n\n"
            "1. Переходим по ссылке, прокладываем маршрут и просматриваем всю информацию.\n"
            "2. Через 30 минут оставляем отзыв."
        ),
        "extra_text": SNIPPET_REQ, "warning": WARNING
    },
    "яу": {
        "instruction": "🔥 Яндекс Услуги\n\n1. Переходим по ссылке.\n2. Оставляем отзыв.",
        "extra_text": SNIPPET_REQ, "warning": WARNING
    },
    "яб": {
        "instruction": (
            "🔥 Яндекс Браузер\n\n"
            "1. Переходим по ссылке.\n"
            "2. Открывается сайт компании — в нижнем или верхнем правом углу жмём 3 точки.\n"
            "3. Жмём на количество отзывов и оставляем отзыв с текстом."
        ),
        "extra_text": SNIPPET_REQ, "warning": WARNING
    },
    "h": {
        "instruction": (
            "🔥 HH.RU\n\n"
            "1. Зайти по ссылке.\n"
            "2. Просматриваем фото/видео, лайкаем хорошие отзывы.\n"
            "3. Оставить отзыв."
        ),
        "extra_text": SNIPPET_REQ, "warning": WARNING
    },
    "yell": {
        "instruction": "🔥 Yell\n\n1. Переходим по ссылке.\n2. Переписываем текст.",
        "extra_text": SNIPPET_REQ, "warning": WARNING
    },
}

DEFAULT_MAPPING = {
    "status_col": 10, "executor_col": 11,
    "flag_third_col": 15, "flag_second_col": 16, "flag_first_col": 17,
    "id_col": 19, "order_col": 20,
}


def get_safe_mapping(request: dict, platform: str) -> dict:
    mapping = request.get("mapping")
    if not mapping or "status_col" not in mapping:
        mapping = get_column_mapping(platform)
        request["mapping"] = mapping
    return mapping


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
            return sent.message_id
        return None
    except Exception as e:
        logger.error(f"Ошибка отправки инструкции: {e}")
        return None


async def unpin_instruction(user_id: int, bot):
    try:
        await bot.unpin_all_chat_messages(chat_id=user_id)
        logger.info(f"📌 Инструкция откреплена у {user_id}")
    except Exception as e:
        logger.warning(f"⚠️ Не удалось открепить: {e}")


async def delete_session_messages(user_id: int, bot, request: dict, chat_id: int = None):
    if chat_id is None:
        chat_id = user_id
    for msg_id in request.get("extra_messages", []):
        try:
            await bot.delete_message(chat_id=chat_id, message_id=msg_id)
        except Exception:
            pass
    instr_id = request.get("instruction_msg_id")
    if instr_id:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=instr_id)
            logger.info(f"🗑️ user {user_id}: инструкция удалена (msg {instr_id})")
        except Exception as e:
            logger.warning(f"⚠️ user {user_id}: не удалось удалить инструкцию: {e}")
    controls_id = request.get("controls_msg_id")
    if controls_id:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=controls_id)
            logger.info(f"🗑️ user {user_id}: controls удалено (msg {controls_id})")
        except Exception as e:
            logger.warning(f"⚠️ user {user_id}: не удалось удалить controls: {e}")
    try:
        await bot.unpin_all_chat_messages(chat_id=chat_id)
    except Exception:
        pass


async def check_limit(user_id: int, platform: str) -> bool:
    limit = get_effective_limit(user_id, platform)
    return count_review_takes_last_24h(user_id, platform) < limit


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
    completed_rows = [r for r, n in ordered if n in completed]
    if not remaining:
        await delete_session_messages(user_id, message.bot, request, message.chat.id)
        await message.answer("✅ У вас нет невыполненных отзывов.")
        del slot_requests[user_id]
        return

    platform = request.get("platform", "яндекс")
    mapping = get_safe_mapping(request, platform)
    sheet_title = request.get("sheet_title")
    logger.info(f"🔄 Отмена: {user_id}, {platform}, невыполненных: {len(remaining)}, выполненных: {len(completed_rows)}")

    client = get_client()
    if client and sheet_title:
        try:
            spreadsheet = await asyncio.to_thread(client.open_by_key, SHEET_ID)
            sheet = await asyncio.to_thread(spreadsheet.worksheet, sheet_title)
            batch = []

            for row_idx in remaining:
                for key, val in [("status_col", "не принят в работу"), ("executor_col", ""),
                                 ("flag_third_col", 0), ("flag_second_col", 0), ("flag_first_col", 0),
                                 ("id_col", ""), ("order_col", "")]:
                    if key not in mapping:
                        continue
                    col = chr(64 + mapping[key])
                    batch.append({"range": f"{col}{row_idx}", "values": [[val]]})

            for row_idx in completed_rows:
                col_j = chr(64 + mapping["status_col"])
                batch.append({"range": f"{col_j}{row_idx}", "values": [["на модерации с ОПЗ"]]})

            for i in range(0, len(batch), 50):
                await asyncio.to_thread(sheet.batch_update, batch[i:i+50])
                await asyncio.sleep(0.5)
            logger.info(f"✅ Очищено {len(remaining)} невыполненных + ОПЗ отмечено {len(completed_rows)} выполненных")
        except Exception as e:
            logger.error(f"❌ Ошибка отмены: {e}")

    await delete_session_messages(user_id, message.bot, request, message.chat.id)

    del slot_requests[user_id]

    await _safe_send(
        message.bot, user_id,
        f"✅ Отказ принят.\n\n"
        f"• Выполненные: {len(completed)} – на модерацию с ОПЗ (оплата 70%)\n"
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
    spreadsheet = await asyncio.to_thread(client.open_by_key, SHEET_ID)

    found = []
    worksheets = await asyncio.to_thread(spreadsheet.worksheets)
    for sheet in worksheets:
        sheet_name = sheet.title
        platform = platform_from_sheet_name(sheet_name)
        if not platform:
            continue
        mapping = get_column_mapping(platform)
        try:
            records = await asyncio.to_thread(sheet.get_all_values)
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
        "active_review_row": None, "extra_messages": [],
        "created_business_day": business_day_key()
    }
    await message.answer(
        f"✅ Сессия восстановлена!\n\n"
        f"📋 Платформа: {platform}\n"
        f"📊 Отзывов: {len(row_ids)}",
        reply_markup=InlineKeyboardBuilder().button(
            text="🎯 Активный слот", callback_data=f"active_slot|{user_id}"
        ).as_markup()
    )


# ============ ВВОД КОЛИЧЕСТВА (catch-all, НЕ для команд) ============
@router.message(F.text, ~F.text.startswith("/"))
async def handle_quantity_input(message: Message):
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

    taken_today = count_review_takes_last_24h(user_id, platform)
    limit = get_effective_limit(user_id, platform)
    remaining = limit - taken_today

    if remaining <= 0:
        now_msk = datetime.now(moscow_tz)
        next_reset = now_msk.replace(hour=10, minute=0, second=0, microsecond=0)
        if now_msk >= next_reset:
            next_reset += timedelta(days=1)
        await message.answer(
            f"❌ <b>Лимит исчерпан</b>\n\n"
            f"По платформе <b>{platform}</b> установлен лимит <b>{limit} отзывов</b> в день.\n"
            f"Вы уже взяли сегодня: <b>{taken_today} из {limit}</b>.\n\n"
            f"🔄 Лимит сбросится <b>{next_reset.strftime('%d.%m.%Y в %H:%M')} МСК</b>.\n"
            f"Попробуйте взять слот на другой платформе.",
            parse_mode="HTML"
        )
        del slot_requests[user_id]
        return

    if quantity > remaining:
        await message.answer(
            f"⚠️ <b>Превышение дневного лимита</b>\n\n"
            f"По платформе <b>{platform}</b> лимит: <b>{limit} в день</b>.\n"
            f"Вы уже взяли сегодня: <b>{taken_today}</b>.\n"
            f"Можно взять ещё максимум: <b>{remaining}</b>.\n\n"
            f"🔄 Лимит сбросится в <b>10:00 МСК</b>.\n"
            f"Введите число от 1 до {remaining} или /cancel.",
            parse_mode="HTML"
        )
        return

    mapping = get_safe_mapping(request, platform)
    sheet_title = request.get("sheet_title")

    client = get_client()
    if not client:
        await message.answer("❌ Ошибка доступа к таблице.")
        del slot_requests[user_id]
        return
    spreadsheet = await asyncio.to_thread(client.open_by_key, SHEET_ID)

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
        sheet = await asyncio.to_thread(spreadsheet.worksheet, sheet_title)
        records = await asyncio.to_thread(sheet.get_all_values)
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

        try:
            new_text, kb = build_slot_message(
                slot_info.get("platform", platform),
                slot_info["count"],
                slot_info.get("date") or "",
                slot_info.get("time") or ""
            )
            await message.bot.edit_message_text(
                chat_id=CHANNEL_ID, message_id=slot_msg_id,
                text=new_text, reply_markup=kb, parse_mode=ParseMode.HTML
            )
            logger.info(f"🔄 Слот {slot_info.get('platform', platform)} обновлён до {slot_info['count']} шт после взятия")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось обновить сообщение слота после взятия: {e}")

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
            await asyncio.to_thread(sheet.batch_update, batch[i:i+50])
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
    request["created_business_day"] = business_day_key()
    slot_requests[user_id] = request

    for _ in range(quantity):
        add_review_take(user_id, platform)

    controls_msg = await message.answer(
        f"🎯 Вы взяли {quantity} отзывов на платформе {platform}.\n"
        "Нажмите «Активный слот», чтобы приступить.",
        reply_markup=InlineKeyboardBuilder().button(
            text="🎯 Активный слот", callback_data=f"active_slot|{user_id}"
        ).as_markup()
    )
    request["controls_msg_id"] = controls_msg.message_id
    slot_requests[user_id] = request

    instr_id = await send_instruction(user_id, message.bot)
    if instr_id:
        request["instruction_msg_id"] = instr_id
        slot_requests[user_id] = request


# ============ ВЗЯТЬ СЛОТ ============
@router.callback_query(F.data.startswith("take_slot|"))
async def take_slot_start(callback: CallbackQuery):
    try:
        await callback.answer()
    except Exception:
        pass
    user_id = callback.from_user.id
    if not is_registered(user_id):
        await _safe_send(callback.bot, user_id, "❌ Вы не зарегистрированы.")
        return
    if is_blocked(user_id):
        await _safe_send(callback.bot, user_id, "⛔ Вы заблокированы.")
        return

    from bot.middlewares import is_subscribed
    if not await is_subscribed(user_id, callback.bot):
        await _safe_send(
            callback.bot, user_id,
            f"⚠️ Для использования бота подпишитесь на канал {REQUIRED_CHANNEL_ID}\n"
            f"После подписки нажмите /start и попробуйте снова."
        )
        return

    if user_id in slot_requests:
        await _safe_send(callback.bot, user_id, f"❌ У вас уже есть активный слот: {slot_requests[user_id]['platform']}.")
        return

    parts = callback.data.split("|")
    if len(parts) < 5:
        await _safe_send(callback.bot, user_id, "Некорректный запрос.")
        return
    _, platform_from_cb, count_str, date, time_safe = parts
    try:
        count = int(count_str)
    except:
        count = 0
    time = time_safe.replace('-', ':')
    slot_msg_id = callback.message.message_id

    logger.info(
        f"🎯 take_slot: user={user_id}, msg_id={slot_msg_id}, "
        f"platform_cb={platform_from_cb}, count={count}, date={date}, time={time}"
    )

    slot_info = active_slots.get(slot_msg_id)

    if not slot_info:
        platform_slots = [
            (m, s) for m, s in active_slots.items()
            if s.get("platform") == platform_from_cb and s.get("count", 0) > 0
        ]
        if platform_slots:
            slot_msg_id, slot_info = platform_slots[0]
        else:
            from bot.database import get_all_active_slots
            db_slots = get_all_active_slots()
            if slot_msg_id in db_slots:
                slot_info = db_slots[slot_msg_id]
                active_slots[slot_msg_id] = slot_info
            else:
                platform_db = [
                    (m, s) for m, s in db_slots.items()
                    if s.get("platform") == platform_from_cb and s.get("count", 0) > 0
                ]
                if platform_db:
                    slot_msg_id, slot_info = platform_db[0]
                    active_slots[slot_msg_id] = slot_info
                else:
                    await _safe_send(
                        callback.bot, user_id,
                        "❌ Слот не найден или уже разобран. Проверьте канал — возможно, слот "
                        "переопубликован, нажмите «Взять слот» в свежем сообщении, либо /resume."
                    )
                    return

    if slot_info.get("count", 0) == 0:
        await _safe_send(callback.bot, user_id, "❌ Этот слот уже разобран. Ожидайте следующий.")
        return

    sheet_title = slot_info.get("sheet_title")
    real_platform = platform_from_sheet_name(sheet_title) if sheet_title else None

    if real_platform is None:
        platform = platform_from_cb
    elif real_platform != platform_from_cb:
        logger.warning(
            f"⚠️ take_slot: РАССИНХРОН! callback говорит '{platform_from_cb}', "
            f"а sheet_title='{sheet_title}' соответствует '{real_platform}'."
        )
        platform = real_platform
    else:
        platform = real_platform

    if not await check_limit(user_id, platform):
        limit = get_effective_limit(user_id, platform)
        taken_today = count_review_takes_last_24h(user_id, platform)
        now_msk = datetime.now(moscow_tz)
        next_reset = now_msk.replace(hour=10, minute=0, second=0, microsecond=0)
        if now_msk >= next_reset:
            next_reset += timedelta(days=1)
        await _safe_send(
            callback.bot, user_id,
            f"❌ <b>Лимит исчерпан на сегодня</b>\n\n"
            f"Платформа: <b>{platform}</b>\n"
            f"Установлено: <b>{limit} отзывов в день</b>\n"
            f"Вы уже взяли: <b>{taken_today}</b>\n\n"
            f"🔄 Лимит сбросится <b>{next_reset.strftime('%d.%m.%Y в %H:%M')} МСК</b>.",
            parse_mode="HTML"
        )
        return

    mapping = slot_info.get("mapping") or get_column_mapping(platform)
    slot_requests[user_id] = {
        "platform": platform, "count": slot_info.get("count", count),
        "date": date, "time": time, "slot_msg_id": slot_msg_id,
        "state": "waiting_quantity", "assigned_rows": [], "current_index": 0,
        "row_ids": slot_info["row_ids"], "from_menu": False,
        "mapping": mapping,
        "sheet_title": sheet_title,
        "created_business_day": business_day_key()
    }
    await _safe_send(
        callback.bot, user_id,
        f"📊 Доступно: {slot_info.get('count', count)} шт.\n"
        f"Сколько выполните?\n\n"
        f"Если хотите отказаться пропишите команду /cancel."
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

    request = slot_requests[user_id]
    request["controls_msg_id"] = callback.message.message_id
    slot_requests[user_id] = request

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
        "яндекс": "Яндекс", "яндекс негатив": "Я.Негатив",
        "google": "Google", "2гис": "2ГИС", "авито": "Авито",
        "вк": "ВК", "отзовик": "Отзовик", "доктору": "Doctoru", "докдок": "ДокДок",
        "про докторов": "Про Докторов", "докту": "ДокТу", "32топ": "32ТОП",
        "zoon": "ZOON", "яу": "ЯУ", "яб": "ЯБ", "h": "HH", "yell": "Yell"
    }
    name = names.get(platform, platform.capitalize())
    builder = InlineKeyboardBuilder()
    for row_idx, num in ordered:
        if num not in completed:
            builder.button(text=f"{name} {num}", callback_data=f"select_review|{num}")
    builder.adjust(3)
    await message.edit_text("📋 Выберите номер отзыва:", reply_markup=builder.as_markup())


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

    request["controls_msg_id"] = callback.message.message_id
    slot_requests[user_id] = request

    platform = request.get("platform", "яндекс")
    sheet_title = request.get("sheet_title")

    if not sheet_title:
        logger.error(f"❌ select_review: sheet_title пуст у user {user_id} — просим /resume")
        await callback.answer(
            "❌ Потеряна сессия. Введите /resume для восстановления.",
            show_alert=True
        )
        return

    real_platform = platform_from_sheet_name(sheet_title)
    if real_platform and real_platform != platform:
        logger.warning(
            f"⚠️ select_review: рассинхрон! request.platform='{platform}', "
            f"sheet_title='{sheet_title}' => '{real_platform}'."
        )
        platform = real_platform
        request["platform"] = platform
        request["mapping"] = get_column_mapping(platform)
        slot_requests[user_id] = request

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

    if target_row not in request.get("assigned_rows", []):
        logger.error(
            f"❌ select_review: row {target_row} НЕ в assigned_rows "
            f"({request.get('assigned_rows')}) для user {user_id}"
        )
        await callback.answer(
            "❌ Эта строка вам не принадлежит. Введите /resume.",
            show_alert=True
        )
        return

    request["active_review_row"] = target_row
    request["state"] = "working_on_review"
    slot_requests[user_id] = request

    client = get_client()
    if not client:
        await callback.answer("❌ Ошибка доступа.", show_alert=True)
        return
    spreadsheet = await asyncio.to_thread(client.open_by_key, SHEET_ID)

    try:
        sheet = await asyncio.to_thread(spreadsheet.worksheet, sheet_title)
    except Exception as e:
        logger.error(f"❌ select_review: не открыть лист '{sheet_title}': {e}")
        await callback.answer(
            "❌ Ошибка доступа к листу. Введите /resume.",
            show_alert=True
        )
        return

    await show_review_info(callback.message, user_id, target_row, sheet, mapping, platform)
    await callback.answer()


async def show_review_info(message: Message, user_id: int, row_idx: int, sheet, mapping, platform):
    request = slot_requests[user_id]

    if not mapping or "status_col" not in mapping:
        mapping = get_column_mapping(platform)
        request["mapping"] = mapping
        slot_requests[user_id] = request

    row = await asyncio.to_thread(sheet.row_values, row_idx)
    if len(row) < 30:
        row = row + [""] * (30 - len(row))

    extra_ids = []
    logger.info(f"📄 Показ отзыва строка {row_idx}, платформа {platform}, mapping.text_col={mapping.get('text_col')}")

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
            f"{SNIPPET_REQ}\n\n"
            f"👨‍⚕️ <b>Информация по врачу:</b>\n"
            f"Имя врача: {doctor_name}\n"
            f"Направление: {doctor_direction}\n\n"
            f"<b>Информация по отзыву:</b>\n"
            f"Пол: {gender_text}\n"
            f"Кол-во звезд: {stars}\n"
            f"Платформа: {platform_name}\n"
            f"Ссылка на платформу: {link}\n\n"
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

        photo_link = ""
        photo_col = mapping.get("photo_col")
        if photo_col and len(row) >= photo_col:
            photo_link = row[photo_col-1]

        template = PLATFORM_TEMPLATES.get(platform, PLATFORM_TEMPLATES["яндекс"])
        instruction_text = template["instruction"]
        extra_text = template["extra_text"]
        warning = template["warning"]

        gender_clean = (gender or "").strip().upper()

        gender_text = ""
        gender_kind = None
        if gender_clean in ("М", "M"):
            gender_kind = "м"
            gender_text = "👨 Отзыв мужской. Его должен выполнить мужчина с мужским именем на картах."
        elif gender_clean in ("Ж", "J"):
            gender_kind = "ж"
            gender_text = "👩 Отзыв женский. Её должна выполнить женщина с женским именем на картах."
        else:
            gender_text = "👤 Отзыв без пола. Может выполнить и мужчина, и женщина."

        final_msg = (
            f"{extra_text}\n\n"
            f"{instruction_text}\n\n"
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

        if gender_kind == "ж":
            sent = await message.answer(
                "⚠️ <b>ВАЖНО ПРО ПОЛ!</b>\n\n"
                "Этот текст должна выполнить <b>ДЕВУШКА</b> от <b>женского имени</b>.\n\n"
                "Если отзыв напишет парень или с мужского имени — "
                "отзыв <b>НЕ БУДЕТ ОПЛАЧЕН</b>.\n\n"
                "Пожалуйста, будьте внимательны!",
                parse_mode="HTML"
            )
            extra_ids.append(sent.message_id)
        elif gender_kind == "м":
            sent = await message.answer(
                "⚠️ <b>ВАЖНО ПРО ПОЛ!</b>\n\n"
                "Этот текст должен выполнить <b>МУЖЧИНА</b> от <b>мужского имени</b>.\n\n"
                "Если отзыв напишет девушка или с женского имени — "
                "отзыв <b>НЕ БУДЕТ ОПЛАЧЕН</b>.\n\n"
                "Пожалуйста, будьте внимательны!",
                parse_mode="HTML"
            )
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

    logger.info(
        f"📸 PHOTO: user={user_id} (@{message.from_user.username}) "
        f"в slot_requests={user_id in slot_requests}, "
        f"state={(slot_requests.get(user_id) or {}).get('state')}"
    )

    if user_id not in slot_requests:
        await message.answer(
            "⚠️ Не нашёл вашу активную сессию со слотами.\n\n"
            "Возможные причины:\n"
            "• Бот перезапускался, и сессия потерялась\n"
            "• Вы уже сдали все отзывы\n"
            "• Вы отменили задание через /cancel\n\n"
            "Попробуйте /resume — бот восстановит ваш слот по таблице.\n"
            "Если не сработает — обратитесь в /support."
        )
        return

    request = slot_requests[user_id]
    if request.get("state") != "working_on_review":
        await message.answer(
            "❌ Сначала выберите отзыв, к которому относится скриншот:\n"
            "1. Нажмите «🎯 Активный слот».\n"
            "2. Тапните на номер отзыва.\n"
            "3. Отправьте скриншот ещё раз."
        )
        return

    active_row = request.get("active_review_row")
    if active_row is None:
        await message.answer("❌ Активный отзыв не найден. Выберите заново через «🎯 Активный слот».")
        return

    if active_row not in request.get("assigned_rows", []):
        logger.error(
            f"❌ handle_screenshot: row {active_row} НЕ в assigned_rows "
            f"({request.get('assigned_rows')}) для user {user_id}"
        )
        await message.answer(
            "❌ Ошибка сессии: строка не принадлежит вам. Введите /resume."
        )
        return

    sheet_title = request.get("sheet_title")
    if not sheet_title:
        logger.error(f"❌ handle_screenshot: sheet_title пуст у user {user_id}")
        await message.answer(
            "❌ Потеряна сессия. Введите /resume для восстановления."
        )
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

    client = get_client()
    if not client:
        await message.answer("❌ Ошибка доступа.")
        return
    spreadsheet = await asyncio.to_thread(client.open_by_key, SHEET_ID)

    try:
        sheet = await asyncio.to_thread(spreadsheet.worksheet, sheet_title)
    except Exception as e:
        logger.error(f"❌ handle_screenshot: не открыть лист '{sheet_title}': {e}")
        await message.answer("❌ Лист не найден. Введите /resume.")
        return

    review_id = await asyncio.to_thread(sheet.cell, active_row, mapping["id_col"])
    review_id = review_id.value if review_id else None
    if not review_id:
        review_id = secrets.token_hex(4)
        await asyncio.to_thread(sheet.update_cell, active_row, mapping["id_col"], review_id)

    try:
        await asyncio.to_thread(sheet.update_cell, active_row, mapping["status_col"], "на модерации")
        await asyncio.to_thread(sheet.update_cell, active_row, mapping["flag_final_col"], 333)
        await asyncio.to_thread(
            sheet.format,
            f"{chr(64+mapping['flag_final_col'])}{active_row}",
            {"backgroundColor": {"red": 0, "green": 0.8, "blue": 0}}
        )
        logger.info(f"✅ Строка {active_row} (лист '{sheet_title}') → 'на модерации', id={review_id}")
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await message.answer("❌ Ошибка сохранения.")
        return

    try:
        user = get_user(user_id)
        user_mention = f"@{user['tg_username']}" if user and user.get('tg_username') else f"@{message.from_user.username}"
        timestamp = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        caption = f"{user_mention} – {timestamp}\nID: {review_id or 'Unknown'}"
        if not SCREENSHOT_CHANNEL_ID:
            logger.warning("⚠️ SCREENSHOT_CHANNEL_ID не задан — скриншот не отправлен")
        else:
            await message.bot.send_photo(chat_id=SCREENSHOT_CHANNEL_ID, photo=message.photo[-1].file_id, caption=caption)
            logger.info(f"📤 Скриншот отправлен в {SCREENSHOT_CHANNEL_ID} от user {user_id}")
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
        instr_id = request.get("instruction_msg_id")
        if instr_id:
            try:
                await message.bot.delete_message(chat_id=chat_id, message_id=instr_id)
            except Exception:
                pass
        controls_id = request.get("controls_msg_id")
        if controls_id:
            try:
                await message.bot.delete_message(chat_id=chat_id, message_id=controls_id)
            except Exception:
                pass
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
