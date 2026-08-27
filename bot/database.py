import sqlite3
from datetime import datetime
from typing import Optional
from .config import DB_PATH, OWNER_ID

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
                top32_total INTEGER DEFAULT 0
            )
        """)
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
        cur.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        if OWNER_ID:
            cur.execute("INSERT OR IGNORE INTO admins (user_id, role) VALUES (?, 'owner')", (OWNER_ID,))
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

# ---------- Роли администраторов ----------
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

# ---------- Предупреждения (с датами истечения) ----------
def add_warning(user_id: int, reason: str, warned_by: int):
    # Продлеваем существующие активные предупреждения на 45 дней
    extend_warnings_expiry(user_id, 45)
    # Добавляем новое (срок 30 дней)
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

# ---------- Настройки ----------
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

# ---------- Выплаты и рефералы ----------
def get_all_users_with_payout():
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE payout >= 150")
        return [dict(row) for row in cur.fetchall()]
