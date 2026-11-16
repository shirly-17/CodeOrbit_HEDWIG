import sqlite3
import os


DB_PATH = os.path.join(
    os.path.dirname(__file__),
    "history.db"
)


def initialize_database():
    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS command_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    connection.commit()
    connection.close()


def save_history(role, message):
    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT INTO command_history (role, message)
        VALUES (?, ?)
        """,
        (role, message)
    )

    connection.commit()
    connection.close()


def get_history():
    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()

    cursor.execute("""
        SELECT role, message, created_at
        FROM command_history
        ORDER BY id ASC
    """)

    records = cursor.fetchall()
    connection.close()

    return records


def clear_history():
    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()

    cursor.execute("DELETE FROM command_history")

    connection.commit()
    connection.close()