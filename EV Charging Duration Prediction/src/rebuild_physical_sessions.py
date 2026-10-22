"""Rebuild Component 2 sessions so the clock and the energy agree with the duration.

The place names, vehicles, and start times stay. Session length is generated as

    energy_kwh = battery_kwh * (end_soc - start_soc) / 100
    duration_hours = energy_kwh / charging_rate_kw
    end_time = start_time + duration_hours

So labelled duration equals end time minus start time, and energy equals rate times duration.
This is a generated table, not a meter log from the five chargers.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import RAW_DATA_PATH  # noqa: E402


def _time_of_day(hour: int) -> str:
    if 5 <= hour < 12:
        return "Morning"
    if 12 <= hour < 17:
        return "Afternoon"
    if 17 <= hour < 21:
        return "Evening"
    return "Night"


def rebuild(path: Path | None = None) -> pd.DataFrame:
    path = path or RAW_DATA_PATH
    frame = pd.read_csv(path)
    rate = pd.to_numeric(frame["Charging Rate (kW)"], errors="coerce")
    by_type = frame.assign(_rate=rate).groupby("Charger Type")["_rate"].median()
    missing_rate = rate.isna() | (rate <= 0)
    rate = rate.where(~missing_rate, frame["Charger Type"].map(by_type))
    if rate.isna().any() or (rate <= 0).any():
        raise ValueError("A charger type has no positive rate to fill missing power values.")

    battery = pd.to_numeric(frame["Battery Capacity (kWh)"], errors="coerce")
    battery = battery.where(battery > 0, battery[battery > 0].median())
    start = pd.to_numeric(frame["State of Charge (Start %)"], errors="coerce").clip(0, 100)
    end = pd.to_numeric(frame["State of Charge (End %)"], errors="coerce")
    usable_end = end.notna() & (end > start) & (end <= 100)
    end = end.where(usable_end, np.minimum(100, start + 25))
    start = start.where(start < end, end - 15)
    start = start.clip(lower=0)
    end = np.minimum(100, np.maximum(end, start + 1))

    energy = battery * (end - start) / 100.0
    hours = energy / rate
    if (hours <= 0).any() or energy.isna().any():
        raise ValueError("Rebuilt duration or energy is missing or not positive.")

    start_time = pd.to_datetime(frame["Charging Start Time"], errors="raise")
    end_time = start_time + pd.to_timedelta(hours, unit="h")
    frame["Battery Capacity (kWh)"] = battery
    frame["Charging Rate (kW)"] = rate
    frame["State of Charge (Start %)"] = start
    frame["State of Charge (End %)"] = end
    frame["Energy Consumed (kWh)"] = energy
    frame["Charging Duration (hours)"] = hours
    frame["Charging Duration (minutes)"] = hours * 60.0
    frame["Charging Start Time"] = start_time.dt.strftime("%Y-%m-%d %H:%M:%S")
    frame["Charging End Time"] = end_time.dt.strftime("%Y-%m-%d %H:%M:%S")
    frame["Time of Day"] = start_time.dt.hour.map(_time_of_day)
    frame["Day of Week"] = start_time.dt.day_name()
    tariff = pd.to_numeric(frame["Illustrative Tariff (LKR/kWh)"], errors="coerce").fillna(120.0)
    frame["Illustrative Tariff (LKR/kWh)"] = tariff
    frame["Illustrative Charging Cost (LKR)"] = energy * tariff
    frame.to_csv(path, index=False)

    clock_hours = (end_time - start_time).dt.total_seconds() / 3600.0
    print(
        {
            "rows": int(len(frame)),
            "clock_correlation": float(pd.Series(clock_hours).corr(hours)),
            "energy_correlation": float(energy.corr(rate * hours)),
            "soc_end_below_start": int((end < start).sum()),
            "missing_energy": int(energy.isna().sum()),
        }
    )
    return frame


if __name__ == "__main__":
    rebuild()
