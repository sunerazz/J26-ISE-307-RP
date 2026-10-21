"""Lookup station feature snapshots for live 'check now' predictions."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

from src.config import PROJECT_ROOT, STATION_COL, TIMESTAMP_COL
from src.prepare_waiting_time_data import waiting_feature_columns

logger = logging.getLogger("api.station_data")

SNAPSHOT_PATHS = [
    PROJECT_ROOT / "data" / "processed" / "waiting_time" / "modelling_table.csv",
    PROJECT_ROOT / "data" / "processed" / "waiting_time" / "test.csv",
]


@lru_cache(maxsize=1)
def load_station_snapshots() -> pd.DataFrame:
    path = next((p for p in SNAPSHOT_PATHS if p.exists()), None)
    if path is None:
        raise FileNotFoundError(
            "No processed waiting-time table found. Run: python -m src.prepare_waiting_time_data"
        )
    df = pd.read_csv(path, parse_dates=[TIMESTAMP_COL])
    missing = [c for c in waiting_feature_columns() if c not in df.columns]
    if missing:
        raise ValueError(f"Snapshot table missing required features: {missing}")
    logger.info("Loaded station snapshots from %s (%s rows)", path, len(df))
    return df


def list_stations() -> list[dict[str, Any]]:
    df = load_station_snapshots()
    rows = []
    for sid, g in df.groupby(STATION_COL):
        rows.append(
            {
                "station_id": str(sid),
                "location_type": str(g["location_type"].iloc[0]),
                "n_snapshots": int(len(g)),
                "first_timestamp": g[TIMESTAMP_COL].min().isoformat(sep=" "),
                "last_timestamp": g[TIMESTAMP_COL].max().isoformat(sep=" "),
            }
        )
    return sorted(rows, key=lambda r: r["station_id"])


def _round_to_quarter(dt: datetime) -> datetime:
    """Round to the nearest 15-minute slot, carrying into the next hour or day."""
    base = dt.replace(minute=0, second=0, microsecond=0)
    quarters = round((dt.minute + dt.second / 60) / 15)
    return base + timedelta(minutes=15 * quarters)


def _plain(value: Any) -> Any:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    return value.item() if hasattr(value, "item") else value


def _observation(row: pd.Series) -> dict[str, Any]:
    return {
        "timestamp": pd.Timestamp(row[TIMESTAMP_COL]).isoformat(sep=" "),
        "queue_length": _plain(row.get("current_queue_length")),
        "waiting_time_min": _plain(row.get("estimated_waiting_time_now_min")),
        "congestion_level": _plain(row.get("congestion_level_now")),
        "available_chargers": _plain(row.get("available_chargers")),
        "total_chargers": _plain(row.get("total_chargers")),
    }


REPORTS = PROJECT_ROOT / "reports"


@lru_cache(maxsize=1)
def _test_reports() -> dict[str, dict]:
    reports = {}
    for key, name in (
        ("queue", "test_metrics.json"),
        ("waiting_time", "waiting_time_test_metrics.json"),
        ("congestion", "congestion_test_metrics.json"),
    ):
        path = REPORTS / name
        reports[key] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    return reports


def station_error_profile(station_id: str) -> dict[str, Any]:
    """Held-out test error for this station, read from the saved evaluation reports."""
    reports = _test_reports()
    queue = (reports["queue"].get("by_station") or {}).get(station_id) or {}
    wait = (reports["waiting_time"].get("by_station") or {}).get(station_id) or {}
    congestion = (reports["congestion"].get("by_station") or {}).get(station_id) or {}
    return {
        "queue_mae_vehicles": queue.get("mae"),
        "waiting_time_mae_min": wait.get("mae_min"),
        "congestion_accuracy": congestion.get("accuracy"),
        "source": "test split (13-30 April 2025 synthetic dates), per station",
    }


def find_snapshot_for_station(
    station_id: str,
    when: datetime | None = None,
) -> dict[str, Any]:
    """Pick a historical/synthetic snapshot that matches the requested clock time.

    The training CSV covers 2025 simulated dates, so 'now' is mapped by
    day-of-week + hour + nearest 15-minute slot to the latest matching row.
    """
    df = load_station_snapshots()
    station = df[df[STATION_COL] == station_id]
    if station.empty:
        raise KeyError(f"Unknown station_id: {station_id}")

    when = when or datetime.now()
    slot = _round_to_quarter(when)
    hour, minute = slot.hour, slot.minute
    dow = slot.strftime("%A")

    candidates = station[
        (station["day_of_week"] == dow)
        & (station["hour"] == hour)
        & (station["minute"] == minute)
    ]
    match_note = "exact day_of_week+hour+minute"
    if candidates.empty:
        candidates = station[(station["hour"] == hour) & (station["minute"] == minute)]
        match_note = "hour+minute (any weekday)"
    if candidates.empty:
        candidates = station[station["hour"] == hour]
        match_note = "hour only (nearest later used)"
    if candidates.empty:
        candidates = station
        match_note = "latest available snapshot for station"

    row = candidates.sort_values(TIMESTAMP_COL).iloc[-1]
    payload: dict[str, Any] = {}
    for col in waiting_feature_columns():
        val = row[col]
        if hasattr(val, "item"):
            val = val.item()
        payload[col] = val
    payload["timestamp"] = pd.Timestamp(row[TIMESTAMP_COL]).isoformat(sep=" ")

    # What the synthetic history recorded 30 minutes later. Shown after the forecast
    # for comparison only; it is never a model input.
    later = station[station[TIMESTAMP_COL] == pd.Timestamp(row[TIMESTAMP_COL]) + pd.Timedelta(minutes=30)]
    recorded = _observation(later.iloc[0]) if not later.empty else None

    return {
        "station_id": station_id,
        "requested_local_time": when.isoformat(sep=" ", timespec="seconds"),
        "matched_snapshot_timestamp": payload["timestamp"],
        "match_rule": match_note,
        "matched_hour": int(row["hour"]),
        "matched_minute": int(row["minute"]),
        "matched_day_of_week": str(row["day_of_week"]),
        "location_type": str(row["location_type"]),
        "features": payload,
        "observed_now": _observation(row),
        "recorded_outcome_30min": recorded,
        "data_note": (
            "Predictions use a synthetic historical snapshot closest to the current "
            "clock pattern (day/hour/15-min slot), not a live IoT feed."
        ),
    }
