"""Connection check: run inside a container (or on the Pi) to see where MQTT breaks.

    docker compose cp ..\\pi\\diag.py pi-sim:/app/diag.py
    docker compose exec pi-sim python diag.py
"""
import os
import socket
import sqlite3
import time
from importlib.metadata import version

HOST = os.getenv("MQTT_HOST", "mosquitto")
PORT = int(os.getenv("MQTT_PORT", "1883"))


def step(n, text):
    print(f"\n[{n}] {text}")


step(1, "paho-mqtt version")
print("   ", version("paho-mqtt"))

step(2, f"DNS lookup of '{HOST}'")
try:
    addrs = sorted({a[4][0] for a in socket.getaddrinfo(HOST, PORT, proto=socket.IPPROTO_TCP)})
    print("    OK ->", addrs)
except OSError as e:
    print("    FAILED:", e)
    raise SystemExit("    => MQTT_HOST is wrong or the containers are not on the same network")

step(3, f"TCP connect to {HOST}:{PORT}")
try:
    socket.create_connection((HOST, PORT), timeout=3).close()
    print("    OK")
except OSError as e:
    print("    FAILED:", e)
    raise SystemExit("    => broker not listening / not reachable on this port")

step(4, "MQTT connect, subscribe irrigation/#, publish a test message")
import paho.mqtt.client as mqtt

got = []
result = {}
c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"diag-{os.getpid()}")
c.on_connect = lambda cl, u, f, rc, p: result.update(rc=str(rc)) or cl.subscribe("irrigation/#", 1)
c.on_message = lambda cl, u, m: got.append(m.topic)
c.connect(HOST, PORT, 10)
c.loop_start()
for _ in range(30):
    if "rc" in result:
        break
    time.sleep(0.1)
print("    connect result:", result.get("rc", "NO ANSWER"))
time.sleep(0.5)
c.publish("irrigation/diag/readings", "test", qos=1).wait_for_publish(3)
time.sleep(6)                               # also catches real readings for a few seconds
c.loop_stop()
c.disconnect()
print(f"    messages seen on irrigation/#: {len(got)}")
for t in sorted(set(got)):
    print("     -", t, "x", got.count(t))

step(5, "Pi buffer (pi-sim only)")
path = os.getenv("PI_DB_PATH")
if path and os.path.exists(path):
    conn = sqlite3.connect(path)
    print("    pending:", conn.execute("SELECT COUNT(*) FROM outbox WHERE sent_at IS NULL").fetchone()[0],
          " sent:", conn.execute("SELECT COUNT(*) FROM outbox WHERE sent_at IS NOT NULL").fetchone()[0])
else:
    print("    (no PI_DB_PATH here)")
