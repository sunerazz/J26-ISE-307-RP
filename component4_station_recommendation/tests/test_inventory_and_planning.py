"""Rebuilt inventory, road matrix and charging-stop planner. No test calls OSRM."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.charging_plan import DESTINATION, ORIGIN, PlannerSettings, Vehicle, compare_strategies, plan_charging, single_stop
from src.recommend_stations import recommend
from src.route_optimizer import RoadMatrix, build_matrix
from src.routing_provider import RoutingError, parse_osrm_table
from src.schemas import LatLon, RecommendRequest, RouteLeg
from src.stations import RAW_CSV, load_stations, power_for_connector, tariff_for_connector


def test_inventory_loads_ocm_listings_and_keeps_live_fields_unknown():
    stations = load_stations(RAW_CSV)
    by_id = {row["station_id"]: row for row in stations}
    assert len(stations) == 67
    assert "ST063" not in by_id  # duplicate listing of ST062
    assert [row["station_id"] for row in stations[:4]] == ["ST001", "ST002", "ST003", "ST004"]
    assert all(row["queue_length_current"] is None for row in stations)
    assert all(row["waiting_time_min"] is None for row in stations)
    assert all(row["availability_status"] == "unknown" for row in stations)
    assert sum(row["in_greater_colombo"] for row in stations) == 18


def test_power_and_tariff_follow_the_plug_type():
    by_id = {row["station_id"]: row for row in load_stations(RAW_CSV)}
    trace = by_id["ST001"]
    assert power_for_connector(trace, "CHAdeMO") == 24
    assert power_for_connector(trace, "Type 1") == 6.6
    assert power_for_connector(trace, None) == 24
    assert tariff_for_connector(trace, "CHAdeMO")[0] == 120
    assert tariff_for_connector(trace, "Type 1")[0] == 70
    # Two different rates and no plug named: no single number is chosen.
    assert tariff_for_connector(trace, None)[0] is None
    # CEB stations publish no rate in the listing.
    assert tariff_for_connector(by_id["ST008"], "CHAdeMO")[0] is None


def test_osrm_table_keeps_unroutable_pairs_missing():
    km, minutes = parse_osrm_table(
        {"code": "Ok", "distances": [[0, 1500], [None, 0]], "durations": [[0, 120], [None, 0]]}, 2
    )
    assert km == [[0.0, 1.5], [None, 0.0]]
    assert minutes == [[0.0, 2.0], [None, 0.0]]
    with pytest.raises(RoutingError):
        parse_osrm_table({"code": "NoTable"}, 2)


class TableRouter:
    """Points on a line, 1 km per 0.01 degree of longitude, 1 minute per km. Labelled 'mock'."""

    name = "mock"
    max_table_points = 100

    def __init__(self):
        self.table_calls = 0
        self.route_calls = 0

    def _km(self, a: LatLon, b: LatLon) -> float:
        return abs(a.longitude - b.longitude) * 100 + abs(a.latitude - b.latitude) * 100

    def route(self, origin: LatLon, destination: LatLon) -> RouteLeg:
        self.route_calls += 1
        km = self._km(origin, destination)
        return RouteLeg(distance_km=km, duration_min=km, provider="mock", geometry=[[origin.latitude, origin.longitude], [destination.latitude, destination.longitude]])

    def table(self, points):
        self.table_calls += 1
        km = [[self._km(a, b) for b in points] for a in points]
        return km, [row[:] for row in km]


def _station(sid: str, longitude: float, power: float = 50, tariff: float | None = 100) -> dict:
    return {
        "station_id": sid,
        "station_name": sid,
        "area": sid,
        "latitude": 7.0,
        "longitude": longitude,
        "connector_types_listed": ["CHAdeMO"],
        "connector_details": [{"connector": "CHAdeMO", "quantity": 1, "power_kw": power, "supply": "DC"}],
        "max_power_kw_listed": power,
        "tariff_dc_lkr_per_kwh": tariff,
        "tariff_ac_lkr_per_kwh": None,
        "tariff_lkr_per_kwh_listed": None,
    }


def _matrix(stations: dict[str, dict], destination_longitude: float) -> RoadMatrix:
    points = {ORIGIN: LatLon(latitude=7.0, longitude=80.0), DESTINATION: LatLon(latitude=7.0, longitude=destination_longitude)}
    points.update({sid: LatLon(latitude=s["latitude"], longitude=s["longitude"]) for sid, s in stations.items()})
    return build_matrix(TableRouter(), points)


def test_build_matrix_uses_one_table_request():
    router = TableRouter()
    points = {ORIGIN: LatLon(latitude=7.0, longitude=80.0), DESTINATION: LatLon(latitude=7.0, longitude=81.0)}
    matrix = build_matrix(router, points)
    assert router.table_calls == 1 and router.route_calls == 0
    assert matrix.leg(ORIGIN, DESTINATION) == pytest.approx((100.0, 100.0))
    assert matrix.provider == "mock-table"


# 20 kWh usable, 20 kWh/100 km: 1% of battery per km.
CAR = dict(usable_kwh=20, consumption_kwh_per_100km=20, reserve_percent=10, max_charge_soc_percent=80, connector="CHAdeMO")


def test_planner_needs_two_stops_when_one_cannot_cover_the_trip():
    # Stations every 50 km on a 150 km road. One stop at 80% covers only 70 km after it.
    stations = {"A": _station("A", 80.5), "B": _station("B", 81.0)}
    vehicle = Vehicle(start_soc_percent=70, **CAR)
    settings = PlannerSettings(stop_overhead_min=5, max_stops=4)
    matrix = _matrix(stations, 81.5)
    plan = plan_charging(matrix, stations, vehicle, settings)
    assert plan["status"] == "planned"
    assert [stop["station_id"] for stop in plan["stops"]] == ["A", "B"]
    for stop in plan["stops"]:
        assert stop["arrival_soc_percent"] >= vehicle.reserve_percent - 1e-9
        assert stop["departure_soc_percent"] <= vehicle.max_charge_soc_percent + 1e-9
    assert plan["arrival_soc_at_destination_percent"] == pytest.approx(10.0)
    # No single stop finishes this trip, so every simple rule fails.
    comparison = compare_strategies(matrix, stations, vehicle, settings, plan, "A")
    assert [row["feasible"] for row in comparison["rows"]] == [False, False, False, True]


def test_planner_is_never_slower_than_the_best_single_stop():
    stations = {"A": _station("A", 80.3, power=7), "B": _station("B", 80.5, power=50), "C": _station("C", 80.7, power=24)}
    vehicle = Vehicle(start_soc_percent=60, **CAR)
    settings = PlannerSettings()
    matrix = _matrix(stations, 81.0)
    plan = plan_charging(matrix, stations, vehicle, settings)
    singles = [single_stop(matrix, station, vehicle, settings) for station in stations.values()]
    best = min(item["total_trip_min"] for item in singles if item["feasible"])
    assert plan["totals"]["total_min"] <= best + 1e-9
    # The 50 kW station is the fastest single stop and the plan uses it.
    assert "B" in [stop["station_id"] for stop in plan["stops"]]


def test_planner_reports_no_charge_needed_and_infeasible():
    stations = {"A": _station("A", 80.5)}
    settings = PlannerSettings()
    short = plan_charging(_matrix(stations, 80.2), stations, Vehicle(start_soc_percent=80, **CAR), settings)
    assert short["status"] == "no_charge_needed" and short["stops"] == []
    far = plan_charging(_matrix(stations, 83.0), stations, Vehicle(start_soc_percent=80, **CAR), settings)
    assert far["status"] == "infeasible" and far["totals"] is None


def test_recommend_routes_every_station_with_one_table_request():
    stations = load_stations(RAW_CSV)
    router = TableRouter()
    request = RecommendRequest(
        origin_latitude=6.93,
        origin_longitude=79.85,
        destination_latitude=7.29,
        destination_longitude=80.63,
        current_soc_percent=60,
        usable_battery_capacity_kwh=37,
        consumption_kwh_per_100km=16,
        minimum_reserve_percent=10,
        required_connector="CHAdeMO",
    )
    result = recommend(request, router, stations)
    summary = result.routing_summary
    assert router.table_calls == 1
    assert summary["table_requests"] == 1
    assert summary["total_requests"] <= 1 + 1 + 2 * request.geometry_for_top
    assert summary["per_station_requests_equivalent"] == 1 + 2 * summary["stations_routed"]
    assert result.charging_plan is not None and result.strategy_comparison is not None
    top = result.recommended_station
    assert top.charging_power_kw is not None and top.origin_to_station.geometry is not None
    # Only the top stations get a road shape; the rest keep matrix distances without a drawn line.
    ranked = [item for item in result.alternatives if item.included_in_ranking]
    assert all(item.origin_to_station.geometry is None for item in ranked[request.geometry_for_top :])
