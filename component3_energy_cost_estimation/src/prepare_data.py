"""Split the energy table. The target and its rearrangements stay out of the features."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import (  # noqa: E402
    CATEGORICAL_FEATURES,
    FEATURE_COLUMNS,
    ID_COL,
    LEAKED_COLUMNS,
    NUMERIC_FEATURES,
    PROCESSED_DIR,
    TARGET_COL,
    TRAIN_FRACTION,
    VAL_FRACTION,
)
from src.dataset_checks import inspect_frame, load_dataset, require_energy_target  # noqa: E402


def prepare(save: bool = True):
    frame, path = load_dataset()
    report = inspect_frame(frame, path)
    target = require_energy_target(report)
    if target != TARGET_COL:
        raise ValueError(f"Expected target {TARGET_COL}, found {target}.")
    missing_columns = [column for column in [ID_COL, TARGET_COL, *FEATURE_COLUMNS] if column not in frame.columns]
    if missing_columns:
        raise ValueError("Energy table is missing columns: " + ", ".join(missing_columns))

    work = frame.sort_values(ID_COL).reset_index(drop=True)
    before = len(work)
    work = work.dropna(subset=[TARGET_COL, *FEATURE_COLUMNS])
    dropped = before - len(work)
    if (work[TARGET_COL] < 0).any():
        raise ValueError("Negative energy_consumption_kwh rows are invalid labels and were not clipped.")

    n = len(work)
    train_end = int(n * TRAIN_FRACTION)
    val_end = int(n * (TRAIN_FRACTION + VAL_FRACTION))
    if not (0 < train_end < val_end < n):
        raise ValueError(f"Split boundaries are invalid for {n} rows.")
    train_df = work.iloc[:train_end].copy()
    val_df = work.iloc[train_end:val_end].copy()
    test_df = work.iloc[val_end:].copy()

    categories = {
        column: sorted(str(value) for value in work[column].dropna().unique())
        for column in CATEGORICAL_FEATURES
    }
    split_meta = {
        "source_path": str(path),
        "n_rows": int(n),
        "rows_dropped_for_missing_values": int(dropped),
        "split": "trip_id order, first 70% train, next 15% validation, last 15% test",
        "random_seed": None,
        "reason": "The file has no timestamps. trip_id order is the generation order and is held out in blocks.",
        "target": TARGET_COL,
        "target_unit": "kWh",
        "feature_columns": FEATURE_COLUMNS,
        "numeric_features": NUMERIC_FEATURES,
        "categorical_features": CATEGORICAL_FEATURES,
        "excluded_as_leakage": list(LEAKED_COLUMNS),
        "leakage_reason": report.get("label_matches_soc_drop_times_capacity"),
        "categories": categories,
        "counts": {"train": int(len(train_df)), "validation": int(len(val_df)), "test": int(len(test_df))},
    }
    if save:
        PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        train_df.to_csv(PROCESSED_DIR / "train.csv", index=False)
        val_df.to_csv(PROCESSED_DIR / "val.csv", index=False)
        test_df.to_csv(PROCESSED_DIR / "test.csv", index=False)
        (PROCESSED_DIR / "split_meta.json").write_text(json.dumps(split_meta, indent=2), encoding="utf-8")
    return train_df, val_df, test_df, split_meta


def main() -> None:
    _train, _val, _test, meta = prepare(save=True)
    print(json.dumps(meta["counts"]))


if __name__ == "__main__":
    main()
