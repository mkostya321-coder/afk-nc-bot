import os, sqlite3, logging, asyncio, secrets
from datetime import datetime, timedelta
import pytz, gspread
from oauth2client.service_account import ServiceAccountCredentials
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode
from bot.config import SHEET_ID, DB_PATH, get_credentials_path, CHANNEL_ID, OTHER_JOBS_CHANNEL
from bot.database import get_user_by_username, get_user
from bot.state import active_slots, slot_requests

logger = logging.getLogger(__name__)
moscow_tz = pytz.timezone("Europe/Moscow")

PRICES = {
    "яндекс": 150,
    "google": 50,
    "2гис": 50,
    "авито": 700,
    "вк": 50,
    "отзовик": 100,
    "доктору": 100,
    "докдок": 100,
    "про докторов": 200,
    "докту": 110,
    "32топ": 100,
}

PLATFORM_ALIASES = {
    "яндекс": ["яндекс", "ян", "yandex"],
    "google": ["google", "гугл"],
    "2гис": ["2гис", "гис", "2 гис"],
    "авито": ["авито", "avito"],
    "вк": ["вк", "vk"],
    "отзовик": ["отзовик", "otzovik"],
    "доктору": ["доктору", "docto", "doctoru", "докто ру"],
    "докдок": ["докдок", "doc doc", "doc"],
    "про докторов": ["про докторов", "продокторов", "pro doctors"],
    "докту": ["докту", "doctu"],
    "32топ": ["32топ", "32top", "32 топ"],
}

SHEET_NAME_TO_PLATFORM = {
    "ЯНДЕКС (К)": "яндекс",
    "2ГИС (Г)": "2гис",
    "google (С)": "google",
    "АВИТО (А)": "авито",
    "Продокторов (ПР)": "про докторов",
    "ВК (ВК)": "вк",
    "ДокДок (ДД)": "докдок",
    "32Топ (Т)": "32топ",
    "Докту (ДК)": "докту",
    "ЯНДЕКС": "яндекс", "Яндекс": "яндекс", "yandex": "яндекс",
    "2ГИС": "2гис", "2гис": "2гис",
    "google": "google", "Google": "google", "GOOGLE": "google",
    "АВИТО": "авито", "Авито": "авито", "avito": "авито",
    "Продокторов": "про докторов", "про докторов": "про докторов", "prodoctors": "про докторов",
    "ВК": "вк", "вк": "вк", "vk": "вк",
    "ДокДок": "докдок", "докдок": "докдок",
    "32Топ": "32топ", "32топ": "32топ", "32top": "32топ",
    "Докту": "докту", "докту": "докту", "doctu": "докту",
}

def get_column_mapping(platform: str):
    standard = {
        "date_col": 1,
        "time_col": 2,
        "stars_col": 3,
        "platform_col": 4,
        "link_col": 7,
        "status_col": 10,
        "executor_col": 11,
        "gender_col": 13,
        "text_col": 14,
        "flag_first_col": 17,
        "flag_second_col": 16,
        "flag_third_col": 15,
        "flag_final_col": 9,
        "id_col": 19,
        "update_col": 5,
        "order_col": 20,
    }
    if platform == "про докторов":
        return {
            "date_col": 1,
            "time_col": 2,
            "stars_col": 3,
            "platform_col": 4,
            "link_col": 11,
            "status_col": 14,
            "executor_col": 15,
            "gender_col": 16,
            "text_col": None,
            "flag_first_col": 22,
            "flag_second_col": 21,
            "flag_third_col": 20,
            "flag_final_col": 13,
            "id_col": 23,
            "update_col": 5,
            "order_col": 24,
            "text_history_col": 17,
            "text_like_col": 18,
            "text_minus_col": 19,
            "tz_col": 10,
            "doctor_name_col": 12,
            "doctor_direction_col": 9,
            "photo_doc_col": 8,
        }
    return standard

def match_platform(raw_name: str) -> str | None:
    name = raw_name.strip().lower()
    for std, aliases in PLATFORM_ALIASES.items():
        for a in aliases:
            if a in name:
                return std
    return None

