# bot/helpers.py
import logging
from datetime import datetime, timedelta
import pytz

logger = logging.getLogger(__name__)
moscow_tz = pytz.timezone("Europe/Moscow")

PRICES = {
    "яндекс": 150, "google": 50, "2гис": 50, "авито": 700, "вк": 50,
    "отзовик": 100, "доктору": 100, "докдок": 100, "про докторов": 200,
    "докту": 100, "32топ": 125, "zoon": 50, "яу": 100, "яб": 100, "h": 50,
    "yell": 50,
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
    "zoon": ["zoon", "зун", "z"],
    "яу": ["яу", "яндекс услуги", "yandex services"],
    "яб": ["яб", "яндекс браузер", "yandex browser"],
    "h": ["h", "hh", "hh.ru", "headhunter"],
    "yell": ["yell", "йелл", "йэлл"],
}

SHEET_NAME_TO_PLATFORM = {
    # Яндекс
    "ЯНДЕКС (К)": "яндекс", "Яндекс (К)": "яндекс", "ЯНДЕКС": "яндекс", "Яндекс": "яндекс",
    # 2ГИС
    "2ГИС (Г)": "2гис", "2гис (Г)": "2гис", "2ГИС 2.0 (Г)": "2гис", "2ГИС 2.0": "2гис",
    "2ГИС": "2гис", "2гис": "2гис", "2 ГИС": "2гис",
    # Google
    "google (С)": "google", "Google (С)": "google", "google": "google",
    "Google": "google", "GOOGLE": "google",
    # Авито
    "АВИТО (А)": "авито", "Авито (А)": "авито", "АВИТО": "авито", "Авито": "авито",
    # Продокторов
    "Продокторов (ПР)": "про докторов", "Продокторов": "про докторов", "про докторов": "про докторов",
    # ВК
    "ВК (ВК)": "вк", "ВК": "вк", "вк": "вк",
    # ДокДок
    "ДокДок (ДД)": "докдок", "ДокДок": "докдок", "докдок": "докдок",
    # 32ТОП
    "32Топ (Т)": "32топ", "32Топ": "32топ", "32топ": "32топ",
    # ДокТу
    "Докту (ДК)": "докту", "Докту": "докту", "докту": "докту",
    # ZOON
    "ZOON (Z)": "zoon", "ZOON 2.0 (Z2)": "zoon", "ZOON 2.0": "zoon", "ZOON": "zoon", "zoon": "zoon",
    # Яндекс Услуги
    "ЯНДЕКС УСЛУГИ (ЯУ)": "яу", "Яндекс Услуги (ЯУ)": "яу", "Яндекс Услуги": "яу", "ЯУ": "яу",
    # Яндекс Браузер
    "ЯНДЕКС БРАУЗЕР (ЯБ)": "яб", "Яндекс Браузер (ЯБ)": "яб", "Яндекс Браузер": "яб", "ЯБ": "яб",
    # HH.RU
    "HH.RU (H)": "h", "HH (H)": "h", "HH.RU": "h", "HHRU": "h", "H": "h", "HH": "h",
    # Yell
    "yell (y)": "yell", "Yell (y)": "yell", "YELL (y)": "yell",
    "Yell (Y)": "yell", "YELL (Y)": "yell",
    "Yell": "yell", "YELL": "yell", "yell": "yell",
}


def _find_col(headers: list, *keys, default: int = 0, default_idx: int = None) -> int:
    """
    Ищет номер колонки (1-based) по подстроке в заголовке.
    Принимает и `default`, и `default_idx` — оба работают одинаково.
    """
    fallback = default if default else (default_idx if default_idx else 1)
    if not headers:
        return fallback
    for i, cell in enumerate(headers):
        cell_l = str(cell or "").strip().lower()
        for k in keys:
            if k in cell_l:
                return i + 1
    return fallback


