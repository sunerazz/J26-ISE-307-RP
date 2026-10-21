"""Score the saved pipeline once on the held-out trip block."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import PROCESSED_DIR, RESULTS_DIR, TARGET_COL  # noqa: E402
from src.predict_energy import load_pipeline  # noqa: E402
from src.train_models import regression_metrics  # noqa: E402


def evaluate() -> dict:
    test_path = PROCESSED_DIR / "test.csv"
    train_path = PROCESSED_DIR / "train.csv"
    if not test_path.exists() or not train_path.exists():
        raise FileNotFoundError("Processed splits are missing. Run src.prepare_data first.")
    pipeline, meta = load_pipeline()
    test_df = pd.read_csv(test_path)
    train_df = pd.read_csv(train_path)
    features = meta["feature_columns"]
    raw = pipeline.predict(test_df[features])
    metrics = regression_metrics(test_df[TARGET_COL], raw)
    train_median = float(train_df[TARGET_COL].median())
    baseline = regression_metrics(test_df[TARGET_COL], np.full(len(test_df), train_median))
    payload = {
        "selected_model": meta.get("selected_model"),
        "selected_params": meta.get("selected_params"),
        "test_metrics_raw": metrics,
        "train_median_baseline_on_test": baseline,
        "train_median_kwh": train_median,
        "train_median_baseline_note": "Median of the training labels, scored on the test block. It was not used to choose the model.",
        "n": metrics["n"],
        "excluded_as_leakage": meta.get("excluded_as_leakage"),
        "training_data": "synthetic",
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / "test_metrics.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return payload


def main() -> None:
    evaluate()


if __name__ == "__main__":
    main()
