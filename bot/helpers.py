# bot/helpers.py
# Вспомогательные функции, вынесенные из google_sheets.py для избежания циклического импорта

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
    "ZOON (Z)": "zoon",
    "ЯНДЕКС": "яндекс", "Яндекс": "яндекс", "yandex": "яндекс",
    "2ГИС": "2гис", "2гис": "2гис",
    "google": "google", "Google": "google", "GOOGLE": "google",
    "АВИТО": "авито", "Авито": "авито", "avito": "авито",
    "Продокторов": "про докторов", "про докторов": "про докторов", "prodoctors": "про докторов",
    "ВК": "вк", "вк": "вк", "vk": "вк",
    "ДокДок": "докдок", "докдок": "докдок",
    "32Топ": "32топ", "32топ": "32топ", "32top": "32топ",
    "Докту": "докту", "докту": "докту", "doctu": "докту",
    "ZOON": "zoon", "ЗУН": "zoon", "zoon": "zoon",
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
