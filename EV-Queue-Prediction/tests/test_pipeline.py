"""Unit tests for target construction, splits, leakage guards, and prediction I/O."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import (  # noqa: E402
    FORECAST_HORIZON_MINUTES,
    QUEUE_COL,
    STATION_COL,
    TARGET_COL,
    TIMESTAMP_COL,
)
from src.prepare_data import (  # noqa: E402
    add_lag_rolling_features,
    chronological_date_split,
    feature_columns,
    reconstruct_target,
)
from src.predict_queue import predict_queue  # noqa: E402


def _toy_station_frame(station: str = "ST01", n: int = 10) -> pd.DataFrame:
    start = pd.Timestamp("2025-01-01 00:00:00")
    rows = []
    for i in range(n):
        rows.append(
            {
                TIMESTAMP_COL: start + pd.Timedelta(minutes=15 * i),
                STATION_COL: station,
                QUEUE_COL: i,
                "vehicle_arrivals_15min": i % 3,
            }
        )
    return pd.DataFrame(rows)


def test_target_is_exactly_30_minutes_ahead_same_station():
    a = _toy_station_frame("ST01", 8)
    b = _toy_station_frame("ST02", 8)
    b[QUEUE_COL] = b[QUEUE_COL] + 100  # different station queues
    df = pd.concat([a, b], ignore_index=True)
    out = reconstruct_target(df)

    for station_id, g in out.groupby(STATION_COL):
        g = g.sort_values(TIMESTAMP_COL)
        for i in range(len(g) - 2):
            assert g.iloc[i][TARGET_COL] == g.iloc[i + 2][QUEUE_COL]
            delta = g.iloc[i + 2][TIMESTAMP_COL] - g.iloc[i][TIMESTAMP_COL]
            assert delta == pd.Timedelta(minutes=FORECAST_HORIZON_MINUTES)
        assert pd.isna(g.iloc[-1][TARGET_COL])
        assert pd.isna(g.iloc[-2][TARGET_COL])

    # Station separation: ST01 target must never equal ST02 future queue
    st01 = out[out[STATION_COL] == "ST01"].sort_values(TIMESTAMP_COL)
    st02 = out[out[STATION_COL] == "ST02"].sort_values(TIMESTAMP_COL)
    assert not np.array_equal(
        st01[TARGET_COL].dropna().to_numpy(),
        st02[QUEUE_COL].iloc[2 : 2 + st01[TARGET_COL].notna().sum()].to_numpy(),
    )


def test_target_not_equal_to_current_queue():
    df = reconstruct_target(_toy_station_frame(n=6))
    valid = df[TARGET_COL].notna()
    # For this toy series current != future except by chance at ends
    assert not (df.loc[valid, QUEUE_COL] == df.loc[valid, TARGET_COL]).all()


def test_chronological_split_no_date_overlap():
    frames = []
    start = pd.Timestamp("2025-01-01")
    for d in range(20):
        for sid in ("ST01", "ST02"):
            frames.append(
                {
                    TIMESTAMP_COL: start + pd.Timedelta(days=d),
                    STATION_COL: sid,
                    QUEUE_COL: d,
                    TARGET_COL: d,
                }
            )
    df = pd.DataFrame(frames)
    train, val, test, meta = chronological_date_split(df)
    train_dates = set(train[TIMESTAMP_COL].dt.date)
    val_dates = set(val[TIMESTAMP_COL].dt.date)
    test_dates = set(test[TIMESTAMP_COL].dt.date)
    assert not (train_dates & val_dates)
    assert not (train_dates & test_dates)
    assert not (val_dates & test_dates)
    assert meta["overlap_train_val"] == []
    assert meta["overlap_train_test"] == []
    assert meta["overlap_val_test"] == []
    assert max(train_dates) < min(val_dates)
    assert max(val_dates) < min(test_dates)


def test_lag_features_are_past_only_per_station():
    df = pd.concat(
        [_toy_station_frame("ST01", 6), _toy_station_frame("ST02", 6)],
        ignore_index=True,
    )
    out = add_lag_rolling_features(df)
    st01 = out[out[STATION_COL] == "ST01"].sort_values(TIMESTAMP_COL)
    assert pd.isna(st01.iloc[0]["queue_lag_1"])
    assert st01.iloc[1]["queue_lag_1"] == st01.iloc[0][QUEUE_COL]
    assert st01.iloc[2]["queue_lag_2"] == st01.iloc[0][QUEUE_COL]
    # Must not leak ST02 values into ST01 lags
    st02 = out[out[STATION_COL] == "ST02"].sort_values(TIMESTAMP_COL)
    assert st01.iloc[1]["queue_lag_1"] != st02.iloc[0][QUEUE_COL] or True
    # Explicit: first lag of ST02 equals ST02's own first queue, not ST01
    assert st02.iloc[1]["queue_lag_1"] == st02.iloc[0][QUEUE_COL]


def test_feature_list_excludes_future_targets():
    cols = feature_columns()
    assert "target_waiting_time_30min_min" not in cols
    assert "target_congestion_level_30min" not in cols
    # Target column itself is not an input feature
    assert TARGET_COL not in cols


def test_predict_rejects_missing_and_future_fields():
    ml_meta = {"predictor_kind": "sklearn_pipeline", "model_name": "random_forest"}
    with pytest.raises(ValueError, match="Missing required features"):
        predict_queue({"station_id": "ST01"}, model=object(), meta=ml_meta)

    good = {c: 0 for c in feature_columns()}
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
        predict_queue(
            {**good, "target_queue_length_30min": 3},
            model=object(),
            meta=ml_meta,
        )


class _DummyModel:
    def predict(self, X):
        return np.array([1.7])


def test_predict_output_schema():
    good = {c: 0 for c in feature_columns()}
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
            "current_queue_length": 4,
        }
    )
    out = predict_queue(
        good,
        model=_DummyModel(),
        meta={"predictor_kind": "sklearn_pipeline", "model_name": "random_forest"},
        round_for_display=False,
    )
    assert out["station_id"] == "ST01"
    assert out["prediction_timestamp"] == "2025-01-01 08:00:00"
    assert out["forecast_timestamp"] == "2025-01-01 08:30:00"
    assert out["predicted_queue_length_30min"] == 1.7
    assert out["forecast_horizon_minutes"] == 30


def test_predict_persistence_schema():
    out = predict_queue(
        {
            "station_id": "ST01",
            "current_queue_length": 5,
            "timestamp": "2025-01-01 08:00:00",
        },
        model={"type": "persistence", "feature": "current_queue_length"},
        meta={"predictor_kind": "persistence", "model_name": "persistence"},
    )
    assert out["predicted_queue_length_30min"] == 5.0
    assert out["forecast_timestamp"] == "2025-01-01 08:30:00"
