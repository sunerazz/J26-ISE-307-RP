"""Call the model services over HTTP. Used when the Render environment variables are set."""

from __future__ import annotations

from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict


class RemoteError(RuntimeError):
    """The remote model service did not return a usable response."""


def _detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except Exception:  # noqa: BLE001
        return response.text
    detail = payload.get("detail", payload) if isinstance(payload, dict) else payload
    return detail if isinstance(detail, str) else str(detail)


def _request(method: str, url: str, payload: dict | None = None) -> Any:
    try:
        response = httpx.request(method, url, json=payload, timeout=60.0)
    except httpx.HTTPError as exc:
        raise RemoteError(f"Could not reach {url}: {exc}") from exc
    if response.status_code == 422:
        raise ValueError(_detail(response))
    if response.status_code >= 400:
        raise RemoteError(f"{url} returned {response.status_code}: {_detail(response)}")
    return response.json()


class RemoteStationNowRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    station_id: str
    use_current_time: bool = True
    timestamp: str | None = None
    include_llm: bool = False


class _Dump:
    def __init__(self, data: dict):
        self._data = data

    def model_dump(self) -> dict:
        return self._data


def load_remote_queue(base_url: str) -> dict[str, Any]:
    base = base_url.rstrip("/")

    class _Registry:
        def status(self) -> dict:
            try:
                body = _request("GET", f"{base}/health")
            except (RemoteError, ValueError) as exc:
                return {"reachable": False, "error": str(exc)}
            models = body.get("models")
            return models if isinstance(models, dict) else {"reachable": True, "health": body}

        def all_loaded(self) -> bool:
            try:
                return bool(_request("GET", f"{base}/health").get("all_models_loaded"))
            except (RemoteError, ValueError):
                return False

    def list_stations() -> list:
        body = _request("GET", f"{base}/api/v1/stations")
        return body.get("stations", body) if isinstance(body, dict) else body

    def predict_station_now(request: RemoteStationNowRequest) -> _Dump:
        body = _request("POST", f"{base}/api/v1/predict/station-now", request.model_dump(mode="json"))
        return _Dump(body)

    return {
        "registry": _Registry(),
        "list_stations": list_stations,
        "predict_station_now": predict_station_now,
        "StationNowRequest": RemoteStationNowRequest,
        "horizon_minutes": 30,
        "metrics": {},
        "remote_url": base,
    }


def _remote_predictor(base_url: str, predict_key: str) -> dict[str, Any]:
    base = base_url.rstrip("/")
    bundle: dict[str, Any] = {
        "feature_columns": [],
        "categories": {},
        "meta": {"numeric_features": []},
        "metrics": None,
        "selected_model": None,
        "pipeline": None,
        "remote_url": base,
        "condition_features": [],
    }

    def refresh() -> dict:
        schema = _request("GET", f"{base}/api/v1/schema")
        bundle["feature_columns"] = list(schema.get("feature_columns") or [])
        bundle["categories"] = dict(schema.get("categories") or {})
        bundle["meta"] = {"numeric_features": list(schema.get("numeric_features") or [])}
        bundle["metrics"] = schema.get("test_metrics")
        bundle["selected_model"] = schema.get("selected_model")
        bundle["condition_features"] = list(schema.get("condition_features") or [])
        return schema

    def predict(record: dict, pipeline: Any = None, meta: dict | None = None) -> dict:
        del pipeline, meta
        if not bundle["feature_columns"]:
            refresh()
        return _request("POST", f"{base}/api/v1/predict", dict(record))

    bundle["refresh"] = refresh
    bundle[predict_key] = predict
    try:
        refresh()
    except (RemoteError, ValueError) as exc:
        bundle["refresh_error"] = str(exc)
    return bundle


def load_remote_duration(base_url: str) -> dict[str, Any]:
    return _remote_predictor(base_url, "predict_duration")


def load_remote_energy(base_url: str, estimate_charging_cost) -> dict[str, Any]:
    bundle = _remote_predictor(base_url, "predict_energy")
    raw_refresh = bundle["refresh"]

    def refresh() -> dict:
        schema = raw_refresh()
        bundle["metrics"] = {"test_metrics_raw": schema.get("test_metrics")}
        return schema

    bundle["refresh"] = refresh
    bundle["estimate_charging_cost"] = estimate_charging_cost
    bundle["energy_model_loaded"] = True
    bundle["energy_model_path"] = None
    raw_metrics = bundle.get("metrics")
    bundle["metrics"] = {"test_metrics_raw": raw_metrics} if raw_metrics else None
    bundle["energy_model_reason"] = (
        "The energy model is the separate service at ENERGY_API_URL. "
        "It runs only when elevation, temperature, air conditioning, traffic, road type, and vehicle mass are supplied. "
        "Ending state of charge and kWh per kilometre are not inputs."
    )
    return bundle
