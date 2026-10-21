"""Unit tests use a fake routing provider. They do not call OSRM."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.battery_feasibility import assess_reachability
from src.recommend_stations import recommend
from src.route_optimizer import detour
from src.routing_provider import RoutingError, parse_osrm_payload
from src.schemas import LatLon, RecommendRequest, RouteLeg
from src.stations import RAW_CSV, load_stations, save_processed

VALID = dict(
    origin_latitude=6.9271,
    origin_longitude=79.8612,
    destination_latitude=6.8649,
    destination_longitude=79.8997,
    current_soc_percent=80,
    usable_battery_capacity_kwh=40,
    consumption_kwh_per_100km=15,
    minimum_reserve_percent=10,
)


class FakeRouter:
    """Deterministic road legs. Results are labelled provider='mock', not OSRM."""

    name = "mock"

    def __init__(self, fail=None, legs=None):
        self.fail = fail or set()
        self.calls = []
        self.legs = legs or {}

    def route(self, origin: LatLon, destination: LatLon) -> RouteLeg:
        key = (
            round(origin.latitude, 5),
            round(origin.longitude, 5),
            round(destination.latitude, 5),
            round(destination.longitude, 5),
        )
        self.calls.append(key)
        if key in self.fail or "all" in self.fail:
            raise RoutingError("Mock routing failure. This is not a measured road distance.")
        if key in self.legs:
            distance, minutes = self.legs[key]
        else:
            distance, minutes = 8.0, 16.0
        return RouteLeg(distance_km=distance, duration_min=minutes, provider="mock")


def _request(**overrides) -> RecommendRequest:
    data = dict(VALID)
    data.update(overrides)
    return RecommendRequest(**data)


def test_csv_loads_four_stations_and_keeps_blanks_unknown():
    stations = load_stations(RAW_CSV)
    assert [row["station_id"] for row in stations] == ["ST001", "ST002", "ST003", "ST004"]
    assert all(row["availability_status"] == "unknown" for row in stations)
    assert all(row["queue_length_current"] is None for row in stations)
    assert all(row["waiting_time_min"] is None for row in stations)
    assert all(row["waiting_time_min"] != 0 for row in stations)
    assert all(row["confirmed_operational"] is False for row in stations)
    tariffs = {row["station_id"]: row["tariff_lkr_per_kwh_listed"] for row in stations}
    assert tariffs["ST001"] is None
    assert tariffs["ST002"] is None
    assert tariffs["ST003"] == 120
    assert tariffs["ST004"] is None
    assert all(6.8 < row["latitude"] < 7.0 for row in stations)
    assert all(79.8 < row["longitude"] < 80.0 for row in stations)
    saved = save_processed(stations)
    text = saved.read_text(encoding="utf-8")
    assert "ST001" in text
    assert ",0," not in text.splitlines()[1]


def test_invalid_coordinates_and_battery_inputs_are_rejected():
    with pytest.raises(ValidationError):
        _request(origin_latitude=95)
    with pytest.raises(ValidationError):
        _request(origin_longitude=200)
    with pytest.raises(ValidationError):
        _request(current_soc_percent=140)
    with pytest.raises(ValidationError):
        _request(current_soc_percent=-1)
    with pytest.raises(ValidationError):
        _request(usable_battery_capacity_kwh=0)
    with pytest.raises(ValidationError):
        _request(consumption_kwh_per_100km=-5)


def test_osrm_parser_rejects_invalid_payloads():
    with pytest.raises(RoutingError):
        parse_osrm_payload({"code": "NoRoute", "routes": []})
    with pytest.raises(RoutingError):
        parse_osrm_payload({"code": "Ok", "routes": [{"distance": "x"}]})
    leg = parse_osrm_payload({"code": "Ok", "routes": [{"distance": 2500, "duration": 600}]})
    assert leg.distance_km == 2.5
    assert leg.duration_min == 10
    assert leg.provider == "osrm"
    assert leg.geometry is None
    shaped = parse_osrm_payload(
        {
            "code": "Ok",
            "routes": [
                {
                    "distance": 1000,
                    "duration": 60,
                    "geometry": {"type": "LineString", "coordinates": [[79.85, 6.93], [79.86, 6.94]]},
                }
            ],
        },
        require_geometry=True,
    )
    assert shaped.geometry == [[6.93, 79.85], [6.94, 79.86]]
    with pytest.raises(RoutingError, match="geometry"):
        parse_osrm_payload(
            {"code": "Ok", "routes": [{"distance": 1000, "duration": 60}]},
            require_geometry=True,
        )


def test_routing_provider_error_does_not_invent_a_route():
    stations = load_stations(RAW_CSV)
    with pytest.raises(RoutingError, match="unavailable"):
        recommend(_request(), FakeRouter(fail={"all"}), stations)


def test_direct_route_and_detour_math():
    direct = RouteLeg(distance_km=10, duration_min=20, provider="mock")
    extra_km, extra_min = detour(direct, 6 + 8, 12 + 16)
    assert extra_km == 4
    assert extra_min == 8


def test_battery_feasibility_cases():
    feasible = assess_reachability(50, 50, 40, 15, 20)
    assert feasible.status == "feasible"
    assert feasible.estimated_energy_kwh == 7.5
    infeasible = assess_reachability(100, 50, 40, 15, 20)
    assert infeasible.status == "infeasible"
    unknown = assess_reachability(None, 50, 40, 15, 20)
    assert unknown.status == "unknown"
    assert unknown.estimated_energy_kwh is None


def test_connector_incompatibility_excludes_station():
    stations = load_stations(RAW_CSV)
    result = recommend(_request(required_connector="CCS"), FakeRouter(), stations)
    excluded = {item.station_id: item.exclusion_reason for item in result.alternatives}
    assert result.recommended_station is None
    assert all(item.connector_compatible is False for item in result.alternatives)
    assert "CCS" in excluded["ST001"]


def test_unknown_availability_is_not_called_available():
    stations = load_stations(RAW_CSV)
    result = recommend(_request(), FakeRouter(), stations)
    assert result.live_availability is False
    assert result.recommended_station is not None
    assert result.recommended_station.availability_status == "unknown"
    assert result.recommended_station.queue_length_current is None
    assert result.recommended_station.waiting_time_min is None
    assert any("unknown" in warning.lower() for warning in result.warnings)


def test_missing_tariff_and_wait_are_not_zero_and_weights_renormalize():
    stations = load_stations(RAW_CSV)
    router = FakeRouter(
        legs={
            (round(6.9271, 5), round(79.8612, 5), round(6.8649, 5), round(79.8997, 5)): (10, 20),
        }
    )
    result = recommend(_request(energy_to_add_kwh=10), router, stations)
    by_id = {result.recommended_station.station_id: result.recommended_station}
    for item in result.alternatives:
        by_id[item.station_id] = item
    st001 = by_id["ST001"]
    assert st001.waiting_time_min is None
    assert st001.tariff_lkr_per_kwh_listed is None
    assert st001.estimated_charging_cost_lkr is None
    assert "not treated as zero" in st001.ranking_explanation or "Omitted missing factors" in st001.ranking_explanation
    st003 = by_id["ST003"]
    if st003.included_in_ranking:
        assert st003.estimated_charging_cost_lkr == 1200
        assert "waiting_time" in st003.ranking_explanation
        assert "fewer than two" in st003.ranking_explanation


def test_lower_detour_ranks_first():
    stations = [load_stations(RAW_CSV)[0], load_stations(RAW_CSV)[2]]
    origin = (round(6.9271, 5), round(79.8612, 5))
    dest = (round(6.8649, 5), round(79.8997, 5))
    st1 = (round(stations[0]["latitude"], 5), round(stations[0]["longitude"], 5))
    st3 = (round(stations[1]["latitude"], 5), round(stations[1]["longitude"], 5))
    legs = {
        origin + dest: (10, 20),
        origin + st1: (3, 6),
        st1 + dest: (8, 16),
        origin + st3: (9, 18),
        st3 + dest: (9, 18),
    }
    result = recommend(_request(), FakeRouter(legs=legs), stations)
    assert result.recommended_station.station_id == "ST001"
    assert result.recommended_station.detour_distance_km == pytest.approx(1)
    assert result.direct_route.provider == "mock"
    assert result.recommended_station.origin_to_station.provider == "mock"


def test_no_feasible_station_when_battery_is_too_low():
    stations = load_stations(RAW_CSV)
    result = recommend(
        _request(current_soc_percent=5, minimum_reserve_percent=20, consumption_kwh_per_100km=30),
        FakeRouter(),
        stations,
    )
    assert result.recommended_station is None
    assert any("No station can be recommended" in warning for warning in result.warnings)
    assert all(item.battery.status == "infeasible" for item in result.alternatives)


def test_api_validation_and_response_shape(monkeypatch):
    from api.main import app

    app.state.stations = load_stations(RAW_CSV)
    app.state.provider = FakeRouter()
    client = TestClient(app)
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["stations_loaded"] == 4
    assert health.json()["live_availability"] is False
    listed = client.get("/api/v1/stations")
    assert listed.status_code == 200
    assert listed.json()["stations"][0]["waiting_time_min"] is None
    bad = client.post("/api/v1/recommend-station", json={**VALID, "origin_latitude": 120})
    assert bad.status_code == 422
    ok = client.post("/api/v1/recommend-station", json=VALID)
    assert ok.status_code == 200
    body = ok.json()
    assert body["live_queue_prediction"] is False
    assert body["direct_route"]["provider"] == "mock"
    assert body["recommended_station"]["address"]
    assert "limitations" in body
    app.state.provider = FakeRouter(fail={"all"})
    down = client.post("/api/v1/recommend-station", json=VALID)
    assert down.status_code == 503
    assert "fabricated" in down.json()["detail"] or "unavailable" in down.json()["detail"]
