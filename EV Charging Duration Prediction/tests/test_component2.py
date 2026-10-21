"""Tests for Component 2 data, leakage controls, and the saved pipeline."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import LinearRegression

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import (  # noqa: E402
    EXCLUDED_FEATURES,
    PIPELINE_PATH,
    TARGET_COL,
    TARGET_HOURS_COL,
)
from src.inspect_dataset import load_raw  # noqa: E402
from src.predict_duration import predict_duration  # noqa: E402
from src.prepare_data import add_target, feature_columns, prepare  # noqa: E402
from src.train_models import build_pipeline  # noqa: E402


def test_dataset_loads_and_target_is_usable():
    df = load_raw()
    assert len(df) == 1320
    assert df.shape[1] == 20
    assert TARGET_HOURS_COL in df.columns
    hours = pd.to_numeric(df[TARGET_HOURS_COL])
    assert hours.notna().all()
    assert (hours > 0).all()
    modelled = add_target(df)
    assert np.allclose(modelled[TARGET_COL], hours * 60)


def test_no_target_leakage_features():
    df = add_target(load_raw())
    features = feature_columns(df)
    blocked = {
        "Charging Duration (hours)",
        "charging_duration_min",
        "Charging End Time",
        "State of Charge (End %)",
        "Energy Consumed (kWh)",
        "Charging Cost (USD)",
    }
    assert blocked.isdisjoint(features)
    for name in blocked:
        assert name in EXCLUDED_FEATURES


def test_preprocessing_fits_and_training_predicts_minutes():
    train, _val, _test, meta = prepare(save=False)
    features = meta["feature_columns"]
    pipe = build_pipeline(
        LinearRegression(),
        meta["numeric_features"],
        meta["categorical_features"],
        scale=True,
    )
    pipe.fit(train[features], train[TARGET_COL])
    pred = pipe.predict(train[features].head(5))
    assert np.isfinite(pred).all()
    assert pred.dtype.kind == "f"


def test_chronological_dates_do_not_overlap():
    train, val, test, meta = prepare(save=False)
    tr = set(pd.to_datetime(train["Charging Start Time"]).dt.date)
    va = set(pd.to_datetime(val["Charging Start Time"]).dt.date)
    te = set(pd.to_datetime(test["Charging Start Time"]).dt.date)
    assert not (tr & va or tr & te or va & te)
    assert max(tr) < min(va) < max(va)
    assert max(va) < min(te)
    assert meta["date_overlap_train_test"] == []


def test_saved_pipeline_loads_and_clips_negative_duration():
    if not PIPELINE_PATH.exists():
        pytest.fail("Saved pipeline is missing. Run python -m src.train_models first.")
    import joblib

    pipe = joblib.load(PIPELINE_PATH)
    meta = joblib.load(PIPELINE_PATH.with_name("charging_duration_pipeline_meta.joblib"))
    row = {c: 0 for c in meta["numeric_features"]}
    row.update(
        {
            "Vehicle Model": "Nissan Leaf",
            "Charging Station Location": "Houston",
            "Time of Day": "Morning",
            "Day of Week": "Monday",
            "Charger Type": "Level 2",
            "User Type": "Commuter",
        }
    )
    # Force a negative raw output by wrapping predict.
    class _Neg:
        def predict(self, X):
            return np.array([-12.5])

    out = predict_duration(row, pipeline=_Neg(), meta=meta, clip_non_negative=True)
    assert out["unit"] == "minutes"
    assert out["predicted_charging_duration_min"] == 0.0
    assert out["raw_prediction_min"] == -12.5
    assert np.isfinite(pipe.predict(pd.DataFrame([row]))).all()


def test_predict_rejects_leaked_fields():
    meta = {
        "feature_columns": ["Vehicle Model"],
        "selected_model": "linear_regression",
    }
    with pytest.raises(ValueError, match="not allowed"):
        predict_duration(
            {"Vehicle Model": "BMW i3", "Charging End Time": "2024-01-01 02:00:00"},
            pipeline=object(),
            meta=meta,
        )
