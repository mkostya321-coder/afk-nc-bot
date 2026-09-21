import os, sqlite3, logging, asyncio, secrets
from datetime import datetime, timedelta, date, timezone
from collections import defaultdict
import pytz, gspread
from oauth2client.service_account import ServiceAccountCredentials
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode
from bot.config import SHEET_ID, DB_PATH, get_credentials_path, CHANNEL_ID, OTHER_JOBS_CHANNEL
from bot.database import (
    get_user_by_username, get_user,
    save_channel_message, delete_channel_message,
    get_setting, set_setting,
)
from bot.state import active_slots, slot_requests
from bot.helpers import (
    platform_from_sheet_name, get_column_mapping, match_platform,
    PRICES, PLATFORM_ALIASES, SHEET_NAME_TO_PLATFORM,
    business_day_key,
)

logger = logging.getLogger(__name__)
moscow_tz = pytz.timezone("Europe/Moscow")

BLOCKED_STATUSES = (
    "в работе",
    "на модерации",
    "на модерации с опз",
    "опубликован",
    "опубликовано",
    "опубликован опз",
    "оплачено",
    "в отчете испол",
    "удален",
)

BLUE_BG = {"red": 0, "green": 0, "blue": 0.8}


def get_credentials():
    path = get_credentials_path()
    if not os.path.exists(path):
        logger.error(f"Файл ключа не найден: {path}")
        return None
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    return ServiceAccountCredentials.from_json_keyfile_name(path, scope)


def get_client():
    creds = get_credentials()
    if not creds:
        return None
    return gspread.authorize(creds)


async def retry_api_call(func, *args, max_attempts=8, **kwargs):
    for attempt in range(1, max_attempts + 1):
        try:
            return func(*args, **kwargs)
        except gspread.exceptions.APIError as e:
            error_msg = str(e)
            if '429' in error_msg or 'RESOURCE_EXHAUSTED' in error_msg or 'quota' in error_msg.lower():
                wait = min(2 ** attempt, 60)
                logger.warning(f"⚠️ 429 (попытка {attempt}/{max_attempts}), ждём {wait} сек")
                await asyncio.sleep(wait)
                continue
            raise
        except Exception as e:
            logger.error(f"❌ Ошибка API: {e}")
            raise
    raise Exception(f"Не удалось выполнить после {max_attempts} попыток")


async def _batch_format_cells(spreadsheet, sheet_id: int, cells: list, bg_color: dict):
    """
    Красит N ячеек ОДНИМ запросом через Spreadsheet.batch_update.
    cells: список (row_idx, col_idx) 1-based.
    """
    if not cells:
        return
    requests = []
    for row_idx, col_idx in cells:
        requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": row_idx - 1,
                    "endRowIndex": row_idx,
                    "startColumnIndex": col_idx - 1,
                    "endColumnIndex": col_idx,
                },
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": bg_color
                    }
                },
                "fields": "userEnteredFormat.backgroundColor"
            }
        })
    # Google принимает до ~100 requests за раз
    for i in range(0, len(requests), 100):
        chunk = requests[i:i+100]
        await retry_api_call(spreadsheet.batch_update, {"requests": chunk})
        await asyncio.sleep(1.0)


