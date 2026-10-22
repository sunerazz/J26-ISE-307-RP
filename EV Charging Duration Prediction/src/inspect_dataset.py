"""Inspect the Component 2 Excel dataset and write a quality report."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import (  # noqa: E402
    EXCLUDED_FEATURES,
    RAW_DATA_PATH,
    RESULTS_DIR,
    START_TIME_COL,
    TARGET_HOURS_COL,
)


def load_raw(path: Path | None = None) -> pd.DataFrame:
    path = path or RAW_DATA_PATH
    if not path.exists():
        raise FileNotFoundError(
            f"Dataset not found at {path}. Place "
            "component2_charging_duration_sri_lanka_5_stations.csv in data/raw/."
        )
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    return pd.read_excel(path)


def temperature_column(columns) -> str:
    matches = [c for c in columns if str(c).startswith("Temperature")]
    if len(matches) != 1:
        raise ValueError(f"Expected one Temperature column, found {matches}")
    return matches[0]


def inspect(df: pd.DataFrame) -> dict:
    df = df.copy()
    df[START_TIME_COL] = pd.to_datetime(df[START_TIME_COL], errors="coerce")
    df["Charging End Time"] = pd.to_datetime(df["Charging End Time"], errors="coerce")
    temp = temperature_column(df.columns)
    report = {
        "source_path": str(RAW_DATA_PATH),
        "n_rows": int(len(df)),
        "n_columns": int(df.shape[1]),
        "columns": list(map(str, df.columns)),
        "dtypes": {str(c): str(t) for c, t in df.dtypes.items()},
        "missing_counts": {str(c): int(v) for c, v in df.isna().sum().items() if v},
        "duplicate_rows": int(df.duplicated().sum()),
        "target_source_column": TARGET_HOURS_COL,
        "target_source_unit": "hours",
        "target_modelling_unit": "minutes",
        "conversion": "charging_duration_min = Charging Duration (hours) * 60",
    }
    hours = df[TARGET_HOURS_COL]
    report["duration_hours"] = {
        "min": float(hours.min()),
        "median": float(hours.median()),
        "mean": float(hours.mean()),
        "max": float(hours.max()),
        "non_positive": int((hours <= 0).sum()),
        "missing": int(hours.isna().sum()),
    }
    soc_s = df["State of Charge (Start %)"]
    soc_e = df["State of Charge (End %)"]
    report["soc_start_outside_0_100"] = int(((soc_s < 0) | (soc_s > 100)).sum())
    report["soc_end_outside_0_100"] = int(((soc_e < 0) | (soc_e > 100)).sum())
    report["soc_end_below_start"] = int((soc_e < soc_s).sum())
    batt = df["Battery Capacity (kWh)"]
    report["battery_kwh_below_10"] = int((batt < 10).sum())
    report["battery_kwh_above_120"] = int((batt > 120).sum())
    report["timestamp_min"] = str(df[START_TIME_COL].min())
    report["timestamp_max"] = str(df[START_TIME_COL].max())
    report["n_unique_start_times"] = int(df[START_TIME_COL].nunique())
    report["n_unique_dates"] = int(df[START_TIME_COL].dt.date.nunique())
    report["categorical_levels"] = {
        c: df[c].value_counts(dropna=False).to_dict()
        for c in [
            "Vehicle Model",
            "Charger Type",
            "Time of Day",
            "Day of Week",
            "User Type",
            "Charging Station Location",
        ]
    }
    report["temperature_column"] = temp
    report["excluded_features"] = EXCLUDED_FEATURES
    clock_hours = (
        pd.to_datetime(df["Charging End Time"]) - pd.to_datetime(df[START_TIME_COL])
    ).dt.total_seconds() / 3600.0
    clock_corr = float(clock_hours.corr(hours))
    paired = df.dropna(subset=["Energy Consumed (kWh)", "Charging Rate (kW)"])
    energy_rate_corr = float(
        paired["Energy Consumed (kWh)"].corr(
            paired["Charging Rate (kW)"] * paired[TARGET_HOURS_COL]
        )
    )
    locations = df["Charging Station Location"].value_counts().to_dict()
    report["clock_versus_labelled_duration_correlation"] = clock_corr
    report["energy_versus_rate_times_duration_correlation"] = energy_rate_corr
    report["location_counts"] = {str(k): int(v) for k, v in locations.items()}
    report["data_limitations"] = [
        (
            "Place names are five Sri Lankan labels: "
            + ", ".join(f"{name} ({count})" for name, count in locations.items())
            + ". Each label has the same number of rows, which is a generated balance, not evidence of equal real demand."
        ),
        (
            f"Labelled duration matches Charging End Time minus Charging Start Time "
            f"(correlation {clock_corr:.3f}). The duration column is that clock difference."
        ),
        (
            f"Energy consumed matches charging rate times labelled duration "
            f"(correlation {energy_rate_corr:.3f}). "
            "Both identities were generated from battery capacity, the SOC rise, and charging rate. "
            "This is not a meter log from those chargers."
        ),
        (
            f"SOC start outside 0–100: {report['soc_start_outside_0_100']}. "
            f"SOC end outside 0–100: {report['soc_end_outside_0_100']}. "
            f"SOC end below start: {report['soc_end_below_start']}."
        ),
        "A low error means the model recovered that generated formula. It does not mean the minutes were measured at the chargers.",
    ]
    return report


def write_report(report: dict) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    json_path = RESULTS_DIR / "dataset_quality_report.json"
    json_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    lines = [
        "# Component 2 dataset quality report",
        "",
        f"- Path: `{report['source_path']}`",
        f"- Shape: {report['n_rows']} rows × {report['n_columns']} columns",
        f"- Duplicate rows: {report['duplicate_rows']}",
        f"- Target: `{report['target_source_column']}` in **{report['target_source_unit']}**, modelled as **{report['target_modelling_unit']}**",
        f"- Conversion: {report['conversion']}",
        f"- Duration hours min/median/max: {report['duration_hours']['min']:.3f} / {report['duration_hours']['median']:.3f} / {report['duration_hours']['max']:.3f}",
        f"- Non-positive durations: {report['duration_hours']['non_positive']}",
        f"- SOC start outside 0–100: {report['soc_start_outside_0_100']}",
        f"- SOC end outside 0–100: {report['soc_end_outside_0_100']}",
        f"- SOC end below start: {report['soc_end_below_start']}",
        f"- Coverage: {report['timestamp_min']} → {report['timestamp_max']} ({report['n_unique_dates']} dates)",
        "",
        "## Missing values",
        "",
    ]
    if report["missing_counts"]:
        for k, v in report["missing_counts"].items():
            lines.append(f"- `{k}`: {v}")
    else:
        lines.append("- None")
    lines.extend(["", "## Limitations", ""])
    for note in report["data_limitations"]:
        lines.append(f"- {note}")
    lines.append("")
    md_path = RESULTS_DIR / "dataset_quality_report.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return md_path


def main() -> None:
    df = load_raw()
    report = inspect(df)
    path = write_report(report)
    print(
        json.dumps(
            {
                "rows": report["n_rows"],
                "cols": report["n_columns"],
                "target": report["target_source_column"],
                "report": str(path),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
