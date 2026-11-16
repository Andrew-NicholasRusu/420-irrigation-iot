"""MQTT subscriber: validates readings from the Pi(s) and stores them in SQLite.

Topics:
  irrigation/<device>/readings   JSON reading (QoS 1)
  irrigation/<device>/status     'online' / 'offline' (retained, Last Will)

clean_session=False + QoS 1: if this container restarts, Mosquitto keeps the
messages for us and delivers them when we reconnect.
"""
import logging
import os
from contextlib import closing
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

from db import get_connection, init_db
from validation import InvalidReading, parse_reading

MQTT_HOST = os.getenv("MQTT_HOST", "mosquitto")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
CLIENT_ID = os.getenv("MQTT_CLIENT_ID", "laptop-subscriber")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("subscriber")

INSERT_SQL = """
INSERT OR IGNORE INTO sensor_readings
    (msg_id, device, collected_at, received_at, temperature, humidity, water_pressure)
VALUES (:msg_id, :device, :collected_at, :received_at, :temperature, :humidity, :water_pressure)
"""


def store_reading(conn, raw):
    """Validate and insert. Returns 'stored', 'duplicate' or 'rejected: <reason>'."""
    try:
        reading = parse_reading(raw)
    except InvalidReading as err:
        return f"rejected: {err}"
    with conn:
        cur = conn.execute(INSERT_SQL, reading)
    return "stored" if cur.rowcount == 1 else "duplicate"


def store_status(conn, device, status):
    if status not in ("online", "offline"):
        return
    with conn:
        conn.execute(
            """INSERT INTO device_status (device, status, updated_at) VALUES (?, ?, ?)
               ON CONFLICT(device) DO UPDATE SET status = excluded.status,
                                                 updated_at = excluded.updated_at""",
            (device, status, datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")),
        )


def main():
    init_db()
    conn = get_connection()
    log.info("Database ready at %s, connecting to %s:%s", os.getenv("DB_PATH", "/data/irrigation.db"), MQTT_HOST, MQTT_PORT)

    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            log.error("Connect failed: %s", reason_code)
            return
        log.info("Connected to %s:%s", MQTT_HOST, MQTT_PORT)
        client.subscribe([("irrigation/+/readings", 1), ("irrigation/+/status", 1)])

    def on_message(client, userdata, msg):
        parts = msg.topic.split("/")
        if len(parts) != 3:
            return
        _, device, kind = parts
        if kind == "readings":
            result = store_reading(conn, msg.payload)
            level = logging.WARNING if result.startswith("rejected") else logging.INFO
            log.log(level, "%s %s", device, result)
        elif kind == "status":
            store_status(conn, device, msg.payload.decode(errors="replace"))
            log.info("%s is %s", device, msg.payload.decode(errors="replace"))

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=CLIENT_ID, clean_session=False)
    def on_connect_fail(client, userdata):
        log.warning("Cannot reach MQTT broker %s:%s, retrying", MQTT_HOST, MQTT_PORT)

    def on_disconnect(client, userdata, flags, reason_code, properties):
        log.warning("Disconnected from broker (%s), retrying", reason_code)

    client.on_connect = on_connect
    client.on_connect_fail = on_connect_fail
    client.on_disconnect = on_disconnect
    client.on_message = on_message
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    client.connect_async(MQTT_HOST, MQTT_PORT, keepalive=30)
    try:
        client.loop_forever(retry_first_connection=True)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
