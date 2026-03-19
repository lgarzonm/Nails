import sqlite3
from contextlib import contextmanager
from datetime import datetime

DB_PATH = "nails.db"


@contextmanager
def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Create all tables and seed default provider + services if not present."""
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS providers (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT    NOT NULL,
                phone       TEXT,
                whatsapp_notify INTEGER DEFAULT 1,
                created_at  TEXT    DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS services (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                provider_id      INTEGER NOT NULL REFERENCES providers(id),
                name             TEXT    NOT NULL,
                duration_minutes INTEGER NOT NULL,
                is_active        INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS availability_rules (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                provider_id  INTEGER NOT NULL REFERENCES providers(id),
                day_of_week  INTEGER NOT NULL,  -- 0=Monday ... 6=Sunday
                start_time   TEXT    NOT NULL,   -- 'HH:MM'
                end_time     TEXT    NOT NULL,   -- 'HH:MM'
                is_active    INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS blocked_windows (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                provider_id INTEGER NOT NULL REFERENCES providers(id),
                date        TEXT    NOT NULL,  -- 'YYYY-MM-DD'
                start_time  TEXT    NOT NULL,  -- 'HH:MM'
                end_time    TEXT    NOT NULL,  -- 'HH:MM'
                reason      TEXT
            );

            CREATE TABLE IF NOT EXISTS bookings (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                provider_id       INTEGER NOT NULL REFERENCES providers(id),
                service_id        INTEGER NOT NULL REFERENCES services(id),
                client_name       TEXT    NOT NULL,
                client_phone      TEXT    NOT NULL,
                requested_datetime TEXT   NOT NULL,  -- ISO format 'YYYY-MM-DD HH:MM'
                duration_minutes  INTEGER NOT NULL,
                status            TEXT    DEFAULT 'pending',  -- pending | confirmed | rejected
                notes             TEXT,
                created_at        TEXT    DEFAULT (datetime('now'))
            );
        """)

        # Seed default provider (Diana) if not exists
        row = conn.execute("SELECT id FROM providers WHERE id = 1").fetchone()
        if not row:
            conn.execute(
                "INSERT INTO providers (id, name, phone, whatsapp_notify) VALUES (1, 'Diana', NULL, 1)"
            )

        # Seed default services if none exist
        count = conn.execute(
            "SELECT COUNT(*) FROM services WHERE provider_id = 1"
        ).fetchone()[0]
        if count == 0:
            conn.executemany(
                "INSERT INTO services (provider_id, name, duration_minutes, is_active) VALUES (?, ?, ?, 1)",
                [
                    (1, "Manicure", 60),
                    (1, "Pedicure", 60),
                    (1, "Manicure + Pedicure", 120),
                ],
            )


# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------

def get_active_services(provider_id: int) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, name, duration_minutes FROM services WHERE provider_id = ? AND is_active = 1",
            (provider_id,),
        ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Availability rules
# ---------------------------------------------------------------------------

def get_availability_rules(provider_id: int) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT id, day_of_week, start_time, end_time, is_active
               FROM availability_rules
               WHERE provider_id = ?
               ORDER BY day_of_week, start_time""",
            (provider_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def upsert_availability_rule(provider_id: int, day_of_week: int, start_time: str, end_time: str) -> int:
    """Insert or replace a rule for a given day. Returns the rule id."""
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM availability_rules WHERE provider_id = ? AND day_of_week = ?",
            (provider_id, day_of_week),
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE availability_rules SET start_time = ?, end_time = ?, is_active = 1 WHERE id = ?",
                (start_time, end_time, existing["id"]),
            )
            return existing["id"]
        else:
            cur = conn.execute(
                "INSERT INTO availability_rules (provider_id, day_of_week, start_time, end_time) VALUES (?, ?, ?, ?)",
                (provider_id, day_of_week, start_time, end_time),
            )
            return cur.lastrowid


def deactivate_availability_rule(rule_id: int):
    with get_connection() as conn:
        conn.execute(
            "UPDATE availability_rules SET is_active = 0 WHERE id = ?", (rule_id,)
        )


# ---------------------------------------------------------------------------
# Blocked windows
# ---------------------------------------------------------------------------

def get_blocked_windows(provider_id: int, date: str) -> list[dict]:
    """Return blocked windows for a specific date (YYYY-MM-DD)."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, start_time, end_time, reason FROM blocked_windows WHERE provider_id = ? AND date = ?",
            (provider_id, date),
        ).fetchall()
    return [dict(r) for r in rows]


def get_all_blocked_windows(provider_id: int) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT id, date, start_time, end_time, reason
               FROM blocked_windows
               WHERE provider_id = ?
               ORDER BY date, start_time""",
            (provider_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def add_blocked_window(provider_id: int, date: str, start_time: str, end_time: str, reason: str = "") -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO blocked_windows (provider_id, date, start_time, end_time, reason) VALUES (?, ?, ?, ?, ?)",
            (provider_id, date, start_time, end_time, reason),
        )
        return cur.lastrowid


def delete_blocked_window(window_id: int):
    with get_connection() as conn:
        conn.execute("DELETE FROM blocked_windows WHERE id = ?", (window_id,))


# ---------------------------------------------------------------------------
# Bookings
# ---------------------------------------------------------------------------

def create_booking(
    provider_id: int,
    service_id: int,
    client_name: str,
    client_phone: str,
    requested_datetime: str,
    duration_minutes: int,
    notes: str = "",
) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO bookings
               (provider_id, service_id, client_name, client_phone,
                requested_datetime, duration_minutes, status, notes)
               VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)""",
            (provider_id, service_id, client_name, client_phone,
             requested_datetime, duration_minutes, notes),
        )
        return cur.lastrowid


def get_busy_slots(provider_id: int, date: str) -> list[dict]:
    """
    Return only (requested_datetime, duration_minutes, status) for bookings on
    the given date with status pending or confirmed. Never exposes client PII.
    """
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT requested_datetime, duration_minutes, status
               FROM bookings
               WHERE provider_id = ?
                 AND date(requested_datetime) = ?
                 AND status IN ('pending', 'confirmed')""",
            (provider_id, date),
        ).fetchall()
    return [dict(r) for r in rows]


def get_pending_bookings(provider_id: int) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT b.id, b.client_name, b.client_phone, b.requested_datetime,
                      b.duration_minutes, b.notes, b.created_at,
                      s.name AS service_name
               FROM bookings b
               JOIN services s ON s.id = b.service_id
               WHERE b.provider_id = ? AND b.status = 'pending'
               ORDER BY b.requested_datetime""",
            (provider_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_confirmed_bookings(provider_id: int) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT b.id, b.client_name, b.client_phone, b.requested_datetime,
                      b.duration_minutes, b.notes,
                      s.name AS service_name
               FROM bookings b
               JOIN services s ON s.id = b.service_id
               WHERE b.provider_id = ? AND b.status = 'confirmed'
                 AND date(b.requested_datetime) >= date('now')
               ORDER BY b.requested_datetime""",
            (provider_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def update_booking_status(booking_id: int, status: str):
    """status must be 'confirmed' or 'rejected'."""
    assert status in ("confirmed", "rejected"), "Invalid status"
    with get_connection() as conn:
        conn.execute(
            "UPDATE bookings SET status = ? WHERE id = ?", (status, booking_id)
        )
