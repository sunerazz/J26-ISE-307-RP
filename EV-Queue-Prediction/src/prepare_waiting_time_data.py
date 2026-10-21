"""Prepare Model 2 modelling table for 30-minute-ahead waiting-time prediction.

Does not modify Model 1 processed CSVs. Writes under data/processed/waiting_time/.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.config import (
    CATEGORICAL_BASE_FEATURES,
    FORECAST_HORIZON_MINUTES,
    FORECAST_STEPS,
    NUMERIC_BASE_FEATURES,
    PROJECT_ROOT,
    QUEUE_COL,
    RAW_DATA_PATH,
    REPORTS_DIR,
    STATION_COL,
    TIMESTAMP_COL,
    WAIT_COL,
    WAITING_ENGINEERED_FEATURES,
    WAITING_PROCESSED_DIR,
    WAITING_TARGET_COL,
)
from src.prepare_data import chronological_date_split, load_raw


def reconstruct_waiting_target(df: pd.DataFrame) -> pd.DataFrame:
    """target_waiting_time_30min_min = estimated_waiting_time_now_min at same station t+30.

    Exact timestamp match only. Unmatched rows become NaN (never filled with 0).
    """
    if WAIT_COL not in df.columns:
        raise ValueError(
            f"Missing '{WAIT_COL}'. Dataset does not contain station-level "
            "waiting-time snapshots required for a 30-minute-ahead forecast."
        )

    parts = []
    unmatched = 0
    for station_id, group in df.groupby(STATION_COL, sort=False):
        g = group.sort_values(TIMESTAMP_COL).copy()
        future_ts = g[TIMESTAMP_COL] + pd.Timedelta(minutes=FORECAST_HORIZON_MINUTES)
        future_wait = g.set_index(TIMESTAMP_COL)[WAIT_COL]
        g[WAITING_TARGET_COL] = future_ts.map(future_wait)

        shift_target = g[WAIT_COL].shift(-FORECAST_STEPS)
        shift_delta = (
            g[TIMESTAMP_COL].shift(-FORECAST_STEPS) - g[TIMESTAMP_COL]
        ).dt.total_seconds() / 60.0
        exact = shift_delta == FORECAST_HORIZON_MINUTES
        disagree = (
            g[WAITING_TARGET_COL].notna()
            & exact
            & (g[WAITING_TARGET_COL] != shift_target)
        )
        if disagree.any():
            raise ValueError(
                f"Waiting-time target reconstruction disagreement for {station_id}"
            )
        unmatched += int(g[WAITING_TARGET_COL].isna().sum())
        parts.append(g)

    out = pd.concat(parts, ignore_index=True)
    out.attrs["unmatched_target_rows"] = unmatched
    return out


def add_waiting_lag_features(df: pd.DataFrame) -> pd.DataFrame:
    """Past-only queue/arrival/wait lags, separately per station."""
    parts = []
    for _station_id, group in df.groupby(STATION_COL, sort=False):
        g = group.sort_values(TIMESTAMP_COL).copy()
        q = g[QUEUE_COL]
        a = g["vehicle_arrivals_15min"]
        w = g[WAIT_COL]

        g["queue_lag_1"] = q.shift(1)
        g["queue_lag_2"] = q.shift(2)
        g["queue_lag_4"] = q.shift(4)
        g["queue_roll_mean_4"] = q.shift(1).rolling(4, min_periods=1).mean()
        g["queue_roll_mean_8"] = q.shift(1).rolling(8, min_periods=1).mean()
        g["queue_roll_std_4"] = q.shift(1).rolling(4, min_periods=2).std()
        g["queue_delta_1"] = q - g["queue_lag_1"]

        g["arrivals_lag_1"] = a.shift(1)
        g["arrivals_lag_2"] = a.shift(2)
        g["arrivals_roll_mean_4"] = a.shift(1).rolling(4, min_periods=1).mean()

        g["wait_lag_1"] = w.shift(1)
        g["wait_lag_2"] = w.shift(2)
        g["wait_lag_4"] = w.shift(4)
        g["wait_roll_mean_4"] = w.shift(1).rolling(4, min_periods=1).mean()
        g["wait_roll_mean_8"] = w.shift(1).rolling(8, min_periods=1).mean()
        g["wait_delta_1"] = w - g["wait_lag_1"]

        parts.append(g)
    return pd.concat(parts, ignore_index=True)


def waiting_feature_columns() -> list[str]:
    return NUMERIC_BASE_FEATURES + CATEGORICAL_BASE_FEATURES + WAITING_ENGINEERED_FEATURES


def write_waiting_feature_docs(unmatched: int, split_meta: dict) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    md = [
        "# Waiting-Time Feature and Target Definitions (Model 2)",
        "",
        "## Experiment label",
        "",
        "**SIMULATION-BASED** — synthetic EV charging snapshot dataset.",
        "",
        "## Waiting-time provenance",
        "",
        f"- Column `{WAIT_COL}` is an **estimated** station-level waiting time in minutes "
        "(name and ≥240 cap pattern indicate a derived/heuristic quantity, not a "
        "vehicle-session stopwatch measured from arrival until charging start).",
        "- No raw arrival→charge-start event log is present in the CSV.",
        "- Values are simulated/derived; results are not real-world deployment evidence.",
        "",
        "## Target",
        "",
        f"- Name: `{WAITING_TARGET_COL}`",
        f"- Definition: expected station waiting time (`{WAIT_COL}`) for a new arrival "
        f"at the **same** `{STATION_COL}` exactly **{FORECAST_HORIZON_MINUTES} minutes** "
        "after the prediction timestamp.",
        "- Construction: exact timestamp match (`t + 30 min`).",
        f"- Unmatched rows dropped (never filled with 0): **{unmatched}**.",
        f"- Current `{WAIT_COL}` is a feature, not the future target.",
        "- Future queue length is **not** reused as the waiting-time target.",
        "",
        "## Selected features (known at prediction time)",
        "",
    ]
    for col in waiting_feature_columns():
        md.append(f"- `{col}`")
    md.extend(
        [
            "",
            "## Excluded inputs",
            "",
            f"- `{WAITING_TARGET_COL}` (future label / leakage)",
            "- `target_queue_length_30min` (future queue; separate Model 1 task)",
            "- `target_congestion_level_30min` (future congestion; separate later task)",
            "- Charging start/end times not present; none assumed known in advance",
            "- Full-dataset statistics before chronological split",
            "",
            "## Assumptions about real-time information",
            "",
            f"- `{WAIT_COL}`, `{QUEUE_COL}`, charger counts, utilization, weather and "
            "traffic fields are treated as known at the prediction timestamp "
            "(consistent with a station telemetry snapshot).",
            "",
            "## Cleaning",
            "",
            "1. Parse timestamps; abort if invalid.",
            "2. Reconstruct waiting target from same-station wait@t+30.",
            "3. Drop rows without a matched future waiting observation.",
            "4. Engineer per-station past-only lag/rolling features (queue, arrivals, wait).",
            "5. Drop lag warm-up rows with NaN engineered features.",
            "6. Chronological date split (70/15/15), identical policy to Model 1.",
            "7. No SMOTE; no filling unknown waits with zero; no scaling for trees.",
            "",
            "## Chronological split",
            "",
            "```json",
            json.dumps(split_meta, indent=2, default=str),
            "```",
            "",
        ]
    )
    (REPORTS_DIR / "waiting_time_feature_target_definitions.md").write_text(
        "\n".join(md), encoding="utf-8"
    )


def prepare_waiting_time(
    raw_path: Path | None = None,
    save: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    df = load_raw(raw_path or RAW_DATA_PATH)

    if df.duplicated(subset=[STATION_COL, TIMESTAMP_COL]).any():
        raise ValueError("Duplicate station-timestamp records found.")
    if (df[WAIT_COL] < 0).any():
        raise ValueError("Negative waiting times found.")

    # Drop other future labels; rebuild waiting target from observations
    for col in (
        "target_queue_length_30min",
        "target_waiting_time_30min_min",
        "target_congestion_level_30min",
    ):
        if col in df.columns:
            df = df.drop(columns=[col])

    df = reconstruct_waiting_target(df)
    unmatched = int(
        df.attrs.get("unmatched_target_rows", df[WAITING_TARGET_COL].isna().sum())
    )

    before = len(df)
    df = df[df[WAITING_TARGET_COL].notna()].copy()
    dropped_no_target = before - len(df)

    df = add_waiting_lag_features(df)
    before_warm = len(df)
    df = df.dropna(subset=WAITING_ENGINEERED_FEATURES).copy()
    dropped_warmup = before_warm - len(df)

    df[WAITING_TARGET_COL] = df[WAITING_TARGET_COL].astype(float)

    train, val, test, split_meta = chronological_date_split(df)
    split_meta.update(
        {
            "task": "waiting_time_30min",
            "wait_column": WAIT_COL,
            "target_column": WAITING_TARGET_COL,
            "dropped_no_target": int(dropped_no_target),
            "dropped_lag_warmup": int(dropped_warmup),
            "unmatched_target_rows": unmatched,
            "n_train_rows": int(len(train)),
            "n_val_rows": int(len(val)),
            "n_test_rows": int(len(test)),
            "feature_columns": waiting_feature_columns(),
            "target_unit": "minutes",
            "target_min_train": float(train[WAITING_TARGET_COL].min()),
            "target_max_train": float(train[WAITING_TARGET_COL].max()),
            "target_zero_fraction_train": float(
                (train[WAITING_TARGET_COL] == 0).mean()
            ),
        }
    )
    write_waiting_feature_docs(unmatched=unmatched, split_meta=split_meta)

    if save:
        WAITING_PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        train.to_csv(WAITING_PROCESSED_DIR / "train.csv", index=False)
        val.to_csv(WAITING_PROCESSED_DIR / "val.csv", index=False)
        test.to_csv(WAITING_PROCESSED_DIR / "test.csv", index=False)
        df.to_csv(WAITING_PROCESSED_DIR / "modelling_table.csv", index=False)
        with open(WAITING_PROCESSED_DIR / "split_meta.json", "w", encoding="utf-8") as f:
            json.dump(split_meta, f, indent=2, default=str)

    return train, val, test, split_meta


def main() -> None:
    train, val, test, meta = prepare_waiting_time(save=True)
    print(
        json.dumps(
            {
                "n_train": len(train),
                "n_val": len(val),
                "n_test": len(test),
                "train_dates": f"{meta['train_date_start']} -> {meta['train_date_end']}",
                "val_dates": f"{meta['val_date_start']} -> {meta['val_date_end']}",
                "test_dates": f"{meta['test_date_start']} -> {meta['test_date_end']}",
                "overlaps": {
                    "train_val": meta["overlap_train_val"],
                    "train_test": meta["overlap_train_test"],
                    "val_test": meta["overlap_val_test"],
                },
                "target_mean_train": float(train[WAITING_TARGET_COL].mean()),
                "target_zero_fraction_train": meta["target_zero_fraction_train"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    import sys

    sys.path.insert(0, str(PROJECT_ROOT))
    main()
