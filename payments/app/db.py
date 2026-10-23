import os
import sqlite3
from typing import Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS students (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    phone       TEXT    NOT NULL,
    group_name  TEXT    NOT NULL,
    monthly_fee INTEGER NOT NULL CHECK (monthly_fee >= 0)
);
CREATE TABLE IF NOT EXISTS payments (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    amount     INTEGER NOT NULL CHECK (amount > 0),
    paid_at    TEXT    NOT NULL  -- ISO date YYYY-MM-DD
);
CREATE INDEX IF NOT EXISTS idx_payments_student_date ON payments(student_id, paid_at);
"""


def db_path() -> str:
    return os.environ.get("DB_PATH", "payments.db")


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    conn = connect()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def get_db() -> Iterator[sqlite3.Connection]:
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()
