"""Flask dashboard: latest values, Chart.js history and recent readings.

All data comes from SQLite (written by the subscriber). Times are stored in
UTC; the browser converts them to local time.
"""
import os
from contextlib import closing

from flask import Flask, jsonify, render_template, request

from db import get_connection, init_db

GRAFANA_URL = os.getenv("GRAFANA_URL", "http://localhost:3000/d/irrigation")
BUFFERED_AFTER_SECONDS = 60     # delivered later than this = came from the Pi's buffer

app = Flask(__name__)
init_db()


def rows_to_dicts(rows):
    return [dict(r) for r in rows]


def selected_device():
    """?device=pi5-01 limits a query to one device; missing or empty = all devices."""
    return request.args.get("device") or None


@app.get("/api/devices")
def devices():
    with closing(get_connection()) as conn:
        rows = conn.execute(
            """SELECT r.device, COUNT(*) AS readings, MAX(r.collected_at) AS last_seen,
                      s.status
               FROM sensor_readings r LEFT JOIN device_status s ON s.device = r.device
               GROUP BY r.device ORDER BY r.device"""
        ).fetchall()
    return jsonify(devices=rows_to_dicts(rows))


@app.get("/")
def index():
    return render_template("index.html", grafana_url=GRAFANA_URL)


@app.get("/api/latest")
def latest():
    with closing(get_connection()) as conn:
        device = selected_device()
        reading = conn.execute(
            """SELECT device, collected_at, received_at, temperature, humidity, water_pressure
               FROM sensor_readings
               WHERE (:device IS NULL OR device = :device)
               ORDER BY collected_at DESC, id DESC LIMIT 1""",
            {"device": device},
        ).fetchone()
        devices = conn.execute(
            """SELECT device, status, updated_at FROM device_status
               WHERE (:device IS NULL OR device = :device) ORDER BY device""",
            {"device": device},
        ).fetchall()
        pending_like = conn.execute(
            """SELECT COUNT(*) FROM sensor_readings
               WHERE received_at >= datetime('now', '-1 hour')
                 AND (:device IS NULL OR device = :device)
                 AND strftime('%s', received_at) - strftime('%s', collected_at) > :late""",
            {"device": device, "late": BUFFERED_AFTER_SECONDS},
        ).fetchone()[0]
    return jsonify(reading=dict(reading) if reading else None,
                   devices=rows_to_dicts(devices),
                   buffered_last_hour=pending_like)


@app.get("/api/history")
def history():
    """?minutes=60 (1..1440)&device=pi5-01 (optional). Averaged into ~300 buckets;
    with no device, all devices are averaged together."""
    minutes = request.args.get("minutes", default=60, type=int)
    minutes = max(1, min(minutes, 1440))
    bucket = max(1, minutes * 60 // 300)          # seconds per point
    with closing(get_connection()) as conn:
        rows = conn.execute(
            """SELECT datetime(CAST(strftime('%s', collected_at) AS INTEGER) / :b * :b,
                               'unixepoch') AS collected_at,
                      ROUND(AVG(temperature), 2)    AS temperature,
                      ROUND(AVG(humidity), 2)       AS humidity,
                      ROUND(AVG(water_pressure), 2) AS water_pressure,
                      MAX(strftime('%s', received_at) - strftime('%s', collected_at)) AS delay_s
               FROM sensor_readings
               WHERE collected_at >= datetime('now', :since)
                 AND (:device IS NULL OR device = :device)
               GROUP BY 1
               ORDER BY 1""",
            {"b": bucket, "since": f"-{minutes} minutes", "device": selected_device()},
        ).fetchall()
    return jsonify(minutes=minutes, bucket_seconds=bucket, device=selected_device(),
                   readings=rows_to_dicts(rows))


@app.get("/api/recent")
def recent():
    limit = max(1, min(request.args.get("limit", default=10, type=int), 100))
    with closing(get_connection()) as conn:
        rows = conn.execute(
            """SELECT id, device, collected_at, received_at, temperature, humidity, water_pressure,
                      strftime('%s', received_at) - strftime('%s', collected_at) AS delay_s
               FROM sensor_readings
               WHERE (:device IS NULL OR device = :device)
               ORDER BY collected_at DESC, id DESC LIMIT :limit""",
            {"device": selected_device(), "limit": limit},
        ).fetchall()
    return jsonify(readings=rows_to_dicts(rows), buffered_after_s=BUFFERED_AFTER_SECONDS)


@app.get("/health")
def health():
    return {"ok": True}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
