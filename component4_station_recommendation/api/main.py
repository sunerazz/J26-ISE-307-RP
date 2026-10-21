"""FastAPI service for Component 4 station recommendation."""

from __future__ import annotations

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
from src.stations import load_stations, save_processed

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
        "Route-optimization prototype for four Colombo charging-station listings. "
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
