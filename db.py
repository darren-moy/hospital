import sqlite3
from pathlib import Path

DB_PATH = "hospital.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_connection() as conn:
        conn.executescript(SCHEMA_PATH.read_text())

if __name__ == "__main__":
    init_db()
    print("Database ready.")

    