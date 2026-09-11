import sqlite3
import json
from datetime import datetime, timedelta
from typing import Optional
from .config import DB_PATH, OWNER_ID
import pytz


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                registered_at TIMESTAMP,
                name TEXT,
                tg_username TEXT,
                timezone TEXT,
                city TEXT,
                phone_card TEXT,
                bank TEXT,
                blocked INTEGER DEFAULT 0,
                payout INTEGER DEFAULT 0,
                total_earned INTEGER DEFAULT 0,
                admin_topup INTEGER DEFAULT 0,
                referrer TEXT,
                referral_bonus_paid INTEGER DEFAULT 0,
                yandex_passed INTEGER DEFAULT 0,
                google_passed INTEGER DEFAULT 0,
                gis_passed INTEGER DEFAULT 0,
                avito_passed INTEGER DEFAULT 0,
                vk_passed INTEGER DEFAULT 0,
                otzovik_passed INTEGER DEFAULT 0,
                doctoru_passed INTEGER DEFAULT 0,
                dokdok_passed INTEGER DEFAULT 0,
                prodoctors_passed INTEGER DEFAULT 0,
                doctu_passed INTEGER DEFAULT 0,
                top32_passed INTEGER DEFAULT 0,
                zoon_passed INTEGER DEFAULT 0,
                yandex_total INTEGER DEFAULT 0,
                google_total INTEGER DEFAULT 0,
                gis_total INTEGER DEFAULT 0,
                avito_total INTEGER DEFAULT 0,
                vk_total INTEGER DEFAULT 0,
                otzovik_total INTEGER DEFAULT 0,
                doctoru_total INTEGER DEFAULT 0,
                dokdok_total INTEGER DEFAULT 0,
                prodoctors_total INTEGER DEFAULT 0,
                doctu_total INTEGER DEFAULT 0,
                top32_total INTEGER DEFAULT 0,
                zoon_total INTEGER DEFAULT 0
            )
        """)

        cur.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in cur.fetchall()]
        needed_columns = {
            "zoon_passed": "INTEGER DEFAULT 0",
            "zoon_total": "INTEGER DEFAULT 0",
            "admin_topup": "INTEGER DEFAULT 0",
        }
        for col_name, col_type in needed_columns.items():
            if col_name not in columns:
                cur.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}")
                print(f"✅ Добавлена колонка users.{col_name}")

        cur.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY,
                role TEXT NOT NULL DEFAULT 'moderator'
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                reason TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                warned_by INTEGER NOT NULL,
                expires_at TIMESTAMP
            )
        """)
        cur.execute("PRAGMA table_info(warnings)")
        columns = [col[1] for col in cur.fetchall()]
        if 'expires_at' not in columns:
            cur.execute("ALTER TABLE warnings ADD COLUMN expires_at TIMESTAMP")

        cur.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS review_takes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                platform TEXT NOT NULL,
                taken_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS channel_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # === ХРАНЕНИЕ СЕССИЙ В БД ===
        cur.execute("""
            CREATE TABLE IF NOT EXISTS active_slots (
                msg_id INTEGER PRIMARY KEY,
                platform TEXT NOT NULL,
                count INTEGER DEFAULT 0,
                row_ids TEXT,
                date TEXT,
                time TEXT,
                publish_time TIMESTAMP,
                attempt INTEGER DEFAULT 1,
                sheet_title TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS slot_requests_db (
                user_id INTEGER PRIMARY KEY,
                platform TEXT,
                count INTEGER DEFAULT 0,
                date TEXT,
                time TEXT,
                slot_msg_id INTEGER,
                state TEXT,
                assigned_rows TEXT,
                row_ids TEXT,
                sheet_title TEXT,
                ordered_reviews TEXT,
                completed_reviews TEXT,
                active_review_row INTEGER,
                extra_messages TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        if OWNER_ID:
            cur.execute("INSERT OR IGNORE INTO admins (user_id, role) VALUES (?, 'owner')", (OWNER_ID,))
        conn.commit()


# ============ USERS ============
def add_user(user_id: int, username: str, first_name: str):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT OR IGNORE INTO users (user_id, username, first_name, registered_at)
            VALUES (?, ?, ?, ?)
        """, (user_id, username, first_name, datetime.now()))
        conn.commit()


