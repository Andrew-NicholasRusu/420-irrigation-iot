"""Fill the laptop database with dummy history so Chart.js and Grafana have data right away.

    docker compose run --rm subscriber python seed_history.py --hours 24
    docker compose run --rm subscriber python seed_history.py --hours 24 --device pi5-demo --every 60

Readings are written with device 'pi5-demo' by default so you can tell them apart
(or delete them later: DELETE FROM sensor_readings WHERE device = 'pi5-demo').
"""
import argparse
import uuid
from contextlib import closing
from datetime import datetime, timedelta, timezone

from db import get_connection, init_db
from dummy_sensors import DummyIrrigationSensors
from subscriber import INSERT_SQL


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=24)
    ap.add_argument("--every", type=int, default=60, help="seconds between readings")
    ap.add_argument("--device", default="pi5-demo")
    args = ap.parse_args()

    init_db()
    sensors = DummyIrrigationSensors(seed=42)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    start = now - timedelta(hours=args.hours)
    rows = []
    t = start
    while t <= now:
        reading = sensors.read(t.astimezone())          # local time drives the daily pattern
        stamp = t.strftime("%Y-%m-%d %H:%M:%S")
        rows.append({"msg_id": f"seed-{uuid.uuid4()}", "device": args.device,
                     "collected_at": stamp, "received_at": stamp, **reading})
        t += timedelta(seconds=args.every)

    with closing(get_connection()) as conn:
        with conn:
            conn.executemany(INSERT_SQL, rows)
    print(f"Inserted {len(rows)} readings for {args.device} from {start} to {now} UTC")


if __name__ == "__main__":
    main()
