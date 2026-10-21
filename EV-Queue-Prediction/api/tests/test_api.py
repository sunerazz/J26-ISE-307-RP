"""API tests for Component 1 FastAPI prediction service."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from api.model_loader import clear_registry, load_registry  # noqa: E402
from api.main import app  # noqa: E402


def _station_payload_from_processed() -> dict:
    path = PROJECT_ROOT / "data" / "processed" / "waiting_time" / "test.csv"
    row = pd.read_csv(path, nrows=1).iloc[0]
    # Feature order from waiting/congestion training meta
    from src.prepare_waiting_time_data import waiting_feature_columns

    payload = {}
    for col in waiting_feature_columns():
        val = row[col]
        if hasattr(val, "item"):
            val = val.item()
        payload[col] = val
    payload["timestamp"] = str(row["timestamp"])
    # JSON-safe types
    for k, v in list(payload.items()):
        if isinstance(v, (pd.Timestamp,)):
            payload[k] = str(v)
        elif hasattr(v, "item"):
            payload[k] = v.item()
    return payload


@pytest.fixture(scope="module")
def client():
    clear_registry()
    load_registry(force=True)
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def station_payload():
    return _station_payload_from_processed()


def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["forecast_horizon_minutes"] == 30
    assert body["all_models_loaded"] is True
    assert body["status"] == "ok"
    assert body["models"]["queue"]["loaded"] is True
    assert body["models"]["waiting_time"]["loaded"] is True
    assert body["models"]["congestion"]["loaded"] is True


def test_models_catalog(client):
    r = client.get("/api/v1/models")
    assert r.status_code == 200
    body = r.json()
    assert body["forecast_horizon_minutes"] == 30
    keys = {m["key"] for m in body["models"]}
    assert keys == {"queue", "waiting_time", "congestion"}
    for m in body["models"]:
        assert m["prediction_horizon_minutes"] == 30
        assert m["evaluation_metrics"] is not None


def test_predict_queue_success(client):
    r = client.post(
        "/api/v1/predict/queue",
        json={
            "station_id": "ST01",
            "current_queue_length": 3,
            "timestamp": "2025-04-13T00:00:00",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["station_id"] == "ST01"
    assert body["forecast_horizon_minutes"] == 30
    assert body["prediction_timestamp"] is not None
    assert body["forecast_timestamp"] is not None
    assert body["predicted_queue_length"] == 3
    assert body["raw_prediction"] == 3.0
    assert isinstance(body["predicted_queue_length"], int)
    assert body["predicted_queue_length"] >= 0


def test_predict_waiting_time_success(client, station_payload):
    r = client.post("/api/v1/predict/waiting-time", json=station_payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["forecast_horizon_minutes"] == 30
    assert body["unit"] == "minutes"
    assert body["station_id"] == station_payload["station_id"]
    assert isinstance(body["predicted_waiting_time_min"], (int, float))
    assert body["predicted_waiting_time_min"] >= 0
    assert "model_name" in body


def test_predict_congestion_success(client, station_payload):
    r = client.post("/api/v1/predict/congestion", json=station_payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["forecast_horizon_minutes"] == 30
    assert body["predicted_congestion_level"] in {"Low", "Medium", "High"}
    assert body["allowed_classes"] == ["Low", "Medium", "High"]
    assert body["class_probabilities"] is not None
    assert set(body["class_probabilities"]) == {"Low", "Medium", "High"}
    total = sum(body["class_probabilities"].values())
    assert abs(total - 1.0) < 1e-5


def test_missing_required_feature_waiting(client, station_payload):
    bad = dict(station_payload)
    del bad["current_queue_length"]
    r = client.post("/api/v1/predict/waiting-time", json=bad)
    assert r.status_code == 422


def test_missing_required_feature_queue(client):
    r = client.post("/api/v1/predict/queue", json={"station_id": "ST01"})
    assert r.status_code == 422


def test_invalid_types_and_values(client, station_payload):
    bad = dict(station_payload)
    bad["hour"] = 99
    r = client.post("/api/v1/predict/waiting-time", json=bad)
    assert r.status_code == 422

    bad2 = dict(station_payload)
    bad2["congestion_level_now"] = "Severe"
    r2 = client.post("/api/v1/predict/congestion", json=bad2)
    assert r2.status_code == 422

    bad3 = dict(station_payload)
    bad3["station_id"] = "ST99"
    r3 = client.post("/api/v1/predict/waiting-time", json=bad3)
    assert r3.status_code == 422

    r4 = client.post(
        "/api/v1/predict/queue",
        json={"station_id": "ST01", "current_queue_length": -1},
    )
    assert r4.status_code == 422


def test_reject_future_target_fields(client, station_payload):
    bad = dict(station_payload)
    bad["target_waiting_time_30min_min"] = 12.0
    r = client.post("/api/v1/predict/waiting-time", json=bad)
    assert r.status_code == 422

    r2 = client.post(
        "/api/v1/predict/queue",
        json={
            "station_id": "ST01",
            "current_queue_length": 1,
            "target_queue_length_30min": 5,
        },
    )
    assert r2.status_code == 422


def test_feature_order_consistency(station_payload):
    """API payload keys for wait/congestion match training feature order list."""
    from src.prepare_waiting_time_data import waiting_feature_columns
    from src.prepare_congestion_data import congestion_feature_columns

    wait_cols = waiting_feature_columns()
    cong_cols = congestion_feature_columns()
    assert wait_cols == cong_cols
    # Payload contains all required features in the same set
    assert set(wait_cols).issubset(set(station_payload.keys()))
    # Order used by predictors is the training list order
    assert list(wait_cols) == congestion_feature_columns()


def test_missing_model_artifact_returns_503(client, monkeypatch, tmp_path):
    """Simulate incompatible/missing artifact after registry clear."""
    import api.model_loader as ml
    from api import model_loader

    clear_registry()
    monkeypatch.setattr(
        model_loader,
        "QUEUE_MODEL_PATH",
        tmp_path / "does_not_exist.joblib",
    )
    monkeypatch.setattr(
        model_loader,
        "QUEUE_META_PATH",
        tmp_path / "does_not_exist_meta.joblib",
    )
    load_registry(force=True)
    # Recreate client lifespan is already running; force get_registry to new state
    r = client.post(
        "/api/v1/predict/queue",
        json={"station_id": "ST01", "current_queue_length": 1},
    )
    assert r.status_code == 503
    # Restore for other tests
    monkeypatch.undo()
    clear_registry()
    load_registry(force=True)


def test_quarter_rounding_carries_into_next_day():
    from datetime import datetime

    from api.station_data import _round_to_quarter

    # Sunday 23:55 belongs to Monday 00:00, not Sunday 00:00.
    slot = _round_to_quarter(datetime(2026, 10, 25, 23, 55))
    assert (slot.strftime("%A"), slot.hour, slot.minute) == ("Monday", 0, 0)
    assert _round_to_quarter(datetime(2026, 10, 21, 10, 8)).minute == 15


def test_station_now_reports_observation_outcome_and_station_error():
    from datetime import datetime

    from api.station_data import find_snapshot_for_station

    snap = find_snapshot_for_station("ST01", datetime(2026, 10, 21, 12, 0))
    now = snap["observed_now"]
    assert now["timestamp"] == snap["matched_snapshot_timestamp"]
    assert now["congestion_level"] in {"Low", "Medium", "High"}
    later = snap["recorded_outcome_30min"]
    if later is not None:
        assert pd.Timestamp(later["timestamp"]) - pd.Timestamp(now["timestamp"]) == pd.Timedelta(minutes=30)
    with TestClient(app) as client:
        body = client.post(
            "/api/v1/predict/station-now", json={"station_id": "ST01", "include_llm": False}
        ).json()
    assert body["typical_error"]["waiting_time_mae_min"] > 0
    assert "Right now" in body["human_summary"]


def test_llm_summary_with_invented_number_is_rejected():
    from api.llm_explain import summary_matches

    payload = {"station_id": "ST01", "predictions": {"waiting_time": {"predicted_waiting_time_min": 12.4}}}
    assert summary_matches("Station ST01 should have about 12 minutes of waiting.", payload)
    assert not summary_matches("Station ST01 should have about 45 minutes of waiting.", payload)