def build_slot_message(platform: str, count: int, date: str, time: str):
    platform_names = {
        "яндекс": "Яндекс", "google": "Google", "2гис": "2ГИС",
        "авито": "Авито", "вк": "ВК", "отзовик": "Otzovik", "доктору": "Doctoru",
        "докдок": "ДокДок", "про докторов": "Про Докторов", "докту": "ДокТу",
        "32топ": "32ТОП", "zoon": "ZOON",
        "яу": "Яндекс Услуги", "яб": "Яндекс Браузер", "h": "HH.RU"
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
    builder = InlineKeyboardBuilder()
    builder.button(text="✋ Взять слот", callback_data=callback_data)
    builder.button(text="🚀 Перейти к задаче", url="https://t.me/ncjobbot?start")
    builder.button(text="📋 Другие задания", url=OTHER_JOBS_CHANNEL)
    builder.adjust(1)
    return post_text, builder.as_markup()


async def monitor_schedule(bot):
    logger.info("📅 Планировщик слотов запущен")
    while True:
        try:
            client = get_client()
            if not client:
                logger.error("❌ Нет credentials")
                await asyncio.sleep(60)
                continue

            spreadsheet = client.open_by_key(SHEET_ID)
            worksheets = spreadsheet.worksheets()
            now = datetime.now(moscow_tz)
            today = now.date()
            logger.info(f"🔍 Проверка в {now.strftime('%H:%M')} МСК, листов: {len(worksheets)}")

            after_close = (now.hour == 23 and now.minute >= 30) or (now.hour < 4) or (now.hour == 4 and now.minute < 30)

            for sheet in worksheets:
                sheet_name = sheet.title
                platform = platform_from_sheet_name(sheet_name)
                if not platform:
                    logger.info(f"⏭️ Лист '{sheet_name}' — платформа не определена")
                    continue

                mapping = get_column_mapping(platform)

                try:
                    records = await retry_api_call(sheet.get_all_values)
                except Exception as e:
                    logger.error(f"❌ Чтение '{sheet_name}': {e}")
                    continue

                if not records or len(records) < 2:
                    logger.info(f"ℹ️ '{sheet_name}' ({platform}): пусто / только заголовок")
                    await asyncio.sleep(0.3)
                    continue

                to_publish = []
                stats = {
                    "total": 0, "no_date_time": 0, "already_flagged": 0,
                    "blocked_status": 0, "has_executor": 0, "future_time": 0,
                    "bad_date_format": 0, "too_short": 0,
                }

                if not after_close:
                    for row_idx, row in enumerate(records[1:], start=2):
                        stats["total"] += 1
                        if not any((c or "").strip() for c in row):
                            continue
                        if len(row) < 8:
                            stats["too_short"] += 1
                            continue

                        date_str = row[mapping["date_col"]-1].strip() if len(row) >= mapping["date_col"] else ""
                        time_str = row[mapping["time_col"]-1].strip() if len(row) >= mapping["time_col"] else ""
                        if not date_str or not time_str:
                            stats["no_date_time"] += 1
                            continue

                        flag_first = row[mapping["flag_first_col"]-1].strip() if len(row) >= mapping["flag_first_col"] else ""
                        flag_second = row[mapping["flag_second_col"]-1].strip() if len(row) >= mapping["flag_second_col"] else ""
                        flag_third = row[mapping["flag_third_col"]-1].strip() if len(row) >= mapping["flag_third_col"] else ""
                        flag_final = row[mapping["flag_final_col"]-1].strip() if len(row) >= mapping["flag_final_col"] else ""

                        if (flag_first in ("1", "999") or flag_second == "1" or flag_third == "1"
                                or flag_final in ("1", "999", "333", "666", "888", "7")):
                            stats["already_flagged"] += 1
                            continue

                        status = row[mapping["status_col"]-1].strip().lower() if len(row) >= mapping["status_col"] else ""
                        executor = row[mapping["executor_col"]-1].strip() if len(row) >= mapping["executor_col"] else ""

                        if status in BLOCKED_STATUSES:
                            stats["blocked_status"] += 1
                            continue
                        if executor:
                            stats["has_executor"] += 1
                            continue

                        try:
                            slot_time = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%Y %H:%M")
                            slot_time = moscow_tz.localize(slot_time)
                        except Exception:
                            stats["bad_date_format"] += 1
                            _d = (date_str or "").lower()
                            _t = (time_str or "").lower()
                            if "дата" in _d or "впл" in _d or "время" in _t or "пбл" in _t:
                                continue
                            logger.warning(f"  [{sheet_name}] строка {row_idx}: не парсится '{date_str} {time_str}'")
                            continue

                        if now >= slot_time:
                            to_publish.append((row_idx, row))
                        else:
                            stats["future_time"] += 1

                    if not to_publish:
                        logger.info(
                            f"ℹ️ '{sheet_name}' (platform={platform}): строк {stats['total']}, "
                            f"время ещё не пришло {stats['future_time']}, "
                            f"уже с флагом {stats['already_flagged']}, "
                            f"статус-блок {stats['blocked_status']}, "
                            f"есть исполнитель {stats['has_executor']}, "
                            f"нет даты/времени {stats['no_date_time']}, "
                            f"битый формат {stats['bad_date_format']}, "
                            f"коротких {stats['too_short']}"
                        )
                        await asyncio.sleep(0.3)
                        continue

                # ============ ПУБЛИКАЦИЯ / ДОПОЛНЕНИЕ ============
                existing_msg_id = None
                slot = None
                for mid, s in active_slots.items():
                    if s.get("platform") == platform and s.get("count", 0) > 0:
                        existing_msg_id = mid
                        slot = s
                        break

                row_ids = [r[0] for r in to_publish]
                first_row = to_publish[0][1]
                date_str = first_row[mapping["date_col"]-1].strip()
                time_str = first_row[mapping["time_col"]-1].strip()

                if existing_msg_id is not None and slot is not None:
                    new_rows = [r for r in row_ids if r not in slot["row_ids"]]

                    if not new_rows:
                        slot_alive = False
                        dead = False
                        try:
                            text_check, kb_check = build_slot_message(
                                platform, slot.get("count", 0),
                                slot.get("date") or "", slot.get("time") or ""
                            )
                            await bot.edit_message_text(
                                chat_id=CHANNEL_ID, message_id=existing_msg_id,
                                text=text_check, reply_markup=kb_check,
                                parse_mode=ParseMode.HTML
                            )
                            slot_alive = True
                        except Exception as e:
                            err = str(e).lower()
                            if "message is not modified" in err:
                                slot_alive = True
                            elif ("message to edit not found" in err
                                  or "message_id_invalid" in err
                                  or "message can't be edited" in err):
                                dead = True
                                logger.warning(
                                    f"🗑️ Слот {platform} (msg {existing_msg_id}) мёртв: {e}. "
                                    f"Удаляю запись и публикую заново."
                                )

                        if slot_alive:
                            logger.info(
                                f"ℹ️ '{sheet_name}' (platform={platform}): все {len(row_ids)} строк "
                                f"уже в активном слоте (msg {existing_msg_id})"
                            )
                            await asyncio.sleep(0.3)
                            continue

                        if dead:
                            try:
                                del active_slots[existing_msg_id]
                            except KeyError:
                                pass

                            new_text, kb = build_slot_message(
                                platform, slot.get("count", 0),
                                slot.get("date") or date_str,
                                slot.get("time") or time_str
                            )
                            try:
                                sent_msg = await bot.send_message(
                                    chat_id=CHANNEL_ID, text=new_text,
                                    reply_markup=kb, parse_mode=ParseMode.HTML
                                )
                                save_channel_message(sent_msg.message_id, CHANNEL_ID)
                                active_slots[sent_msg.message_id] = {
                                    "platform": platform, "count": slot.get("count", 0),
                                    "initial_count": slot.get("count", 0),
                                    "row_ids": list(slot.get("row_ids", [])),
                                    "date": slot.get("date") or date_str,
                                    "time": slot.get("time") or time_str,
                                    "publish_time": datetime.now(moscow_tz),
                                    "attempt": 1, "mapping": mapping, "sheet_title": sheet_name
                                }
                                logger.info(
                                    f"✅ Переопубликован {platform} "
                                    f"({slot.get('count', 0)} шт, msg {sent_msg.message_id})"
                                )
                            except Exception as e:
                                logger.error(f"❌ Не удалось переопубликовать слот {platform}: {e}")

                            await asyncio.sleep(0.5)
                            continue
                        else:
                            await asyncio.sleep(0.5)
                            continue

                    candidate_row_ids = list(slot["row_ids"]) + new_rows
                    candidate_count = len(candidate_row_ids)
                    new_text, kb = build_slot_message(platform, candidate_count, date_str, time_str)

                    edit_ok = False
                    edit_failed_dead = False
                    try:
                        await bot.edit_message_text(
                            chat_id=CHANNEL_ID, message_id=existing_msg_id,
                            text=new_text, reply_markup=kb, parse_mode=ParseMode.HTML
                        )
                        edit_ok = True
                        logger.info(f"✅ Слот {platform} дополнен до {candidate_count} шт (msg {existing_msg_id})")
                    except Exception as e:
                        err = str(e).lower()
                        if "message is not modified" in err:
                            edit_ok = True
                        elif ("message to edit not found" in err
                              or "message_id_invalid" in err
                              or "message can't be edited" in err):
                            logger.warning(
                                f"🗑️ Слот {platform} (msg {existing_msg_id}) мёртв: {e}. "
                                f"Публикую новый слот ({candidate_count} шт)."
                            )
                            edit_failed_dead = True
                        else:
                            logger.warning(
                                f"⚠️ Не удалось отредактировать слот {platform} (msg {existing_msg_id}): {e}"
                            )

                    if edit_failed_dead:
                        try:
                            del active_slots[existing_msg_id]
                        except KeyError:
                            pass

                        try:
                            sent_msg = await bot.send_message(
                                chat_id=CHANNEL_ID, text=new_text,
                                reply_markup=kb, parse_mode=ParseMode.HTML
                            )
                            save_channel_message(sent_msg.message_id, CHANNEL_ID)
                            active_slots[sent_msg.message_id] = {
                                "platform": platform, "count": candidate_count,
                                "initial_count": candidate_count, "row_ids": candidate_row_ids,
                                "date": date_str, "time": time_str,
                                "publish_time": datetime.now(moscow_tz),
                                "attempt": 1, "mapping": mapping, "sheet_title": sheet_name
                            }
                            logger.info(f"✅ Переопубликован {platform} ({candidate_count} шт, msg {sent_msg.message_id})")

                            batch = []
                            for row_idx in new_rows:
                                review_id = secrets.token_hex(4)
                                col_q = chr(64 + mapping["flag_first_col"])
                                batch.append({"range": f"{col_q}{row_idx}", "values": [[1]]})
                                col_s = chr(64 + mapping["id_col"])
                                batch.append({"range": f"{col_s}{row_idx}", "values": [[review_id]]})
                            try:
                                for i in range(0, len(batch), 50):
                                    await retry_api_call(sheet.batch_update, batch[i:i+50])
                                    await asyncio.sleep(0.5)
                            except Exception as e:
                                logger.error(f"❌ Q/S: {e}")
                        except Exception as e:
                            logger.error(f"❌ Не удалось переопубликовать слот {platform}: {e}")

                        await asyncio.sleep(0.5)
                        continue

                    if not edit_ok:
                        await asyncio.sleep(0.5)
                        continue

                    slot["row_ids"] = candidate_row_ids
                    slot["count"] = candidate_count
                    slot["date"] = date_str
                    slot["time"] = time_str
                    active_slots[existing_msg_id] = slot

                    batch = []
                    for row_idx in new_rows:
                        review_id = secrets.token_hex(4)
                        col_q = chr(64 + mapping["flag_first_col"])
                        batch.append({"range": f"{col_q}{row_idx}", "values": [[1]]})
                        col_s = chr(64 + mapping["id_col"])
                        batch.append({"range": f"{col_s}{row_idx}", "values": [[review_id]]})
                    try:
                        for i in range(0, len(batch), 50):
                            await retry_api_call(sheet.batch_update, batch[i:i+50])
                            await asyncio.sleep(0.5)
                    except Exception as e:
                        logger.error(f"❌ Q/S: {e}")
                else:
                    new_text, kb = build_slot_message(platform, len(row_ids), date_str, time_str)
                    try:
                        sent_msg = await bot.send_message(
                            chat_id=CHANNEL_ID, text=new_text,
                            reply_markup=kb, parse_mode=ParseMode.HTML
                        )
                        save_channel_message(sent_msg.message_id, CHANNEL_ID)
                        logger.info(f"✅ Новый слот {platform} ({len(row_ids)} шт, msg {sent_msg.message_id})")

                        active_slots[sent_msg.message_id] = {
                            "platform": platform, "count": len(row_ids),
                            "initial_count": len(row_ids), "row_ids": row_ids,
                            "date": date_str, "time": time_str,
                            "publish_time": datetime.now(moscow_tz),
                            "attempt": 1, "mapping": mapping, "sheet_title": sheet_name
                        }
                    except Exception as e:
                        logger.error(f"❌ Ошибка публикации: {e}")
                        await asyncio.sleep(0.3)
                        continue

                    batch = []
                    for row_idx in row_ids:
                        review_id = secrets.token_hex(4)
                        col_q = chr(64 + mapping["flag_first_col"])
                        batch.append({"range": f"{col_q}{row_idx}", "values": [[1]]})
                        col_s = chr(64 + mapping["id_col"])
                        batch.append({"range": f"{col_s}{row_idx}", "values": [[review_id]]})
                    try:
                        for i in range(0, len(batch), 50):
                            await retry_api_call(sheet.batch_update, batch[i:i+50])
                            await asyncio.sleep(0.5)
                    except Exception as e:
                        logger.error(f"❌ Q/S: {e}")

                await asyncio.sleep(0.5)

            await _check_republish(bot, client, now)

            # === Смена бизнес-дня ===
            current_bd = business_day_key(now)
            last_closed_bd = get_setting("last_closed_business_day")

            if last_closed_bd is None:
                logger.info(f"🕒 Первый запуск: current_bd={current_bd}, закрываю все старые сессии")
                ok = await _close_day(bot, client, now, current_bd)
                if ok:
                    set_setting("last_closed_business_day", current_bd)
                    logger.info(f"🕒 last_closed_business_day установлен на {current_bd}")
                else:
                    logger.warning("⚠️ Первый запуск: _close_day с ошибками — повторю на след. итерации")
            elif current_bd > last_closed_bd:
                logger.info(f"🕒 Смена бизнес-дня: {last_closed_bd} → {current_bd}, закрываю прошлые сессии")
                ok = await _close_day(bot, client, now, current_bd)
                if ok:
                    set_setting("last_closed_business_day", current_bd)
                    logger.info(f"🕒 last_closed_business_day обновлён на {current_bd}")
                else:
                    logger.warning(
                        f"⚠️ _close_day завершился с ошибками — НЕ обновляю last_closed_business_day, "
                        f"повторю на следующей итерации"
                    )

        except Exception as e:
            logger.error(f"❌ Ошибка планировщика: {e}", exc_info=True)
        await asyncio.sleep(120)


async def _check_republish(bot, client, now):
    spreadsheet = client.open_by_key(SHEET_ID)
    expired_slots = []

    logger.info(f"🔄 _check_republish: слотов в памяти {len(active_slots)}")
    for _mid, _slot in list(active_slots.items()):
        _pt = _slot.get("publish_time")
        _age = ""
        if _pt:
            try:
                _age = f"{(now - _pt).total_seconds() / 60:.0f} мин"
            except Exception:
                _age = "?"
        logger.info(
            f"  msg {_mid}: platform={_slot.get('platform')} "
            f"attempt={_slot.get('attempt')} rows={len(_slot.get('row_ids', []))} age={_age}"
        )

    for msg_id, slot in list(active_slots.items()):
        if slot.get("attempt", 1) >= 4:
            continue
        publish_time = slot.get("publish_time")
        if not publish_time:
            continue
        if (now - publish_time).total_seconds() < 7200:
            continue

        slot_mapping = slot.get("mapping")
        if not slot_mapping or "status_col" not in slot_mapping:
            platform = slot.get("platform", "яндекс")
            slot_mapping = get_column_mapping(platform)
            slot["mapping"] = slot_mapping
            active_slots[msg_id] = slot
            logger.warning(f"⚠️ mapping восстановлен для слота {msg_id}, платформа {platform}")

        sheet_title = slot.get("sheet_title")
        try:
            sheet = spreadsheet.worksheet(sheet_title)
            records = await retry_api_call(sheet.get_all_values)
        except:
            continue

        available = []
        for row_idx in slot["row_ids"]:
            if row_idx - 1 >= len(records):
                continue
            row = records[row_idx - 1]
            if not row:
                continue
            status = row[slot_mapping["status_col"]-1].strip().lower() if len(row) >= slot_mapping["status_col"] else ""
            executor = row[slot_mapping["executor_col"]-1].strip() if len(row) >= slot_mapping["executor_col"] else ""
            if status in BLOCKED_STATUSES:
                continue
            if executor:
                continue
            available.append(row_idx)

        if available:
            expired_slots.append((msg_id, slot, available, slot_mapping))

    for msg_id, slot, available_rows, slot_mapping in expired_slots:
        new_attempt = slot["attempt"] + 1
        logger.info(f"🔄 Переопубликация {slot['platform']} (попытка {new_attempt}, строк {len(available_rows)})")

        try:
            await bot.edit_message_text(
                chat_id=CHANNEL_ID, message_id=msg_id,
                text="Срок размещения истёк. Переопубликуем."
            )
        except:
            pass
        del active_slots[msg_id]

        col = None
        if new_attempt == 2:
            col = slot_mapping["flag_second_col"]
        elif new_attempt == 3:
            col = slot_mapping["flag_third_col"]
        elif new_attempt == 4:
            col = slot_mapping["flag_final_col"]

        if col:
            try:
                sheet = spreadsheet.worksheet(slot.get("sheet_title"))
                batch = []
                for row_idx in available_rows:
                    batch.append({"range": f"{chr(64+col)}{row_idx}", "values": [[1]]})
                for i in range(0, len(batch), 50):
                    await retry_api_call(sheet.batch_update, batch[i:i+50])
                    await asyncio.sleep(0.5)
            except Exception as e:
                logger.error(f"❌ Флаги: {e}")

        new_text, kb = build_slot_message(slot["platform"], len(available_rows), slot["date"], slot["time"])
        try:
            sent_msg = await bot.send_message(chat_id=CHANNEL_ID, text=new_text, reply_markup=kb, parse_mode=ParseMode.HTML)
            save_channel_message(sent_msg.message_id, CHANNEL_ID)
            active_slots[sent_msg.message_id] = {
                "platform": slot["platform"], "count": len(available_rows),
                "initial_count": len(available_rows), "row_ids": available_rows,
                "date": slot["date"], "time": slot["time"],
                "publish_time": datetime.now(moscow_tz),
                "attempt": new_attempt, "mapping": slot_mapping,
                "sheet_title": slot.get("sheet_title")
            }
            logger.info(f"✅ Переопубликован {slot['platform']} ({len(available_rows)} шт)")
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")


async def _close_day(bot, client, now, current_business_day: str) -> bool:
    logger.info(f"🕒 Закрытие дня (текущий бизнес-день {current_business_day})")

    all_requests = list(slot_requests.items())
    logger.info(f"🕒 Сессий в БД: {len(all_requests)}")

    spreadsheet = client.open_by_key(SHEET_ID)
    any_critical_error = False
    to_remove = []

    # ============ ЗАКРЫТИЕ СЕССИЙ ПОЛЬЗОВАТЕЛЕЙ ============
    for user_id, request in all_requests:
        created_bd = (request.get("created_business_day") or "").strip()
        if created_bd and created_bd >= current_business_day:
            logger.info(f"⏭️ user {user_id}: сессия создана в {created_bd} — не трогаю")
            continue

        assigned_rows = request.get("assigned_rows", [])
        sheet_title = request.get("sheet_title")
        platform_key = request.get("platform") or "яндекс"

        if not assigned_rows:
            logger.info(f"⏭️ user {user_id} ({platform_key}): нет assigned_rows — удаляю сессию")
            to_remove.append(user_id)
            continue

        if not sheet_title:
            logger.warning(f"⚠️ user {user_id} ({platform_key}): нет sheet_title")
            to_remove.append(user_id)
            continue

        mapping = request.get("mapping")
        if not mapping or "status_col" not in mapping:
            mapping = get_column_mapping(platform_key)
            request["mapping"] = mapping
            slot_requests[user_id] = request
            logger.info(f"🔧 user {user_id}: восстановлен mapping для '{platform_key}'")

        try:
            sheet = spreadsheet.worksheet(sheet_title)
            records = await retry_api_call(sheet.get_all_values)
        except Exception as e:
            logger.error(f"❌ user {user_id}: не открыть лист '{sheet_title}': {e}")
            any_critical_error = True
            continue

        batch = []
        cells_to_blue = []
        statuses_seen = {}

        for row_idx in assigned_rows:
            if row_idx - 1 >= len(records):
                continue
            row = records[row_idx - 1]
            if not row:
                continue
            j_val = row[mapping["status_col"]-1].strip().lower() if len(row) >= mapping["status_col"] else ""
            statuses_seen[j_val] = statuses_seen.get(j_val, 0) + 1

            col_j = chr(64 + mapping["status_col"])
            col_k = chr(64 + mapping["executor_col"])
            col_i_letter = chr(64 + mapping["flag_final_col"])

            if j_val == "на модерации":
                batch.append({"range": f"{col_j}{row_idx}", "values": [["на модерации с ОПЗ"]]})
            elif j_val == "в работе":
                batch.append({"range": f"{col_j}{row_idx}", "values": [["не принят в работу"]]})
                batch.append({"range": f"{col_k}{row_idx}", "values": [[""]]})
                batch.append({"range": f"{col_i_letter}{row_idx}", "values": [[888]]})
                cells_to_blue.append((row_idx, mapping["flag_final_col"]))

        logger.info(
            f"🕒 user {user_id} ({platform_key}, '{sheet_title}'): "
            f"строк {len(assigned_rows)}, статусы: {statuses_seen}, к обновлению {len(batch)}, "
            f"закрасить {len(cells_to_blue)}"
        )

        if batch:
            try:
                for i in range(0, len(batch), 50):
                    await retry_api_call(sheet.batch_update, batch[i:i+50])
                    await asyncio.sleep(0.6)
            except Exception as e:
                logger.error(f"❌ user {user_id}: ошибка batch_update: {e} — оставляю сессию для повтора")
                any_critical_error = True
                continue

        if cells_to_blue:
            try:
                sheet_id = sheet.id
                await _batch_format_cells(spreadsheet, sheet_id, cells_to_blue, BLUE_BG)
            except Exception as e:
                logger.warning(f"⚠️ user {user_id}: не удалось закрасить {len(cells_to_blue)} ячеек: {e}")
                # не критично — 888 уже проставлен

        if batch:
            logger.info(f"✅ user {user_id}: обновлено {len(batch)} ячеек, покрашено {len(cells_to_blue)}")

        try:
            await bot.send_message(user_id, "⚠️ Не выполнили задачи до 23:59. Оплата на 30% ниже.")
        except Exception as e:
            logger.warning(f"⚠️ user {user_id}: уведомление не отправилось: {e}")

        to_remove.append(user_id)

    # ============ ПОМЕТКА НЕРАЗОБРАННЫХ 888 ============
    taken_rows_by_sheet = {}
    for _uid, _req in all_requests:
        _st = _req.get("sheet_title")
        if not _st:
            continue
        taken_rows_by_sheet.setdefault(_st, set()).update(_req.get("assigned_rows", []))

    logger.info(f"🕒 Обрабатываю неразобранные строки в {len(active_slots)} слотах")
    ok_slots_to_delete = []
    for msg_id, slot in list(active_slots.items()):
        sheet_title = slot.get("sheet_title")
        if not sheet_title:
            continue
        platform_key = slot.get("platform") or "яндекс"
        mapping = slot.get("mapping")
        if not mapping or "status_col" not in mapping:
            mapping = get_column_mapping(platform_key)

        slot_rows = slot.get("row_ids", [])
        taken = taken_rows_by_sheet.get(sheet_title, set())
        not_taken = [r for r in slot_rows if r not in taken]

        if not not_taken:
            logger.info(f"⏭️ msg {msg_id} ({platform_key}): все {len(slot_rows)} строк были взяты")
            ok_slots_to_delete.append(msg_id)
            continue

        try:
            sheet = spreadsheet.worksheet(sheet_title)
            records = await retry_api_call(sheet.get_all_values)
        except Exception as e:
            logger.error(f"❌ _close_day: не открыть '{sheet_title}' для неразобранных: {e}")
            any_critical_error = True
            continue

        batch = []
        cells_to_blue = []
        skipped_by_status = 0
        already_888 = 0

        for row_idx in not_taken:
            if row_idx - 1 >= len(records):
                continue
            row = records[row_idx - 1]
            if not row:
                continue
            j_val = row[mapping["status_col"]-1].strip().lower() if len(row) >= mapping["status_col"] else ""
            if j_val in BLOCKED_STATUSES:
                skipped_by_status += 1
                continue
            i_val = row[mapping["flag_final_col"]-1].strip() if len(row) >= mapping["flag_final_col"] else ""
            col_i_letter = chr(64 + mapping["flag_final_col"])
            if i_val == "888":
                already_888 += 1
                # Всё равно красим (могло не пройти в прошлый раз)
                cells_to_blue.append((row_idx, mapping["flag_final_col"]))
                continue
            batch.append({"range": f"{col_i_letter}{row_idx}", "values": [[888]]})
            cells_to_blue.append((row_idx, mapping["flag_final_col"]))

        logger.info(
            f"🕒 msg {msg_id} ({platform_key}, '{sheet_title}'): "
            f"в слоте {len(slot_rows)}, неразобрано {len(not_taken)}, "
            f"уже 888: {already_888}, по статусу пропуск: {skipped_by_status}, "
            f"проставить 888: {len(batch)}, покрасить: {len(cells_to_blue)}"
        )

        slot_ok = True

        if batch:
            try:
                for i in range(0, len(batch), 50):
                    await retry_api_call(sheet.batch_update, batch[i:i+50])
                    await asyncio.sleep(0.6)
                logger.info(f"✅ msg {msg_id}: 888 проставлен в {len(batch)} строк")
            except Exception as e:
                logger.error(f"❌ msg {msg_id}: ошибка batch_update 888: {e} — слот оставлю для повтора")
                any_critical_error = True
                slot_ok = False

        if cells_to_blue:
            try:
                sheet_id = sheet.id
                await _batch_format_cells(spreadsheet, sheet_id, cells_to_blue, BLUE_BG)
                logger.info(f"✅ msg {msg_id}: закрашено {len(cells_to_blue)} ячеек одним запросом")
            except Exception as e:
                logger.warning(f"⚠️ msg {msg_id}: не удалось закрасить: {e}")
                # закраска не критична — 888 уже проставлен

        if slot_ok:
            ok_slots_to_delete.append(msg_id)

    # Удаляем успешно закрытые слоты
    for msg_id in ok_slots_to_delete:
        try:
            del active_slots[msg_id]
        except KeyError:
            pass

    # Удаляем успешно закрытые сессии
    for user_id in to_remove:
        try:
            del slot_requests[user_id]
            logger.info(f"🗑️ user {user_id}: сессия удалена")
        except KeyError:
            pass

    # ============ ЗАКРЫТИЕ СООБЩЕНИЙ СЛОТОВ ============
    # Закрываем только те, которые успешно обработались
    logger.info(f"🕒 Сообщений-слотов к закрытию: {len(ok_slots_to_delete)}")
    for msg_id in ok_slots_to_delete:
        try:
            await bot.edit_message_text(
                chat_id=CHANNEL_ID, message_id=msg_id,
                text="Рабочий день завершён. Все слоты закрыты."
            )
        except Exception as e:
            logger.warning(f"⚠️ msg {msg_id}: не закрыть ({e})")

    if any_critical_error:
        logger.warning(
            f"🕒 День закрыт ЧАСТИЧНО — есть ошибки. "
            f"Осталось слотов: {len(active_slots)}, сессий: {len(slot_requests)}. Верну False для повтора."
        )
        return False

    logger.info("✅ День закрыт полностью")
    return True


async def update_stats_from_sheet():
    while True:
        now = datetime.now(moscow_tz)
        weekday = now.weekday()
        target_times = []
        if weekday == 2:
            next_day = now.replace(hour=10, minute=0, second=0, microsecond=0) + timedelta(days=1)
            await asyncio.sleep((next_day - now).total_seconds())
            continue
        if weekday == 3:
            thursday_2000 = now.replace(hour=20, minute=0, second=0, microsecond=0)
            if now < thursday_2000:
                target_times = [thursday_2000]
            else:
                target_times = [now.replace(hour=10, minute=0, second=0, microsecond=0) + timedelta(days=1)]
        else:
            target_times = [
                now.replace(hour=10, minute=0, second=0, microsecond=0),
                now.replace(hour=20, minute=0, second=0, microsecond=0),
            ]
        future = [t for t in target_times if t > now]
        if not future:
            future = [now.replace(hour=10, minute=0, second=0, microsecond=0) + timedelta(days=1)]
        next_target = min(future)
        await asyncio.sleep((next_target - now).total_seconds())
        await update_stats_from_sheet_once()


async def update_stats_from_sheet_once():
    try:
        logger.info("🔄 Обновление статистики")
        client = get_client()
        if not client:
            return
        spreadsheet = client.open_by_key(SHEET_ID)
        updates_by_sheet = {}

        for sheet in spreadsheet.worksheets():
            try:
                records = await retry_api_call(sheet.get_all_values)
            except:
                continue
            if len(records) < 2:
                continue
            sheet_name = sheet.title
            platform = platform_from_sheet_name(sheet_name)
            mapping = get_column_mapping(platform) if platform else get_column_mapping("яндекс")
            sheet_updates = []

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
                            "яндекс": "yandex", "google": "google", "2гис": "gis",
                            "авито": "avito", "вк": "vk", "отзовик": "otzovik",
                            "доктору": "doctoru", "докдок": "dokdok",
                            "про докторов": "prodoctors", "докту": "doctu",
                            "32топ": "top32", "zoon": "zoon",
                            "яу": "yau", "яб": "yab", "h": "hh",
                        }
                        fp = field_map.get(platform)
                        with sqlite3.connect(DB_PATH) as conn:
                            cur = conn.cursor()
                            if fp:
                                cur.execute(f"UPDATE users SET {fp}_passed = {fp}_passed + 1, {fp}_total = {fp}_total + 1 WHERE user_id = ?", (uid,))
                            cur.execute("UPDATE users SET payout = payout + ?, total_earned = total_earned + ? WHERE user_id = ?", (price, price, uid))
                            conn.commit()
                        e_value = 1
                    else:
                        e_value = 2

                elif status == "опубликован опз":
                    if user:
                        uid = user["user_id"]
                        price = PRICES.get(platform, 0)
                        price_opz = int(price * 0.7)
                        field_map = {
                            "яндекс": "yandex", "google": "google", "2гис": "gis",
                            "авито": "avito", "вк": "vk", "отзовик": "otzovik",
                            "доктору": "doctoru", "докдок": "dokdok",
                            "про докторов": "prodoctors", "докту": "doctu",
                            "32топ": "top32", "zoon": "zoon",
                            "яу": "yau", "яб": "yab", "h": "hh",
                        }
                        fp = field_map.get(platform)
                        with sqlite3.connect(DB_PATH) as conn:
                            cur = conn.cursor()
                            if fp:
                                cur.execute(f"UPDATE users SET {fp}_passed = {fp}_passed + 1, {fp}_total = {fp}_total + 1 WHERE user_id = ?", (uid,))
                            cur.execute("UPDATE users SET payout = payout + ?, total_earned = total_earned + ? WHERE user_id = ?", (price_opz, price_opz, uid))
                            conn.commit()
                        e_value = 1
                    else:
                        e_value = 2

                elif status == "удален":
                    if user:
                        uid = user["user_id"]
                        field_map = {
                            "яндекс": "yandex", "google": "google", "2гис": "gis",
                            "авито": "avito", "вк": "vk", "отзовик": "otzovik",
                            "доктору": "doctoru", "докдок": "dokdok",
                            "про докторов": "prodoctors", "докту": "doctu",
                            "32топ": "top32", "zoon": "zoon",
                            "яу": "yau", "яб": "yab", "h": "hh",
                        }
                        fp = field_map.get(platform)
                        with sqlite3.connect(DB_PATH) as conn:
                            cur = conn.cursor()
                            if fp:
                                cur.execute(
                                    f"UPDATE users SET "
                                    f"  {fp}_total = CASE WHEN {fp}_total > 0 THEN {fp}_total - 1 ELSE 0 END, "
                                    f"  {fp}_passed = CASE WHEN {fp}_passed > 0 THEN {fp}_passed - 1 ELSE 0 END "
                                    f"WHERE user_id = ?",
                                    (uid,)
                                )
                            conn.commit()
                        e_value = 7
                    else:
                        e_value = 2

                elif status == "опубликован не по тх":
                    e_value = 4

                if e_value is not None:
                    sheet_updates.append({"row_idx": row_idx, "e_value": e_value})

            if sheet_updates:
                updates_by_sheet[sheet] = sheet_updates

        for sheet, updates in updates_by_sheet.items():
            batch = [{"range": f"E{u['row_idx']}", "values": [[u["e_value"]]]} for u in updates]
            try:
                for i in range(0, len(batch), 50):
                    await retry_api_call(sheet.batch_update, batch[i:i+50])
                    await asyncio.sleep(0.6)
            except Exception as e:
                logger.error(f"❌ E: {e}")

        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT user_id, yandex_passed, google_passed, gis_passed, avito_passed, vk_passed,
                       otzovik_passed, doctoru_passed, dokdok_passed, prodoctors_passed,
                       doctu_passed, top32_passed, zoon_passed, yau_passed, yab_passed, hh_passed,
                       admin_topup
                FROM users
            """)
            for ur in cur.fetchall():
                uid = ur[0]
                total = (
                    ur[1] * PRICES.get("яндекс", 0) + ur[2] * PRICES.get("google", 0) +
                    ur[3] * PRICES.get("2гис", 0) + ur[4] * PRICES.get("авито", 0) +
                    ur[5] * PRICES.get("вк", 0) + ur[6] * PRICES.get("отзовик", 0) +
                    ur[7] * PRICES.get("доктору", 0) + ur[8] * PRICES.get("докдок", 0) +
                    ur[9] * PRICES.get("про докторов", 0) + ur[10] * PRICES.get("докту", 0) +
                    ur[11] * PRICES.get("32топ", 0) + ur[12] * PRICES.get("zoon", 0) +
                    ur[13] * PRICES.get("яу", 0) + ur[14] * PRICES.get("яб", 0) +
                    ur[15] * PRICES.get("h", 0)
                )
                admin_topup = ur[16] or 0
                total += admin_topup
                cur.execute("UPDATE users SET payout = ? WHERE user_id = ?", (total, uid))
            conn.commit()

        logger.info(f"✅ Обновлено листов: {len(updates_by_sheet)}")
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}", exc_info=True)


async def mark_as_paid_in_table(user_ids: list):
    try:
        client = get_client()
        if not client:
            return
        spreadsheet = client.open_by_key(SHEET_ID)
        users_map = {}
        for uid in user_ids:
            user = get_user(uid)
            if user:
                users_map[uid] = user.get('tg_username', '').lower()

        for sheet in spreadsheet.worksheets():
            try:
                records = await retry_api_call(sheet.get_all_values)
            except:
                continue
            if len(records) < 2:
                continue
            platform = platform_from_sheet_name(sheet.title)
            mapping = get_column_mapping(platform) if platform else get_column_mapping("яндекс")
            batch = []
            for row_idx, row in enumerate(records[1:], start=2):
                if len(row) < max(mapping["status_col"], mapping["executor_col"], mapping["update_col"]):
                    continue
                e_val = row[mapping["update_col"]-1].strip()
                if e_val != "1":
                    continue
                status = row[mapping["status_col"]-1].strip().lower()
                if status not in ("опубликован", "опубликовано"):
                    continue
                executor = row[mapping["executor_col"]-1].strip().lstrip("@").lower()
                if not executor:
                    continue
                matched = None
                for uid, uname in users_map.items():
                    if uname and executor == uname:
                        matched = uid
                        break
                if matched:
                    col = chr(64 + mapping["status_col"])
                    batch.append({"range": f"{col}{row_idx}", "values": [["В отчете ИСПЛ"]]})
            if batch:
                try:
                    for i in range(0, len(batch), 50):
                        await retry_api_call(sheet.batch_update, batch[i:i+50])
                        await asyncio.sleep(0.6)
                except Exception as e:
                    logger.error(f"❌ Статус: {e}")
    except Exception as e:
        logger.error(f"❌ mark_as_paid: {e}")


async def cleanup_channel(bot):
    logger.info("🧹 Автоочистка канала (4:30 МСК)")

    last_cleanup_str = get_setting("last_cleanup_date")
    last_cleanup_date = None
    if last_cleanup_str:
        try:
            last_cleanup_date = date.fromisoformat(last_cleanup_str)
        except Exception:
            last_cleanup_date = None

    while True:
        try:
            now = datetime.now(moscow_tz)
            today_date = now.date()
            today_target = now.replace(hour=4, minute=30, second=0, microsecond=0)
            should = (now >= today_target and last_cleanup_date != today_date)

            if should:
                logger.info(f"🧹 Очистка канала (запуск в {now.strftime('%H:%M')} МСК)")
                cutoff_msk = today_target
                cutoff_utc = cutoff_msk.astimezone(pytz.utc).replace(tzinfo=None)
                cutoff_str = cutoff_utc.strftime("%Y-%m-%d %H:%M:%S")
                logger.info(f"🧹 Отсечка: до {cutoff_msk.strftime('%d.%m.%Y %H:%M')} МСК (UTC {cutoff_str})")

                with sqlite3.connect(DB_PATH) as conn:
                    conn.row_factory = sqlite3.Row
                    cur = conn.cursor()
                    cur.execute(
                        "SELECT id, message_id, chat_id FROM channel_messages WHERE created_at < ?",
                        (cutoff_str,)
                    )
                    old = [dict(r) for r in cur.fetchall()]

                logger.info(f"🧹 Найдено сообщений для удаления: {len(old)}")
                deleted = 0
                failed = 0
                for msg in old:
                    try:
                        await bot.delete_message(chat_id=msg["chat_id"], message_id=msg["message_id"])
                        deleted += 1
                        await asyncio.sleep(0.3)
                    except Exception as e:
                        logger.warning(f"⚠️ msg {msg['message_id']}: {e}")
                        failed += 1
                    finally:
                        try:
                            delete_channel_message(msg["id"])
                        except Exception as e:
                            logger.error(f"❌ Удаление из БД {msg['id']}: {e}")
                logger.info(f"✅ Удалено {deleted}, не удалось {failed}")

                try:
                    active_slots.clear()
                    logger.info("🧹 active_slots очищены")
                except Exception as e:
                    logger.error(f"❌ active_slots.clear(): {e}")

                last_cleanup_date = today_date
                set_setting("last_cleanup_date", last_cleanup_date.isoformat())

            if last_cleanup_date == today_date:
                next_target = today_target + timedelta(days=1)
            elif now < today_target:
                next_target = today_target
            else:
                next_target = today_target + timedelta(days=1)
            wait = (next_target - now).total_seconds()
            logger.info(f"⏳ Следующая очистка в {next_target.strftime('%d.%m.%Y %H:%M')} МСК")
            await asyncio.sleep(min(wait, 3600) if wait > 3600 else max(wait, 60))
        except Exception as e:
            logger.error(f"❌ Очистка: {e}", exc_info=True)
            await asyncio.sleep(60)