def platform_from_sheet_name(sheet_name: str) -> str | None:
    key = sheet_name.strip()
    if key in SHEET_NAME_TO_PLATFORM:
        return SHEET_NAME_TO_PLATFORM[key]
    key_lower = key.lower()
    if key_lower in SHEET_NAME_TO_PLATFORM:
        return SHEET_NAME_TO_PLATFORM[key_lower]
    first_word = key.split()[0] if key.split() else key
    if first_word in SHEET_NAME_TO_PLATFORM:
        return SHEET_NAME_TO_PLATFORM[first_word]
    first_word_lower = first_word.lower()
    if first_word_lower in SHEET_NAME_TO_PLATFORM:
        return SHEET_NAME_TO_PLATFORM[first_word_lower]
    return None

def get_credentials():
    path = get_credentials_path()
    if not os.path.exists(path):
        logger.error(f"Файл ключа не найден: {path}")
        return None
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    return ServiceAccountCredentials.from_json_keyfile_name(path, scope)

async def publish_scheduled_slot(bot, platform: str, count: int,
                                 date: str, time: str, row_ids: list, attempt: int = 1,
                                 mapping=None, sheet_title=None):
    if mapping is None:
        mapping = get_column_mapping(platform)
    platform_names = {
        "яндекс": "Яндекс", "google": "Google", "2гис": "2ГИС",
        "авито": "Авито", "вк": "ВК", "отзовик": "Otzovik", "доктору": "Doctoru",
        "докдок": "ДокДок", "про докторов": "Про Докторов", "докту": "ДокТу", "32топ": "32ТОП"
    }
    pretty_name = platform_names.get(platform, platform)
    post_text = (
        f"🔥 Слот: {pretty_name}\n"
        f"📅 Дата: {date}\n"
        f"⏰ Время: {time} (МСК)\n"
        f"📌 Доступно отзывов: {count} шт.\n"
        f"⏳ Дедлайн: Сегодня до 23:59 (МСК)\n\n"
        f"Чтобы забрать слот, нажмите кнопку «Взять слот», затем перейдите в бота по кнопке «Перейти к задаче»."
    )
    time_safe = time.replace(':', '-')
    callback_data = f"take_slot|{platform}|{count}|{date}|{time_safe}"
    url_to_bot = "https://t.me/ncjobbot?start"
    builder = InlineKeyboardBuilder()
    builder.button(text="✋ Взять слот", callback_data=callback_data)
    builder.button(text="🚀 Перейти к задаче", url=url_to_bot)
    builder.button(text="📋 Другие задания", url=OTHER_JOBS_CHANNEL)
    builder.adjust(1)
    try:
        sent_msg = await bot.send_message(
            chat_id=CHANNEL_ID, text=post_text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML
        )
        logger.info(f"✅ Слот {platform} опубликован, ID сообщения: {sent_msg.message_id}")
        active_slots[sent_msg.message_id] = {
            "platform": platform,
            "count": count,
            "initial_count": count,
            "row_ids": row_ids,
            "date": date,
            "time": time,
            "publish_time": datetime.now(moscow_tz),
            "attempt": attempt,
            "mapping": mapping,
            "sheet_title": sheet_title
        }
        return sent_msg
    except Exception as e:
        logger.error(f"❌ Ошибка при отправке сообщения слота: {e}")
        return None

