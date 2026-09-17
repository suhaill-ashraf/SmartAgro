"""
SmartAgro Backend — Database Layer
SQLite | Multi-user: users + per-user profile, logs, settings, notifications
Context manager pattern | Full type hints | Proper error handling
"""

import sqlite3
import os
import secrets
from contextlib import contextmanager
from typing import Optional
from datetime import datetime, date

from werkzeug.security import generate_password_hash, check_password_hash

from config import (
    DB_PATH,
    DATA_DIR,
    TABLE_ORCHARD,
    TABLE_SPRAY_LOG,
    TABLE_SPRAY_DB,
    TABLE_SETTINGS,
    TABLE_NOTIFICATIONS,
    STATUS_DONE,
    STATUS_POSTPONED,
    STATUS_SKIPPED,
    DEFAULT_MIN_INTERVAL,
    DEFAULT_LAT,
    DEFAULT_LON,
    DEFAULT_LOCATION,
    DEFAULT_RAIN_RISK_ALERT,
    DEFAULT_SPRAY_WINDOW_ALERT,
    DEFAULT_MISSED_SPRAY_ALERT,
    DEFAULT_PREFERRED_HOURS,
    DEFAULT_WEATHER_REFRESH_HOURS,
    DEFAULT_LANGUAGE,
    GROWTH_STAGES, 
)
from spray_db import SPRAY_DB

TABLE_USERS = "users"


@contextmanager
def get_db():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ════════════════════════════════════════════════
# TABLE CREATION
# ════════════════════════════════════════════════
def create_tables() -> None:
    with get_db() as conn:
        cursor = conn.cursor()

        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {TABLE_ORCHARD} (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id           INTEGER NOT NULL DEFAULT 0,
                farmer_name       TEXT    NOT NULL,
                location          TEXT    NOT NULL DEFAULT '{DEFAULT_LOCATION}',
                lat               REAL    NOT NULL DEFAULT {DEFAULT_LAT},
                lon               REAL    NOT NULL DEFAULT {DEFAULT_LON},
                crop_type         TEXT    NOT NULL DEFAULT 'Apple',
                growth_stage      TEXT    NOT NULL DEFAULT 'Fruit Set',
                last_spray_date   TEXT    NOT NULL,
                min_interval_days INTEGER NOT NULL DEFAULT {DEFAULT_MIN_INTERVAL},
                preferred_time    TEXT    NOT NULL DEFAULT '6 AM - 9 AM',
                created_at        TEXT    DEFAULT (datetime('now'))
            )
        """)

        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {TABLE_SPRAY_LOG} (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id           INTEGER NOT NULL DEFAULT 0,
                date              TEXT    NOT NULL,
                spray_name        TEXT    NOT NULL,
                dosage            TEXT    NOT NULL DEFAULT '',
                growth_stage      TEXT    NOT NULL DEFAULT '',
                status            TEXT    NOT NULL DEFAULT '{STATUS_DONE}'
                                          CHECK(status IN (
                                              '{STATUS_DONE}',
                                              '{STATUS_POSTPONED}',
                                              '{STATUS_SKIPPED}'
                                          )),
                notes             TEXT    DEFAULT '',
                temp_at_spray     REAL    DEFAULT 0.0,
                humidity_at_spray REAL    DEFAULT 0.0,
                wind_at_spray     REAL    DEFAULT 0.0,
                created_at        TEXT    DEFAULT (datetime('now'))
            )
        """)

        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {TABLE_SPRAY_DB} (
                id            INTEGER PRIMARY KEY,
                growth_stage  TEXT    NOT NULL,
                spray_name    TEXT    NOT NULL,
                spray_type    TEXT    NOT NULL,
                dosage        TEXT    NOT NULL,
                best_window   TEXT    NOT NULL DEFAULT '6 AM - 9 AM',
                interval_days INTEGER DEFAULT {DEFAULT_MIN_INTERVAL},
                target        TEXT    DEFAULT '',
                caution       TEXT    DEFAULT '',
                source        TEXT    DEFAULT 'SKUAST-K 2026'
            )
        """)

        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {TABLE_SETTINGS} (
                user_id    INTEGER NOT NULL DEFAULT 0,
                key        TEXT NOT NULL,
                value      TEXT NOT NULL,
                updated_at TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (user_id, key)
            )
        """)

        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {TABLE_NOTIFICATIONS} (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL DEFAULT 0,
                type       TEXT NOT NULL,
                title      TEXT NOT NULL,
                message    TEXT NOT NULL,
                is_read    INTEGER NOT NULL DEFAULT 0,
                created_at TEXT    DEFAULT (datetime('now'))
            )
        """)

    print("  [DB] Tables created successfully.")


def create_users_table() -> None:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {TABLE_USERS} (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                username      TEXT    NOT NULL UNIQUE,
                password_hash TEXT    NOT NULL,
                token         TEXT,
                created_at    TEXT    DEFAULT (datetime('now'))
            )
        """)
    print("  [DB] Users table ready.")


