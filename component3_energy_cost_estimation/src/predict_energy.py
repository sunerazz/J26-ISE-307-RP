"""Load the saved energy pipeline and predict kWh for one trip."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Mapping

import joblib
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import LEAKED_COLUMNS, META_PATH, PIPELINE_PATH, TARGET_COL  # noqa: E402

FORBIDDEN = set(LEAKED_COLUMNS) | {TARGET_COL, "trip_id"}


def load_pipeline(path: Path | None = None):
    path = path or PIPELINE_PATH
    if not path.exists():
        raise FileNotFoundError(path)
    pipe = joblib.load(path)
    meta = joblib.load(META_PATH)
    return pipe, meta


def predict_energy(
    record: Mapping[str, Any],
    pipeline=None,
    meta: dict | None = None,
) -> dict:
    """Predict trip energy in kWh. Missing features and leaked columns are rejected."""
    leaked = sorted(FORBIDDEN.intersection(record))
    if leaked:
        raise ValueError(
            "These fields reconstruct the target and are not model inputs: " + ", ".join(leaked)
        )
    if pipeline is None or meta is None:
        loaded_pipe, loaded_meta = load_pipeline()
        pipeline = loaded_pipe if pipeline is None else pipeline
        meta = loaded_meta if meta is None else meta
    features = list(meta["feature_columns"])
    missing = [column for column in features if record.get(column) in (None, "")]
    if missing:
        raise ValueError("Missing required features: " + ", ".join(missing))
    categories = meta.get("categories") or {}
    for column, allowed in categories.items():
        if str(record.get(column)) not in [str(item) for item in allowed]:
            raise ValueError(f"{column} must be one of {list(allowed)}.")
    row = {column: record[column] for column in features}
    frame = pd.DataFrame([row])
    raw = float(np.asarray(pipeline.predict(frame), dtype=float)[0])
    if not np.isfinite(raw) or raw < 0:
        raise ValueError(
            "The energy model returned a negative or non-finite kWh value. "
            "It was not replaced with zero."
        )
    return {
        "predicted_energy_kwh": raw,
        "raw_prediction_kwh": raw,
        "unit": "kWh",
        "model_name": meta.get("selected_model"),
        "training_data": "synthetic",
    }