async def monitor_schedule(bot):
    logger.info("📅 Планировщик слотов запущен")
    while True:
        try:
            creds = get_credentials()
            if not creds:
                logger.error("❌ Не удалось получить credentials для Google Sheets")
                await asyncio.sleep(60)
                continue
            client = gspread.authorize(creds)
            spreadsheet = client.open_by_key(SHEET_ID)
            worksheets = spreadsheet.worksheets()
            now = datetime.now(moscow_tz)
            logger.info(f"🔍 Проверка таблицы в {now.strftime('%H:%M')}, листов: {len(worksheets)}")
            sheet_names = [ws.title for ws in worksheets]
            logger.info(f"📋 Названия листов: {sheet_names}")

            for sheet in worksheets:
                sheet_name = sheet.title
                platform = platform_from_sheet_name(sheet_name)
                if not platform:
                    logger.info(f"⏭️ Пропускаем лист '{sheet_name}' (неизвестная платформа)")
                    continue
                logger.info(f"📋 Обработка листа '{sheet_name}' (платформа: {platform})")
                mapping = get_column_mapping(platform)

                records = sheet.get_all_values()
                if not records or len(records) < 2:
                    logger.info(f"ℹ️ Лист '{sheet_name}' пуст или только заголовки")
                    continue

                # --- Первичная публикация ---
                to_publish = []
                for row_idx, row in enumerate(records[1:], start=2):
                    if len(row) < 8:
                        continue
                    date_str = row[mapping["date_col"]-1].strip() if len(row) >= mapping["date_col"] else ""
                    time_str = row[mapping["time_col"]-1].strip() if len(row) >= mapping["time_col"] else ""
                    if not date_str or not time_str:
                        continue
                    flag_first = row[mapping["flag_first_col"]-1].strip() if len(row) >= mapping["flag_first_col"] else ""
                    flag_second = row[mapping["flag_second_col"]-1].strip() if len(row) >= mapping["flag_second_col"] else ""
                    flag_third = row[mapping["flag_third_col"]-1].strip() if len(row) >= mapping["flag_third_col"] else ""
                    flag_final = row[mapping["flag_final_col"]-1].strip() if len(row) >= mapping["flag_final_col"] else ""
                    if flag_first in ("1", "999") or flag_second == "1" or flag_third == "1" or flag_final in ("1", "999", "333", "666", "888"):
                        continue
                    status = row[mapping["status_col"]-1].strip().lower() if len(row) >= mapping["status_col"] else ""
                    if status in ("в работе", "на модерации", "на модерации с опз"):
                        continue
                    try:
                        slot_time = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%Y %H:%M")
                        slot_time = moscow_tz.localize(slot_time)
                    except:
                        continue
                    if now >= slot_time:
                        to_publish.append((row_idx, row))

                if to_publish:
                    logger.info(f"📢 Найдено {len(to_publish)} строк для публикации на листе '{sheet_name}'")
                    from collections import defaultdict
                    groups = defaultdict(list)
                    for row_idx, row in to_publish:
                        date_str = row[mapping["date_col"]-1].strip()
                        time_str = row[mapping["time_col"]-1].strip()
                        groups[(date_str, time_str)].append((row_idx, row))

                    for (date, time), items in groups.items():
                        count_available = len(items)
                        row_ids = [item[0] for item in items]
                        logger.info(f"🚀 Публикуем слот {platform} на {date} {time}, {count_available} шт.")
                        sent_msg = await publish_scheduled_slot(
                            bot, platform, count_available,
                            date, time, row_ids, attempt=1, mapping=mapping, sheet_title=sheet_name
                        )
                        if sent_msg:
                            for row_idx in row_ids:
                                try:
                                    review_id = secrets.token_hex(4)
                                    sheet.update_cell(row_idx, mapping["flag_first_col"], 1)
                                    sheet.update_cell(row_idx, mapping["id_col"], review_id)
                                    logger.info(f"✅ Флаги Q=1 и ID={review_id} установлены для строки {row_idx}")
                                except Exception as e:
                                    logger.error(f"Не удалось обновить флаг/ID для строки {row_idx}: {e}")
                        else:
                            logger.error(f"❌ Не удалось опубликовать слот {platform} – сообщение не отправлено")
                else:
                    logger.info(f"ℹ️ Нет строк для публикации на листе '{sheet_name}'")

                # --- Перепубликация ---
                expired_slots = []
                for msg_id, slot in list(active_slots.items()):
                    if slot.get("attempt", 1) >= 4:
                        continue
                    publish_time = slot.get("publish_time")
                    if publish_time and (now - publish_time).total_seconds() >= 7200:
                        available_rows = []
                        slot_mapping = slot.get("mapping", mapping)
                        for row_idx in slot["row_ids"]:
                            try:
                                status_val = sheet.cell(row_idx, slot_mapping["status_col"]).value or ""
                                if status_val.lower() not in ("в работе", "на модерации", "на модерации с опз"):
                                    available_rows.append(row_idx)
                            except:
                                continue
                        if available_rows:
                            expired_slots.append((msg_id, slot, available_rows, slot_mapping))

                for msg_id, slot, available_rows, slot_mapping in expired_slots:
                    new_attempt = slot["attempt"] + 1
                    logger.info(f"🔄 Перепубликация слота {slot['platform']} (попытка {new_attempt})")
                    try:
                        await bot.edit_message_text(
                            chat_id=CHANNEL_ID, message_id=msg_id,
                            text="Срок размещения истёк. Неразобранные отзывы будут переопубликованы."
                        )
                    except:
                        pass
                    del active_slots[msg_id]

                    if new_attempt == 2:
                        col = slot_mapping["flag_second_col"]
                        flag_name = "P" if platform != "про докторов" else "U"
                    elif new_attempt == 3:
                        col = slot_mapping["flag_third_col"]
                        flag_name = "O" if platform != "про докторов" else "T"
                    elif new_attempt == 4:
                        col = slot_mapping["flag_final_col"]
                        flag_name = "I" if platform != "про докторов" else "M"
                    else:
                        col = None
                        flag_name = "?"

                    if col:
                        logger.info(f"📌 Обновляем столбец {flag_name} (col={col}) для {len(available_rows)} строк")
                        for row_idx in available_rows:
                            try:
                                sheet.update_cell(row_idx, col, 1)
                                logger.info(f"✅ Обновлён столбец {flag_name} (col={col}) для строки {row_idx}")
                            except Exception as e:
                                logger.error(f"Не удалось обновить столбец {col} для строки {row_idx}: {e}")
                    else:
                        logger.warning(f"⚠️ Неизвестный номер попытки {new_attempt}, столбец не определён")

                    sent_msg = await publish_scheduled_slot(
                        bot, slot["platform"], len(available_rows),
                        slot["date"], slot["time"], available_rows,
                        attempt=new_attempt, mapping=slot_mapping, sheet_title=slot.get("sheet_title")
                    )
                    if sent_msg:
                        logger.info(f"✅ Слот {slot['platform']} переопубликован (попытка {new_attempt})")
                    else:
                        logger.error(f"❌ Не удалось переопубликовать слот {slot['platform']}")

                # --- Закрытие в 23:30 ---
                if now.hour == 23 and now.minute >= 30:
                    logger.info("🕒 Начинаем закрытие слотов в 23:30")
                    from bot.state import slot_requests

                    if slot_requests:
                        logger.info(f"👥 Найдено {len(slot_requests)} активных сессий пользователей")
                        for user_id, request in list(slot_requests.items()):
                            assigned_rows = request.get("assigned_rows", [])
                            if not assigned_rows:
                                continue
                            mapping = request.get("mapping", get_column_mapping("яндекс"))
                            sheet_title = request.get("sheet_title")
                            platform = request.get("platform", "неизвестно")

                            logger.info(f"👤 Обработка сессии пользователя {user_id}, платформа {platform}, строк: {assigned_rows}")

                            for row_idx in assigned_rows:
                                found = False
                                if sheet_title:
                                    try:
                                        sheet = spreadsheet.worksheet(sheet_title)
                                        found = True
                                    except Exception as e:
                                        logger.error(f"Не удалось найти лист {sheet_title}: {e}")
                                if not found:
                                    for s in spreadsheet.worksheets():
                                        try:
                                            s.cell(row_idx, 1)
                                            sheet = s
                                            found = True
                                            break
                                        except:
                                            continue
                                if not found:
                                    logger.error(f"❌ Не найден лист для строки {row_idx}")
                                    continue

                                try:
                                    j_val = sheet.cell(row_idx, mapping["status_col"]).value or ""
                                    logger.info(f"🔍 Строка {row_idx}, статус J = '{j_val}'")

                                    if j_val.lower() == "на модерации":
                                        sheet.update_cell(row_idx, mapping["status_col"], "на модерации с ОПЗ")
                                        logger.info(f"✅ Строка {row_idx} переведена в 'на модерации с ОПЗ'")
                                    elif j_val.lower() == "в работе":
                                        sheet.update_cell(row_idx, mapping["status_col"], "не принят в работу")
                                        sheet.update_cell(row_idx, mapping["executor_col"], "")
                                        sheet.update_cell(row_idx, mapping["flag_final_col"], 888)
                                        sheet.format(f"{chr(64+mapping['flag_final_col'])}{row_idx}", {
                                            "backgroundColor": {"red": 0, "green": 0, "blue": 0.8}
                                        })
                                        logger.info(f"✅ Строка {row_idx} снята (не принят в работу), I=888")
                                except Exception as e:
                                    logger.error(f"❌ Ошибка обновления строки {row_idx}: {e}")

                            try:
                                await bot.send_message(
                                    user_id,
                                    "⚠️ Вы не успели выполнить все отзывы до 23:59 МСК.\n"
                                    "Невыполненные отзывы сняты с вас.\n"
                                    "Оплата за выполненные отзывы в этом слоте будет снижена на 30%."
                                )
                                logger.info(f"📩 Уведомление отправлено пользователю {user_id}")
                            except Exception as e:
                                logger.error(f"Не удалось отправить уведомление пользователю {user_id}: {e}")

                            del slot_requests[user_id]

                    for msg_id in list(active_slots.keys()):
                        try:
                            await bot.edit_message_text(
                                chat_id=CHANNEL_ID, message_id=msg_id,
                                text="Рабочий день завершён. Все слоты закрыты."
                            )
                        except Exception as e:
                            logger.error(f"Не удалось отредактировать сообщение слота {msg_id}: {e}")
                        del active_slots[msg_id]
                    logger.info("✅ Все слоты закрыты в 23:30")

        except Exception as e:
            logger.error(f"❌ Ошибка в планировщике слотов: {e}", exc_info=True)
        await asyncio.sleep(60)

