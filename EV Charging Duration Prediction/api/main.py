"""Standalone duration-model API. The integration service calls this when DURATION_API_URL is set."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.predict_duration import load_pipeline, predict_duration  # noqa: E402

PIPELINE, META = load_pipeline()
CATEGORIES: dict[str, list[str]] = {}
TRAIN_CSV = ROOT / "data" / "processed" / "train.csv"
CATEGORICAL = list(META.get("categorical_features") or [])
if TRAIN_CSV.exists() and CATEGORICAL:
    import pandas as pd

    frame = pd.read_csv(TRAIN_CSV, usecols=CATEGORICAL)
    for column in CATEGORICAL:
        CATEGORIES[column] = sorted(str(value) for value in frame[column].dropna().unique())

METRICS_PATH = ROOT / "results" / "test_metrics.json"
TEST_METRICS = None
if METRICS_PATH.exists():
    import json

    TEST_METRICS = json.loads(METRICS_PATH.read_text(encoding="utf-8")).get("test_metrics_raw")

app = FastAPI(
    title="EV charging duration model",
    version="1.0.0",
    description="Component 2 session-duration model. Inputs are battery size, charger power, start charge, and requested end charge.",
)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "model_loaded": True,
        "selected_model": META.get("selected_model"),
        "training_data": "charging session table",
    }


@app.get("/api/v1/schema")
def schema() -> dict:
    return {
        "feature_columns": list(META.get("feature_columns") or []),
        "numeric_features": list(META.get("numeric_features") or []),
        "categorical_features": CATEGORICAL,
        "categories": CATEGORIES,
        "selected_model": META.get("selected_model"),
        "test_metrics": TEST_METRICS,
        "note": "Send every training feature. Do not send Colombo as a station location. Missing values are not filled.",
    }


@app.post("/api/v1/predict")
def predict(body: dict) -> dict:
    try:
        return predict_duration(body, pipeline=PIPELINE, meta=META)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
