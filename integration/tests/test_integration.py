"""Integration tests. Routing is mocked. Model tests that load artifacts are marked."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bootstrap import load_component1, load_component2, load_component3, load_component4
from explain import explanation_matches, template_explanation
from orchestrate import TripRequest, build_recommendation

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


def _deps(fail_route=False):
    component4 = load_component4()
    component3 = load_component3()
    component4["provider"] = FakeRouter(component4["RouteLeg"], component4["RoutingError"], fail=fail_route)
    return {
        "component4": component4,
        "component3": component3,
        "component2": None,
        "component1": None,
        "errors": {},
    }


def test_four_colombo_stations_load_from_csv():
    stations = load_component4()["load_stations"]()
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


def test_recommendation_uses_mock_routes_and_leaves_queue_unknown():
    result = build_recommendation(TripRequest(**VALID), _deps(), explain=True)
    assert result["direct_route"]["provider"] == "mock"
    assert result["recommended_route"]["provider"] == "mock"
    assert len(result["recommended_route"]["geometry"]) >= 2
    assert result["recommended_station"]["station_id"] == "ST001"
    assert result["recommended_station"]["queue_prediction"]["predicted_waiting_time_min"] is None
    assert result["recommended_station"]["queue_prediction"]["observed_queue_length"] is None
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


def test_listed_power_duration_changes_rank_and_missing_tariff_stays_empty():
    body = TripRequest(**{**VALID, "target_soc_percent": 100})
    result = build_recommendation(body, _deps(), explain=False)
    by_id = {result["recommended_station"]["station_id"]: result["recommended_station"]}
    for item in result["alternatives"]:
        by_id[item["station_id"]] = item
    # Mock legs are 8 km at 15 kWh/100 km: 1.2 kWh, so the car arrives at 77%, not 80%.
    # 40 kWh * (100 - 77) / 100 = 9.2 kWh; 9.2 / 30 kW * 60 = 18.4 min.
    assert by_id["ST001"]["trip_plan"]["arrival_soc_percent"] == pytest.approx(77.0)
    assert by_id["ST001"]["listed_power_duration_min"] == pytest.approx(18.4)
    assert by_id["ST004"]["listed_power_duration_min"] > by_id["ST001"]["listed_power_duration_min"]
    assert by_id["ST004"]["rank"] == 4
    assert by_id["ST001"]["scenario_cost_lkr"] is None
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


def test_duration_model_requires_real_features_and_rejects_colombo():
    component2 = load_component2()
    deps = _deps()
    deps["component2"] = component2
    columns = component2["feature_columns"]
    temperature = next(column for column in columns if column.startswith("Temperature"))
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
        "Distance Driven (since last charge) (km)": 15,
        "Vehicle Age (years)": 3,
        temperature: 28,
        "Vehicle Model": "Nissan Leaf",
        "Charging Station Location": "Colombo",
        "Time of Day": "Morning",
        "Day of Week": "Monday",
        "Charger Type": "DC Fast Charger",
        "User Type": "Commuter",
    }
    rejected = build_recommendation(TripRequest(**{**VALID, "duration_features": record}), deps, explain=False)
    assert rejected["charging_duration"]["status"] == "unavailable"
    record["Charging Station Location"] = "New York"
    predicted = build_recommendation(TripRequest(**{**VALID, "duration_features": record}), deps, explain=False)
    assert predicted["charging_duration"]["status"] == "predicted"
    assert predicted["charging_duration"]["predicted_charging_duration_min"] > 0
    assert predicted["charging_duration"]["used_in_ranking"] is False
    assert predicted["recommended_station"]["queue_prediction"]["predicted_waiting_time_min"] is None


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
        assert stations.json()["count"] == 4
        assert stations.json()["stations"][0]["waiting_time_min"] is None
        bad = client.post("/api/v1/recommend", json={**VALID, "origin_latitude": 120})
        assert bad.status_code == 422
        app.state.bundle["component4"]["provider"] = FakeRouter(
            app.state.bundle["component4"]["RouteLeg"],
            app.state.bundle["component4"]["RoutingError"],
        )
        ok = client.post("/api/v1/recommend", json=VALID)
        assert ok.status_code == 200
        body = ok.json()
        assert body["direct_route"]["provider"] == "mock"
        assert body["live_queue_prediction"] is False
        assert body["recommended_station"]["queue_prediction"]["status"] == "unavailable"
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
    assert used["recommended_station"]["battery"]["method"] == "component3_energy_model"
    assert used["recommended_station"]["drive_energy_model"]["predicted_energy_kwh"] > 0
    assert "soc_end_pct" in used["models"]["energy"]["excluded_as_leakage"]
    ok, reason = explanation_matches(used["explanation"]["text"], used)
    assert ok, reason