async def update_stats_from_sheet():
    """Обновление статистики по расписанию: каждый день в 10:00 и 20:00, кроме среды. В четверг только в 20:00."""
    while True:
        now = datetime.now(moscow_tz)
        weekday = now.weekday()  # 0=понедельник, 2=среда, 3=четверг
        target_times = []

        # Среда - НЕТ обновлений
        if weekday == 2:  # среда
            logger.info("📅 Сегодня среда, обновление статистики отключено")
            next_day = now.replace(hour=10, minute=0, second=0, microsecond=0) + timedelta(days=1)
            wait_seconds = (next_day - now).total_seconds()
            logger.info(f"⏳ Следующее обновление статистики в {next_day.strftime('%d.%m.%Y %H:%M')}, ждём {wait_seconds/3600:.1f} ч.")
            await asyncio.sleep(wait_seconds)
            continue

        # Четверг - только в 20:00
        if weekday == 3:  # четверг
            thursday_2000 = now.replace(hour=20, minute=0, second=0, microsecond=0)
            if now < thursday_2000:
                target_times = [thursday_2000]
            else:
                # Если уже после 20:00 в четверг, ждём до пятницы 10:00
                friday_1000 = now.replace(hour=10, minute=0, second=0, microsecond=0) + timedelta(days=1)
                target_times = [friday_1000]
        else:
            # Остальные дни (пн, вт, пт, сб, вс) - 10:00 и 20:00
            morning = now.replace(hour=10, minute=0, second=0, microsecond=0)
            evening = now.replace(hour=20, minute=0, second=0, microsecond=0)
            target_times = [morning, evening]

        future_times = [t for t in target_times if t > now]
        if not future_times:
            tomorrow = now.replace(hour=10, minute=0, second=0, microsecond=0) + timedelta(days=1)
            future_times = [tomorrow]

        next_target = min(future_times)
        wait_seconds = (next_target - now).total_seconds()
        logger.info(f"⏳ Следующее обновление статистики в {next_target.strftime('%d.%m.%Y %H:%M')}, ждём {wait_seconds/60:.1f} мин.")
        await asyncio.sleep(wait_seconds)
        await update_stats_from_sheet_once()