# ════════════════════════════════════════════════
# USERS & AUTH
# ════════════════════════════════════════════════
def register_user(username: str, password: str) -> dict:
    """Creates a new user. Returns {'error': ...} if the username is taken."""
    username = (username or "").strip().lower()
    if not username or not password:
        return {"error": "Username and password are required."}
    if len(password) < 4:
        return {"error": "Password must be at least 4 characters."}

    pw_hash = generate_password_hash(password)
    token = secrets.token_hex(32)
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"INSERT INTO {TABLE_USERS} (username, password_hash, token) VALUES (?, ?, ?)",
                (username, pw_hash, token),
            )
            user_id = cursor.lastrowid
        return {"user_id": user_id, "username": username, "token": token}
    except sqlite3.IntegrityError:
        return {"error": "That username is already taken."}


def login_user(username: str, password: str) -> dict:
    """Verifies credentials. Returns a fresh token on success, else {'error': ...}."""
    username = (username or "").strip().lower()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM {TABLE_USERS} WHERE username = ?", (username,))
        row = cursor.fetchone()
        if not row:
            return {"error": "Invalid username or password."}
        if not check_password_hash(row["password_hash"], password):
            return {"error": "Invalid username or password."}
        token = secrets.token_hex(32)
        cursor.execute(f"UPDATE {TABLE_USERS} SET token = ? WHERE id = ?", (token, row["id"]))
    return {"user_id": row["id"], "username": username, "token": token}


def get_user_by_token(token: str) -> Optional[dict]:
    """Looks up a user by their token. Used to authenticate each request."""
    if not token:
        return None
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT id, username FROM {TABLE_USERS} WHERE token = ?", (token,))
        row = cursor.fetchone()
    return dict(row) if row else None


# ════════════════════════════════════════════════
# SPRAY LOOKUP (shared reference data — not per-user)
# ════════════════════════════════════════════════
def seed_spray_db() -> None:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT COUNT(*) FROM {TABLE_SPRAY_DB}")
        count = cursor.fetchone()[0]
        if count > 0:
            print(f"  [DB] Spray DB already seeded ({count} rows). Skipping.")
            return
        for item in SPRAY_DB:
            cursor.execute(f"""
                INSERT INTO {TABLE_SPRAY_DB}
                    (id, growth_stage, spray_name, spray_type,
                     dosage, best_window, interval_days,
                     target, caution, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                item["id"], item["growth_stage"], item["spray_name"],
                item["spray_type"], item["dosage"], item["best_window"],
                item["interval"], item["target"], item["caution"], item["source"],
            ))
    print(f"  [DB] Spray DB seeded with {len(SPRAY_DB)} rows.")


def get_spray_by_stage(growth_stage: str) -> dict:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM {TABLE_SPRAY_DB} WHERE growth_stage = ?", (growth_stage,))
        row = cursor.fetchone()
    if row:
        return dict(row)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM {TABLE_SPRAY_DB} WHERE growth_stage = 'Fruit Set'")
        row = cursor.fetchone()
    return dict(row) if row else {}


def get_all_spray_stages() -> list:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM {TABLE_SPRAY_DB} ORDER BY id")
        rows = cursor.fetchall()
    return [dict(r) for r in rows]
def has_log_for_date(user_id: int, target_date: str) -> bool:
    """Returns True if this user already logged any spray on the given date (YYYY-MM-DD)."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT COUNT(*) AS c FROM {TABLE_SPRAY_LOG} WHERE user_id = ? AND date = ?",
            (user_id, target_date),
        )
        row = cursor.fetchone()
    return (row["c"] if row else 0) > 0


