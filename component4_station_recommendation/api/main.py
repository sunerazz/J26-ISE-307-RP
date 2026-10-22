"""FastAPI service for Component 4 station recommendation."""

from __future__ import annotations

import json
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.recommend_stations import recommend
from src.routing_provider import OsrmRoutingProvider, RoutingError
from src.schemas import HealthResponse, RecommendRequest, RecommendResponse, StationListResponse
from src.stations import PROJECT_ROOT, load_stations, save_processed

RESULTS = PROJECT_ROOT / "results"

@asynccontextmanager
async def lifespan(app: FastAPI):
    if not getattr(app.state, "stations", None):
        app.state.stations = load_stations()
    save_processed(app.state.stations)
    if not getattr(app.state, "provider", None):
        app.state.provider = OsrmRoutingProvider()
    yield


app = FastAPI(
    title="Colombo EV station recommendation",
    version="1.0.0",
    description=(
        "Station recommendation and charging-stop planning over Open Charge Map listings for Sri Lanka. "
        "It does not report live availability or live queues."
    ),
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    stations = getattr(app.state, "stations", [])
    provider = getattr(app.state, "provider", None)
    return HealthResponse(
        status="ok" if stations else "degraded",
        stations_loaded=len(stations),
        routing_provider=getattr(provider, "name", "unconfigured"),
        live_availability=False,
        detail="Station inventory is loaded from the local CSV. This check does not call the routing service.",
    )


@app.get("/api/v1/stations", response_model=StationListResponse)
def list_stations() -> StationListResponse:
    stations = app.state.stations
    public = []
    for station in stations:
        public.append(
            {
                "station_id": station["station_id"],
                "station_name": station["station_name"],
                "address": station["address"],
                "area": station["area"],
                "latitude": station["latitude"],
                "longitude": station["longitude"],
                "connector_types_listed": station["connector_types_listed"],
                "max_power_kw_listed": station["max_power_kw_listed"],
                "tariff_lkr_per_kwh_listed": station["tariff_lkr_per_kwh_listed"],
                "tariff_status": station["tariff_status"],
                "tariff_raw": station["tariff_raw"],
                "availability_status": station["availability_status"],
                "queue_length_current": station["queue_length_current"],
                "waiting_time_min": station["waiting_time_min"],
                "operational_listing": station["operational_listing"],
                "confirmed_operational": station["confirmed_operational"],
                "source_url": station["source_url"],
                "source_note": station["source_note"],
                "city": station.get("city"),
                "province": station.get("province"),
                "distance_from_colombo_fort_km": station.get("distance_from_colombo_fort_km"),
                "in_greater_colombo": station.get("in_greater_colombo"),
                "number_of_points": station.get("number_of_points"),
                "connector_details": station.get("connector_details"),
                "dc_max_power_kw": station.get("dc_max_power_kw"),
                "ac_max_power_kw": station.get("ac_max_power_kw"),
                "tariff_dc_lkr_per_kwh": station.get("tariff_dc_lkr_per_kwh"),
                "tariff_ac_lkr_per_kwh": station.get("tariff_ac_lkr_per_kwh"),
                "usage_type": station.get("usage_type"),
                "access_note": station.get("access_note"),
                "opening_hours_listed": station.get("opening_hours_listed"),
                "phone": station.get("phone"),
                "retrieved_on": station.get("retrieved_on"),
            }
        )
    return StationListResponse(
        count=len(public),
        stations=public,
        note="Blank queue and waiting fields are null, not zero. Availability unknown is not availability.",
    )


@app.post("/api/v1/recommend-station", response_model=RecommendResponse)
def recommend_station(body: RecommendRequest) -> RecommendResponse:
    try:
        return recommend(body, app.state.provider, app.state.stations)
    except RoutingError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def research_summary() -> dict:
    """Saved evaluation outputs. Missing files are reported as missing, not filled in."""
    def read(name: str) -> dict | None:
        path = RESULTS / name
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    return {
        "data_completeness": read("data_completeness_report.json"),
        "routing_evaluation": read("routing_evaluation_summary.json"),
        "figures": sorted(path.name for path in RESULTS.glob("*.png")) if RESULTS.exists() else [],
        "how_to_reproduce": [
            "python -m src.build_inventory",
            "python -m src.evaluate_routing",
        ],
    }


@app.get("/api/v1/research")
def research() -> dict:
    return research_summary()
