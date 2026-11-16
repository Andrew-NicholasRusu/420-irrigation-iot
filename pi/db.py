"""Local SQLite buffer ("outbox") on the Raspberry Pi.

Every reading is saved here FIRST, then forwarded to MQTT.
- sent_at IS NULL  -> still waiting to be delivered
- sent_at has text -> the broker acknowledged it (QoS 1 PUBACK)

Because the reading is on disk before we try to send it, nothing is lost
if the network, the broker or even the Pi's power goes down mid-send.
"""
import os
import sqlite3
from contextlib import closing

DB_PATH = os.getenv("PI_DB_PATH", "pi_buffer.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS outbox (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    msg_id       TEXT NOT NULL UNIQUE,   -- lets the laptop ignore duplicates
    collected_at TEXT NOT NULL,          -- ISO 8601 UTC, e.g. 2026-11-12T14:05:00Z
    payload      TEXT NOT NULL,          -- the exact JSON sent over MQTT
    sent_at      TEXT                    -- 'YYYY-MM-DD HH:MM:SS' UTC, NULL = pending
);
CREATE INDEX IF NOT EXISTS idx_outbox_pending ON outbox (sent_at, id);
"""


def get_connection(path=DB_PATH):
    conn = sqlite3.connect(path, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(conn):
    conn.executescript(SCHEMA)


def add_reading(conn, msg_id, collected_at, payload):
    with conn:
        conn.execute(
            "INSERT INTO outbox (msg_id, collected_at, payload) VALUES (?, ?, ?)",
            (msg_id, collected_at, payload),
        )


def get_pending(conn, limit):
    """Oldest unsent readings first, so the laptop receives them in order."""
    return conn.execute(
        "SELECT id, msg_id, payload FROM outbox WHERE sent_at IS NULL ORDER BY id LIMIT ?",
        (limit,),
    ).fetchall()


def mark_sent(conn, ids):
    if not ids:
        return
    with conn:
        conn.executemany(
            "UPDATE outbox SET sent_at = datetime('now') WHERE id = ?",
            [(i,) for i in ids],
        )


def count_pending(conn):
    return conn.execute("SELECT COUNT(*) FROM outbox WHERE sent_at IS NULL").fetchone()[0]


def purge_sent(conn, keep_days):
    """Delete delivered readings older than keep_days. Pending rows are never deleted."""
    with conn:
        cur = conn.execute(
            "DELETE FROM outbox WHERE sent_at IS NOT NULL AND sent_at < datetime('now', ?)",
            (f"-{int(keep_days)} days",),
        )
    return cur.rowcount


if __name__ == "__main__":
    # Quick check: python db.py
    with closing(get_connection()) as conn:
        init_db(conn)
        with conn:
            for pragma in ("journal_mode", "synchronous", "foreign_keys"):
                print(pragma, "=", conn.execute(f"PRAGMA {pragma}").fetchone()[0])
        print("pending =", count_pending(conn))
