"""Remote model clients talk HTTP only. No joblib load."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import remote_models  # noqa: E402


class _Response:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


def test_duration_client_posts_the_feature_row(monkeypatch):
    seen = {}

    def fake_request(method, url, json=None, timeout=None):
        del timeout
        seen["method"] = method
        seen["url"] = url
        seen["json"] = json
        if url.endswith("/schema"):
            return _Response(
                200,
                {
                    "feature_columns": ["Battery Capacity (kWh)"],
                    "numeric_features": ["Battery Capacity (kWh)"],
                    "categories": {},
                    "selected_model": "random_forest",
                    "test_metrics": {"mae_min": 53.6},
                },
            )
        return _Response(200, {"predicted_charging_duration_min": 40.0, "raw_prediction_min": 40.0, "model_name": "random_forest"})

    monkeypatch.setattr(remote_models.httpx, "request", fake_request)
    bundle = remote_models.load_remote_duration("https://duration.example")
    result = bundle["predict_duration"]({"Battery Capacity (kWh)": 40}, pipeline="ignored", meta=None)
    assert result["predicted_charging_duration_min"] == 40.0
    assert seen["url"] == "https://duration.example/api/v1/predict"
    assert bundle["selected_model"] == "random_forest"
    assert bundle["feature_columns"] == ["Battery Capacity (kWh)"]


def test_energy_client_rejects_a_remote_422(monkeypatch):
    def fake_request(method, url, json=None, timeout=None):
        del method, json, timeout
        if url.endswith("/schema"):
            return _Response(200, {"feature_columns": ["distance_km"], "categories": {}, "test_metrics": None})
        return _Response(422, {"detail": "Missing required features: distance_km"})

    monkeypatch.setattr(remote_models.httpx, "request", fake_request)
    bundle = remote_models.load_remote_energy("https://energy.example/", lambda *args, **kwargs: {"estimated_total": 0})
    try:
        bundle["predict_energy"]({})
    except ValueError as exc:
        assert "distance_km" in str(exc)
    else:
        raise AssertionError("expected ValueError")
    assert bundle["energy_model_loaded"] is True
    assert bundle["remote_url"] == "https://energy.example"
