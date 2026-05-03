import sqlite3
from datetime import datetime
from typing import Optional
from .config import DB_PATH

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
                referrer TEXT,
                referral_bonus_paid INTEGER DEFAULT 0,

                -- периодические счётчики (сбрасываются)
                yandex_passed INTEGER DEFAULT 0,
                google_passed INTEGER DEFAULT 0,
                gis_passed INTEGER DEFAULT 0,
                avito_passed INTEGER DEFAULT 0,
                vk_passed INTEGER DEFAULT 0,
                otzovik_passed INTEGER DEFAULT 0,
                doctoru_passed INTEGER DEFAULT 0,

                -- общие счётчики (не сбрасываются)
                yandex_total INTEGER DEFAULT 0,
                google_total INTEGER DEFAULT 0,
                gis_total INTEGER DEFAULT 0,
                avito_total INTEGER DEFAULT 0,
                vk_total INTEGER DEFAULT 0,
                otzovik_total INTEGER DEFAULT 0,
                doctoru_total INTEGER DEFAULT 0
            )
        """)
        conn.commit()

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
        cur.execute(
            "SELECT * FROM users WHERE LOWER(tg_username) IN (?, ?)",
            (clean, f"@{clean}")
        )
        row = cur.fetchone()
        return dict(row) if row else None

def is_registered(user_id: int) -> bool:
    user = get_user(user_id)
    return user is not None and user.get("name") is not None

def is_blocked(user_id: int) -> bool:
    user = get_user(user_id)
    return user.get("blocked", 0) == 1 if user else False

def toggle_block(user_id: int):
    user = get_user(user_id)
    if not user:
        return None
    new_status = 0 if user["blocked"] else 1
    update_user_field(user_id, "blocked", new_status)
    return new_status
