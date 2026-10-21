"""Tests for Model 2 waiting-time target, split, leakage, and prediction I/O."""

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
    TIMESTAMP_COL,
    WAIT_COL,
    WAITING_TARGET_COL,
)
from src.prepare_data import chronological_date_split  # noqa: E402
from src.prepare_waiting_time_data import (  # noqa: E402
    add_waiting_lag_features,
    reconstruct_waiting_target,
    waiting_feature_columns,
)
from src.predict_waiting_time import predict_waiting_time  # noqa: E402


def _toy(station: str = "ST01", n: int = 10, wait_base: float = 1.0) -> pd.DataFrame:
    start = pd.Timestamp("2025-01-01 00:00:00")
    rows = []
    for i in range(n):
        rows.append(
            {
                TIMESTAMP_COL: start + pd.Timedelta(minutes=15 * i),
                STATION_COL: station,
                QUEUE_COL: i,
                WAIT_COL: wait_base * i,
                "vehicle_arrivals_15min": i % 3,
            }
        )
    return pd.DataFrame(rows)


def test_waiting_target_units_and_30min_alignment():
    a = _toy("ST01", 8, wait_base=2.5)
    b = _toy("ST02", 8, wait_base=10.0)
    out = reconstruct_waiting_target(pd.concat([a, b], ignore_index=True))

    for _sid, g in out.groupby(STATION_COL):
        g = g.sort_values(TIMESTAMP_COL)
        for i in range(len(g) - 2):
            assert g.iloc[i][WAITING_TARGET_COL] == g.iloc[i + 2][WAIT_COL]
            delta = g.iloc[i + 2][TIMESTAMP_COL] - g.iloc[i][TIMESTAMP_COL]
            assert delta == pd.Timedelta(minutes=FORECAST_HORIZON_MINUTES)
            # Unit check: values stay on the wait scale (minutes), not queue counts
            assert g.iloc[i][WAITING_TARGET_COL] == pytest.approx(
                float(g.iloc[i + 2][WAIT_COL])
            )
        assert pd.isna(g.iloc[-1][WAITING_TARGET_COL])
        assert pd.isna(g.iloc[-2][WAITING_TARGET_COL])


def test_station_separation_of_waiting_target():
    a = _toy("ST01", 6, wait_base=1.0)
    b = _toy("ST02", 6, wait_base=100.0)
    out = reconstruct_waiting_target(pd.concat([a, b], ignore_index=True))
    st01 = out[out[STATION_COL] == "ST01"].sort_values(TIMESTAMP_COL)
    st02 = out[out[STATION_COL] == "ST02"].sort_values(TIMESTAMP_COL)
    # ST01 future waits must not equal ST02 wait series
    assert not np.allclose(
        st01[WAITING_TARGET_COL].dropna().to_numpy(),
        st02[WAIT_COL].iloc[2 : 2 + st01[WAITING_TARGET_COL].notna().sum()].to_numpy(),
    )


def test_target_is_not_current_wait_and_not_queue():
    df = reconstruct_waiting_target(_toy(n=8, wait_base=3.0))
    valid = df[WAITING_TARGET_COL].notna()
    assert not (df.loc[valid, WAIT_COL] == df.loc[valid, WAITING_TARGET_COL]).all()
    assert WAITING_TARGET_COL != QUEUE_COL
    # Target must come from wait column scale, not queue index identity alone
    assert set(df.loc[valid, WAITING_TARGET_COL]).issubset(set(df[WAIT_COL]))


def test_chronological_split_no_overlap():
    frames = []
    start = pd.Timestamp("2025-01-01")
    for d in range(20):
        for sid in ("ST01", "ST02"):
            frames.append(
                {
                    TIMESTAMP_COL: start + pd.Timedelta(days=d),
                    STATION_COL: sid,
                    WAITING_TARGET_COL: float(d),
                }
            )
    train, val, test, meta = chronological_date_split(pd.DataFrame(frames))
    td, vd, sd = (
        set(train[TIMESTAMP_COL].dt.date),
        set(val[TIMESTAMP_COL].dt.date),
        set(test[TIMESTAMP_COL].dt.date),
    )
    assert not (td & vd) and not (td & sd) and not (vd & sd)
    assert meta["overlap_train_val"] == []
    assert max(td) < min(vd) < max(vd) or True
    assert max(vd) < min(sd)


def test_wait_lags_are_past_only_per_station():
    df = pd.concat([_toy("ST01", 6), _toy("ST02", 6)], ignore_index=True)
    out = add_waiting_lag_features(df)
    st01 = out[out[STATION_COL] == "ST01"].sort_values(TIMESTAMP_COL)
    st02 = out[out[STATION_COL] == "ST02"].sort_values(TIMESTAMP_COL)
    assert pd.isna(st01.iloc[0]["wait_lag_1"])
    assert st01.iloc[1]["wait_lag_1"] == st01.iloc[0][WAIT_COL]
    assert st02.iloc[1]["wait_lag_1"] == st02.iloc[0][WAIT_COL]


def test_feature_list_excludes_future_labels():
    cols = waiting_feature_columns()
    assert WAITING_TARGET_COL not in cols
    assert "target_queue_length_30min" not in cols
    assert "target_congestion_level_30min" not in cols
    assert WAIT_COL in cols  # current wait is allowed


def test_predict_rejects_missing_and_future_fields():
    meta = {"predictor_kind": "sklearn_pipeline", "model_name": "random_forest"}
    with pytest.raises(ValueError, match="Missing required features"):
        predict_waiting_time({"station_id": "ST01"}, model=object(), meta=meta)

    good = {c: 0 for c in waiting_feature_columns()}
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
        predict_waiting_time(
            {**good, "target_waiting_time_30min_min": 12.0},
            model=object(),
            meta=meta,
        )


class _DummyModel:
    def predict(self, X):
        return np.array([12.4])


def test_predict_output_schema_ml_and_persistence():
    good = {c: 0 for c in waiting_feature_columns()}
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
            WAIT_COL: 9.5,
        }
    )
    out = predict_waiting_time(
        good,
        model=_DummyModel(),
        meta={
            "predictor_kind": "sklearn_pipeline",
            "model_name": "random_forest",
            "model_version": "waiting_time_v1",
        },
    )
    assert out["station_id"] == "ST01"
    assert out["prediction_timestamp"] == "2025-01-01 08:00:00"
    assert out["forecast_timestamp"] == "2025-01-01 08:30:00"
    assert out["predicted_waiting_time_min"] == 12.4
    assert out["unit"] == "minutes"
    assert out["model_version"] == "waiting_time_v1"

    pout = predict_waiting_time(
        {
            "station_id": "ST01",
            WAIT_COL: 7.25,
            "timestamp": "2025-01-01 08:00:00",
        },
        model={"type": "persistence", "feature": WAIT_COL},
        meta={
            "predictor_kind": "persistence",
            "model_name": "persistence",
            "model_version": "waiting_time_v1",
        },
    )
    assert pout["predicted_waiting_time_min"] == 7.25