# ════════════════════════════════════════════════
# ORCHARD PROFILE (per-user)
# ════════════════════════════════════════════════
def save_orchard_profile(data: dict, user_id: int) -> None:
    required = ["farmer_name", "location", "growth_stage", "last_spray_date"]
    for field in required:
        if not data.get(field):
            raise ValueError(f"Missing required field: {field}")
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(f"DELETE FROM {TABLE_ORCHARD} WHERE user_id = ?", (user_id,))
        cursor.execute(f"""
            INSERT INTO {TABLE_ORCHARD}
                (user_id, farmer_name, location, lat, lon, crop_type,
                 growth_stage, last_spray_date,
                 min_interval_days, preferred_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            data.get("farmer_name"),
            data.get("location",          DEFAULT_LOCATION),
            data.get("lat",               DEFAULT_LAT),
            data.get("lon",               DEFAULT_LON),
            data.get("crop_type",         "Apple"),
            data.get("growth_stage",      "Fruit Set"),
            data.get("last_spray_date"),
            data.get("min_interval_days", DEFAULT_MIN_INTERVAL),
            data.get("preferred_time",    "6 AM - 9 AM"),
        ))

# ── Add to database.py ──
# Needs: from config import GROWTH_STAGES   (add GROWTH_STAGES to the config import at the top)

def advance_growth_stage(user_id: int) -> Optional[str]:
    """
    Moves THIS user's orchard profile to the NEXT growth stage in the SKUAST-K list.
    Called when a spray is logged as DONE.
    Returns the new stage name, or None if no profile / already at last stage.
    """
    profile = get_orchard_profile(user_id)
    if not profile:
        return None

    current_stage = profile.get("growth_stage", "Fruit Set")
    try:
        idx = GROWTH_STAGES.index(current_stage)
    except ValueError:
        idx = GROWTH_STAGES.index("Fruit Set")

    # Already at the final stage — stay there
    if idx >= len(GROWTH_STAGES) - 1:
        return current_stage

    next_stage = GROWTH_STAGES[idx + 1]

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE {TABLE_ORCHARD} SET growth_stage = ? WHERE user_id = ?",
            (next_stage, user_id),
        )
    return next_stage

def get_orchard_profile(user_id: int) -> Optional[dict]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM {TABLE_ORCHARD} WHERE user_id = ? LIMIT 1", (user_id,))
        row = cursor.fetchone()
    return dict(row) if row else None


# ════════════════════════════════════════════════
# SPRAY LOG (per-user)
# ════════════════════════════════════════════════
def save_spray_log(data: dict, user_id: int) -> None:
    required = ["date", "spray_name", "growth_stage", "status"]
    for field in required:
        if not data.get(field):
            raise ValueError(f"Missing required field: {field}")
    valid_statuses = [STATUS_DONE, STATUS_POSTPONED, STATUS_SKIPPED]
    if data["status"] not in valid_statuses:
        raise ValueError(f"Invalid status: {data['status']}.")
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(f"""
            INSERT INTO {TABLE_SPRAY_LOG}
                (user_id, date, spray_name, dosage, growth_stage,
                 status, notes,
                 temp_at_spray, humidity_at_spray, wind_at_spray)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            data.get("date"),
            data.get("spray_name"),
            data.get("dosage",            ""),
            data.get("growth_stage",      ""),
            data.get("status",            STATUS_DONE),
            data.get("notes",             ""),
            data.get("temp_at_spray",     0.0),
            data.get("humidity_at_spray", 0.0),
            data.get("wind_at_spray",     0.0),
        ))


def get_spray_history(user_id: int) -> list:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM {TABLE_SPRAY_LOG} WHERE user_id = ? ORDER BY date DESC", (user_id,))
        rows = cursor.fetchall()
    return [dict(r) for r in rows]

def get_last_spray_date(user_id: int) -> Optional[str]:
    """
    Date of the most recent spray that was acted on (DONE or SKIPPED) for this user.
    POSTPONED is excluded on purpose, so a delayed spray keeps re-prompting.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT date FROM {TABLE_SPRAY_LOG}
            WHERE user_id = ? AND status IN (?, ?)
            ORDER BY date DESC LIMIT 1
        """, (user_id, STATUS_DONE, STATUS_SKIPPED))
        row = cursor.fetchone()
    return row["date"] if row else None

def delete_spray_log(log_id: int, user_id: int) -> bool:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(f"DELETE FROM {TABLE_SPRAY_LOG} WHERE id = ? AND user_id = ?", (log_id, user_id))
        deleted = cursor.rowcount > 0
    return deleted


