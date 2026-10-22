"""Smoke test of a running deployment: every component, the dashboard and the research data."""

import json
import sys
import time
import urllib.request

BASE = sys.argv[1].rstrip("/")
failures = []


def call(path, body=None, timeout=120):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(BASE + path, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            kind = response.headers.get("content-type", "")
            return response.status, (json.loads(raw) if "json" in kind else raw.decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  {detail}" if detail else ""))
    if not ok:
        failures.append(name)


for _ in range(90):
    try:
        status, health = call("/health", timeout=5)
        if status == 200:
            break
    except Exception:  # noqa: BLE001
        time.sleep(1)
check("health", status == 200 and not health.get("load_errors"), json.dumps(health.get("components", {}).get("queue_waiting_congestion", {}).get("queue", {}).get("model_name")))
c = health.get("components", {})
check("all models loaded", c.get("duration_model_loaded") and c.get("energy_model_loaded") and c.get("route_optimizer_loaded"))

status, page = call("/")
check("dashboard served at /", status == 200 and "<div id=\"root\">" in page)
asset = page.split('src="')[1].split('"')[0] if 'src="' in page else ""
status, _ = call(asset)
check("dashboard script served", status == 200, asset)

status, stations = call("/api/v1/colombo-stations")
check("67 stations", status == 200 and stations.get("count") == 67, str(stations.get("count")))

status, research = call("/api/v1/component4/research")
check("component 4 research", status == 200 and research["routing_evaluation"]["strategies"]["optimised_plan"]["success_rate"] > 0.5)

status, synthetic = call("/api/v1/synthetic/stations")
check("component 1 stations", status == 200 and len(synthetic["stations"]) == 5)
status, now = call("/api/v1/synthetic/predict/station-now", {"station_id": "ST01", "use_current_time": True, "include_llm": False})
check("component 1 station-now", status == 200 and now["predictions"]["waiting_time"]["predicted_waiting_time_min"] is not None)

status, schema = call("/api/v1/duration-schema")
check("component 2 schema", status == 200 and len(schema["feature_columns"]) == 12)
features = {}
for column in schema["feature_columns"]:
    features[column] = schema["categories"][column][0] if column in schema["categories"] else 30
status, duration = call("/api/v1/duration/predict", {"features": features, "charging_start_time": "2026-10-22T14:00"})
check("component 2 prediction + completion", status == 200 and duration.get("expected_completion_time"), str(duration.get("expected_completion_time") if status == 200 else duration)[:120])

status, eschema = call("/api/v1/energy-schema")
check("component 3 schema", status == 200 and eschema["test_metrics"]["r2"] > 0.8)
record = {"distance_km": 115, "average_speed_kmh": 52, "trip_duration_min": 132, "battery_capacity_kwh": 40, "soc_start_pct": 80,
          "elevation_gain_m": 500, "elevation_loss_m": 20, "ambient_temperature_c": 30, "ac_on": 1, "vehicle_mass_kg": 1700,
          "traffic_level": "medium", "road_type": "mixed"}
status, energy = call("/api/v1/energy/predict", record)
check("component 3 prediction", status == 200 and energy["predicted_energy_kwh"] > 0, str(energy.get("predicted_energy_kwh") if status == 200 else energy)[:80])
status, cost = call("/api/v1/energy/cost", {"energy_kwh": 10, "tariff_lkr_per_kwh": 120})
check("component 3 cost", status == 200 and cost["estimated_total"] == 1200)

trip = {
    "origin_latitude": 6.9339, "origin_longitude": 79.85, "destination_latitude": 6.8428, "destination_longitude": 79.9534,
    "current_soc_percent": 40, "usable_battery_capacity_kwh": 39, "consumption_kwh_per_100km": 16, "minimum_reserve_percent": 10,
    "required_connector": "CHAdeMO", "target_soc_percent": 80, "user_tariff_lkr_per_kwh": 120, "include_explanation": True,
    "energy_conditions": {"elevation_gain_m": 10, "elevation_loss_m": 10, "ambient_temperature_c": 30, "ac_on": True,
                          "traffic_level": "medium", "road_type": "urban", "vehicle_mass_kg": 1700},
}
started = time.time()
status, result = call("/api/v1/recommend", trip, timeout=180)
check("trip (OSRM live)", status == 200, f"{time.time() - started:.1f}s" if status == 200 else str(result)[:200])
if status == 200:
    best = result["recommended_station"]
    check("C1 in trip", best["queue_prediction"]["status"] == "area_model", best["queue_prediction"].get("trained_area"))
    check("C2 completion time in trip", bool(best["timeline"].get("charging_complete_time")), best["timeline"].get("charging_complete_time"))
    check("C3 energy model applied", result["energy_and_cost"]["energy_model_applied"], f"{result['trip_check']['direct_energy_kwh']:.2f} kWh")
    check("C3 cost in trip", result["energy_and_cost"]["scenario_cost"]["estimated_total"] > 0)
    check("C4 plan + strategies", result["charging_plan"]["status"] in ("planned", "no_charge_needed") and len(result["strategy_comparison"]["rows"]) == 4)
    check("congestion metrics", result["models"]["congestion"]["test_metrics"]["macro_f1"] > 0)
    check("explanation", bool(result.get("explanation", {}).get("text")))

status, missing = call("/api/v1/does-not-exist")
check("unknown API path is 404", status == 404)
print("FAILURES:", failures or "none")
