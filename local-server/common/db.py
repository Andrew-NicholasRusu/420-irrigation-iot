"""Laptop-side SQLite database, shared by the subscriber, Flask and Grafana.

All three containers mount the same ./data folder, so they see one file:
    ./data/irrigation.db  (host)  ==  /data/irrigation.db  (containers)
"""
import os
import sqlite3
from contextlib import closing

DB_PATH = os.getenv("DB_PATH", "/data/irrigation.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS sensor_readings (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    msg_id         TEXT NOT NULL UNIQUE,   -- from the Pi; duplicates are ignored
    device         TEXT NOT NULL,
    collected_at   TEXT NOT NULL,          -- 'YYYY-MM-DD HH:MM:SS' UTC, time on the Pi
    received_at    TEXT NOT NULL,          -- 'YYYY-MM-DD HH:MM:SS' UTC, time stored here
    temperature    REAL,                   -- °C
    humidity       REAL,                   -- %
    water_pressure REAL                    -- kPa
);
CREATE INDEX IF NOT EXISTS idx_readings_time ON sensor_readings (collected_at);

CREATE TABLE IF NOT EXISTS device_status (
    device     TEXT PRIMARY KEY,
    status     TEXT NOT NULL,              -- 'online' or 'offline'
    updated_at TEXT NOT NULL               -- 'YYYY-MM-DD HH:MM:SS' UTC
);
"""


def get_connection(path=None):
    conn = sqlite3.connect(path or DB_PATH, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")      # readers never block the writer
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(path=None):
    with closing(get_connection(path)) as conn:
        conn.executescript(SCHEMA)
