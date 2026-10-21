"""Load each component from its own folder without mixing their `src` packages."""

from __future__ import annotations

import importlib
import importlib.util
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger("integration.bootstrap")

SYSTEM_ROOT = Path(__file__).resolve().parents[1]
C1 = SYSTEM_ROOT / "EV-Queue-Prediction"
C2 = SYSTEM_ROOT / "EV Charging Duration Prediction"
C3 = SYSTEM_ROOT / "component3_energy_cost_estimation"
C4 = SYSTEM_ROOT / "component4_station_recommendation"

_bundle: dict[str, Any] | None = None


def _purge(prefixes: tuple[str, ...]) -> None:
    for key in list(sys.modules):
        if any(key == prefix or key.startswith(prefix + ".") for prefix in prefixes):
            del sys.modules[key]


def _activate(root: Path) -> None:
    _purge(("src", "api"))
    for path in (C1, C2, C3, C4):
        text = str(path)
        while text in sys.path:
            sys.path.remove(text)
    sys.path.insert(0, str(root))


def _read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_component4() -> dict[str, Any]:
    _activate(C4)
    recommend_mod = importlib.import_module("src.recommend_stations")
    stations_mod = importlib.import_module("src.stations")
    routing_mod = importlib.import_module("src.routing_provider")
    schemas_mod = importlib.import_module("src.schemas")
    return {
        "recommend": recommend_mod.recommend,
        "load_stations": stations_mod.load_stations,
        "OsrmRoutingProvider": routing_mod.OsrmRoutingProvider,
        "RoutingError": routing_mod.RoutingError,
        "RecommendRequest": schemas_mod.RecommendRequest,
        "RouteLeg": schemas_mod.RouteLeg,
        "csv_path": stations_mod.RAW_CSV,
    }


def _env_url(name: str) -> str:
    return os.getenv(name, "").strip().rstrip("/")


def load_component3() -> dict[str, Any]:
    _activate(C3)
    cost_mod = importlib.import_module("src.calculate_charging_cost")
    remote = _env_url("ENERGY_API_URL")
    if remote:
        from remote_models import load_remote_energy

        return load_remote_energy(remote, cost_mod.estimate_charging_cost)
    pipeline_path = C3 / "models" / "energy_consumption_pipeline.joblib"
    bundle: dict[str, Any] = {
        "estimate_charging_cost": cost_mod.estimate_charging_cost,
        "energy_model_path": pipeline_path,
        "energy_model_loaded": False,
        "predict_energy": None,
        "pipeline": None,
        "meta": None,
        "categories": {},
        "feature_columns": [],
        "selected_model": None,
        "metrics": _read_json(C3 / "results" / "test_metrics.json"),
        "energy_model_reason": (
            "No saved energy model. Training stops until energy_consumption_kwh is in the Component 3 table."
        ),
    }
    if not pipeline_path.exists():
        return bundle
    predict_mod = importlib.import_module("src.predict_energy")
    pipeline, meta = predict_mod.load_pipeline()
    bundle.update(
        {
            "energy_model_loaded": True,
            "predict_energy": predict_mod.predict_energy,
            "pipeline": pipeline,
            "meta": meta,
            "categories": meta.get("categories") or {},
            "feature_columns": list(meta.get("feature_columns") or []),
            "selected_model": meta.get("selected_model"),
            "condition_features": [
                "elevation_gain_m",
                "elevation_loss_m",
                "ambient_temperature_c",
                "ac_on",
                "traffic_level",
                "road_type",
                "vehicle_mass_kg",
            ],
            "energy_model_reason": (
                "Loaded from the synthetic trip table. The model runs only when elevation, temperature, "
                "air conditioning, traffic, road type, and vehicle mass are supplied. "
                "Ending state of charge and kWh per kilometre are not inputs."
            ),
        }
    )
    return bundle


def load_component2() -> dict[str, Any]:
    remote = _env_url("DURATION_API_URL")
    if remote:
        from remote_models import load_remote_duration

        return load_remote_duration(remote)
    _activate(C2)
    predict_mod = importlib.import_module("src.predict_duration")
    pipeline, meta = predict_mod.load_pipeline()
    categories: dict[str, list[str]] = {}
    train_csv = C2 / "data" / "processed" / "train.csv"
    categorical = list(meta.get("categorical_features") or [])
    if train_csv.exists() and categorical:
        import pandas as pd

        frame = pd.read_csv(train_csv, usecols=categorical)
        for column in categorical:
            categories[column] = sorted(str(value) for value in frame[column].dropna().unique())
    metrics = _read_json(C2 / "results" / "test_metrics.json")
    return {
        "predict_duration": predict_mod.predict_duration,
        "pipeline": pipeline,
        "meta": meta,
        "categories": categories,
        "metrics": (metrics or {}).get("test_metrics_raw"),
        "selected_model": meta.get("selected_model"),
        "feature_columns": list(meta.get("feature_columns") or []),
    }


def load_component1() -> dict[str, Any]:
    remote = _env_url("QUEUE_API_URL")
    if remote:
        from remote_models import load_remote_queue

        return load_remote_queue(remote)
    _activate(C1)
    loader = importlib.import_module("api.model_loader")
    station_data = importlib.import_module("api.station_data")
    schemas = importlib.import_module("api.schemas")
    main = importlib.import_module("api.main")
    registry = loader.load_registry()
    return {
        "registry": registry,
        "catalog": loader.build_models_catalog(registry),
        "list_stations": station_data.list_stations,
        "predict_station_now": main.predict_station_now,
        "StationNowRequest": schemas.StationNowRequest,
        "horizon_minutes": loader.FORECAST_HORIZON_MINUTES,
        "metrics": {
            "queue": _read_json(C1 / "reports" / "test_metrics.json"),
            "waiting_time": _read_json(C1 / "reports" / "waiting_time_test_metrics.json"),
            "congestion": _read_json(C1 / "reports" / "congestion_test_metrics.json"),
        },
    }


def load_all(force: bool = False) -> dict[str, Any]:
    global _bundle
    if _bundle is not None and not force:
        return _bundle
    bundle: dict[str, Any] = {"errors": {}}
    for name, loader in (
        ("component4", load_component4),
        ("component3", load_component3),
        ("component2", load_component2),
        ("component1", load_component1),
    ):
        try:
            bundle[name] = loader()
        except Exception as exc:  # noqa: BLE001 — health must report the real failure
            logger.exception("Failed to load %s", name)
            bundle[name] = None
            bundle["errors"][name] = str(exc)
    _bundle = bundle
    return bundle


def clear_bundle() -> None:
    global _bundle
    _bundle = None
