"""Load the saved duration pipeline and return minutes."""

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

from src.config import META_PATH, PIPELINE_PATH  # noqa: E402

FORBIDDEN = {
    "Charging Duration (hours)",
    "Charging Duration (minutes)",
    "charging_duration_min",
    "Charging End Time",
    "Energy Consumed (kWh)",
    "Charging Cost (USD)",
    "Illustrative Charging Cost (LKR)",
}


def load_pipeline(path: Path | None = None):
    path = path or PIPELINE_PATH
    if not path.exists():
        raise FileNotFoundError(path)
    pipe = joblib.load(path)
    meta = joblib.load(META_PATH)
    return pipe, meta


def predict_duration(
    record: Mapping[str, Any],
    pipeline=None,
    meta: dict | None = None,
    clip_non_negative: bool = True,
) -> dict:
    """Predict charging duration in minutes from features known at session start."""
    leaked = sorted(FORBIDDEN.intersection(record))
    if leaked:
        raise ValueError("Future or target fields are not allowed: " + ", ".join(leaked))
    if pipeline is None or meta is None:
        loaded_pipe, loaded_meta = load_pipeline()
        pipeline = loaded_pipe if pipeline is None else pipeline
        meta = loaded_meta if meta is None else meta
    features = meta["feature_columns"]
    missing = [c for c in features if c not in record]
    if missing:
        raise ValueError("Missing required features: " + ", ".join(missing))
    row = {c: record[c] for c in features}
    frame = pd.DataFrame([row])
    raw = float(np.asarray(pipeline.predict(frame), dtype=float)[0])
    if not np.isfinite(raw):
        raise ValueError("Model returned a non-finite duration.")
    value = max(0.0, raw) if clip_non_negative else raw
    return {
        "predicted_charging_duration_min": value,
        "raw_prediction_min": raw,
        "unit": "minutes",
        "model_name": meta.get("selected_model"),
        "clipped_at_zero": bool(clip_non_negative and raw < 0),
    }