def update_user_field(user_id: int, field: str, value):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute(f"UPDATE users SET {field} = ? WHERE user_id = ?", (value, user_id))
        conn.commit()


def get_user(user_id: int) -> Optional[dict]:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def get_user_by_username(username: str) -> Optional[dict]:
    clean = username.lstrip("@").lower()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE LOWER(tg_username) = ? OR LOWER(username) = ?", (clean, clean))
        row = cur.fetchone()
        return dict(row) if row else None


def is_registered(user_id: int) -> bool:
    user = get_user(user_id)
    return user is not None and user.get("name") is not None


def is_blocked(user_id: int) -> bool:
    user = get_user(user_id)
    return user.get("blocked", 0) == 1 if user else False


def toggle_block(user_id: int) -> Optional[int]:
    user = get_user(user_id)
    if not user:
        return None
    new_status = 0 if user["blocked"] else 1
    update_user_field(user_id, "blocked", new_status)
    return new_status


# ============ ADMINS ============
def get_admin_role(user_id: int) -> Optional[str]:
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("SELECT role FROM admins WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
        return row[0] if row else None


def set_admin_role(user_id: int, role: str):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO admins (user_id, role) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET role = ?", (user_id, role, role))
        conn.commit()


def is_owner(user_id: int) -> bool:
    return get_admin_role(user_id) == 'owner'


def is_ga(user_id: int) -> bool:
    role = get_admin_role(user_id)
    return role in ('owner', 'ga')


def is_moderator(user_id: int) -> bool:
    role = get_admin_role(user_id)
    return role in ('owner', 'ga', 'moderator')


def is_comoderator(user_id: int) -> bool:
    role = get_admin_role(user_id)
    return role in ('owner', 'ga', 'moderator', 'comoderator')


# ============ WARNINGS ============
def add_warning(user_id: int, reason: str, warned_by: int):
    extend_warnings_expiry(user_id, 45)
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO warnings (user_id, reason, warned_by, expires_at)
            VALUES (?, ?, ?, datetime('now', '+30 days'))
        """, (user_id, reason, warned_by))
        conn.commit()


def get_warning_count(user_id: int) -> int:
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM warnings WHERE user_id = ? AND expires_at > datetime('now')", (user_id,))
        return cur.fetchone()[0]


def get_active_warnings(user_id: int) -> list:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("""
            SELECT id, reason, created_at, expires_at, warned_by
            FROM warnings
            WHERE user_id = ? AND expires_at > datetime('now')
            ORDER BY created_at ASC
        """, (user_id,))
        return [dict(row) for row in cur.fetchall()]


def extend_warnings_expiry(user_id: int, days: int = 45):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("""
            UPDATE warnings
            SET expires_at = datetime(expires_at, '+' || ? || ' days')
            WHERE user_id = ? AND expires_at > datetime('now')
        """, (days, user_id))
        conn.commit()


# ============ SETTINGS ============
def get_setting(key: str) -> Optional[str]:
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cur.fetchone()
        return row[0] if row else None


def set_setting(key: str, value: str):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
        conn.commit()


def get_all_users_with_payout():
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE payout >= 150")
        return [dict(row) for row in cur.fetchall()]


# ============ REVIEW TAKES ============
def add_review_take(user_id: int, platform: str):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO review_takes (user_id, platform) VALUES (?, ?)", (user_id, platform))
        conn.commit()


def count_review_takes_last_24h(user_id: int, platform: str) -> int:
    moscow_tz = pytz.timezone("Europe/Moscow")
    now = datetime.now(moscow_tz)
    today_10am = now.replace(hour=10, minute=0, second=0, microsecond=0)
    if now < today_10am:
        today_10am -= timedelta(days=1)
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT COUNT(*) FROM review_takes
            WHERE user_id = ? AND platform = ? AND taken_at > ?
        """, (user_id, platform, today_10am.isoformat()))
        return cur.fetchone()[0]


def get_limit(platform: str) -> int:
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("SELECT value FROM settings WHERE key = ?", (f"limit_{platform}",))
        row = cur.fetchone()
        if row:
            return int(row[0])
        return 10


def set_limit(platform: str, limit: int):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (f"limit_{platform}", str(limit)))
        conn.commit()


