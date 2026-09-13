# bot/helpers.py

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
    "докту": 100,
    "32топ": 125,
    "zoon": 50,
    "яу": 100,
    "яб": 100,
    "h": 50,
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
}

SHEET_NAME_TO_PLATFORM = {
    # === Основные листы (с расширенным сопоставлением) ===
    "ЯНДЕКС (К)": "яндекс",
    "Яндекс (К)": "яндекс",
    "ЯНДЕКС": "яндекс",
    "Яндекс": "яндекс",
    
    "2ГИС (Г)": "2гис",
    "2гис (Г)": "2гис",
    "2ГИС": "2гис",
    "2гис": "2гис",
    
    "google (С)": "google",
    "Google (С)": "google",
    "google": "google",
    "Google": "google",
    "GOOGLE": "google",
    
    "АВИТО (А)": "авито",
    " АВИТО (А)": "авито",
    "Авито (А)": "авито",
    "АВИТО": "авито",
    "Авито": "авито",
    
    "Продокторов (ПР)": "про докторов",
    "Продокторов": "про докторов",
    "про докторов": "про докторов",
    
    "ВК (ВК)": "вк",
    "ВК": "вк",
    "вк": "вк",
    
    "ДокДок (ДД)": "докдок",
    "ДокДок": "докдок",
    "докдок": "докдок",
    
    "32Топ (Т)": "32топ",
    "32Топ": "32топ",
    "32топ": "32топ",
    
    "Докту (ДК)": "докту",
    "Докту": "докту",
    "докту": "докту",
    
    "ZOON (Z)": "zoon",
    "ZOON 2.0 (Z2)": "zoon",
    "ZOON": "zoon",
    "zoon": "zoon",
    
    # === Новые платформы ===
    "ЯНДЕКС УСЛУГИ (ЯУ)": "яу",
    "Яндекс Услуги (ЯУ)": "яу",
    "Яндекс Услуги": "яу",
    "ЯУ": "яу",
    
    "ЯНДЕКС БРАУЗЕР (ЯБ)": "яб",
    "Яндекс Браузер (ЯБ)": "яб",
    "Яндекс Браузер": "яб",
    "ЯБ": "яб",
    
    "HH.RU (H)": "h",
    "HH (H)": "h",
    "HH.RU": "h",
    "HHRU": "h",
    "H": "h",
    "HH": "h",
}


def get_column_mapping(platform: str):
    standard = {
        "date_col": 1, "time_col": 2, "stars_col": 3, "platform_col": 4,
        "link_col": 7, "status_col": 10, "executor_col": 11, "gender_col": 13,
        "text_col": 14, "flag_first_col": 17, "flag_second_col": 16,
        "flag_third_col": 15, "flag_final_col": 9, "id_col": 19,
        "update_col": 5, "order_col": 20,
    }
    if platform == "про докторов":
        return {
            "date_col": 1, "time_col": 2, "stars_col": 3, "platform_col": 4,
            "link_col": 11, "status_col": 14, "executor_col": 15, "gender_col": 16,
            "text_col": None, "flag_first_col": 22, "flag_second_col": 21,
            "flag_third_col": 20, "flag_final_col": 13, "id_col": 23,
            "update_col": 5, "order_col": 24, "text_history_col": 17,
            "text_like_col": 18, "text_minus_col": 19, "tz_col": 10,
            "doctor_name_col": 12, "doctor_direction_col": 9, "photo_doc_col": 8,
        }
    return standard


def match_platform(raw_name: str):
    name = raw_name.strip().lower()
    for std, aliases in PLATFORM_ALIASES.items():
        for a in aliases:
            if a in name:
                return std
    return None


def platform_from_sheet_name(sheet_name: str):
    # Точное совпадение
    key = sheet_name.strip()
    if key in SHEET_NAME_TO_PLATFORM:
        return SHEET_NAME_TO_PLATFORM[key]
    key_lower = key.lower()
    if key_lower in SHEET_NAME_TO_PLATFORM:
        return SHEET_NAME_TO_PLATFORM[key_lower]

    # По первому слову
    first_word = key.split()[0] if key.split() else key
    if first_word in SHEET_NAME_TO_PLATFORM:
        return SHEET_NAME_TO_PLATFORM[first_word]
    first_word_lower = first_word.lower()
    if first_word_lower in SHEET_NAME_TO_PLATFORM:
        return SHEET_NAME_TO_PLATFORM[first_word_lower]

    # По родительской платформе в скобках
    if "(" in key:
        base = key.split("(")[0].strip()
        if base in SHEET_NAME_TO_PLATFORM:
            return SHEET_NAME_TO_PLATFORM[base]
        if base.lower() in SHEET_NAME_TO_PLATFORM:
            return SHEET_NAME_TO_PLATFORM[base.lower()]

    return None