def get_monthly_report(year: int, month: int, user_id: int) -> dict:
    prefix = f"{year}-{str(month).zfill(2)}"
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT status, COUNT(*) as count FROM {TABLE_SPRAY_LOG}
            WHERE date LIKE ? AND user_id = ? GROUP BY status
        """, (f"{prefix}%", user_id))
        rows = cursor.fetchall()
        cursor.execute(f"""
            SELECT date FROM {TABLE_SPRAY_LOG}
            WHERE date LIKE ? AND status = ? AND user_id = ?
        """, (f"{prefix}%", STATUS_DONE, user_id))
        done_rows = cursor.fetchall()
    report = {STATUS_DONE: 0, STATUS_POSTPONED: 0, STATUS_SKIPPED: 0}
    for row in rows:
        if row["status"] in report:
            report[row["status"]] = row["count"]
    weekly = {1: 0, 2: 0, 3: 0, 4: 0}
    for row in done_rows:
        try:
            day = int(row["date"].split("-")[2])
            weekly[min((day - 1) // 7 + 1, 4)] += 1
        except Exception:
            pass
    total = sum(report.values())
    compliance = round((report[STATUS_DONE] / total) * 100, 1) if total > 0 else 0.0
    return {
        "month":        f"{year}-{str(month).zfill(2)}",
        "year":         year,
        "month_number": month,
        "done":         report[STATUS_DONE],
        "postponed":    report[STATUS_POSTPONED],
        "skipped":      report[STATUS_SKIPPED],
        "total":        total,
        "compliance":   compliance,
        "weekly_trend": weekly,
    }


# ════════════════════════════════════════════════
# SETTINGS (per-user)
# ════════════════════════════════════════════════
def seed_settings(user_id: int) -> None:
    defaults = {
        "rain_risk_alert":       str(DEFAULT_RAIN_RISK_ALERT),
        "spray_window_alert":    str(DEFAULT_SPRAY_WINDOW_ALERT),
        "missed_spray_alert":    str(DEFAULT_MISSED_SPRAY_ALERT),
        "preferred_hours":       DEFAULT_PREFERRED_HOURS,
        "weather_refresh_hours": str(DEFAULT_WEATHER_REFRESH_HOURS),
        "language":              DEFAULT_LANGUAGE,
    }
    with get_db() as conn:
        cursor = conn.cursor()
        for key, value in defaults.items():
            cursor.execute(f"""
                INSERT OR IGNORE INTO {TABLE_SETTINGS} (user_id, key, value)
                VALUES (?, ?, ?)
            """, (user_id, key, value))


def get_all_settings(user_id: int) -> dict:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT key, value FROM {TABLE_SETTINGS} WHERE user_id = ?", (user_id,))
        rows = cursor.fetchall()
    settings = {row["key"]: row["value"] for row in rows}
    if not settings:
        seed_settings(user_id)
        return get_all_settings(user_id)
    return settings


def get_setting(key: str, user_id: int) -> Optional[str]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT value FROM {TABLE_SETTINGS} WHERE key = ? AND user_id = ?", (key, user_id))
        row = cursor.fetchone()
    return row["value"] if row else None


def update_setting(key: str, value: str, user_id: int) -> None:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(f"""
            INSERT INTO {TABLE_SETTINGS} (user_id, key, value, updated_at)
            VALUES (?, ?, ?, datetime('now'))
            ON CONFLICT(user_id, key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at
        """, (user_id, key, str(value)))


# ════════════════════════════════════════════════
# NOTIFICATIONS (per-user)
# ════════════════════════════════════════════════
def save_notification(notif_type: str, title: str, message: str, user_id: int) -> None:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(f"""
            INSERT INTO {TABLE_NOTIFICATIONS} (user_id, type, title, message)
            VALUES (?, ?, ?, ?)
        """, (user_id, notif_type, title, message))


def get_all_notifications(user_id: int) -> list:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM {TABLE_NOTIFICATIONS} WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
        rows = cursor.fetchall()
    return [dict(r) for r in rows]


def get_unread_notifications(user_id: int) -> list:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT * FROM {TABLE_NOTIFICATIONS}
            WHERE is_read = 0 AND user_id = ? ORDER BY created_at DESC
        """, (user_id,))
        rows = cursor.fetchall()
    return [dict(r) for r in rows]


def mark_notification_read(notif_id: int, user_id: int) -> bool:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(f"UPDATE {TABLE_NOTIFICATIONS} SET is_read = 1 WHERE id = ? AND user_id = ?", (notif_id, user_id))
        updated = cursor.rowcount > 0
    return updated


def mark_all_notifications_read(user_id: int) -> None:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(f"UPDATE {TABLE_NOTIFICATIONS} SET is_read = 1 WHERE user_id = ?", (user_id,))


def delete_notification(notif_id: int, user_id: int) -> bool:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(f"DELETE FROM {TABLE_NOTIFICATIONS} WHERE id = ? AND user_id = ?", (notif_id, user_id))
        deleted = cursor.rowcount > 0
    return deleted


def get_unread_count(user_id: int) -> int:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT COUNT(*) FROM {TABLE_NOTIFICATIONS} WHERE is_read = 0 AND user_id = ?", (user_id,))
        row = cursor.fetchone()
    return row[0] if row else 0


def notification_exists_today(setting_key: str, user_id: int) -> bool:
    today = date.today().strftime("%Y-%m-%d")
    last_value = get_setting(setting_key, user_id)
    return last_value == today


# ════════════════════════════════════════════════
# INIT
# ════════════════════════════════════════════════
def init_db() -> None:
    print("\n" + "=" * 50)
    print("  SMARTAGRO DATABASE — INITIALISING")
    print("=" * 50)
    create_tables()
    create_users_table()
    seed_spray_db()
    print(f"  [DB] Ready → {DB_PATH}")
    print("=" * 50 + "\n")