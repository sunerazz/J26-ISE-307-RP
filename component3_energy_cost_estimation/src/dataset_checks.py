"""Locate the energy CSV and refuse a target that is not in the file."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.config import (
    DISCOVERED_ENERGY_PATH,
    DISCOVERED_LEGACY_PATH,
    ENERGY_COLUMN_CANDIDATES,
    ENERGY_DATA_PATH,
    LEGACY_DATA_PATH,
    TARGET_COL,
)


class EnergyTargetUnavailable(RuntimeError):
    """Raised when the CSV cannot support an energy-consumption model."""


def resolve_dataset_path() -> Path:
    for path in (ENERGY_DATA_PATH, DISCOVERED_ENERGY_PATH, LEGACY_DATA_PATH, DISCOVERED_LEGACY_PATH):
        if path.exists():
            return path
    raise FileNotFoundError(
        "No Component 3 CSV was found. Place component3_energy_consumption.csv at "
        f"{ENERGY_DATA_PATH}."
    )


def load_dataset(path: Path | None = None) -> tuple[pd.DataFrame, Path]:
    path = path or resolve_dataset_path()
    frame = pd.read_csv(path)
    return frame, path


def find_energy_column(columns: list[str]) -> str | None:
    lookup = {c.strip().lower(): c for c in columns}
    for candidate in ENERGY_COLUMN_CANDIDATES:
        if candidate.lower() in lookup:
            return lookup[candidate.lower()]
    for column in columns:
        lowered = column.lower()
        if "per_km" in lowered or "per km" in lowered:
            continue
        if "kwh" in lowered:
            return column
    return None


def inspect_frame(frame: pd.DataFrame, path: Path) -> dict:
    columns = [str(c) for c in frame.columns]
    energy_column = find_energy_column(columns)
    numeric = frame.select_dtypes(include="number")
    start = "soc_start_pct" in frame.columns
    end = "soc_end_pct" in frame.columns
    report = {
        "path": str(path),
        "n_rows": int(len(frame)),
        "n_columns": int(frame.shape[1]),
        "columns": columns,
        "dtypes": {c: str(frame[c].dtype) for c in frame.columns},
        "missing_counts": {str(c): int(v) for c, v in frame.isna().sum().items() if int(v) > 0},
        "duplicate_rows": int(frame.duplicated().sum()),
        "energy_column": energy_column,
        "target_status": "present_in_file" if energy_column else "missing",
        "has_battery_capacity": "battery_capacity_kwh" in frame.columns,
        "has_start_and_end_soc": start and end,
        "numeric_ranges": {
            str(c): {"min": float(numeric[c].min()), "max": float(numeric[c].max())}
            for c in numeric.columns
        },
    }
    if energy_column and start and end and "battery_capacity_kwh" in frame.columns:
        reconstructed = (frame["soc_start_pct"] - frame["soc_end_pct"]) / 100.0 * frame["battery_capacity_kwh"]
        gap = (reconstructed - frame[energy_column]).abs()
        report["label_matches_soc_drop_times_capacity"] = {
            "mae_kwh": float(gap.mean()),
            "max_abs_kwh": float(gap.max()),
            "note": (
                "energy_consumption_kwh matches (soc_start_pct - soc_end_pct) / 100 * battery_capacity_kwh "
                "within rounding. soc_end_pct is therefore the target written another way and is excluded."
            ),
        }
    report["why_training_stopped"] = (
        None
        if energy_column
        else (
            "No energy-consumption column is present. kWh cannot be measured from the columns "
            "in this file. A physics estimate would be an invented label and is not used."
        )
    )
    report["training_file_is_energy_table"] = energy_column == TARGET_COL
    return report


def require_energy_target(report: dict) -> str:
    if not report.get("energy_column"):
        raise EnergyTargetUnavailable(report["why_training_stopped"])
    return report["energy_column"]