def get_all_registered_users():
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT user_id, tg_username FROM users WHERE name IS NOT NULL")
        return [dict(row) for row in cur.fetchall()]


# ============ СООБЩЕНИЯ КАНАЛА ============
def save_channel_message(message_id: int, chat_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO channel_messages (message_id, chat_id) VALUES (?, ?)", (message_id, chat_id))
        conn.commit()


def get_old_channel_messages(hours: int = 12):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("""
            SELECT id, message_id, chat_id FROM channel_messages
            WHERE created_at < datetime('now', '-' || ? || ' hours')
        """, (hours,))
        return [dict(row) for row in cur.fetchall()]


def delete_channel_message(record_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM channel_messages WHERE id = ?", (record_id,))
        conn.commit()


# ============ ХРАНЕНИЕ СЕССИЙ (active_slots) ============
def save_active_slot(msg_id: int, data: dict):
    """Сохраняет активный слот в БД."""
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT OR REPLACE INTO active_slots 
            (msg_id, platform, count, row_ids, date, time, publish_time, attempt, sheet_title)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            msg_id,
            data.get("platform"),
            data.get("count", 0),
            json.dumps(data.get("row_ids", [])),
            data.get("date"),
            data.get("time"),
            data.get("publish_time").isoformat() if data.get("publish_time") else None,
            data.get("attempt", 1),
            data.get("sheet_title")
        ))
        conn.commit()


def update_active_slot(msg_id: int, data: dict):
    save_active_slot(msg_id, data)


def delete_active_slot(msg_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM active_slots WHERE msg_id = ?", (msg_id,))
        conn.commit()


def get_all_active_slots() -> dict:
    """Возвращает {msg_id: {...}}."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT * FROM active_slots")
        result = {}
        for row in cur.fetchall():
            d = dict(row)
            d["row_ids"] = json.loads(d.get("row_ids") or "[]")
            if d.get("publish_time"):
                try:
                    d["publish_time"] = datetime.fromisoformat(d["publish_time"])
                except:
                    pass
            result[d["msg_id"]] = d
        return result


# ============ ХРАНЕНИЕ СЕССИЙ (slot_requests) ============
def save_slot_request(user_id: int, data: dict):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT OR REPLACE INTO slot_requests_db 
            (user_id, platform, count, date, time, slot_msg_id, state, assigned_rows,
             row_ids, sheet_title, ordered_reviews, completed_reviews, active_review_row,
             extra_messages, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            data.get("platform"),
            data.get("count", 0),
            data.get("date"),
            data.get("time"),
            data.get("slot_msg_id"),
            data.get("state"),
            json.dumps(data.get("assigned_rows", [])),
            json.dumps(data.get("row_ids", [])),
            data.get("sheet_title"),
            json.dumps(data.get("ordered_reviews", [])),
            json.dumps(data.get("completed_reviews", [])),
            data.get("active_review_row"),
            json.dumps(data.get("extra_messages", [])),
            datetime.now()
        ))
        conn.commit()


def delete_slot_request(user_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM slot_requests_db WHERE user_id = ?", (user_id,))
        conn.commit()


def get_all_slot_requests() -> dict:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT * FROM slot_requests_db")
        result = {}
        for row in cur.fetchall():
            d = dict(row)
            d["assigned_rows"] = json.loads(d.get("assigned_rows") or "[]")
            d["row_ids"] = json.loads(d.get("row_ids") or "[]")
            d["ordered_reviews"] = json.loads(d.get("ordered_reviews") or "[]")
            d["completed_reviews"] = json.loads(d.get("completed_reviews") or "[]")
            d["extra_messages"] = json.loads(d.get("extra_messages") or "[]")
            result[d["user_id"]] = d
        return result


def get_slot_request(user_id: int) -> Optional[dict]:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT * FROM slot_requests_db WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
        if not row:
            return None
        d = dict(row)
        d["assigned_rows"] = json.loads(d.get("assigned_rows") or "[]")
        d["row_ids"] = json.loads(d.get("row_ids") or "[]")
        d["ordered_reviews"] = json.loads(d.get("ordered_reviews") or "[]")
        d["completed_reviews"] = json.loads(d.get("completed_reviews") or "[]")
        d["extra_messages"] = json.loads(d.get("extra_messages") or "[]")
        return d
