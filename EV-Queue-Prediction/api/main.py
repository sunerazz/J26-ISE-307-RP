"""FastAPI application exposing Component 1 EV prediction models."""

from __future__ import annotations

import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# Ensure project root is importable when started via `uvicorn api.main:app`
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from api.model_loader import (  # noqa: E402
    FORECAST_HORIZON_MINUTES,
    build_models_catalog,
    get_registry,
    load_registry,
)
from api.llm_explain import llm_summary  # noqa: E402
from api.schemas import (  # noqa: E402
    CongestionPredictResponse,
    HealthResponse,
    ModelsCatalogResponse,
    QueuePredictRequest,
    QueuePredictResponse,
    StationFeatureRequest,
    StationNowRequest,
    StationNowResponse,
    WaitingTimePredictResponse,
)
from api.station_data import (  # noqa: E402
    find_snapshot_for_station,
    list_stations,
    station_error_profile,
)
from src.predict_congestion import predict_congestion  # noqa: E402
from src.predict_queue import predict_queue  # noqa: E402
from src.predict_waiting_time import predict_waiting_time  # noqa: E402

logging.basicConfig(
    level=os.getenv("API_LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("api.main")


def _cors_origins() -> list[str]:
    raw = os.getenv(
        "CORS_ORIGINS",
        "http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:5173",
    )
    origins = [o.strip() for o in raw.split(",") if o.strip()]
    if "*" in origins:
        # Refuse wildcard: require explicit origins for local React / production safety
        logger.warning(
            "Wildcard CORS origin '*' is not allowed; falling back to localhost React defaults."
        )
        origins = [
            "http://localhost:3000",
            "http://localhost:5173",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:5173",
        ]
    return origins


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Loading Component 1 model artifacts from %s", PROJECT_ROOT / "models")
    registry = load_registry(force=True)
    status = registry.status()
    logger.info("Model load status: %s", status)
    if not registry.all_loaded():
        logger.error("One or more models failed to load: %s", status)
    yield
    logger.info("API shutdown")


app = FastAPI(
    title="EV Charging Prediction API",
    description=(
        "REST API for Component 1 of the AI-Based Intelligent EV Charging "
        "Prediction and Decision Support Framework. "
        "All endpoints forecast **30 minutes ahead** using the saved trained artifacts "
        "(queue length, waiting time, congestion level)."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


def _require_model(loaded: bool, name: str, error: str | None) -> None:
    if not loaded:
        raise HTTPException(
            status_code=503,
            detail=(
                f"Model '{name}' is not available. {error or 'Artifact missing or failed to load.'} "
                "Generate artifacts with the project training scripts, then restart the API."
            ),
        )


@app.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    registry = get_registry()
    ok = registry.all_loaded()
    return HealthResponse(
        status="ok" if ok else "degraded",
        forecast_horizon_minutes=FORECAST_HORIZON_MINUTES,
        all_models_loaded=ok,
        models=registry.status(),
    )


@app.get("/api/v1/models", response_model=ModelsCatalogResponse, tags=["system"])
def list_models() -> ModelsCatalogResponse:
    registry = get_registry()
    return ModelsCatalogResponse(
        forecast_horizon_minutes=FORECAST_HORIZON_MINUTES,
        models=build_models_catalog(registry),
    )


@app.get("/api/v1/stations", tags=["station"])
def stations() -> dict:
    try:
        return {"stations": list_stations()}
    except Exception as exc:
        logger.exception("Failed to list stations")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post(
    "/api/v1/predict/station-now",
    response_model=StationNowResponse,
    tags=["station"],
    summary="Select a station and get queue, wait, congestion + human summary",
)
def predict_station_now(body: StationNowRequest) -> StationNowResponse:
    """User picks a station; models forecast +30 min using a time-matched snapshot."""
    registry = get_registry()
    _require_model(registry.queue.loaded, "queue", registry.queue.error)
    _require_model(
        registry.waiting_time.loaded, "waiting_time", registry.waiting_time.error
    )
    _require_model(registry.congestion.loaded, "congestion", registry.congestion.error)

    from datetime import datetime

    when = datetime.now() if body.use_current_time or body.timestamp is None else body.timestamp
    if body.timestamp is not None and not body.use_current_time:
        when = body.timestamp

    try:
        snap = find_snapshot_for_station(body.station_id, when=when)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Snapshot lookup failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    features = dict(snap["features"])
    ts = features.get("timestamp")

    try:
        q = predict_queue(
            {
                "station_id": body.station_id,
                "current_queue_length": features["current_queue_length"],
                "timestamp": ts,
            },
            model=registry.queue.artifact,
            meta=registry.queue.meta,
            clip_non_negative=True,
            round_for_display=True,
        )
        w = predict_waiting_time(
            features,
            model=registry.waiting_time.artifact,
            meta=registry.waiting_time.meta,
            clip_non_negative=True,
            round_for_display=False,
        )
        c = predict_congestion(
            features,
            model=registry.congestion.artifact,
            meta=registry.congestion.meta,
        )
    except Exception as exc:
        logger.exception("Station-now prediction failed")
        raise HTTPException(
            status_code=500,
            detail="Could not generate station predictions.",
        ) from exc

    predictions = {
        "queue": {
            "predicted_queue_length": int(q["predicted_queue_length_30min"]),
            "raw_prediction": float(q["raw_prediction"]),
            "model_name": registry.queue.meta.get("model_name"),
            "unit": "vehicles",
            "plain_english": (
                "No vehicles expected in queue"
                if int(q["predicted_queue_length_30min"]) == 0
                else f"About {int(q['predicted_queue_length_30min'])} vehicle(s) expected in queue"
            ),
        },
        "waiting_time": {
            "predicted_waiting_time_min": float(w["predicted_waiting_time_min"]),
            "raw_prediction_min": float(w["raw_prediction_min"]),
            "model_name": registry.waiting_time.meta.get("model_name"),
            "unit": "minutes",
            "plain_english": (
                f"About {float(w['predicted_waiting_time_min']):.0f} minutes of waiting expected"
            ),
        },
        "congestion": {
            "predicted_congestion_level": c["predicted_congestion_level"],
            "class_probabilities": c.get("class_probabilities"),
            "model_name": registry.congestion.meta.get("model_name"),
            "plain_english": f"Congestion looks {c['predicted_congestion_level']}",
        },
        "forecast_timestamp": q.get("forecast_timestamp") or w.get("forecast_timestamp"),
    }

    typical_error = station_error_profile(body.station_id)
    explain_payload = {
        "station_id": body.station_id,
        "location_type": snap["location_type"],
        "requested_local_time": snap["requested_local_time"],
        "matched_snapshot_timestamp": snap["matched_snapshot_timestamp"],
        "forecast_horizon_minutes": FORECAST_HORIZON_MINUTES,
        "predictions": predictions,
        "observed_now": snap["observed_now"],
        "typical_error": typical_error,
        "data_note": snap["data_note"],
    }

    if body.include_llm:
        summary, used_llm, provider = llm_summary(explain_payload)
    else:
        from api.llm_explain import template_summary

        summary, used_llm, provider = template_summary(explain_payload), False, "template_only"

    return StationNowResponse(
        station_id=body.station_id,
        location_type=snap["location_type"],
        requested_local_time=snap["requested_local_time"],
        matched_snapshot_timestamp=snap["matched_snapshot_timestamp"],
        forecast_horizon_minutes=FORECAST_HORIZON_MINUTES,
        match_rule=snap["match_rule"],
        data_note=snap["data_note"],
        predictions=predictions,
        human_summary=summary,
        llm_used=used_llm,
        explanation_provider=provider,
        observed_now=snap["observed_now"],
        recorded_outcome_30min=snap["recorded_outcome_30min"],
        typical_error=typical_error,
    )


@app.post(
    "/api/v1/predict/queue",
    response_model=QueuePredictResponse,
    tags=["prediction"],
    summary="Predict queue length 30 minutes ahead",
)
def predict_queue_endpoint(body: QueuePredictRequest) -> QueuePredictResponse:
    registry = get_registry()
    _require_model(registry.queue.loaded, "queue", registry.queue.error)
    try:
        record = body.model_dump(mode="python")
        if record.get("timestamp") is not None:
            record["timestamp"] = record["timestamp"].isoformat(sep=" ")
        result = predict_queue(
            record,
            model=registry.queue.artifact,
            meta=registry.queue.meta,
            clip_non_negative=True,
            round_for_display=True,
        )
        return QueuePredictResponse(
            station_id=str(result["station_id"]),
            prediction_timestamp=result.get("prediction_timestamp"),
            forecast_timestamp=result.get("forecast_timestamp"),
            forecast_horizon_minutes=FORECAST_HORIZON_MINUTES,
            predicted_queue_length=int(result["predicted_queue_length_30min"]),
            raw_prediction=float(result["raw_prediction"]),
            model_name=registry.queue.meta.get("model_name"),
            predictor_kind=registry.queue.meta.get("predictor_kind"),
        )
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Queue prediction failed")
        raise HTTPException(
            status_code=500,
            detail="Queue prediction failed due to an internal error.",
        ) from exc


@app.post(
    "/api/v1/predict/waiting-time",
    response_model=WaitingTimePredictResponse,
    tags=["prediction"],
    summary="Predict waiting time (minutes) 30 minutes ahead",
)
def predict_waiting_time_endpoint(
    body: StationFeatureRequest,
) -> WaitingTimePredictResponse:
    registry = get_registry()
    _require_model(
        registry.waiting_time.loaded, "waiting_time", registry.waiting_time.error
    )
    try:
        record = body.model_dump(mode="python")
        if record.get("timestamp") is not None:
            record["timestamp"] = record["timestamp"].isoformat(sep=" ")
        result = predict_waiting_time(
            record,
            model=registry.waiting_time.artifact,
            meta=registry.waiting_time.meta,
            clip_non_negative=True,
            round_for_display=False,
        )
        return WaitingTimePredictResponse(
            station_id=str(result["station_id"]),
            prediction_timestamp=result.get("prediction_timestamp"),
            forecast_timestamp=result.get("forecast_timestamp"),
            forecast_horizon_minutes=FORECAST_HORIZON_MINUTES,
            predicted_waiting_time_min=float(result["predicted_waiting_time_min"]),
            raw_prediction_min=float(result["raw_prediction_min"]),
            unit="minutes",
            model_name=registry.waiting_time.meta.get("model_name"),
            model_version=registry.waiting_time.meta.get("model_version"),
        )
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Waiting-time prediction failed")
        raise HTTPException(
            status_code=500,
            detail="Waiting-time prediction failed due to an internal error.",
        ) from exc


@app.post(
    "/api/v1/predict/congestion",
    response_model=CongestionPredictResponse,
    tags=["prediction"],
    summary="Predict congestion class (Low/Medium/High) 30 minutes ahead",
)
def predict_congestion_endpoint(
    body: StationFeatureRequest,
) -> CongestionPredictResponse:
    registry = get_registry()
    _require_model(registry.congestion.loaded, "congestion", registry.congestion.error)
    try:
        record = body.model_dump(mode="python")
        if record.get("timestamp") is not None:
            record["timestamp"] = record["timestamp"].isoformat(sep=" ")
        result = predict_congestion(
            record,
            model=registry.congestion.artifact,
            meta=registry.congestion.meta,
        )
        probs = result.get("class_probabilities")
        return CongestionPredictResponse(
            station_id=str(result["station_id"]),
            prediction_timestamp=result.get("prediction_timestamp"),
            forecast_timestamp=result.get("forecast_timestamp"),
            forecast_horizon_minutes=FORECAST_HORIZON_MINUTES,
            predicted_congestion_level=result["predicted_congestion_level"],
            class_probabilities=probs,
            model_name=registry.congestion.meta.get("model_name"),
            model_version=registry.congestion.meta.get("model_version"),
            allowed_classes=list(result.get("allowed_classes") or ["Low", "Medium", "High"]),
        )
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Congestion prediction failed")
        raise HTTPException(
            status_code=500,
            detail="Congestion prediction failed due to an internal error.",
        ) from exc
