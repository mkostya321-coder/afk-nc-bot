import os

# ---------- Основные настройки ----------
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN not found in environment")

# Устаревший список администраторов (можно оставить, но не используется)
ADMIN_IDS_STR = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = [int(x.strip()) for x in ADMIN_IDS_STR.split(",") if x.strip()]

# Владелец (обязательная переменная)
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

# Канал для публикации слотов
CHANNEL_ID = os.getenv("CHANNEL_ID", "@newChapterJob")

# Менеджер и ссылка на другие задания
MANAGER_USERNAME = "New_Chapterr24"
OTHER_JOBS_CHANNEL = "https://t.me/jobNchapter"

# Google Таблица
SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
if not SHEET_ID:
    raise ValueError("GOOGLE_SHEET_ID not found in environment")

# Путь к базе данных SQLite
DB_PATH = "/data/bot.db"

def get_credentials_path():
    """Возвращает путь к файлу google_key.json"""
    if os.path.exists("/data/google_key.json"):
        return "/data/google_key.json"
    return "google_key.json"

# ---------- Каналы и беседы ----------
# Канал для пересылки скриншотов
SCREENSHOT_CHANNEL_ID = os.getenv("SCREENSHOT_CHANNEL_ID", "-100...")

# Канал для логирования действий администраторов (основной лог)
LOG_CHANNEL_ID = os.getenv("LOG_CHANNEL_ID", "-100...")

# Канал/беседа для отчета по выплатам
REPORT_CHAT_ID = os.getenv("REPORT_CHAT_ID", "-100...")
REPORT_THREAD_ID = int(os.getenv("REPORT_THREAD_ID", "0"))  # 0 если не тема

# ---------- Инструкция с фото ----------
# ID фото в Telegram (приоритет, если задан)
INSTRUCTION_PHOTO_ID = os.getenv("INSTRUCTION_PHOTO_ID")
# Путь к файлу с инструкцией (если INSTRUCTION_PHOTO_ID не задан)
INSTRUCTION_PHOTO_PATH = os.getenv("INSTRUCTION_PHOTO_PATH", "instruction.jpg")

# ---------- Подписка на канал ----------
# Канал, на который нужно подписаться для использования бота
REQUIRED_CHANNEL_ID = os.getenv("REQUIRED_CHANNEL_ID", "@newchapterjob")

# ---------- Tik Tok ----------
# ID видео в Telegram (приоритет)
TIKTOK_VIDEO_ID = os.getenv("TIKTOK_VIDEO_ID")
# Путь к файлу видео (если TIKTOK_VIDEO_ID не задан)
TIKTOK_VIDEO_PATH = os.getenv("TIKTOK_VIDEO_PATH", "tiktok.mp4")

# Канал/беседа и тема для отчётов Tik Tok
TIKTOK_REPORT_CHAT_ID = os.getenv("TIKTOK_REPORT_CHAT_ID", "-100...")
TIKTOK_REPORT_THREAD_ID = int(os.getenv("TIKTOK_REPORT_THREAD_ID", "0"))

# ---------- Сотрудничество ----------
# Канал/беседа и тема для заявок на сотрудничество
COLLABORATION_CHAT_ID = os.getenv("COLLABORATION_CHAT_ID", "-100...")
COLLABORATION_THREAD_ID = int(os.getenv("COLLABORATION_THREAD_ID", "0"))
