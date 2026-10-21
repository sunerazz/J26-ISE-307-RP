"""Standalone energy-model API. The integration service calls this when ENERGY_API_URL is set."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.calculate_charging_cost import estimate_charging_cost  # noqa: E402
from src.predict_energy import load_pipeline, predict_energy  # noqa: E402

PIPELINE, META = load_pipeline()
METRICS_PATH = ROOT / "results" / "test_metrics.json"
TEST_METRICS = None
if METRICS_PATH.exists():
    TEST_METRICS = json.loads(METRICS_PATH.read_text(encoding="utf-8")).get("test_metrics_raw")

app = FastAPI(
    title="EV trip energy model",
    version="1.0.0",
    description="Component 3 energy model trained on synthetic trips. Ending state of charge is not an input.",
)


class CostRequest(BaseModel):
    energy_kwh: float = Field(..., ge=0)
    tariff_per_kwh: float = Field(..., ge=0)
    currency: str = "LKR"
    tariff_category: str | None = None
    extra_fixed_fees: float = Field(default=0, ge=0)
    energy_basis: str = "vehicle_energy_kwh"


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "model_loaded": True,
        "selected_model": META.get("selected_model"),
        "training_data": "synthetic",
    }


@app.get("/api/v1/schema")
def schema() -> dict:
    return {
        "feature_columns": list(META.get("feature_columns") or []),
        "numeric_features": list(META.get("numeric_features") or []),
        "categorical_features": list(META.get("categorical_features") or []),
        "categories": META.get("categories") or {},
        "condition_features": [
            "elevation_gain_m",
            "elevation_loss_m",
            "ambient_temperature_c",
            "ac_on",
            "traffic_level",
            "road_type",
            "vehicle_mass_kg",
        ],
        "selected_model": META.get("selected_model"),
        "test_metrics": TEST_METRICS,
        "excluded_as_leakage": list(META.get("excluded_as_leakage") or []),
        "training_data": "synthetic",
        "note": "Do not send soc_end_pct or energy_consumption_kwh. Missing values are not filled.",
    }


@app.post("/api/v1/predict")
def predict(body: dict) -> dict:
    try:
        return predict_energy(body, pipeline=PIPELINE, meta=META)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/v1/cost")
def cost(body: CostRequest) -> dict:
    try:
        return estimate_charging_cost(
            body.energy_kwh,
            body.tariff_per_kwh,
            currency=body.currency,
            tariff_category=body.tariff_category,
            extra_fixed_fees=body.extra_fixed_fees,
            energy_basis=body.energy_basis,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
