"""Central API for the Colombo EV decision-support dashboard."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from bootstrap import load_all
from explain import explain_result
from orchestrate import TripRequest, build_recommendation

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("integration.service")


@asynccontextmanager
async def lifespan(app: FastAPI):
    bundle = load_all()
    component4 = bundle.get("component4")
    if component4 is not None and component4.get("provider") is None:
        component4["provider"] = component4["OsrmRoutingProvider"]()
    app.state.bundle = bundle
    if bundle.get("errors"):
        logger.warning("Component load errors: %s", bundle["errors"])
    yield


def _origins() -> list[str]:
    raw = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    return [item.strip() for item in raw.split(",") if item.strip()]


app = FastAPI(
    title="EV charging decision support",
    version="1.0.0",
    description=(
        "Orchestrates the Colombo route recommender, saved queue and duration models, "
        "and the charging-cost function. It does not invent missing predictions."
    ),
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins(),
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class FollowUpRequest(BaseModel):
    result: dict
    question: str = Field(..., min_length=1, max_length=500)


def _bundle():
    return app.state.bundle


@app.get("/health")
def health() -> dict:
    bundle = _bundle()
    component1 = bundle.get("component1") or {}
    registry = component1.get("registry")
    model_status = registry.status() if registry is not None else {}
    return {
        "status": "ok" if bundle.get("component4") else "degraded",
        "routing_ready": bundle.get("component4") is not None,
        "energy_model_loaded": bool((bundle.get("component3") or {}).get("energy_model_loaded")),
        "components": {
            "queue_waiting_congestion": model_status,
            "duration_model_loaded": bundle.get("component2") is not None,
            "energy_model_loaded": bool((bundle.get("component3") or {}).get("energy_model_loaded")),
            "cost_function_loaded": bundle.get("component3") is not None,
            "route_optimizer_loaded": bundle.get("component4") is not None,
        },
        "load_errors": bundle.get("errors") or {},
        "live_availability": False,
        "detail": "Health does not call the routing service and does not invent model outputs.",
    }


@app.get("/api/v1/colombo-stations")
def colombo_stations() -> dict:
    component4 = _bundle().get("component4")
    if component4 is None:
        raise HTTPException(status_code=503, detail="Station inventory is not loaded.")
    stations = component4["load_stations"]()
    return {
        "count": len(stations),
        "source": str(component4["csv_path"]),
        "stations": stations,
        "note": "Queue, waiting time and unverified tariffs are null or unparsed. Unknown availability is not availability.",
    }


@app.post("/api/v1/recommend")
def recommend(body: TripRequest) -> dict:
    bundle = _bundle()
    try:
        return build_recommendation(body, bundle, explain=True)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        routing_error = None
        component4 = bundle.get("component4") or {}
        routing_type = component4.get("RoutingError")
        if routing_type is not None and isinstance(exc, routing_type):
            routing_error = str(exc)
        if routing_error or "Routing is unavailable" in str(exc):
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        logger.exception("Recommendation failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/v1/explain")
def explain(body: FollowUpRequest) -> dict:
    return explain_result(body.result, body.question)


@app.get("/api/v1/duration-schema")
def duration_schema() -> dict:
    component2 = _bundle().get("component2")
    if component2 is None:
        raise HTTPException(status_code=503, detail=_bundle().get("errors", {}).get("component2", "Duration model is not loaded."))
    return {
        "feature_columns": component2["feature_columns"],
        "numeric_features": component2["meta"].get("numeric_features") or [],
        "categories": component2["categories"],
        "note": (
            "These fields belong to the saved duration model. Station location values are US cities from that dataset. "
            "Do not send a Colombo name. Leave the form unused if you do not want this separate estimate."
        ),
    }


@app.get("/api/v1/energy-schema")
def energy_schema() -> dict:
    component3 = _bundle().get("component3") or {}
    if not component3.get("energy_model_loaded"):
        raise HTTPException(status_code=503, detail=component3.get("energy_model_reason") or "Energy model is not loaded.")
    metrics = component3.get("metrics") or {}
    return {
        "feature_columns": component3.get("feature_columns") or [],
        "condition_features": component3.get("condition_features") or [],
        "categories": component3.get("categories") or {},
        "selected_model": component3.get("selected_model"),
        "test_metrics": metrics.get("test_metrics_raw"),
        "excluded_as_leakage": ["soc_end_pct", "energy_consumption_kwh_per_km"],
        "training_data": "synthetic",
        "note": (
            "Predict energy_consumption_kwh from a full feature row. "
            "Do not send soc_end_pct or energy_consumption_kwh. Missing values are not filled in. "
            "A route search can instead send energy_conditions; distance and duration then come from the road leg."
        ),
    }


@app.post("/api/v1/energy/predict")
def energy_predict(body: dict) -> dict:
    component3 = _bundle().get("component3") or {}
    if not component3.get("energy_model_loaded"):
        raise HTTPException(status_code=503, detail=component3.get("energy_model_reason") or "Energy model is not loaded.")
    try:
        prediction = component3["predict_energy"](body, pipeline=component3["pipeline"], meta=component3["meta"])
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    prediction["applies_to_colombo_inventory"] = False
    return prediction


@app.get("/api/v1/synthetic/health")
def synthetic_health() -> dict:
    component1 = _bundle().get("component1")
    if component1 is None:
        return {
            "status": "degraded",
            "all_models_loaded": False,
            "models": {},
            "detail": _bundle().get("errors", {}).get("component1", "Component 1 is not loaded."),
        }
    status = component1["registry"].status()
    return {
        "status": "ok" if component1["registry"].all_loaded() else "degraded",
        "all_models_loaded": component1["registry"].all_loaded(),
        "forecast_horizon_minutes": component1["horizon_minutes"],
        "models": status,
        "training_data": "synthetic",
    }


@app.get("/api/v1/synthetic/stations")
def synthetic_stations() -> dict:
    component1 = _bundle().get("component1")
    if component1 is None:
        raise HTTPException(status_code=503, detail="Synthetic station snapshots are not loaded.")
    return {"stations": component1["list_stations"](), "training_data": "synthetic"}


@app.post("/api/v1/synthetic/predict/station-now")
def synthetic_station_now(body: dict) -> dict:
    component1 = _bundle().get("component1")
    if component1 is None:
        raise HTTPException(status_code=503, detail="Component 1 models are not loaded.")
    try:
        request = component1["StationNowRequest"](**body)
        response = component1["predict_station_now"](request)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Synthetic station check failed")
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    payload = response.model_dump()
    payload["training_data"] = "synthetic"
    payload["applies_to_colombo_inventory"] = False
    return payload
