"""Dummy irrigation sensors (same file as pi/sensors.py, used by seed_history.py).

The values follow a daily pattern with noise so the charts look realistic:
- temperature rises in the afternoon and drops at night
- humidity moves the opposite way
- water pressure drops while the irrigation valve is open
  (3 minutes out of every 15, so you see it quickly in class)
- now and then the humidity sensor fails and returns None, like a real DHT

Replace DummyIrrigationSensors.read() with real sensor code later.
The rest of the program does not change.
"""
import math
import random
from datetime import datetime


class DummyIrrigationSensors:
    def __init__(self, seed=None):
        self.rng = random.Random(seed)

    def read(self, when=None):
        """Return one reading as a dict. `when` is a local datetime (default: now)."""
        when = when or datetime.now()
        hour = when.hour + when.minute / 60
        day_wave = math.sin((hour - 9) / 24 * 2 * math.pi)  # peak mid-afternoon

        temperature = 21 + 6 * day_wave + self.rng.gauss(0, 0.3)
        humidity = 60 - 15 * day_wave + self.rng.gauss(0, 1.5)
        humidity = min(max(humidity, 20), 95)

        valve_open = when.minute % 15 < 3
        if valve_open:
            water_pressure = 215 + self.rng.gauss(0, 6)   # kPa, water flowing
        else:
            water_pressure = 310 + self.rng.gauss(0, 4)   # kPa, line at rest

        if self.rng.random() < 0.02:     # 2 % of reads: humidity sensor failure
            humidity = None

        return {
            "temperature": round(temperature, 1),
            "humidity": None if humidity is None else round(humidity, 1),
            "water_pressure": round(water_pressure, 1),
        }


if __name__ == "__main__":
    sensors = DummyIrrigationSensors()
    for _ in range(5):
        print(sensors.read())
