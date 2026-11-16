"""Raspberry Pi irrigation sensor node with store-and-forward.

Run (inside the virtual environment):
    MQTT_HOST=192.168.1.50 DEVICE_ID=pi5-01 python node.py

Every SAMPLE_SECONDS:
  1. read the 3 sensors (dummy values for now)
  2. save the reading in the local SQLite outbox (pi_buffer.db)
  3. forward every pending reading to MQTT, oldest first, QoS 1
  4. mark a reading as sent only after the broker acknowledges it

If nothing could be delivered for OFFLINE_AFTER_SECONDS (default 60 s), the
node reports that it is OFFLINE and keeps buffering. When the broker is back,
the backlog is forwarded with the ORIGINAL collection times, so the charts on
the laptop have no gap.
"""
import json
import logging
import os
import signal
import time
import uuid
from contextlib import closing
from datetime import datetime, timezone

import db
from sensors import DummyIrrigationSensors

# ---------------------------------------------------------------- settings --
DEVICE_ID = os.getenv("DEVICE_ID", "pi5-01")
MQTT_HOST = os.getenv("MQTT_HOST", "192.168.1.50")      # your laptop's IP address
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
SAMPLE_SECONDS = float(os.getenv("SAMPLE_SECONDS", "5"))
OFFLINE_AFTER_SECONDS = float(os.getenv("OFFLINE_AFTER_SECONDS", "60"))
PUBLISH_TIMEOUT_SECONDS = float(os.getenv("PUBLISH_TIMEOUT_SECONDS", "5"))
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "50"))
KEEP_SENT_DAYS = int(os.getenv("KEEP_SENT_DAYS", "7"))

READINGS_TOPIC = f"irrigation/{DEVICE_ID}/readings"
STATUS_TOPIC = f"irrigation/{DEVICE_ID}/status"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("node")


def utc_now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_message(reading, collected_at):
    """Return (msg_id, JSON payload). msg_id lets the laptop drop duplicates."""
    msg_id = str(uuid.uuid4())
    payload = json.dumps({
        "msg_id": msg_id,
        "device": DEVICE_ID,
        "collected_at": collected_at,
        **reading,
    })
    return msg_id, payload


class Forwarder:
    """Sends pending outbox rows to the broker and tracks online/offline state."""

    def __init__(self, client, conn, topic, clock=time.monotonic):
        self.client = client
        self.conn = conn
        self.topic = topic
        self.clock = clock
        self.last_success = clock()
        self.offline = False

    def flush(self):
        """Forward pending readings. Returns how many the broker acknowledged."""
        if not self.client.is_connected():
            return 0
        sent_ids = []
        for row in db.get_pending(self.conn, BATCH_SIZE):
            info = self.client.publish(self.topic, row["payload"], qos=1)
            try:
                info.wait_for_publish(timeout=PUBLISH_TIMEOUT_SECONDS)
            except (RuntimeError, ValueError):
                break                      # connection dropped: try again later
            if not info.is_published():
                break                      # no PUBACK in time: keep it pending
            sent_ids.append(row["id"])
        db.mark_sent(self.conn, sent_ids)
        if sent_ids:
            self.last_success = self.clock()
        return len(sent_ids)

    def update_state(self, sent_now):
        """Log once when we go offline (>= OFFLINE_AFTER_SECONDS) and once when we recover."""
        pending = db.count_pending(self.conn)
        silent_for = self.clock() - self.last_success
        if not self.offline and pending and silent_for >= OFFLINE_AFTER_SECONDS:
            self.offline = True
            log.warning("OFFLINE for %.0f s: buffering readings on the Pi (%d pending)",
                        silent_for, pending)
        elif self.offline and sent_now:
            self.offline = False
            log.info("ONLINE again: forwarding backlog (%d still pending)", pending)
        return pending


def make_mqtt_client():
    import paho.mqtt.client as mqtt   # imported here so the module can be tested without paho

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"{DEVICE_ID}-node")
    # If the Pi disappears, the broker publishes this for us (Last Will).
    client.will_set(STATUS_TOPIC, "offline", qos=1, retain=True)

    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            log.error("MQTT connect failed: %s", reason_code)
            return
        log.info("Connected to MQTT broker %s:%s", MQTT_HOST, MQTT_PORT)
        client.publish(STATUS_TOPIC, "online", qos=1, retain=True)

    def on_disconnect(client, userdata, flags, reason_code, properties):
        log.warning("Disconnected from MQTT broker (%s); will retry", reason_code)

    def on_connect_fail(client, userdata):
        log.warning("Cannot reach MQTT broker %s:%s, retrying (readings stay buffered)", MQTT_HOST, MQTT_PORT)

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_connect_fail = on_connect_fail
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    client.connect_async(MQTT_HOST, MQTT_PORT, keepalive=30)
    client.loop_start()               # background thread: network I/O + automatic reconnect
    return client


def main():
    sensors = DummyIrrigationSensors()
    client = make_mqtt_client()
    running = True

    def stop(*_):
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    with closing(db.get_connection()) as conn:
        db.init_db(conn)
        log.info("Device %s, buffer %s, %d readings pending from last run",
                 DEVICE_ID, db.DB_PATH, db.count_pending(conn))
        forwarder = Forwarder(client, conn, READINGS_TOPIC)
        next_sample = time.monotonic()
        next_purge = time.monotonic() + 3600

        while running:
            now = time.monotonic()
            if now >= next_sample:
                collected_at = utc_now_iso()
                reading = sensors.read()
                msg_id, payload = build_message(reading, collected_at)
                db.add_reading(conn, msg_id, collected_at, payload)
                log.info("Read %s %s", collected_at, reading)
                next_sample += SAMPLE_SECONDS

            sent = forwarder.flush()
            pending = forwarder.update_state(sent)

            if now >= next_purge:
                removed = db.purge_sent(conn, KEEP_SENT_DAYS)
                log.info("Purged %d delivered readings older than %d days", removed, KEEP_SENT_DAYS)
                next_purge = now + 3600

            # backlog left and connected: keep sending quickly; otherwise rest a bit
            time.sleep(0.05 if pending and client.is_connected() else 0.5)

    log.info("Stopping")
    client.publish(STATUS_TOPIC, "offline", qos=1, retain=True)
    client.loop_stop()
    client.disconnect()


if __name__ == "__main__":
    main()
