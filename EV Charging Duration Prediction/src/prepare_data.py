"""Build the Component 2 modelling table and chronological split."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import (  # noqa: E402
    CATEGORICAL_FEATURES,
    EXCLUDED_FEATURES,
    HOURS_TO_MINUTES,
    NUMERIC_FEATURES,
    PROCESSED_DIR,
    RESULTS_DIR,
    START_TIME_COL,
    TARGET_COL,
    TARGET_HOURS_COL,
    TEST_FRAC,
    TRAIN_FRAC,
    VAL_FRAC,
)
from src.inspect_dataset import load_raw, temperature_column  # noqa: E402


def feature_columns(frame: pd.DataFrame) -> list[str]:
    cols = list(NUMERIC_FEATURES) + list(CATEGORICAL_FEATURES)
    missing = [c for c in cols if c not in frame.columns]
    if missing:
        raise ValueError(f"Expected feature columns are missing: {missing}")
    return cols


def add_target(df: pd.DataFrame) -> pd.DataFrame:
    if TARGET_HOURS_COL not in df.columns:
        raise ValueError(f"Target column '{TARGET_HOURS_COL}' is missing.")
    out = df.copy()
    out[START_TIME_COL] = pd.to_datetime(out[START_TIME_COL], errors="coerce")
    if out[START_TIME_COL].isna().any():
        raise ValueError("Invalid charging start timestamps; refusing to invent times.")
    hours = pd.to_numeric(out[TARGET_HOURS_COL], errors="coerce")
    if hours.isna().any() or (hours <= 0).any():
        raise ValueError("Charging duration has missing or non-positive hour values.")
    out[TARGET_COL] = hours * HOURS_TO_MINUTES
    return out


def chronological_split(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    dates = np.array(sorted(df[START_TIME_COL].dt.date.unique()))
    n = len(dates)
    n_train = int(n * TRAIN_FRAC)
    n_val = int(n * VAL_FRAC)
    if n_train < 1 or n_val < 1 or n - n_train - n_val < 1:
        raise ValueError("Not enough unique dates for a 70/15/15 chronological split.")
    train_dates = set(dates[:n_train])
    val_dates = set(dates[n_train : n_train + n_val])
    test_dates = set(dates[n_train + n_val :])
    day = df[START_TIME_COL].dt.date
    train = df[day.isin(train_dates)].sort_values(START_TIME_COL)
    val = df[day.isin(val_dates)].sort_values(START_TIME_COL)
    test = df[day.isin(test_dates)].sort_values(START_TIME_COL)
    meta = {
        "method": "chronological_by_unique_calendar_date",
        "fractions": {"train": TRAIN_FRAC, "val": VAL_FRAC, "test": TEST_FRAC},
        "n_unique_dates": int(n),
        "n_train_dates": len(train_dates),
        "n_val_dates": len(val_dates),
        "n_test_dates": len(test_dates),
        "train_date_start": str(min(train_dates)),
        "train_date_end": str(max(train_dates)),
        "val_date_start": str(min(val_dates)),
        "val_date_end": str(max(val_dates)),
        "test_date_start": str(min(test_dates)),
        "test_date_end": str(max(test_dates)),
        "n_train_rows": int(len(train)),
        "n_val_rows": int(len(val)),
        "n_test_rows": int(len(test)),
        "date_overlap_train_val": sorted(train_dates & val_dates, key=str),
        "date_overlap_train_test": sorted(train_dates & test_dates, key=str),
        "date_overlap_val_test": sorted(val_dates & test_dates, key=str),
        "limitation": (
            "Sessions are ordered by charging start date. This is not a random split. "
            "The calendar covers only about eight weeks, so the test period is a short future window of the same table."
        ),
    }
    return train, val, test, meta


def write_feature_doc(features: list[str], split_meta: dict, temp_col: str) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    included = {
        "Vehicle Model": "Known before charging starts.",
        "Battery Capacity (kWh)": "Vehicle specification known at start. A few values look unrealistic and are retained, not dropped.",
        "State of Charge (Start %)": "Initial SOC is known when charging starts. Nine values exceed 100% and are retained.",
        "Charging Rate (kW)": (
            "Treated as charger power available at the start of the session. "
            "It is not equal to energy/duration in this file. 66 missing values are imputed from the training fold only."
        ),
        "Distance Driven (since last charge) (km)": "Known before the new charging session. Missing values are imputed on the training fold only.",
        temp_col: "Ambient temperature recorded with the session and treated as known at prediction time.",
        "Vehicle Age (years)": "Vehicle attribute known at prediction time.",
        "Charging Station Location": "Known when the driver selects a station.",
        "Time of Day": "Derived from the start time and available when charging begins.",
        "Day of Week": "Derived from the start date and available when charging begins.",
        "Charger Type": "Known from the selected charger (Level 1, Level 2, DC Fast Charger).",
        "User Type": "Driver category known before the session.",
    }
    lines = [
        "# Feature and target definitions",
        "",
        "## Target",
        "",
        f"- Source column: `{TARGET_HOURS_COL}` (unit: hours).",
        f"- Model target: `{TARGET_COL}` = source × {HOURS_TO_MINUTES:.0f}.",
        "- Unit used for MAE and RMSE: **minutes**.",
        "- No rows were dropped for outliers or inconsistent SOC.",
        "",
        "## Included features",
        "",
    ]
    for col in features:
        lines.append(f"- `{col}`: {included.get(col, 'Available at charging start.')}")
    lines.extend(["", "## Excluded columns", ""])
    for col, reason in EXCLUDED_FEATURES.items():
        lines.append(f"- `{col}`: {reason}")
    lines.extend(
        [
            "",
            "## Split",
            "",
            "```json",
            json.dumps(split_meta, indent=2),
            "```",
            "",
        ]
    )
    (RESULTS_DIR / "feature_definitions.md").write_text("\n".join(lines), encoding="utf-8")


def prepare(save: bool = True):
    raw = load_raw()
    df = add_target(raw)
    features = feature_columns(df)
    train, val, test, split_meta = chronological_split(df)
    temp = temperature_column(df.columns)
    split_meta["feature_columns"] = features
    split_meta["temperature_column"] = temp
    split_meta["numeric_features"] = [c for c in features if c not in CATEGORICAL_FEATURES]
    split_meta["categorical_features"] = [c for c in features if c in CATEGORICAL_FEATURES]
    write_feature_doc(features, split_meta, temp)
    if save:
        PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        keep = features + [TARGET_COL, START_TIME_COL, TARGET_HOURS_COL]
        train[keep].to_csv(PROCESSED_DIR / "train.csv", index=False)
        val[keep].to_csv(PROCESSED_DIR / "val.csv", index=False)
        test[keep].to_csv(PROCESSED_DIR / "test.csv", index=False)
        (PROCESSED_DIR / "split_meta.json").write_text(
            json.dumps(split_meta, indent=2, default=str), encoding="utf-8"
        )
    return train, val, test, split_meta


def main() -> None:
    train, val, test, meta = prepare(save=True)
    print(
        json.dumps(
            {
                "n_train": len(train),
                "n_val": len(val),
                "n_test": len(test),
                "features": meta["feature_columns"],
                "dates": {
                    "train": [meta["train_date_start"], meta["train_date_end"]],
                    "val": [meta["val_date_start"], meta["val_date_end"]],
                    "test": [meta["test_date_start"], meta["test_date_end"]],
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