async def update_stats_from_sheet_once():
    try:
        logger.info("🔄 Запуск обновления статистики")
        creds = get_credentials()
        if not creds:
            logger.error("❌ Нет credentials для обновления статистики")
            return
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key(SHEET_ID)

        updates = []

        for sheet in spreadsheet.worksheets():
            records = sheet.get_all_values()
            if len(records) < 2:
                continue
            sheet_name = sheet.title
            platform = platform_from_sheet_name(sheet_name)
            mapping = get_column_mapping(platform) if platform else get_column_mapping("яндекс")
            logger.info(f"📊 Обработка листа '{sheet_name}' для статистики")

            for row_idx, row in enumerate(records[1:], start=2):
                if len(row) < 10:
                    continue
                platform_raw = row[mapping["platform_col"]-1].strip() if len(row) >= mapping["platform_col"] else ""
                status = row[mapping["status_col"]-1].strip().lower() if len(row) >= mapping["status_col"] else ""
                flag_stat = row[mapping["flag_final_col"]-1].strip() if len(row) >= mapping["flag_final_col"] else ""
                e_flag = row[mapping["update_col"]-1].strip() if len(row) >= mapping["update_col"] else ""
                executor = row[mapping["executor_col"]-1].strip() if len(row) >= mapping["executor_col"] else ""

                if e_flag not in ("", "0"):
                    continue
                if flag_stat in ("666", "888", "999"):
                    continue

                platform = match_platform(platform_raw)
                if not platform:
                    continue

                executor_clean = executor.lstrip("@").lower()
                user = get_user_by_username(executor_clean)
                e_value = None

                if status == "опубликован":
                    if user:
                        uid = user["user_id"]
                        price = PRICES.get(platform, 0)
                        field_map = {
                            "яндекс": "yandex",
                            "google": "google",
                            "2гис": "gis",
                            "авито": "avito",
                            "вк": "vk",
                            "отзовик": "otzovik",
                            "доктору": "doctoru",
                            "докдок": "dokdok",
                            "про докторов": "prodoctors",
                            "докту": "doctu",
                            "32топ": "top32",
                        }
                        field_prefix = field_map.get(platform)
                        with sqlite3.connect(DB_PATH) as conn:
                            cur = conn.cursor()
                            if field_prefix:
                                passed_field = f"{field_prefix}_passed"
                                total_field = f"{field_prefix}_total"
                                cur.execute(f"UPDATE users SET {passed_field} = {passed_field} + 1, {total_field} = {total_field} + 1 WHERE user_id = ?", (uid,))
                            cur.execute("UPDATE users SET payout = payout + ?, total_earned = total_earned + ? WHERE user_id = ?", (price, price, uid))
                            conn.commit()
                        e_value = 1
                        logger.info(f"✅ Начислено {price}₽ пользователю {uid} за {platform}")
                    else:
                        e_value = 2

                elif status == "опубликован опз":
                    if user:
                        uid = user["user_id"]
                        price = PRICES.get(platform, 0)
                        price_opz = int(price * 0.7)
                        field_map = {
                            "яндекс": "yandex",
                            "google": "google",
                            "2гис": "gis",
                            "авито": "avito",
                            "вк": "vk",
                            "отзовик": "otzovik",
                            "доктору": "doctoru",
                            "докдок": "dokdok",
                            "про докторов": "prodoctors",
                            "докту": "doctu",
                            "32топ": "top32",
                        }
                        field_prefix = field_map.get(platform)
                        with sqlite3.connect(DB_PATH) as conn:
                            cur = conn.cursor()
                            if field_prefix:
                                passed_field = f"{field_prefix}_passed"
                                total_field = f"{field_prefix}_total"
                                cur.execute(f"UPDATE users SET {passed_field} = {passed_field} + 1, {total_field} = {total_field} + 1 WHERE user_id = ?", (uid,))
                            cur.execute("UPDATE users SET payout = payout + ?, total_earned = total_earned + ? WHERE user_id = ?", (price_opz, price_opz, uid))
                            conn.commit()
                        e_value = 1
                        logger.info(f"✅ Начислено {price_opz}₽ (ОПЗ) пользователю {uid} за {platform}")
                    else:
                        e_value = 2

                elif status == "удален":
                    if user:
                        uid = user["user_id"]
                        price = PRICES.get(platform, 0)
                        with sqlite3.connect(DB_PATH) as conn:
                            cur = conn.cursor()
                            cur.execute("UPDATE users SET payout = payout - ?, total_earned = total_earned - ? WHERE user_id = ?", (price, price, uid))
                            cur.execute("UPDATE users SET payout = MAX(payout, 0), total_earned = MAX(total_earned, 0) WHERE user_id = ?", (uid,))
                            field_map = {
                                "яндекс": "yandex",
                                "google": "google",
                                "2гис": "gis",
                                "авито": "avito",
                                "вк": "vk",
                                "отзовик": "otzovik",
                                "доктору": "doctoru",
                                "докдок": "dokdok",
                                "про докторов": "prodoctors",
                                "докту": "doctu",
                                "32топ": "top32",
                            }
                            field_prefix = field_map.get(platform)
                            if field_prefix:
                                total_field = f"{field_prefix}_total"
                                cur.execute(f"UPDATE users SET {total_field} = {total_field} - 1 WHERE user_id = ? AND {total_field} > 0", (uid,))
                            conn.commit()
                        e_value = 3
                        logger.info(f"✅ Вычтено {price}₽ у пользователя {uid} за удалённый отзыв ({platform})")
                    else:
                        e_value = 2

                elif status == "опубликован не по тх":
                    e_value = 4
                    logger.info(f"ℹ️ Строка {row_idx} на листе {sheet_name}: опубликован не по ТХ, пропускаем")

                if e_value is not None:
                    updates.append((sheet, row_idx, e_value))

            # ---- ОБНОВЛЕНИЕ E С ПРОВЕРКОЙ ----
            for sheet, row_idx, e_value in updates:
                success = False
                for attempt in range(1, 11):
                    try:
                        sheet.update_cell(row_idx, 5, e_value)
                        check = sheet.cell(row_idx, 5).value
                        if str(check).strip() == str(e_value):
                            logger.info(f"✅ Обновлён E строки {row_idx} на {e_value} (лист {sheet.title})")
                            success = True
                            break
                        else:
                            logger.warning(f"⚠️ Проверка E строки {row_idx}: ожидалось {e_value}, получено {check}, повторная попытка {attempt}/10")
                            await asyncio.sleep(2 ** attempt)
                    except Exception as e:
                        error_msg = str(e)
                        if '429' in error_msg:
                            wait = 2 ** attempt
                            logger.warning(f"⚠️ Ошибка 429 для строки {row_idx}, попытка {attempt}/10, ждём {wait} сек...")
                            await asyncio.sleep(wait)
                        else:
                            logger.error(f"❌ Не удалось обновить E для строки {row_idx} (попытка {attempt}/10): {e}")
                            break
                if not success:
                    logger.error(f"❌ Не удалось обновить E для строки {row_idx} после 10 попыток")

        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT user_id, yandex_passed, google_passed, gis_passed, avito_passed, vk_passed,
                       otzovik_passed, doctoru_passed, dokdok_passed, prodoctors_passed,
                       doctu_passed, top32_passed
                FROM users
            """)
            for user_row in cur.fetchall():
                uid = user_row[0]
                period_total = (
                    user_row[1] * PRICES.get("яндекс", 0) +
                    user_row[2] * PRICES.get("google", 0) +
                    user_row[3] * PRICES.get("2гис", 0) +
                    user_row[4] * PRICES.get("авито", 0) +
                    user_row[5] * PRICES.get("вк", 0) +
                    user_row[6] * PRICES.get("отзовик", 0) +
                    user_row[7] * PRICES.get("доктору", 0) +
                    user_row[8] * PRICES.get("докдок", 0) +
                    user_row[9] * PRICES.get("про докторов", 0) +
                    user_row[10] * PRICES.get("докту", 0) +
                    user_row[11] * PRICES.get("32топ", 0)
                )
                cur.execute("UPDATE users SET payout = ? WHERE user_id = ?", (period_total, uid))
            conn.commit()

        logger.info(f"✅ Статистика обновлена, обработано строк: {len(updates)}")

    except Exception as e:
        logger.error(f"❌ Ошибка обновления статистики: {e}", exc_info=True)

# ---------- НОВАЯ ФУНКЦИЯ
