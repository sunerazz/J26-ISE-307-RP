"""Prepare modelling table: reconstruct 30-min target, engineer lags, split chronologically.

Cleaning operations are documented in reports/feature_target_definitions.md.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.config import (
    CATEGORICAL_BASE_FEATURES,
    CSV_FUTURE_COLUMNS,
    ENGINEERED_FEATURES,
    FORECAST_HORIZON_MINUTES,
    FORECAST_STEPS,
    NUMERIC_BASE_FEATURES,
    PROCESSED_DIR,
    PROJECT_ROOT,
    QUEUE_COL,
    RAW_DATA_PATH,
    REPORTS_DIR,
    STATION_COL,
    TARGET_COL,
    TEST_FRAC,
    TIMESTAMP_COL,
    TRAIN_FRAC,
    VAL_FRAC,
)


def load_raw(path: Path | None = None) -> pd.DataFrame:
    path = path or RAW_DATA_PATH
    df = pd.read_csv(path)
    df[TIMESTAMP_COL] = pd.to_datetime(df[TIMESTAMP_COL], errors="coerce")
    if df[TIMESTAMP_COL].isna().any():
        raise ValueError("Invalid timestamps present; refusing to fabricate times.")
    return df


def reconstruct_target(df: pd.DataFrame) -> pd.DataFrame:
    """Create target_queue_length_30min = current_queue_length at same station t+30.

    Uses exact timestamp matching (tolerance = 0 minutes). Rows without a matching
    future observation receive NaN and are later dropped — never filled with zero.
    """
    out_parts = []
    unmatched = 0
    for station_id, group in df.groupby(STATION_COL, sort=False):
        g = group.sort_values(TIMESTAMP_COL).copy()
        # Prefer exact map on timestamp+30min
        future_ts = g[TIMESTAMP_COL] + pd.Timedelta(minutes=FORECAST_HORIZON_MINUTES)
        future_queue = g.set_index(TIMESTAMP_COL)[QUEUE_COL]
        g[TARGET_COL] = future_ts.map(future_queue)

        # Cross-check against shift(-2) on regular 15-min grid
        shift_target = g[QUEUE_COL].shift(-FORECAST_STEPS)
        shift_delta = (
            g[TIMESTAMP_COL].shift(-FORECAST_STEPS) - g[TIMESTAMP_COL]
        ).dt.total_seconds() / 60.0
        exact_shift = shift_delta == FORECAST_HORIZON_MINUTES
        disagree = (
            g[TARGET_COL].notna()
            & exact_shift
            & (g[TARGET_COL] != shift_target)
        )
        if disagree.any():
            raise ValueError(
                f"Target reconstruction disagreement for station {station_id}"
            )

        unmatched += int(g[TARGET_COL].isna().sum())
        # Drop CSV future columns that are not our reconstructed definition
        for col in CSV_FUTURE_COLUMNS:
            if col in g.columns and col != TARGET_COL:
                g = g.drop(columns=[col])
        # If CSV had a differently defined target column, we already overwrote TARGET_COL
        out_parts.append(g)

    result = pd.concat(out_parts, ignore_index=True)
    result.attrs["unmatched_target_rows"] = unmatched
    return result


def add_lag_rolling_features(df: pd.DataFrame) -> pd.DataFrame:
    """Past-only lag/rolling features, computed separately per station."""
    parts = []
    for station_id, group in df.groupby(STATION_COL, sort=False):
        g = group.sort_values(TIMESTAMP_COL).copy()
        q = g[QUEUE_COL]
        a = g["vehicle_arrivals_15min"]

        g["queue_lag_1"] = q.shift(1)
        g["queue_lag_2"] = q.shift(2)
        g["queue_lag_4"] = q.shift(4)
        # Rolling windows use past values only (shift before rolling)
        g["queue_roll_mean_4"] = q.shift(1).rolling(4, min_periods=1).mean()
        g["queue_roll_mean_8"] = q.shift(1).rolling(8, min_periods=1).mean()
        g["queue_roll_std_4"] = q.shift(1).rolling(4, min_periods=2).std()
        g["queue_delta_1"] = q - g["queue_lag_1"]

        g["arrivals_lag_1"] = a.shift(1)
        g["arrivals_lag_2"] = a.shift(2)
        g["arrivals_roll_mean_4"] = a.shift(1).rolling(4, min_periods=1).mean()

        parts.append(g)
    return pd.concat(parts, ignore_index=True)


def chronological_date_split(
    df: pd.DataFrame,
    train_frac: float = TRAIN_FRAC,
    val_frac: float = VAL_FRAC,
    test_frac: float = TEST_FRAC,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    """Split by unique calendar dates (chronological), keeping all stations together."""
    if abs(train_frac + val_frac + test_frac - 1.0) > 1e-9:
        raise ValueError("Split fractions must sum to 1.")

    dates = np.array(sorted(df[TIMESTAMP_COL].dt.date.unique()))
    n = len(dates)
    n_train = int(n * train_frac)
    n_val = int(n * val_frac)
    # Remainder goes to test to ensure full coverage
    train_dates = set(dates[:n_train])
    val_dates = set(dates[n_train : n_train + n_val])
    test_dates = set(dates[n_train + n_val :])

    d = df[TIMESTAMP_COL].dt.date
    train = df[d.isin(train_dates)].sort_values([TIMESTAMP_COL, STATION_COL])
    val = df[d.isin(val_dates)].sort_values([TIMESTAMP_COL, STATION_COL])
    test = df[d.isin(test_dates)].sort_values([TIMESTAMP_COL, STATION_COL])

    meta = {
        "n_unique_dates": int(n),
        "n_train_dates": len(train_dates),
        "n_val_dates": len(val_dates),
        "n_test_dates": len(test_dates),
        "train_date_start": str(min(train_dates)),
        "train_date_end": str(max(train_dates)),
        "val_date_start": str(min(val_dates)) if val_dates else None,
        "val_date_end": str(max(val_dates)) if val_dates else None,
        "test_date_start": str(min(test_dates)) if test_dates else None,
        "test_date_end": str(max(test_dates)) if test_dates else None,
        "overlap_train_val": sorted(train_dates & val_dates, key=str),
        "overlap_train_test": sorted(train_dates & test_dates, key=str),
        "overlap_val_test": sorted(val_dates & test_dates, key=str),
    }
    return train, val, test, meta


def feature_columns() -> list[str]:
    return NUMERIC_BASE_FEATURES + CATEGORICAL_BASE_FEATURES + ENGINEERED_FEATURES


def write_feature_docs(unmatched: int, split_meta: dict) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    selected = feature_columns()
    excluded = {
        "target_waiting_time_30min_min": "Future waiting-time label; not available at prediction time; out of scope.",
        "target_congestion_level_30min": "Future congestion label; leakage risk; out of scope.",
        "CSV target_queue_length_30min (original)": (
            "Overwritten. Original CSV definition equals queue_after_current_arrivals@t+30, "
            "not current_queue_length@t+30. Modelling target is reconstructed from observations."
        ),
        "timestamp (raw)": "Used for ordering/splitting only; time encoded via hour/minute/day features.",
        "Full-dataset statistics": "Never computed before split; training statistics only.",
        "Future arrivals / completions": "Not present as usable known-at-prediction features beyond current interval.",
    }
    md = [
        "# Feature and Target Definitions",
        "",
        "## Experiment label",
        "",
        "**SIMULATION-BASED** — synthetic EV charging snapshot dataset.",
        "",
        "## Target",
        "",
        f"- Name: `{TARGET_COL}`",
        f"- Definition: `{QUEUE_COL}` at the **same** `{STATION_COL}` exactly "
        f"**{FORECAST_HORIZON_MINUTES} minutes** after the prediction timestamp.",
        f"- Construction: exact timestamp match (`t + {FORECAST_HORIZON_MINUTES} min`).",
        f"- Unmatched rows dropped (never filled with 0): **{unmatched}**.",
        "- Current queue is **not** used as the future target.",
        "",
        "## Selected features (known at prediction time)",
        "",
    ]
    for col in selected:
        md.append(f"- `{col}`")
    md.extend(
        [
            "",
            "## Excluded / not used as inputs",
            "",
        ]
    )
    for k, v in excluded.items():
        md.append(f"- **{k}**: {v}")
    md.extend(
        [
            "",
            "## Cleaning operations",
            "",
            "1. Parse timestamps; abort if invalid.",
            "2. Overwrite target with reconstructed same-station +30 min queue.",
            "3. Drop rows lacking a matched future queue observation.",
            "4. Engineer per-station lag/rolling features from past rows only.",
            "5. Drop rows where required lag features are still NaN (warm-up).",
            "6. Chronological date split (no shuffling).",
            "7. No SMOTE; no imputation of unknown queue with zero.",
            "8. No feature scaling (tree models).",
            "",
            "## Chronological split",
            "",
            "```json",
            json.dumps(split_meta, indent=2, default=str),
            "```",
            "",
            "## Leakage controls",
            "",
            "- Fit preprocessing only on training data (see train script).",
            "- Lags/rolling computed within station and using shifted windows only.",
            "- Validation used for model selection; test evaluated once.",
            "",
        ]
    )
    (REPORTS_DIR / "feature_target_definitions.md").write_text(
        "\n".join(md), encoding="utf-8"
    )


def prepare(
    raw_path: Path | None = None,
    save: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    df = load_raw(raw_path)

    # Basic integrity checks (no silent mass dropping beyond documented rules)
    if df.duplicated(subset=[STATION_COL, TIMESTAMP_COL]).any():
        raise ValueError("Duplicate station-timestamp records found.")
    if (df[QUEUE_COL] < 0).any():
        raise ValueError("Negative queue lengths found.")

    # Replace any CSV future target definition with reconstructed observational target
    if "target_queue_length_30min" in df.columns:
        df = df.drop(columns=["target_queue_length_30min"])
    for col in ("target_waiting_time_30min_min", "target_congestion_level_30min"):
        if col in df.columns:
            df = df.drop(columns=[col])

    df = reconstruct_target(df)
    unmatched = int(df.attrs.get("unmatched_target_rows", df[TARGET_COL].isna().sum()))

    before = len(df)
    df = df[df[TARGET_COL].notna()].copy()
    dropped_no_target = before - len(df)

    df = add_lag_rolling_features(df)
    # Warm-up rows where lags are unavailable
    needed = ENGINEERED_FEATURES
    before_warm = len(df)
    df = df.dropna(subset=needed).copy()
    dropped_warmup = before_warm - len(df)

    df[TARGET_COL] = df[TARGET_COL].astype(float)

    train, val, test, split_meta = chronological_date_split(df)
    split_meta.update(
        {
            "dropped_no_target": int(dropped_no_target),
            "dropped_lag_warmup": int(dropped_warmup),
            "unmatched_target_rows": unmatched,
            "n_train_rows": int(len(train)),
            "n_val_rows": int(len(val)),
            "n_test_rows": int(len(test)),
            "feature_columns": feature_columns(),
        }
    )

    write_feature_docs(unmatched=unmatched, split_meta=split_meta)

    if save:
        PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        train.to_csv(PROCESSED_DIR / "train.csv", index=False)
        val.to_csv(PROCESSED_DIR / "val.csv", index=False)
        test.to_csv(PROCESSED_DIR / "test.csv", index=False)
        df.to_csv(PROCESSED_DIR / "modelling_table.csv", index=False)
        with open(PROCESSED_DIR / "split_meta.json", "w", encoding="utf-8") as f:
            json.dump(split_meta, f, indent=2, default=str)

    return train, val, test, split_meta


def main() -> None:
    train, val, test, meta = prepare(save=True)
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
                "target_mean_train": float(train[TARGET_COL].mean()),
                "target_max_train": float(train[TARGET_COL].max()),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    import sys

    sys.path.insert(0, str(PROJECT_ROOT))
    main()
