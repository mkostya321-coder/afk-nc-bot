import os
import logging

logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN not found in environment")

ADMIN_IDS_STR = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = [int(x.strip()) for x in ADMIN_IDS_STR.split(",") if x.strip()]

OWNER_ID = int(os.getenv("OWNER_ID", "0"))
CHANNEL_ID = os.getenv("CHANNEL_ID", "@newChapterJob")
MANAGER_USERNAME = "New_Chapterr24"
OTHER_JOBS_CHANNEL = "https://t.me/jobNchapter"
SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
if not SHEET_ID:
    raise ValueError("GOOGLE_SHEET_ID not found in environment")

DB_PATH = "/data/bot.db"


def get_credentials_path():
    if os.path.exists("/data/google_key.json"):
        return "/data/google_key.json"
    return "google_key.json"


def _opt_int(name: str, default: int = 0) -> int:
    val = os.getenv(name)
    if val is None or val == "":
        return default
    try:
        return int(val)
    except ValueError:
        logger.warning(f"⚠️ {name}='{val}' не число, использую {default}")
        return default


# ⚠️ ВАЖНО: если переменная не задана — None, а не "-100..."
SCREENSHOT_CHANNEL_ID = os.getenv("SCREENSHOT_CHANNEL_ID") or None
LOG_CHANNEL_ID = os.getenv("LOG_CHANNEL_ID") or None
REPORT_CHAT_ID = os.getenv("REPORT_CHAT_ID") or None
REPORT_THREAD_ID = _opt_int("REPORT_THREAD_ID", 0)

INSTRUCTION_PHOTO_ID = os.getenv("INSTRUCTION_PHOTO_ID") or None
INSTRUCTION_PHOTO_PATH = os.getenv("INSTRUCTION_PHOTO_PATH", "instruction.jpg")

REQUIRED_CHANNEL_ID = os.getenv("REQUIRED_CHANNEL_ID", "@newchapterjob")

# Tik Tok
TIKTOK_VIDEO_ID = os.getenv("TIKTOK_VIDEO_ID") or None
TIKTOK_VIDEO_PATH = os.getenv("TIKTOK_VIDEO_PATH", "tiktok.mp4")
TIKTOK_REPORT_CHAT_ID = os.getenv("TIKTOK_REPORT_CHAT_ID") or None
TIKTOK_REPORT_THREAD_ID = _opt_int("TIKTOK_REPORT_THREAD_ID", 0)

# Сотрудничество
COLLABORATION_CHAT_ID = os.getenv("COLLABORATION_CHAT_ID") or None
COLLABORATION_THREAD_ID = _opt_int("COLLABORATION_THREAD_ID", 0)

# Поддержка
SUPPORT_CHAT_ID = os.getenv("SUPPORT_CHAT_ID") or None
SUPPORT_THREAD_ID = _opt_int("SUPPORT_THREAD_ID", 0)
