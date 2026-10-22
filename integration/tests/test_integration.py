"""Integration tests. Routing is mocked. Model tests that load artifacts are marked."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from functools import partial
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bootstrap import load_component1, load_component2, load_component3, load_component4
from explain import explanation_matches, template_explanation
from orchestrate import SRI_LANKA, TripRequest, build_recommendation

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
    name = "mock"

    def __init__(self, route_leg, error_type, fail=False):
        self.route_leg = route_leg
        self.error_type = error_type
        self.fail = fail

    def route(self, origin, destination):
        if self.fail:
            raise self.error_type("Mock routing failure. No road distance was fabricated.")
        return self.route_leg(
            distance_km=8.0,
            duration_min=16.0,
            provider="mock",
            geometry=[[6.93, 79.85], [6.92, 79.86]],
        )


OFFLINE = {"weather_fetcher": lambda latitude, longitude: None, "elevation_fetcher": lambda geometry: None}


def _deps(fail_route=False):
    component4 = load_component4()
    component3 = load_component3()
    # Ranking tests use the original four Colombo listings as a fixed fixture.
    component4["load_stations"] = partial(component4["load_stations"], component4["legacy_csv_path"])
    component4["provider"] = FakeRouter(component4["RouteLeg"], component4["RoutingError"], fail=fail_route)
    return {
        "component4": component4,
        "component3": component3,
        "component2": None,
        "component1": None,
        "errors": {},
        # Tests never call the weather or elevation services.
        "condition_fetchers": OFFLINE,
    }


def test_inventory_has_ocm_listings_with_live_fields_unknown():
    stations = load_component4()["load_stations"]()
    by_id = {row["station_id"]: row for row in stations}
    assert len(stations) == 67
    assert "TRACE" in by_id["ST001"]["station_name"]
    assert by_id["ST001"]["tariff_dc_lkr_per_kwh"] == 120
    assert all(row["waiting_time_min"] is None for row in stations)
    assert all(row["availability_status"] == "unknown" for row in stations)


def test_four_colombo_stations_load_from_csv():
    component4 = load_component4()
    stations = component4["load_stations"](component4["legacy_csv_path"])
    by_id = {row["station_id"]: row for row in stations}
    assert list(by_id) == ["ST001", "ST002", "ST003", "ST004"]
    assert "TRACE" in by_id["ST001"]["station_name"]
    assert "Pereira" in by_id["ST002"]["address"]
    assert "Kopiyawatta" in by_id["ST003"]["address"]
    assert "Galle Road" in by_id["ST004"]["address"]
    assert all(row["waiting_time_min"] is None for row in stations)
    assert all(row["queue_length_current"] is None for row in stations)
    assert all(row["availability_status"] == "unknown" for row in stations)
    assert by_id["ST001"]["tariff_lkr_per_kwh_listed"] is None
    assert by_id["ST003"]["tariff_lkr_per_kwh_listed"] == 120


def test_area_model_matches_pannipitiya_and_skips_kandy():
    from area_models import match_trained_area

    near = match_trained_area(
        {
            "area": "Pannipitiya",
            "city": "Colombo",
            "station_name": "Ceylon Electricity Board - Pannipitiya",
            "address": "High Level Rd",
            "latitude": 6.8449,
            "longitude": 79.9407,
        }
    )
    assert near is not None
    assert near["station_id"] == "ST04"
    far = match_trained_area(
        {
            "area": "Kandy",
            "city": "Kandy",
            "station_name": "Kandy",
            "address": "Kandy",
            "latitude": 7.2906,
            "longitude": 80.6337,
        }
    )
    assert far is None


def test_recommendation_uses_mock_routes_and_leaves_queue_unknown():
    deps = _deps()
    deps["component1"] = load_component1()
    result = build_recommendation(TripRequest(**VALID), deps, explain=True)
    assert result["direct_route"]["provider"] == "mock"
    assert result["recommended_route"]["provider"] == "mock"
    assert len(result["recommended_route"]["geometry"]) >= 2
    queue = result["recommended_station"]["queue_prediction"]
    assert queue["status"] == "area_model"
    assert queue["predicted_queue_length"] is not None
    assert queue["predicted_waiting_time_min"] is not None
    assert queue["predicted_congestion_level"] in {"Low", "Medium", "High"}
    assert queue["observed_queue_length"] is None
    assert queue["training_data"] == "synthetic"
    assert result["recommended_station"]["availability_status"] == "unknown"
    assert result["energy_and_cost"]["energy_model_loaded"] is True
    assert result["energy_and_cost"]["energy_model_applied"] is False
    assert result["energy_and_cost"]["scenario_cost"] is None
    assert result["charging_duration"]["predicted_charging_duration_min"] is None
    assert "synthetic" in result["explanation"]["text"].lower()
    assert result["explanation"]["llm_used"] is False
    ok, reason = explanation_matches(result["explanation"]["text"], result)
    assert ok, reason


def test_low_battery_recommends_nobody():
    body = TripRequest(**{**VALID, "current_soc_percent": 5, "minimum_reserve_percent": 20, "consumption_kwh_per_100km": 30})
    result = build_recommendation(body, _deps(), explain=True)
    assert result["recommended_station"] is None
    assert "No station can be recommended" in result["explanation"]["text"]
    assert all(item["battery"]["status"] == "infeasible" for item in result["alternatives"])


def test_charge_time_comes_from_component2_not_listed_power():
    body = TripRequest(**{**VALID, "target_soc_percent": 100})
    without_model = build_recommendation(body, _deps(), explain=False)
    # 40 kWh * (100 - 77) / 100 = 9.2 kWh. Divided by 30 kW that would be 18.4 min.
    # That listed-power figure must not be used when the duration model is absent.
    assert without_model["recommended_station"]["trip_plan"]["arrival_soc_percent"] == pytest.approx(77.0)
    assert without_model["recommended_station"]["trip_plan"]["charging_energy_kwh"] == pytest.approx(9.2)
    assert without_model["recommended_station"]["listed_power_duration_min"] is None
    assert without_model["recommended_station"]["duration_source"] == "unavailable"
    assert without_model["recommended_station"]["scenario_cost_lkr"] is None

    deps = _deps()
    deps["component2"] = load_component2()
    result = build_recommendation(body, deps, explain=False)
    by_id = {result["recommended_station"]["station_id"]: result["recommended_station"]}
    for item in result["alternatives"]:
        by_id[item["station_id"]] = item
    assert by_id["ST001"]["duration_source"] == "component2"
    assert by_id["ST001"]["listed_power_duration_min"] > 0
    # Same arrival charge and the same target. The slower charger takes longer.
    assert by_id["ST004"]["max_power_kw_listed"] < by_id["ST001"]["max_power_kw_listed"]
    assert by_id["ST004"]["listed_power_duration_min"] > by_id["ST001"]["listed_power_duration_min"]
    assert "Component 2" in by_id["ST001"]["listed_power_duration_note"]
    assert "not treated as zero" in by_id["ST001"]["ranking_explanation"]


def test_user_tariff_is_labelled_scenario():
    body = TripRequest(**{**VALID, "target_soc_percent": 90, "user_tariff_lkr_per_kwh": 50})
    result = build_recommendation(body, _deps(), explain=False)
    cost = result["energy_and_cost"]["scenario_cost"]
    # 40 kWh * (90 - 77) / 100 = 5.2 kWh at 50 LKR/kWh.
    assert cost["estimated_total"] == pytest.approx(260)
    assert result["energy_and_cost"]["charging_energy_station_id"] == result["recommended_station"]["station_id"]
    assert cost["energy_basis"] == "vehicle_energy_kwh"
    assert "not an official" in result["energy_and_cost"]["summary"]


def test_routing_failure_is_not_replaced():
    with pytest.raises(Exception, match="unavailable|Mock routing"):
        build_recommendation(TripRequest(**VALID), _deps(fail_route=True), explain=False)


def test_explanation_rejects_invented_availability_and_cost():
    result = build_recommendation(TripRequest(**VALID), _deps(), explain=False)
    bad = "Station ST001 is available now and the official tariff makes the cost 9999 LKR."
    ok, _reason = explanation_matches(bad, result)
    assert ok is False
    assert explanation_matches(template_explanation(result), result)[0] is True


def test_duration_model_uses_battery_power_and_charge_levels():
    component2 = load_component2()
    deps = _deps()
    deps["component1"] = load_component1()
    deps["component2"] = component2
    missing = build_recommendation(
        TripRequest(**{**VALID, "duration_features": {"Vehicle Model": "Nissan Leaf"}}),
        deps,
        explain=False,
    )
    assert missing["charging_duration"]["predicted_charging_duration_min"] is None
    assert missing["charging_duration"]["missing_features"]
    record = {
        "Battery Capacity (kWh)": 40,
        "Charging Rate (kW)": 30,
        "State of Charge (Start %)": 20,
        "State of Charge (End %)": 80,
    }
    leaked = build_recommendation(
        TripRequest(**{**VALID, "duration_features": {**record, "Charging End Time": "2024-01-01 02:00:00"}}),
        deps,
        explain=False,
    )
    assert leaked["charging_duration"]["status"] == "unavailable"
    predicted = build_recommendation(TripRequest(**{**VALID, "duration_features": record}), deps, explain=False)
    assert predicted["charging_duration"]["status"] == "predicted"
    assert predicted["charging_duration"]["predicted_charging_duration_min"] > 0
    assert predicted["charging_duration"]["used_in_ranking"] is False
    assert predicted["recommended_station"]["queue_prediction"]["status"] == "area_model"
    assert predicted["recommended_station"]["queue_prediction"]["observed_queue_length"] is None


def test_component1_models_load_and_synthetic_check_is_labelled():
    component1 = load_component1()
    assert component1["registry"].all_loaded()
    response = component1["predict_station_now"](
        component1["StationNowRequest"](station_id="ST01", use_current_time=True, include_llm=False)
    )
    payload = response.model_dump()
    assert payload["predictions"]["queue"]["predicted_queue_length"] >= 0
    assert "synthetic" in payload["data_note"].lower()


def test_api_validation_stations_and_mocked_recommendation():
    from service import app

    with TestClient(app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["energy_model_loaded"] is True
        stations = client.get("/api/v1/colombo-stations")
        assert stations.status_code == 200
        assert stations.json()["count"] == 67
        research = client.get("/api/v1/component4/research")
        assert research.status_code == 200
        assert research.json()["data_completeness"]["stations_in_inventory"] == 67
        assert stations.json()["stations"][0]["waiting_time_min"] is None
        bad = client.post("/api/v1/recommend", json={**VALID, "origin_latitude": 120})
        assert bad.status_code == 422
        app.state.bundle["condition_fetchers"] = OFFLINE
        app.state.bundle["component4"]["provider"] = FakeRouter(
            app.state.bundle["component4"]["RouteLeg"],
            app.state.bundle["component4"]["RoutingError"],
        )
        ok = client.post("/api/v1/recommend", json=VALID)
        assert ok.status_code == 200
        body = ok.json()
        assert body["direct_route"]["provider"] == "mock"
        assert body["live_queue_prediction"] is False
        queue = body["recommended_station"]["queue_prediction"]
        assert queue["observed_queue_length"] is None
        assert queue["status"] in {"area_model", "unavailable"}
        assert body["charging_plan"]["status"] == "no_charge_needed"
        assert [row["strategy"] for row in body["strategy_comparison"]["rows"]][-1] == "optimised_plan"
        assert body["routing_summary"]["stations_routed"] > 4
        app.state.bundle["component4"]["provider"] = FakeRouter(
            app.state.bundle["component4"]["RouteLeg"],
            app.state.bundle["component4"]["RoutingError"],
            fail=True,
        )
        down = client.post("/api/v1/recommend", json=VALID)
        assert down.status_code == 503
        synthetic = client.get("/api/v1/synthetic/health")
        assert synthetic.status_code == 200
        assert synthetic.json()["all_models_loaded"] is True


def test_trip_check_and_plain_summary_use_only_result_numbers():
    result = build_recommendation(TripRequest(**VALID), _deps(), explain=True)
    trip = result["trip_check"]
    assert trip["direct_energy_kwh"] == pytest.approx(1.2)
    assert trip["soc_at_destination_without_charging_percent"] == pytest.approx(77.0)
    assert trip["can_finish_without_charging"] is True
    plan = result["recommended_station"]["trip_plan"]
    # Reserve 10% plus the 3% onward leg.
    assert plan["minimum_target_soc_percent"] == pytest.approx(13.0)
    assert plan["charging_energy_kwh"] is None
    assert "without charging" in result["quick_answer"][0]
    assert "at least 13%" in result["recommended_station"]["plain_summary"]
    ok, reason = explanation_matches(result["explanation"]["text"], result)
    assert ok, reason


def test_target_already_met_on_arrival_needs_no_charge():
    body = TripRequest(**{**VALID, "target_soc_percent": 70, "user_tariff_lkr_per_kwh": 50})
    result = build_recommendation(body, _deps(), explain=True)
    station = result["recommended_station"]
    assert station["trip_plan"]["charging_energy_kwh"] == 0
    assert station["scenario_cost_lkr"] == 0
    assert "no charge is needed" in station["plain_summary"]
    ok, reason = explanation_matches(result["explanation"]["text"], result)
    assert ok, reason


def test_target_too_low_for_onward_leg_is_warned():
    body = TripRequest(**{**VALID, "current_soc_percent": 16, "target_soc_percent": 12})
    result = build_recommendation(body, _deps(), explain=True)
    plan = result["recommended_station"]["trip_plan"]
    # Arrive at 13%; the 12% target is already met, and the 3% onward leg leaves exactly the 10% reserve.
    assert plan["reaches_destination_with_reserve"] is True
    body = TripRequest(**{**VALID, "current_soc_percent": 16, "minimum_reserve_percent": 12, "target_soc_percent": 14})
    result = build_recommendation(body, _deps(), explain=True)
    plan = result["recommended_station"]["trip_plan"]
    assert plan["arrival_soc_percent"] == pytest.approx(13.0)
    assert plan["soc_at_destination_percent"] == pytest.approx(11.0)
    assert plan["reaches_destination_with_reserve"] is False
    assert any("at least 15%" in warning for warning in result["warnings"])
    ok, reason = explanation_matches(result["explanation"]["text"], result)
    assert ok, reason


CONDITIONS = {
    "elevation_gain_m": 20,
    "elevation_loss_m": 15,
    "ambient_temperature_c": 30,
    "ac_on": 1,
    "traffic_level": "medium",
    "road_type": "urban",
    "vehicle_mass_kg": 1800,
}


def test_energy_model_replaces_the_flat_rate_only_when_conditions_are_complete():
    component3 = load_component3()
    assert component3["energy_model_loaded"] is True
    assert component3["selected_model"]
    skipped = build_recommendation(
        TripRequest(**{**VALID, "energy_conditions": {**CONDITIONS, "traffic_level": "gridlock"}}),
        _deps(),
        explain=False,
    )
    assert skipped["energy_and_cost"]["energy_model_applied"] is False
    assert skipped["trip_check"]["direct_energy_kwh"] == pytest.approx(1.2)
    used = build_recommendation(TripRequest(**{**VALID, "energy_conditions": CONDITIONS}), _deps(), explain=True)
    assert used["energy_and_cost"]["energy_model_applied"] is True
    assert used["models"]["energy"]["training_data"] == "synthetic"
    assert used["recommended_station"]["battery"]["method"] == "larger of the Component 3 model and your consumption rate"
    battery = used["recommended_station"]["battery"]
    assert battery["estimated_energy_kwh"] == max(battery["model_energy_kwh"], battery["rate_energy_kwh"])
    assert used["recommended_station"]["drive_energy_model"]["predicted_energy_kwh"] > 0
    assert "soc_end_pct" in used["models"]["energy"]["excluded_as_leakage"]
    ok, reason = explanation_matches(used["explanation"]["text"], used)
    assert ok, reason


def test_timeline_adds_drive_wait_and_charge_in_order():
    from orchestrate import _timeline

    departure = datetime(2026, 10, 22, 9, 0, tzinfo=SRI_LANKA)
    station = {
        "included_in_ranking": True,
        "origin_to_station": {"duration_min": 15.0},
        "station_to_destination": {"duration_min": 20.0},
        "queue_prediction": {"status": "area_model", "predicted_waiting_time_min": 10.0},
        "listed_power_duration_min": 30.0,
    }
    timeline = _timeline(station, departure)
    assert timeline["arrive_at_station_time"].startswith("2026-10-22T09:15")
    assert timeline["start_charging_time"].startswith("2026-10-22T09:25")
    assert timeline["charging_complete_time"].startswith("2026-10-22T09:55")
    assert timeline["arrive_destination_time"].startswith("2026-10-22T10:15")
    assert timeline["missing"] == []
    # Without a queue forecast or a target charge level, those parts are named as missing, not set to zero.
    bare = _timeline({**station, "queue_prediction": {"status": "unavailable"}, "listed_power_duration_min": None}, departure)
    assert bare["charging_complete_time"] is None
    assert len(bare["missing"]) == 2
    assert _timeline({**station, "included_in_ranking": False}, departure) == {"available": False}


def test_duration_and_cost_endpoints():
    from service import app

    with TestClient(app) as client:
        schema = client.get("/api/v1/duration-schema").json()
        features = {
            column: schema["categories"][column][0] if column in schema["categories"] else 30
            for column in schema["feature_columns"]
        }
        ok = client.post("/api/v1/duration/predict", json={"features": features, "charging_start_time": "2026-10-22T14:00"})
        assert ok.status_code == 200, ok.text
        body = ok.json()
        minutes = body["predicted_charging_duration_min"]
        expected = datetime(2026, 10, 22, 14, 0) + timedelta(minutes=minutes)
        assert body["expected_completion_time"] == expected.isoformat(timespec="minutes")
        assert body["test_metrics"]["mae_min"] > 0
        leaked = client.post(
            "/api/v1/duration/predict",
            json={"features": {**features, "Charging End Time": "2024-01-01 02:00:00"}},
        )
        assert leaked.status_code == 422
        missing = client.post("/api/v1/duration/predict", json={"features": {}})
        assert missing.status_code == 422 and "Nothing was guessed" in missing.text
        cost = client.post("/api/v1/energy/cost", json={"energy_kwh": 9, "tariff_lkr_per_kwh": 100, "charging_efficiency": 0.9})
        assert cost.status_code == 200
        assert cost.json()["estimated_total"] == pytest.approx(1000)
        assert client.get("/api/v1/unknown").status_code == 404


def test_automatic_conditions_feed_the_energy_model_and_trip_energy():
    deps = _deps()
    deps["condition_fetchers"] = {
        "weather_fetcher": lambda latitude, longitude: {"temperature_c": 31.0, "weather_text": "Clear sky"},
        "elevation_fetcher": lambda geometry: {"elevation_gain_m": 40.0, "elevation_loss_m": 12.0},
    }
    result = build_recommendation(TripRequest(**VALID), deps, explain=False)
    assert result["energy_and_cost"]["energy_model_applied"] is True
    conditions = result["trip_conditions"]
    assert conditions["weather"]["temperature_c"] == 31.0
    assert conditions["elevation"]["elevation_gain_m"] == 40.0
    assert conditions["road_type"] in {"urban", "mixed", "highway"}
    energy = result["trip_energy"]
    assert energy["rate_kwh"] == pytest.approx(1.2)
    assert energy["used_kwh"] == max(energy["model_kwh"], energy["rate_kwh"])
    assert energy["arrival_soc_percent"] == pytest.approx(80 - energy["used_kwh"] / 40 * 100)


def test_missing_weather_leaves_the_energy_model_off():
    result = build_recommendation(TripRequest(**VALID), _deps(), explain=False)
    assert result["energy_and_cost"]["energy_model_applied"] is False
    assert "weather (Open-Meteo did not answer)" in result["trip_conditions"]["missing"]
    assert result["trip_energy"]["model_kwh"] is None
    assert result["trip_energy"]["used_kwh"] == pytest.approx(1.2)


def test_elevation_profile_ignores_small_noise():
    from conditions import fetch_elevation_profile
    import conditions

    original = conditions._get
    conditions._get = lambda url, timeout: {"elevation": [10, 11, 10, 30, 29, 60, 40]}
    try:
        profile = fetch_elevation_profile([[6.9, 79.8]] * 7)
    finally:
        conditions._get = original
    assert profile["elevation_gain_m"] == pytest.approx(50.0)
    assert profile["elevation_loss_m"] == pytest.approx(20.0)


def test_plan_and_trip_energy_agree_on_charging():
    deps = _deps()
    deps["condition_fetchers"] = {
        "weather_fetcher": lambda latitude, longitude: {"temperature_c": 31.0, "weather_text": "Clear sky"},
        "elevation_fetcher": lambda geometry: {"elevation_gain_m": 40.0, "elevation_loss_m": 12.0},
    }
    for soc in (12, 14, 16, 30, 80):
        result = build_recommendation(TripRequest(**{**VALID, "current_soc_percent": soc}), deps, explain=False)
        energy = result["trip_energy"]
        assert result["planning_consumption_kwh_per_100km"] >= VALID["consumption_kwh_per_100km"]
        no_charge = result["charging_plan"]["status"] == "no_charge_needed"
        # A plan that skips charging must match a trip the battery figures say can be finished.
        assert no_charge == energy["can_finish_without_charging"], (soc, energy, result["charging_plan"]["status"])


def test_recommended_station_always_gets_a_road_line():
    from orchestrate import _plan_road, _with_road_shape

    deps = _deps()
    body = TripRequest(**VALID)
    # The planner leaves road shapes off stations outside its own top three.
    station = {
        "latitude": 6.9,
        "longitude": 79.87,
        "origin_to_station": {"distance_km": 3.0, "duration_min": 8.0, "geometry": None},
        "station_to_destination": {"distance_km": 5.0, "duration_min": 9.0, "geometry": None},
    }
    shaped = _with_road_shape(station, body, deps)
    assert len(shaped["origin_to_station"]["geometry"]) >= 2
    assert len(shaped["station_to_destination"]["geometry"]) >= 2
    plan = {"stops": [{"latitude": 6.9, "longitude": 79.87}, {"latitude": 6.88, "longitude": 79.88}]}
    route = _plan_road(plan, body, deps)
    assert route["stops"] == 2 and len(route["geometry"]) >= 2
    failing = _deps(fail_route=True)
    assert _plan_road(plan, body, failing)["geometry"] is None
