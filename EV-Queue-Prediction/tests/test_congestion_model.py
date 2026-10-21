"""Tests for Model 3 congestion target, split, leakage, and prediction I/O."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import (  # noqa: E402
    CONGESTION_CLASSES,
    CONGESTION_COL,
    CONGESTION_TARGET_COL,
    FORECAST_HORIZON_MINUTES,
    QUEUE_COL,
    STATION_COL,
    TIMESTAMP_COL,
    WAIT_COL,
)
from src.prepare_congestion_data import (  # noqa: E402
    congestion_feature_columns,
    reconstruct_congestion_target,
)
from src.prepare_data import chronological_date_split  # noqa: E402
from src.prepare_waiting_time_data import add_waiting_lag_features  # noqa: E402
from src.predict_congestion import predict_congestion  # noqa: E402


def _toy(station: str = "ST01", n: int = 10) -> pd.DataFrame:
    start = pd.Timestamp("2025-01-01 00:00:00")
    levels = list(CONGESTION_CLASSES)
    rows = []
    for i in range(n):
        rows.append(
            {
                TIMESTAMP_COL: start + pd.Timedelta(minutes=15 * i),
                STATION_COL: station,
                QUEUE_COL: i,
                WAIT_COL: float(i),
                "vehicle_arrivals_15min": i % 3,
                CONGESTION_COL: levels[i % 3],
            }
        )
    return pd.DataFrame(rows)


def test_allowed_class_names():
    assert set(CONGESTION_CLASSES) == {"Low", "Medium", "High"}


def test_congestion_target_30min_alignment_and_station_separation():
    a = _toy("ST01", 9)
    b = _toy("ST02", 9)
    # Force different patterns
    b[CONGESTION_COL] = ["High"] * 9
    out = reconstruct_congestion_target(pd.concat([a, b], ignore_index=True))

    st01 = out[out[STATION_COL] == "ST01"].sort_values(TIMESTAMP_COL)
    for i in range(len(st01) - 2):
        assert st01.iloc[i][CONGESTION_TARGET_COL] == st01.iloc[i + 2][CONGESTION_COL]
        delta = st01.iloc[i + 2][TIMESTAMP_COL] - st01.iloc[i][TIMESTAMP_COL]
        assert delta == pd.Timedelta(minutes=FORECAST_HORIZON_MINUTES)
    assert pd.isna(st01.iloc[-1][CONGESTION_TARGET_COL])

    st02 = out[out[STATION_COL] == "ST02"].sort_values(TIMESTAMP_COL)
    assert set(st02[CONGESTION_TARGET_COL].dropna().unique()) == {"High"}
    # ST01 targets must not all become High from ST02 leakage
    assert set(st01[CONGESTION_TARGET_COL].dropna().unique()) != {"High"}


def test_rejects_invalid_congestion_labels():
    df = _toy("ST01", 4)
    df.loc[0, CONGESTION_COL] = "Severe"
    with pytest.raises(ValueError, match="Unexpected congestion labels"):
        reconstruct_congestion_target(df)


def test_target_not_equal_to_current_congestion():
    df = reconstruct_congestion_target(_toy("ST01", 9))
    valid = df[CONGESTION_TARGET_COL].notna()
    assert not (
        df.loc[valid, CONGESTION_COL] == df.loc[valid, CONGESTION_TARGET_COL]
    ).all()


def test_chronological_split_no_overlap():
    frames = []
    start = pd.Timestamp("2025-01-01")
    for d in range(20):
        for sid in ("ST01", "ST02"):
            frames.append(
                {
                    TIMESTAMP_COL: start + pd.Timedelta(days=d),
                    STATION_COL: sid,
                    CONGESTION_TARGET_COL: "Low",
                }
            )
    train, val, test, meta = chronological_date_split(pd.DataFrame(frames))
    td = set(train[TIMESTAMP_COL].dt.date)
    vd = set(val[TIMESTAMP_COL].dt.date)
    sd = set(test[TIMESTAMP_COL].dt.date)
    assert not (td & vd) and not (td & sd) and not (vd & sd)
    assert meta["overlap_train_val"] == []
    assert max(td) < min(vd)
    assert max(vd) < min(sd)


def test_feature_list_excludes_future_labels():
    cols = congestion_feature_columns()
    assert CONGESTION_TARGET_COL not in cols
    assert "target_queue_length_30min" not in cols
    assert "target_waiting_time_30min_min" not in cols
    assert CONGESTION_COL in cols  # current congestion allowed


def test_lags_past_only():
    out = add_waiting_lag_features(
        pd.concat([_toy("ST01", 6), _toy("ST02", 6)], ignore_index=True)
    )
    st01 = out[out[STATION_COL] == "ST01"].sort_values(TIMESTAMP_COL)
    assert pd.isna(st01.iloc[0]["queue_lag_1"])
    assert st01.iloc[1]["queue_lag_1"] == st01.iloc[0][QUEUE_COL]


class _DummyClf:
    classes_ = np.array(["High", "Low", "Medium"])

    def predict(self, X):
        return np.array(["Medium"])

    def predict_proba(self, X):
        return np.array([[0.1, 0.2, 0.7]])


class _DummyPipe:
    def __init__(self):
        self.named_steps = {"model": _DummyClf()}

    def predict(self, X):
        return self.named_steps["model"].predict(X)

    def predict_proba(self, X):
        return self.named_steps["model"].predict_proba(X)


def test_predict_rejects_missing_and_future_and_validates_output():
    meta = {
        "predictor_kind": "sklearn_pipeline",
        "model_name": "random_forest",
        "model_version": "congestion_v1",
        "label_encoding": "native_strings",
    }
    with pytest.raises(ValueError, match="Missing required features"):
        predict_congestion({"station_id": "ST01"}, model=_DummyPipe(), meta=meta)

    good = {c: 0 for c in congestion_feature_columns()}
    good.update(
        {
            "station_id": "ST01",
            "location_type": "Urban",
            "day_of_week": "Monday",
            "time_slot": "Morning",
            "weather_condition": "Clear",
            "traffic_level": "Low",
            "congestion_level_now": "Low",
            "timestamp": "2025-01-01 08:00:00",
        }
    )
    with pytest.raises(ValueError, match="Future/target"):
        predict_congestion(
            {**good, "target_congestion_level_30min": "High"},
            model=_DummyPipe(),
            meta=meta,
        )

    out = predict_congestion(good, model=_DummyPipe(), meta=meta)
    assert out["station_id"] == "ST01"
    assert out["prediction_timestamp"] == "2025-01-01 08:00:00"
    assert out["forecast_timestamp"] == "2025-01-01 08:30:00"
    assert out["predicted_congestion_level"] == "Medium"
    assert out["model_version"] == "congestion_v1"
    assert set(out["allowed_classes"]) == {"Low", "Medium", "High"}
    assert out["class_probabilities"] is not None
    assert abs(sum(out["class_probabilities"].values()) - 1.0) < 1e-6
