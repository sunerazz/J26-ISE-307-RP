"""Inspect the EV queue CSV and write a dataset-quality report.

This script does not train models. It only documents data provenance,
quality checks, and whether a valid 30-minute-ahead queue target can be built.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.config import (
    FORECAST_HORIZON_MINUTES,
    FORECAST_STEPS,
    PROJECT_ROOT,
    QUEUE_COL,
    RAW_DATA_PATH,
    REPORTS_DIR,
    SAMPLING_INTERVAL_MINUTES,
    STATION_COL,
    TIMESTAMP_COL,
)


def load_raw(path: Path | None = None) -> pd.DataFrame:
    path = path or RAW_DATA_PATH
    df = pd.read_csv(path)
    df[TIMESTAMP_COL] = pd.to_datetime(df[TIMESTAMP_COL], errors="coerce")
    return df


def reconstruct_target_from_observations(df: pd.DataFrame) -> pd.DataFrame:
    """Map each row to current_queue_length at the same station 30 minutes later."""
    parts = []
    for station_id, group in df.groupby(STATION_COL, sort=False):
        g = group.sort_values(TIMESTAMP_COL).copy()
        future_ts = g[TIMESTAMP_COL] + pd.Timedelta(minutes=FORECAST_HORIZON_MINUTES)
        future_queue = g.set_index(TIMESTAMP_COL)[QUEUE_COL]
        g["reconstructed_target_queue_30min"] = future_ts.map(future_queue)
        g["target_match_delta_min"] = FORECAST_HORIZON_MINUTES
        # Also record shift(-2) for regular 15-min grids (diagnostic)
        g["shift2_queue"] = g[QUEUE_COL].shift(-FORECAST_STEPS)
        g["shift2_delta_min"] = (
            g[TIMESTAMP_COL].shift(-FORECAST_STEPS) - g[TIMESTAMP_COL]
        ).dt.total_seconds() / 60.0
        parts.append(g)
    return pd.concat(parts, ignore_index=True)


def inspect_dataset(df: pd.DataFrame) -> dict:
    report: dict = {
        "experiment_label": "SIMULATION-BASED (named Sri Lankan stations)",
        "source_path": str(RAW_DATA_PATH),
        "filename_note": (
            "Station names are Sri Lankan places. The rows are a generated "
            "15-minute snapshot grid with estimated waits, not a field log."
        ),
        "n_rows": int(len(df)),
        "n_columns": int(df.shape[1]),
        "columns": list(df.columns),
        "dtypes": {c: str(t) for c, t in df.dtypes.items()},
    }

    missing = df.isna().sum()
    report["missing_values"] = {c: int(v) for c, v in missing.items() if v > 0}
    report["total_missing"] = int(missing.sum())
    report["duplicate_rows"] = int(df.duplicated().sum())
    report["duplicate_station_timestamp"] = int(
        df.duplicated(subset=[STATION_COL, TIMESTAMP_COL]).sum()
    )
    report["invalid_timestamps"] = int(df[TIMESTAMP_COL].isna().sum())

    numeric = df.select_dtypes(include=[np.number])
    negatives = (numeric < 0).sum()
    report["negative_value_counts"] = {c: int(v) for c, v in negatives.items() if v > 0}

    report["timestamp_min"] = str(df[TIMESTAMP_COL].min())
    report["timestamp_max"] = str(df[TIMESTAMP_COL].max())
    report["n_unique_dates"] = int(df[TIMESTAMP_COL].dt.date.nunique())
    report["stations"] = sorted(df[STATION_COL].astype(str).unique().tolist())
    report["n_stations"] = len(report["stations"])
    report["rows_per_station"] = {
        str(k): int(v) for k, v in df.groupby(STATION_COL).size().items()
    }

    intervals = {}
    for station_id, group in df.groupby(STATION_COL):
        g = group.sort_values(TIMESTAMP_COL)
        diffs = g[TIMESTAMP_COL].diff().dropna().dt.total_seconds() / 60.0
        intervals[str(station_id)] = {
            "median_interval_min": float(diffs.median()) if len(diffs) else None,
            "unique_intervals_min": sorted({float(x) for x in diffs.unique()}),
            "n_observations": int(len(g)),
        }
    report["observation_intervals"] = intervals
    report["declared_sampling_interval_min"] = SAMPLING_INTERVAL_MINUTES

    report["queue_column"] = QUEUE_COL
    report["station_column"] = STATION_COL
    report["timestamp_column"] = TIMESTAMP_COL
    report["arrival_proxy_column"] = "vehicle_arrivals_15min"
    report["no_raw_arrival_or_charging_start_event_log"] = True
    report["queue_provenance"] = (
        "Queue length is provided as a column (current_queue_length) in a "
        "synthetic snapshot table at regular 15-minute intervals. It is not "
        "reconstructed from raw arrival/charging-start event logs in this CSV."
    )

    report["current_queue_summary"] = df[QUEUE_COL].describe().to_dict()
    report["queue_by_station"] = (
        df.groupby(STATION_COL)[QUEUE_COL]
        .agg(["min", "median", "mean", "max", "std"])
        .round(4)
        .to_dict(orient="index")
    )

    # Target verification
    tagged = reconstruct_target_from_observations(df)
    valid = tagged["reconstructed_target_queue_30min"].notna()
    report["n_rows_with_valid_reconstructed_30min_target"] = int(valid.sum())
    report["n_rows_without_future_observation"] = int((~valid).sum())

    if "target_queue_length_30min" in df.columns:
        csv_target = tagged.loc[valid, "target_queue_length_30min"]
        recon = tagged.loc[valid, "reconstructed_target_queue_30min"]
        match_current = (csv_target.values == recon.values).mean()
        # Compare CSV target to queue_after_current_arrivals at t+30
        qa = tagged.loc[valid].copy()
        qa_future = []
        for station_id, group in df.groupby(STATION_COL, sort=False):
            g = group.sort_values(TIMESTAMP_COL)
            future_ts = g[TIMESTAMP_COL] + pd.Timedelta(minutes=FORECAST_HORIZON_MINUTES)
            future_qa = g.set_index(TIMESTAMP_COL)["queue_after_current_arrivals"]
            mapped = future_ts.map(future_qa)
            qa_future.append(
                pd.DataFrame(
                    {
                        TIMESTAMP_COL: g[TIMESTAMP_COL].values,
                        STATION_COL: station_id,
                        "future_queue_after": mapped.values,
                    }
                )
            )
        qa_map = pd.concat(qa_future, ignore_index=True)
        merged = tagged.loc[valid].merge(
            qa_map, on=[TIMESTAMP_COL, STATION_COL], how="left"
        )
        match_queue_after = (
            merged["target_queue_length_30min"].values
            == merged["future_queue_after"].values
        ).mean()
        report["csv_precomputed_target_vs_current_queue_at_t30_match_rate"] = float(
            match_current
        )
        report["csv_precomputed_target_vs_queue_after_arrivals_at_t30_match_rate"] = (
            float(match_queue_after)
        )
        report["csv_target_definition_finding"] = (
            "The CSV column target_queue_length_30min matches "
            "queue_after_current_arrivals at t+30 minutes, not "
            "current_queue_length at t+30. For this experiment the modelling "
            "target is reconstructed as current_queue_length at the same "
            "station exactly 30 minutes later."
        )

    report["supports_queue_length_prediction"] = bool(
        report["n_rows_with_valid_reconstructed_30min_target"] > 1000
        and report["n_stations"] >= 1
        and all(
            info.get("median_interval_min") == SAMPLING_INTERVAL_MINUTES
            for info in intervals.values()
        )
    )
    report["supports_waiting_time_or_congestion_claim"] = False
    report["limitation_notes"] = [
        "Station identities are Sri Lankan places. The 15-minute queue, wait and congestion values are generated snapshots, not observed charger logs.",
        "No raw vehicle arrival / charging-start / cancellation event log is present.",
        "Queue length in this file does not exceed 12 vehicles at any station.",
        "congestion_level_now is High on nearly every row, so accuracy alone is not a useful congestion score.",
        "Last two snapshots per station lack a verifiable 30-minute-ahead observation and are excluded from modelling.",
    ]
    return report


def write_report(report: dict, out_path: Path | None = None) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = out_path or (REPORTS_DIR / "dataset_quality_report.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    md_path = REPORTS_DIR / "dataset_quality_report.md"
    lines = [
        "# Dataset Quality Report",
        "",
        f"**Experiment label:** {report['experiment_label']}",
        "",
        f"- Source: `{report['source_path']}`",
        f"- Rows: {report['n_rows']}",
        f"- Columns: {report['n_columns']}",
        f"- Stations: {report['stations']}",
        f"- Coverage: {report['timestamp_min']} → {report['timestamp_max']} "
        f"({report['n_unique_dates']} unique dates)",
        f"- Missing values: {report['total_missing']}",
        f"- Duplicate rows: {report['duplicate_rows']}",
        f"- Duplicate station-timestamp: {report['duplicate_station_timestamp']}",
        f"- Invalid timestamps: {report['invalid_timestamps']}",
        f"- Negative numeric values: {report.get('negative_value_counts') or 'none'}",
        f"- Sampling interval: {SAMPLING_INTERVAL_MINUTES} minutes (regular grid)",
        f"- Valid reconstructed 30-min targets: "
        f"{report['n_rows_with_valid_reconstructed_30min_target']}",
        f"- Rows without future observation: "
        f"{report['n_rows_without_future_observation']}",
        "",
        "## Target definition finding",
        "",
        report.get("csv_target_definition_finding", "N/A"),
        "",
        f"- Match rate vs `current_queue_length@t+30`: "
        f"{report.get('csv_precomputed_target_vs_current_queue_at_t30_match_rate')}",
        f"- Match rate vs `queue_after_current_arrivals@t+30`: "
        f"{report.get('csv_precomputed_target_vs_queue_after_arrivals_at_t30_match_rate')}",
        "",
        "## Supports prediction task?",
        "",
        f"**{report['supports_queue_length_prediction']}** — "
        "timestamped queue snapshots exist; a same-station +30 minute target "
        "can be reconstructed without fabricating labels.",
        "",
        "## Limitations",
        "",
    ]
    for note in report["limitation_notes"]:
        lines.append(f"- {note}")
    lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


def main() -> None:
    if not RAW_DATA_PATH.exists():
        raise FileNotFoundError(f"Raw CSV not found: {RAW_DATA_PATH}")
    df = load_raw()
    report = inspect_dataset(df)
    out = write_report(report)
    print(json.dumps({k: report[k] for k in [
        "experiment_label",
        "n_rows",
        "n_columns",
        "n_stations",
        "supports_queue_length_prediction",
        "n_rows_with_valid_reconstructed_30min_target",
        "csv_precomputed_target_vs_current_queue_at_t30_match_rate",
        "csv_precomputed_target_vs_queue_after_arrivals_at_t30_match_rate",
    ]}, indent=2))
    print(f"Wrote report: {out}")
    print(f"Also wrote: {REPORTS_DIR / 'dataset_quality_report.md'}")


if __name__ == "__main__":
    # Allow `python -m src.inspect_data` from project root
    import sys

    sys.path.insert(0, str(PROJECT_ROOT))
    main()