def get_column_mapping(platform: str, headers: list = None):
    """
    Если headers передан — определяем колонки по названиям в первой строке таблицы.
    Иначе — стандартный маппинг.
    """
    # === Базовый маппинг (fallback) ===
    if platform == "про докторов":
        default = {
            "date_col": 1, "time_col": 2, "stars_col": 3, "platform_col": 4,
            "link_col": 11, "status_col": 14, "executor_col": 15, "gender_col": 16,
            "text_col": None, "flag_first_col": 22, "flag_second_col": 21,
            "flag_third_col": 20, "flag_final_col": 13, "id_col": 23,
            "update_col": 5, "order_col": 24, "text_history_col": 17,
            "text_like_col": 18, "text_minus_col": 19, "tz_col": 10,
            "doctor_name_col": 12, "doctor_direction_col": 9, "photo_doc_col": 8,
        }
    else:
        default = {
            "date_col": 1, "time_col": 2, "stars_col": 3, "platform_col": 4,
            "link_col": 7, "status_col": 10, "executor_col": 11, "gender_col": 13,
            "text_col": 14, "flag_first_col": 17, "flag_second_col": 16,
            "flag_third_col": 15, "flag_final_col": 9, "id_col": 19,
            "update_col": 5, "order_col": 20,
        }

    if not headers:
        return default

    if platform == "про докторов":
        detected = dict(default)
        detected["date_col"]     = _find_col(headers, "дата", default=default["date_col"])
        detected["time_col"]     = _find_col(headers, "время", default=default["time_col"])
        detected["stars_col"]    = _find_col(headers, "звезд", "звёзд", "оценк", default=default["stars_col"])
        detected["platform_col"] = _find_col(headers, "платформ", default=default["platform_col"])
        detected["link_col"]     = _find_col(headers, "ссылк", default=default["link_col"])
        detected["status_col"]   = _find_col(headers, "статус", default=default["status_col"])
        detected["executor_col"] = _find_col(headers, "исполнител", default=default["executor_col"])
        detected["gender_col"]   = _find_col(headers, "пол", default=default["gender_col"])
        detected["update_col"]   = _find_col(headers, "обновлен", "e-", default=default["update_col"])
        return detected

    # === Стандартные платформы: автодетект ===
    detected = {
        "date_col":     _find_col(headers, "дата", default=default["date_col"]),
        "time_col":     _find_col(headers, "время", default=default["time_col"]),
        "stars_col":    _find_col(headers, "звезд", "звёзд", "оценк", default=default["stars_col"]),
        "platform_col": _find_col(headers, "платформ", default=default["platform_col"]),
        "link_col":     _find_col(headers, "ссылк", default=default["link_col"]),
        "status_col":   _find_col(headers, "статус", default=default["status_col"]),
        "executor_col": _find_col(headers, "исполнител", default=default["executor_col"]),
        "gender_col":   _find_col(headers, "пол", default=default["gender_col"]),
        "text_col":     _find_col(headers, "текст", default=default["text_col"]),
        "update_col":   _find_col(headers, "обновлен", "e-", default=default["update_col"]),
        "flag_first_col":  default["flag_first_col"],
        "flag_second_col": default["flag_second_col"],
        "flag_third_col":  default["flag_third_col"],
        "flag_final_col":  default["flag_final_col"],
        "id_col":          default["id_col"],
        "order_col":       default["order_col"],
    }
    return detected


def match_platform(raw_name: str):
    if not raw_name:
        return None
    name = raw_name.strip().lower()
    for std, aliases in PLATFORM_ALIASES.items():
        for a in aliases:
            if a in name:
                return std
    return None


def platform_from_sheet_name(sheet_name: str):
    if not sheet_name:
        return None
    key = sheet_name.strip()
    if key in SHEET_NAME_TO_PLATFORM:
        return SHEET_NAME_TO_PLATFORM[key]
    key_lower = key.lower()
    for k, v in SHEET_NAME_TO_PLATFORM.items():
        if k.lower() == key_lower:
            return v
    for k in sorted(SHEET_NAME_TO_PLATFORM.keys(), key=len, reverse=True):
        if k.lower() in key_lower:
            logger.debug(f"platform_from_sheet_name: '{sheet_name}' -> '{SHEET_NAME_TO_PLATFORM[k]}'")
            return SHEET_NAME_TO_PLATFORM[k]
    logger.warning(f"⚠️ Не удалось определить платформу для листа '{sheet_name}'")
    return None


def business_day_key(now=None) -> str:
    """Бизнес-день начинается в 4:30 МСК. Возвращает ISO-дату 'YYYY-MM-DD'."""
    if now is None:
        now = datetime.now(moscow_tz)
    if now.hour < 4 or (now.hour == 4 and now.minute < 30):
        d = now.date() - timedelta(days=1)
    else:
        d = now.date()
    return d.isoformat()
