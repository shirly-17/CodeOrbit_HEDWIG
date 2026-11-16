import sqlite3
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).resolve().parent / "reminders.db"


def _connect():
    connection = sqlite3.connect(DB_PATH)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message TEXT NOT NULL,
            due_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL
        )
    """)
    connection.commit()
    return connection


def create_reminder(message, due_at):
    with _connect() as connection:
        cursor = connection.execute(
            "INSERT INTO reminders (message, due_at, status, created_at) "
            "VALUES (?, ?, 'pending', ?)",
            (message, due_at.isoformat(timespec="seconds"),
             datetime.now().isoformat(timespec="seconds"))
        )
        return cursor.lastrowid


def delete_reminder(reminder_id):
    with _connect() as connection:
        cursor = connection.execute(
            "DELETE FROM reminders WHERE id=? AND status='pending'",
            (reminder_id,)
        )
        return cursor.rowcount > 0


def get_reminder(reminder_id):
    with _connect() as connection:
        row = connection.execute(
            "SELECT id, message, due_at, status FROM reminders WHERE id=?",
            (reminder_id,)
        ).fetchone()
    return row


def list_pending_reminders():
    with _connect() as connection:
        rows = connection.execute(
            "SELECT id, message, due_at FROM reminders "
            "WHERE status='pending' ORDER BY due_at"
        ).fetchall()
    return rows


def mark_reminder_done(reminder_id):
    with _connect() as connection:
        connection.execute(
            "UPDATE reminders SET status='done' WHERE id=?",
            (reminder_id,)
        )


def remove_reminder_record(reminder_id):
    with _connect() as connection:
        connection.execute("DELETE FROM reminders WHERE id=?", (reminder_id,))
