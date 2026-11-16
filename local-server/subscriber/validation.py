"""Validate one MQTT reading before it is stored. No MQTT code here, so it is easy to test."""
import json
import re
from datetime import datetime, timedelta, timezone

DEVICE_RE = re.compile(r"[a-z0-9-]{1,32}")

# field -> (min, max) accepted range
RANGES = {
    "temperature": (-40.0, 85.0),      # °C, DHT22 range
    "humidity": (0.0, 100.0),          # %
    "water_pressure": (0.0, 1000.0),   # kPa
}


class InvalidReading(ValueError):
    pass


def parse_reading(raw, now=None):
    """Return a clean dict ready for INSERT, or raise InvalidReading."""
    now = now or datetime.now(timezone.utc)
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise InvalidReading("not valid JSON")
    if not isinstance(data, dict):
        raise InvalidReading("payload must be a JSON object")

    msg_id = data.get("msg_id")
    if not isinstance(msg_id, str) or not 1 <= len(msg_id) <= 64:
        raise InvalidReading("missing or bad msg_id")

    device = data.get("device")
    if not isinstance(device, str) or not DEVICE_RE.fullmatch(device):
        raise InvalidReading("missing or bad device")

    try:
        collected = datetime.fromisoformat(str(data.get("collected_at")).replace("Z", "+00:00"))
    except ValueError:
        raise InvalidReading("bad collected_at")
    if collected.tzinfo is None:
        raise InvalidReading("collected_at must include a time zone (use ...Z for UTC)")
    collected = collected.astimezone(timezone.utc)
    if collected > now + timedelta(minutes=5):
        raise InvalidReading("collected_at is in the future (check the Pi's clock)")

    clean = {
        "msg_id": msg_id,
        "device": device,
        "collected_at": collected.strftime("%Y-%m-%d %H:%M:%S"),
        "received_at": now.strftime("%Y-%m-%d %H:%M:%S"),
    }
    present = 0
    for field, (low, high) in RANGES.items():
        value = data.get(field)
        if value is None:
            clean[field] = None                 # missing reading stays missing
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise InvalidReading(f"{field} must be a number")
        if not low <= value <= high:
            raise InvalidReading(f"{field}={value} outside {low}..{high}")
        clean[field] = float(value)
        present += 1
    if present == 0:
        raise InvalidReading("no sensor values")
    return clean
