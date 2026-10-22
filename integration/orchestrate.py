"""Combine the four components. Missing predictions stay missing."""

from __future__ import annotations

import copy
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import BaseModel, Field

from area_models import match_trained_area
from conditions import automatic_conditions

logger = logging.getLogger("integration.orchestrate")

DEFAULT_WEIGHTS = {
    "detour_distance": 0.40,
    "detour_time": 0.30,
    "waiting_time": 0.15,
    "listed_power_duration": 0.15,
    "scenario_cost": 0.10,
}

QUEUE_REASON = (
    "No queue, waiting time or congestion estimate for this charger. "
    "The synthetic area models cover Nugegoda, Rajagiriya, Malabe, Pannipitiya and Panadura, "
    "and this listing is not close to those towns. The blank listing was not filled with zero."
)

DURATION_REASON = (
    "The Component 2 model predicts charging minutes from battery size, charger power, "
    "the charge on arrival, and the requested end charge. "
    "In its training table the duration is that energy divided by power, and it matches the clock. "
    "It was not applied because those inputs were not available. No duration was invented."
)


class TripRequest(BaseModel):
    origin_latitude: float = Field(..., ge=-90, le=90)
    origin_longitude: float = Field(..., ge=-180, le=180)
    destination_latitude: float = Field(..., ge=-90, le=90)
    destination_longitude: float = Field(..., ge=-180, le=180)
    current_soc_percent: float = Field(..., ge=0, le=100)
    usable_battery_capacity_kwh: float = Field(..., gt=0)
    consumption_kwh_per_100km: float = Field(..., gt=0)
    minimum_reserve_percent: float = Field(..., ge=0, le=100)
    required_connector: str | None = None
    target_soc_percent: float | None = Field(default=None, ge=0, le=100)
    user_tariff_lkr_per_kwh: float | None = Field(default=None, ge=0)
    charging_efficiency: float | None = Field(default=None, gt=0, le=1)
    maximum_detour_km: float | None = Field(default=None, gt=0)
    duration_features: dict[str, Any] | None = None
    energy_conditions: dict[str, Any] | None = None
    ranking_weights: dict[str, float] | None = None
    max_charge_soc_percent: float = Field(default=80, gt=0, le=100)
    # Local departure time for the trip timeline. Defaults to now in Sri Lanka.
    departure_time: datetime | None = None
    stop_overhead_min: float = Field(default=5, ge=0, le=60)
    # When energy_conditions is not sent, read weather and road elevation for this trip.
    auto_conditions: bool = True
    vehicle_mass_kg: float = Field(default=1650, gt=500, le=4000)
    ac_on: bool = True
    traffic_level: str | None = None
    road_type: str | None = None
    include_explanation: bool = True
    follow_up_question: str | None = None


# Sri Lanka has no daylight saving, so a fixed offset is exact.
SRI_LANKA = timezone(timedelta(hours=5, minutes=30), "Asia/Colombo")


def _departure(body: "TripRequest") -> datetime:
    if body.departure_time is None:
        return datetime.now(SRI_LANKA).replace(second=0, microsecond=0)
    departure = body.departure_time
    return departure if departure.tzinfo else departure.replace(tzinfo=SRI_LANKA)


def _clock(moment: datetime) -> str:
    return moment.isoformat(timespec="minutes")


def _timeline(station: dict, departure: datetime) -> dict[str, Any]:
    """Clock times for one station: drive there, wait (Component 1 when applied), charge, drive on.

    A part that was not estimated stays out of the sum and is named in `missing`,
    so a completion time is never shown as more certain than its parts.
    """
    to_station = station.get("origin_to_station") or {}
    onward = station.get("station_to_destination") or {}
    if not station.get("included_in_ranking") or to_station.get("duration_min") is None:
        return {"available": False}
    arrive = departure + timedelta(minutes=to_station["duration_min"])
    queue = station.get("queue_prediction") or {}
    wait = queue.get("predicted_waiting_time_min") if queue.get("status") == "area_model" else None
    charge = station.get("listed_power_duration_min")
    missing = []
    if wait is None:
        missing.append("waiting time (no queue forecast for this charger)")
    if charge is None:
        missing.append("charging time (the Component 2 duration model did not return a session length)")
    start_charging = arrive + timedelta(minutes=wait or 0)
    done = start_charging + timedelta(minutes=charge or 0)
    arrive_destination = done + timedelta(minutes=onward["duration_min"]) if onward.get("duration_min") is not None else None
    return {
        "available": True,
        "departure_time": _clock(departure),
        "arrive_at_station_time": _clock(arrive),
        "predicted_wait_min": wait,
        "start_charging_time": _clock(start_charging),
        "charging_min": charge,
        "charging_complete_time": _clock(done) if charge is not None else None,
        "arrive_destination_time": _clock(arrive_destination) if arrive_destination else None,
        "missing": missing,
        "basis": (
            "Road times from the routing provider (not live traffic)"
            + (", the Component 1 synthetic waiting-time forecast for the nearest trained town" if wait is not None else "")
            + (
                ", and the Component 2 charging-duration model for the session length."
                if charge is not None
                else "."
            )
        ),
    }


def _congestion_metrics(report: dict | None) -> dict | None:
    """Accuracy and macro F1 with the majority-class baseline. Classes are imbalanced, so accuracy alone misleads."""
    selected = (report or {}).get("test_metrics_selected")
    if not selected:
        return None
    baseline = ((report or {}).get("baselines_test") or {}).get("most_frequent") or {}
    return {
        "accuracy": selected.get("accuracy"),
        "macro_f1": selected.get("macro_f1"),
        "n": selected.get("n"),
        "baseline_most_frequent_accuracy": baseline.get("accuracy"),
        "baseline_most_frequent_macro_f1": baseline.get("macro_f1"),
    }


def _out_of_range(deps: dict[str, Any], record: dict[str, Any]) -> list[dict[str, Any]]:
    ranges = (deps.get("component3") or {}).get("feature_ranges") or {}
    flagged = []
    for name, (low, high) in ranges.items():
        value = record.get(name)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and (value < low or value > high):
            flagged.append({"feature": name, "value": value, "training_min": low, "training_max": high})
    return flagged


def _trip_energy(body: "TripRequest", deps: dict[str, Any], direct: dict | None, energy_ctx: dict) -> dict[str, Any] | None:
    """Battery needed for the direct drive: the Component 3 model next to the car's consumption rate."""
    if not direct or not direct.get("distance_km"):
        return None
    km = direct["distance_km"]
    rate = _road_kwh(body, km)
    model = direct.get("model_only_energy_kwh")
    used = max(model, rate) if model is not None else rate
    record = {
        "distance_km": km,
        "trip_duration_min": direct.get("duration_min"),
        "average_speed_kmh": km / (direct["duration_min"] / 60.0) if direct.get("duration_min") else None,
        "battery_capacity_kwh": body.usable_battery_capacity_kwh,
        "soc_start_pct": body.current_soc_percent,
        **(body.energy_conditions or {}),
    }
    return {
        "distance_km": km,
        "duration_min": direct.get("duration_min"),
        "model_kwh": model,
        "rate_kwh": rate,
        "used_kwh": used,
        "used_basis": (
            "Component 3 model" if model is not None and model >= rate else "your car's consumption rate"
        ),
        "battery_percent_needed": _soc_points(body, used),
        "arrival_soc_percent": body.current_soc_percent - _soc_points(body, used),
        "model_kwh_per_100km": model / km * 100 if model is not None else None,
        "rate_kwh_per_100km": body.consumption_kwh_per_100km,
        "can_finish_without_charging": body.current_soc_percent - _soc_points(body, used) >= body.minimum_reserve_percent,
        "model_applied": bool(energy_ctx.get("applied")),
        "out_of_training_range": _out_of_range(deps, record) if model is not None else [],
        "note": (
            "Battery checks use the larger of the two estimates, so a low model prediction never makes a trip look "
            "possible when your car's own consumption rate says it is not."
        ),
    }


class _Point:
    """A latitude/longitude pair in the shape the routing provider reads."""

    def __init__(self, latitude: float, longitude: float):
        self.latitude = latitude
        self.longitude = longitude


def _prepare_energy(body: "TripRequest", deps: dict[str, Any], departure: datetime) -> tuple["TripRequest", dict | None, float]:
    """Read trip conditions and pick the consumption rate the route planner uses.

    The energy model needs the direct road (distance, time, climb), so that road is
    requested first; the routing client caches it, so planning does not ask again.
    Returns the request with conditions filled in, where they came from, and the
    planning rate: the larger of your rate and the model's rate on the direct road.
    """
    trip_conditions = None
    consumption = body.consumption_kwh_per_100km
    if body.energy_conditions is None and not body.auto_conditions:
        return body, None, consumption
    try:
        leg = deps["component4"]["provider"].route(
            _Point(body.origin_latitude, body.origin_longitude),
            _Point(body.destination_latitude, body.destination_longitude),
        )
        direct = leg.model_dump()
    except Exception:  # noqa: BLE001 — routing errors are reported by the planner below
        return body, None, consumption
    if body.energy_conditions is None:
        conditions, trip_conditions = automatic_conditions(
            (body.origin_latitude, body.origin_longitude),
            direct,
            departure,
            body.vehicle_mass_kg,
            body.ac_on,
            body.traffic_level,
            body.road_type,
            **(deps.get("condition_fetchers") or {}),
        )
        if conditions is not None:
            body = body.model_copy(update={"energy_conditions": conditions})
    ctx = _energy_context(body, deps)
    if ctx["applied"] and direct.get("distance_km") and direct.get("duration_min"):
        try:
            model_kwh = _predict_leg_kwh(
                body, deps, ctx, direct["distance_km"], direct["duration_min"], body.current_soc_percent
            )
            consumption = max(consumption, model_kwh / direct["distance_km"] * 100.0)
        except Exception:  # noqa: BLE001
            logger.exception("Energy model failed on the direct road; planning uses your rate")
    return body, trip_conditions, consumption


def _plan_arrival(plan: dict | None, departure: datetime) -> str | None:
    totals = (plan or {}).get("totals") or {}
    if totals.get("total_min") is None:
        return None
    return _clock(departure + timedelta(minutes=totals["total_min"]))


def _penalty(value: float, values: list[float]) -> float:
    low, high = min(values), max(values)
    if high == low:
        return 0.0
    return (value - low) / (high - low)


def rank_candidates(stations: list[dict], weights: dict[str, float]) -> str:
    """Rank only stations the route layer already marked feasible. Lower factors are better."""
    pool = [station for station in stations if station.get("included_in_ranking")]
    if len(pool) == 1:
        only = pool[0]
        only["score"] = 1.0
        only["rank"] = 1
        only["factor_contributions"] = []
        only["ranking_explanation"] = (
            "Only one station passed the battery and connector checks, so numeric factors were not compared."
        )
        return (
            "One station is feasible. It is selected because the others were excluded, "
            "not because missing waiting time or tariff was treated as zero."
        )
    present_rows = []
    for station in pool:
        present_rows.append(
            {
                "detour_distance": station.get("detour_distance_km"),
                "detour_time": station.get("detour_duration_min"),
                "waiting_time": (station.get("queue_prediction") or {}).get("predicted_waiting_time_min"),
                "listed_power_duration": station.get("listed_power_duration_min"),
                "scenario_cost": station.get("scenario_cost_lkr"),
            }
        )
    comparable: dict[str, list[float]] = {}
    for name in DEFAULT_WEIGHTS:
        if weights.get(name, 0) <= 0:
            continue
        values = [row[name] for row in present_rows if row[name] is not None]
        if len(values) >= 2:
            comparable[name] = values
    for station, present in zip(pool, present_rows):
        active = {name: weights[name] for name in comparable if present[name] is not None}
        total = sum(active.values())
        contributions = []
        if total <= 0:
            station["score"] = None
            station["rank"] = None
            station["included_in_ranking"] = False
            station["ranking_explanation"] = "Ranking could not be completed because every weighted factor is missing."
            continue
        score = 0.0
        for name, weight in active.items():
            factor_score = 1.0 - _penalty(present[name], comparable[name])
            share = weight / total
            score += share * factor_score
            contributions.append(
                {
                    "factor": name,
                    "value": present[name],
                    "factor_score": round(factor_score, 3),
                    "weight": round(share, 3),
                }
            )
        dropped = [name for name, value in present.items() if value is None and weights.get(name, 0) > 0]
        skipped = [
            name
            for name in present
            if name not in comparable and present[name] is not None and weights.get(name, 0) > 0
        ]
        station["score"] = score
        station["factor_contributions"] = contributions
        station["ranking_explanation"] = (
            f"Score {score:.3f} from {', '.join(item['factor'] for item in contributions)}. "
            "Battery feasibility and connector compatibility are constraints, not score points. "
            + (f"Omitted missing factors (not treated as zero): {', '.join(dropped)}. " if dropped else "")
            + (
                f"Not compared because fewer than two feasible stations have a value: {', '.join(skipped)}. "
                if skipped
                else ""
            )
        )
    ordered = sorted(
        [station for station in pool if station.get("score") is not None],
        key=lambda station: (-station["score"], station["station_id"]),
    )
    for index, station in enumerate(ordered, start=1):
        station["rank"] = index
    used = ", ".join(sorted(comparable)) if comparable else "none"
    omitted = [name for name in DEFAULT_WEIGHTS if name not in comparable and weights.get(name, 0) > 0]
    return (
        f"Feasible stations are ranked only after battery and connector checks. "
        f"Compared factors: {used}. "
        f"Left out because they were missing or not comparable: {', '.join(omitted) if omitted else 'none'}. "
        "Missing values were not set to zero. A lower detour, wait, Component 2 session duration or scenario cost scores higher. "
        "Session duration is the saved Component 2 model. Listed kilowatts are not used for that time. "
        "An infeasible station cannot win on score."
    )


CHARGING_NOTE = (
    "Charging energy is usable capacity times the rise from the SOC on arrival at the station "
    "(after the drive there) to the target SOC. "
    "This is vehicle battery energy, not a trained Component 3 prediction and not grid energy."
)


ENERGY_CONDITIONS = (
    "elevation_gain_m",
    "elevation_loss_m",
    "ambient_temperature_c",
    "ac_on",
    "traffic_level",
    "road_type",
    "vehicle_mass_kg",
)


def _road_kwh(body: TripRequest, distance_km: float) -> float:
    return distance_km * body.consumption_kwh_per_100km / 100.0


def _energy_context(body: TripRequest, deps: dict[str, Any]) -> dict[str, Any]:
    """Decide whether this search may call the saved energy model. Missing inputs stay missing."""
    component3 = deps.get("component3") or {}
    if not component3.get("energy_model_loaded") or component3.get("predict_energy") is None:
        return {
            "status": "unavailable",
            "applied": False,
            "reason": component3.get("energy_model_reason") or "No energy model is loaded.",
        }
    conditions = body.energy_conditions
    if not conditions:
        return {
            "status": "not_applied",
            "applied": False,
            "reason": (
                "The energy model is loaded but this search did not include elevation, temperature, "
                "air conditioning, traffic, road type, and vehicle mass. Those values were not guessed. "
                "Drive energy uses the consumption figure you entered."
            ),
        }
    missing = [key for key in ENERGY_CONDITIONS if conditions.get(key) in (None, "")]
    if missing:
        return {
            "status": "not_applied",
            "applied": False,
            "reason": (
                "The energy model was not used because these inputs were missing: "
                + ", ".join(missing)
                + ". Drive energy uses the consumption figure you entered."
            ),
        }
    air = conditions.get("ac_on")
    if air in (True, 1, "1"):
        air_value = 1
    elif air in (False, 0, "0"):
        air_value = 0
    else:
        return {
            "status": "not_applied",
            "applied": False,
            "reason": "Air conditioning must be on or off. The energy model was not used.",
        }
    categories = component3.get("categories") or {}
    for column in ("traffic_level", "road_type"):
        allowed = [str(item) for item in categories.get(column, [])]
        if allowed and str(conditions.get(column)) not in allowed:
            return {
                "status": "not_applied",
                "applied": False,
                "reason": f"{column} must be one of {allowed}. The energy model was not used.",
            }
    cleaned = {key: conditions[key] for key in ENERGY_CONDITIONS if key != "ac_on"}
    cleaned["ac_on"] = air_value
    return {
        "status": "ready",
        "applied": True,
        "conditions": cleaned,
        "reason": (
            "Drive energy is the saved energy model for each road leg. "
            "Distance and duration come from the routing provider, and speed is distance divided by that duration. "
            "Elevation, temperature, air conditioning, traffic, road type, and vehicle mass are the values in this request. "
            "The training trips are synthetic. Ending state of charge was not an input."
        ),
    }


def _predict_leg_kwh(
    body: TripRequest,
    deps: dict[str, Any],
    ctx: dict[str, Any],
    distance_km: float | None,
    duration_min: float | None,
    soc_start: float,
) -> float:
    if distance_km is None or duration_min is None or duration_min <= 0:
        raise ValueError("Road distance or duration is missing, so the energy model was not given a speed.")
    component3 = deps["component3"]
    conditions = dict(ctx["conditions"])
    route_km = ctx.get("route_km")
    if route_km:
        # Climb and descent were measured over the whole direct route; each leg gets its share by distance.
        share = distance_km / route_km
        conditions["elevation_gain_m"] = conditions["elevation_gain_m"] * share
        conditions["elevation_loss_m"] = conditions["elevation_loss_m"] * share
    record = {
        "distance_km": distance_km,
        "trip_duration_min": duration_min,
        "average_speed_kmh": distance_km / (duration_min / 60.0),
        "battery_capacity_kwh": body.usable_battery_capacity_kwh,
        "soc_start_pct": soc_start,
        **conditions,
    }
    prediction = component3["predict_energy"](record, pipeline=component3["pipeline"], meta=component3["meta"])
    return float(prediction["predicted_energy_kwh"])


def _model_battery(body: TripRequest, energy_kwh: float, rate_kwh: float | None = None) -> dict[str, Any]:
    available = body.usable_battery_capacity_kwh * body.current_soc_percent / 100.0
    reserve = body.usable_battery_capacity_kwh * body.minimum_reserve_percent / 100.0
    above = available - reserve
    # Safety: never plan on less energy than the car's own consumption rate gives.
    used = max(energy_kwh, rate_kwh) if rate_kwh is not None else energy_kwh
    status = "feasible" if used <= above else "infeasible"
    return {
        "status": status,
        "estimated_energy_kwh": used,
        "model_energy_kwh": energy_kwh,
        "rate_energy_kwh": rate_kwh,
        "energy_above_reserve_kwh": above,
        "method": "larger of the Component 3 model and your consumption rate",
        "assumptions": [
            "Energy is the larger of the saved model prediction for this road leg and road km times your consumption rate.",
            "Distance and duration come from the routing provider.",
            "Average speed is that distance divided by that duration.",
            "The trip conditions in the request were used as supplied.",
            "This does not certify that the vehicle can arrive.",
        ],
    }


def _can_replace_battery(station: dict) -> bool:
    if station.get("connector_compatible") is False:
        return False
    if station.get("included_in_ranking"):
        return True
    return str(station.get("exclusion_reason") or "").startswith("Battery feasibility")


def _apply_energy_model(body: TripRequest, deps: dict[str, Any], routed: dict, stations: list[dict]) -> dict[str, Any]:
    ctx = _energy_context(body, deps)
    if not ctx["applied"]:
        return ctx
    try:
        direct = routed.get("direct_route")
        direct_kwh = None
        if direct and direct.get("distance_km"):
            ctx["route_km"] = direct["distance_km"]
        if direct:
            direct_kwh = _predict_leg_kwh(
                body,
                deps,
                ctx,
                direct.get("distance_km"),
                direct.get("duration_min"),
                body.current_soc_percent,
            )
        prepared = []
        for station in stations:
            if not _can_replace_battery(station):
                continue
            leg = station.get("origin_to_station") or {}
            energy = _predict_leg_kwh(
                body,
                deps,
                ctx,
                leg.get("distance_km"),
                leg.get("duration_min"),
                body.current_soc_percent,
            )
            onward = station.get("station_to_destination") or {}
            onward_kwh = None
            if onward.get("distance_km") is not None and onward.get("duration_min"):
                arrival = body.current_soc_percent - _soc_points(body, energy)
                onward_kwh = _predict_leg_kwh(
                    body,
                    deps,
                    ctx,
                    onward.get("distance_km"),
                    onward.get("duration_min"),
                    arrival,
                )
            prepared.append((station, energy, onward_kwh))
    except Exception as exc:  # noqa: BLE001
        logger.exception("Energy model was not applied")
        return {
            "status": "not_applied",
            "applied": False,
            "reason": f"The energy model was not applied: {exc} Drive energy uses the consumption figure you entered.",
        }
    if direct is not None and direct_kwh is not None:
        direct["model_only_energy_kwh"] = direct_kwh
        direct["model_energy_kwh"] = max(direct_kwh, _road_kwh(body, direct["distance_km"]))
    for station, energy, onward_kwh in prepared:
        leg_km = (station.get("origin_to_station") or {}).get("distance_km")
        battery = _model_battery(body, energy, _road_kwh(body, leg_km) if leg_km is not None else None)
        station["battery"] = battery
        station["drive_energy_model"] = {
            "predicted_energy_kwh": energy,
            "model_name": (deps.get("component3") or {}).get("selected_model"),
            "training_data": "synthetic",
        }
        if onward_kwh is not None:
            onward_km = (station.get("station_to_destination") or {}).get("distance_km")
            station["onward_model_energy_kwh"] = max(onward_kwh, _road_kwh(body, onward_km)) if onward_km else onward_kwh
        if battery["status"] != "feasible":
            station["included_in_ranking"] = False
            station["rank"] = None
            station["score"] = None
            station["exclusion_reason"] = "Battery feasibility is infeasible."
        else:
            station["included_in_ranking"] = True
            station["exclusion_reason"] = None
            station["rank"] = None
            station["score"] = None
    return ctx


def _soc_points(body: TripRequest, kwh: float) -> float:
    return kwh / body.usable_battery_capacity_kwh * 100.0


def _trip_check(body: TripRequest, direct: dict | None) -> dict[str, Any]:
    """Can the direct trip be finished above the reserve without charging? Same energy formula as the gate."""
    if not direct:
        return {
            "status": "unknown",
            "direct_energy_kwh": None,
            "soc_at_destination_without_charging_percent": None,
            "can_finish_without_charging": None,
            "note": "Direct road distance is missing, so the no-charge check was not made.",
        }
    modelled = direct.get("model_energy_kwh")
    kwh = modelled if modelled is not None else _road_kwh(body, direct["distance_km"])
    soc = body.current_soc_percent - _soc_points(body, kwh)
    can_finish = soc >= body.minimum_reserve_percent
    return {
        "status": "checked",
        "direct_energy_kwh": kwh,
        "soc_at_destination_without_charging_percent": round(soc, 1),
        "can_finish_without_charging": can_finish,
        "note": (
            "Direct-route energy is the saved energy model for that road leg. It is not a guarantee of arrival."
            if modelled is not None
            else (
                "Direct road km times your consumption figure, compared with your reserve. "
                "It is an approximation, not a guarantee of arrival."
            )
        ),
    }


def _station_plan(body: TripRequest, station: dict) -> dict[str, Any]:
    """Battery state along origin -> station -> destination, from road distances only."""
    plan: dict[str, Any] = {
        "arrival_soc_percent": None,
        "onward_energy_kwh": None,
        "minimum_target_soc_percent": None,
        "full_charge_insufficient": None,
        "charging_energy_kwh": None,
        "soc_at_destination_percent": None,
        "reaches_destination_with_reserve": None,
    }
    to_kwh = (station.get("battery") or {}).get("estimated_energy_kwh")
    if to_kwh is None:
        return plan
    arrival = body.current_soc_percent - _soc_points(body, to_kwh)
    plan["arrival_soc_percent"] = round(arrival, 1)
    onward = station.get("station_to_destination")
    onward_points = None
    if station.get("onward_model_energy_kwh") is not None:
        onward_kwh = station["onward_model_energy_kwh"]
        onward_points = _soc_points(body, onward_kwh)
        minimum = body.minimum_reserve_percent + onward_points
        plan["onward_energy_kwh"] = onward_kwh
        plan["minimum_target_soc_percent"] = round(minimum, 1)
        plan["full_charge_insufficient"] = minimum > 100
    elif onward:
        onward_kwh = _road_kwh(body, onward["distance_km"])
        onward_points = _soc_points(body, onward_kwh)
        minimum = body.minimum_reserve_percent + onward_points
        plan["onward_energy_kwh"] = onward_kwh
        plan["minimum_target_soc_percent"] = round(minimum, 1)
        plan["full_charge_insufficient"] = minimum > 100
    if body.target_soc_percent is not None and station.get("included_in_ranking"):
        plan["charging_energy_kwh"] = max(
            0.0, body.usable_battery_capacity_kwh * (body.target_soc_percent - arrival) / 100.0
        )
        if onward_points is not None:
            at_destination = max(body.target_soc_percent, arrival) - onward_points
            plan["soc_at_destination_percent"] = round(at_destination, 1)
            plan["reaches_destination_with_reserve"] = at_destination >= body.minimum_reserve_percent
    return plan


def _detour_text(station: dict) -> str:
    km = station.get("detour_distance_km")
    minutes = station.get("detour_duration_min")
    if km is None:
        return "Detour unknown."
    if km <= 0.05:
        return "Practically on your route."
    extra = f" (+{minutes:.0f} min)" if minutes is not None and minutes > 0.5 else ""
    return f"Detour {km:.1f} km{extra} versus driving straight to the destination."


def _plain_station_summary(body: TripRequest, station: dict) -> str:
    """One short paragraph a driver can read. Every number comes from fields on the station."""
    plan = station.get("trip_plan") or {}
    battery = station.get("battery") or {}
    if not station.get("included_in_ranking"):
        if station.get("connector_compatible") is False:
            return f"Skipped: this listing does not show your {body.required_connector} connector."
        if battery.get("status") == "infeasible":
            return (
                f"Not reachable with your battery: the drive needs about {battery['estimated_energy_kwh']:.1f} kWh, "
                f"but only {max(battery['energy_above_reserve_kwh'], 0):.1f} kWh is above your "
                f"{body.minimum_reserve_percent:.0f}% reserve."
            )
        return "Skipped: " + (station.get("exclusion_reason") or "it did not pass the checks.")
    parts = []
    arrival = plan.get("arrival_soc_percent")
    if arrival is not None:
        parts.append(f"You would arrive with about {arrival:.0f}% battery.")
    parts.append(_detour_text(station))
    energy = plan.get("charging_energy_kwh")
    if energy is not None and energy <= 0:
        parts.append(f"You already have your {body.target_soc_percent:.0f}% target on arrival, so no charge is needed here.")
    elif energy is not None:
        text = f"Charging {arrival:.0f}% → {body.target_soc_percent:.0f}% adds about {energy:.1f} kWh"
        minutes = station.get("listed_power_duration_min")
        if minutes:
            text += f". The Component 2 duration model estimates {minutes:.0f} min for a session"
        parts.append(text + ".")
    elif plan.get("minimum_target_soc_percent") is not None and not plan.get("full_charge_insufficient"):
        parts.append(
            f"To finish the trip with your {body.minimum_reserve_percent:.0f}% reserve, "
            f"charge to at least {plan['minimum_target_soc_percent']:.0f}% here."
        )
    if plan.get("full_charge_insufficient"):
        parts.append("Even a full charge here may not be enough to finish the trip above your reserve.")
    elif plan.get("reaches_destination_with_reserve") is False:
        parts.append(
            f"Warning: that target leaves about {plan['soc_at_destination_percent']:.0f}% at the destination, "
            f"below your reserve. Charge to at least {plan['minimum_target_soc_percent']:.0f}%."
        )
    if station.get("scenario_cost_lkr") is not None:
        parts.append(f"Scenario cost about {station['scenario_cost_lkr']:.0f} LKR at the tariff you typed.")
    parts.append("Live availability and queue are unknown.")
    return " ".join(parts)


def _road_points(leg: dict | None) -> list[list[float]] | None:
    if not isinstance(leg, dict):
        return None
    geometry = leg.get("geometry")
    if not isinstance(geometry, list) or len(geometry) < 2:
        return None
    return geometry


def _shape(deps: dict[str, Any], start: tuple[float, float], end: tuple[float, float]) -> list[list[float]] | None:
    """Road line between two points from the routing provider, or None. Cached by the provider."""
    try:
        leg = deps["component4"]["provider"].route(_Point(*start), _Point(*end))
    except Exception:  # noqa: BLE001 — a missing line is reported as missing, never drawn straight
        return None
    return _road_points(leg.model_dump())


def _with_road_shape(station: dict | None, body: "TripRequest", deps: dict[str, Any]) -> dict | None:
    """The planner draws road shapes only for its own top stations; the final pick may differ, so fill it in."""
    if station is None:
        return None
    here = (station["latitude"], station["longitude"])
    for key, start, end in (
        ("origin_to_station", (body.origin_latitude, body.origin_longitude), here),
        ("station_to_destination", here, (body.destination_latitude, body.destination_longitude)),
    ):
        leg = station.get(key)
        if isinstance(leg, dict) and _road_points(leg) is None:
            geometry = _shape(deps, start, end)
            if geometry is not None:
                leg["geometry"] = geometry
    return station


def _plan_road(plan: dict | None, body: "TripRequest", deps: dict[str, Any]) -> dict[str, Any]:
    """Road line through every stop of the charging plan, or the direct road when no stop is needed."""
    stops = (plan or {}).get("stops") or []
    points = [(body.origin_latitude, body.origin_longitude)]
    points += [(stop["latitude"], stop["longitude"]) for stop in stops]
    points.append((body.destination_latitude, body.destination_longitude))
    line: list[list[float]] = []
    for start, end in zip(points, points[1:]):
        part = _shape(deps, start, end)
        if part is None:
            return {"geometry": None, "stops": len(stops), "note": "A road line for part of the plan was not returned. No straight line was drawn."}
        line += part[1:] if line and part[0] == line[-1] else part
    return {
        "geometry": line,
        "stops": len(stops),
        "note": "Road line through the charging plan's stops, from the routing provider.",
    }


def _recommended_road(station: dict | None) -> dict[str, Any]:
    """Join the two driven legs. A missing shape stays missing."""
    if station is None:
        return {
            "geometry": None,
            "provider": None,
            "note": "No station was recommended, so no road line was built.",
        }
    to_station = _road_points(station.get("origin_to_station"))
    onward = _road_points(station.get("station_to_destination"))
    provider = (station.get("origin_to_station") or {}).get("provider")
    if to_station is None or onward is None:
        return {
            "geometry": None,
            "provider": provider,
            "note": "The routing provider did not return a road shape. No straight line was substituted.",
        }
    joined = to_station + (onward[1:] if onward[0] == to_station[-1] else onward)
    return {
        "geometry": joined,
        "provider": provider,
        "note": (
            "Road shape from the routing provider: origin to the station, then the station to the destination. "
            "This is not a straight line and it is not live traffic."
        ),
    }


def _quick_answer(body: TripRequest, result: dict[str, Any]) -> list[str]:
    """The few lines a driver needs first. Numbers are taken from the result, never added."""
    lines: list[str] = []
    trip = result.get("trip_check") or {}
    if trip.get("can_finish_without_charging"):
        lines.append(
            f"You can probably finish this trip without charging: the direct route uses about "
            f"{trip['direct_energy_kwh']:.1f} kWh, leaving about "
            f"{trip['soc_at_destination_without_charging_percent']:.0f}% (your reserve is "
            f"{body.minimum_reserve_percent:.0f}%)."
        )
    plan = result.get("charging_plan") or {}
    multi_stop = plan.get("status") == "planned" and len(plan.get("stops") or []) > 1
    if multi_stop:
        lines.append(
            f"Charging to at most {plan['max_charge_soc_percent']:g}% per stop, one stop is not enough for this trip. "
            + plan["explanation"]
        )
    station = result.get("recommended_station")
    if station is None:
        lines.append("No station can be recommended from the information supplied.")
        return lines
    if multi_stop:
        lines.append(
            f"If you would rather stop once, the top-ranked station is {station['station_id']} ({station['station_name']}), "
            "but you would need to charge above that limit, where DC charging is slow."
        )
    else:
        lines.append(f"Best listed option: {station['station_id']} ({station['station_name']}).")
    lines.append(_plain_station_summary(body, station))
    lines.append("Call ahead or check the operator app before you go: these are listings, not live data.")
    return lines


def _energy_and_cost(
    body: TripRequest,
    deps: dict[str, Any],
    charging_kwh: float | None,
    charging_note: str,
    energy_ctx: dict[str, Any] | None = None,
) -> dict[str, Any]:
    component3 = deps.get("component3") or {}
    energy_model_loaded = bool(component3.get("energy_model_loaded"))
    energy_ctx = energy_ctx or {"applied": False, "status": "unavailable", "reason": component3.get("energy_model_reason")}
    grid_kwh = None
    basis = None
    cost = None
    cost_note = "Charging cost is unavailable."
    if charging_kwh is None:
        cost_note = charging_note
    elif body.charging_efficiency is not None:
        grid_kwh = charging_kwh / body.charging_efficiency
        basis = "grid_energy_kwh"
    else:
        basis = "vehicle_battery_kwh"
    if charging_kwh is not None and body.user_tariff_lkr_per_kwh is None:
        cost_note = (
            "Cost is unavailable. No user-supplied scenario tariff was entered. "
            "Listed station tariff text is not used as an official price."
        )
    elif charging_kwh is not None and body.user_tariff_lkr_per_kwh is not None and "estimate_charging_cost" not in component3:
        cost_note = "The cost function is not loaded, so no price was invented."
    elif charging_kwh is not None and body.user_tariff_lkr_per_kwh is not None:
        priced_kwh = grid_kwh if grid_kwh is not None else charging_kwh
        try:
            cost = component3["estimate_charging_cost"](
                priced_kwh,
                body.user_tariff_lkr_per_kwh,
                currency="LKR",
                tariff_category="user_supplied_scenario",
                energy_basis="station_energy_drawn_kwh" if grid_kwh is not None else "vehicle_energy_kwh",
            )
            if grid_kwh is None:
                cost_note = (
                    "Scenario estimate only: vehicle battery kWh times the tariff you typed. "
                    "Charging losses were not applied because efficiency was not provided. "
                    "This is not an official station tariff."
                )
            else:
                cost_note = (
                    "Scenario estimate: grid kWh equals battery kWh divided by the efficiency you supplied, "
                    "then times the tariff you typed. This is not an official station tariff."
                )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Cost calculation failed")
            cost = None
            cost_note = f"Cost calculation failed: {exc}"
    notes = []
    if energy_ctx.get("reason"):
        notes.append(energy_ctx["reason"])
    elif not energy_model_loaded:
        notes.append("No energy model is loaded.")
    notes.append(charging_note)
    if cost_note != charging_note:
        notes.append(cost_note)
    summary = " ".join(notes)
    return {
        "energy_model_loaded": energy_model_loaded,
        "energy_model_applied": bool(energy_ctx.get("applied")),
        "energy_model_status": energy_ctx.get("status"),
        "energy_model_reason": energy_ctx.get("reason") or component3.get("energy_model_reason"),
        "trip_energy_method": (
            "saved energy model on each road leg"
            if energy_ctx.get("applied")
            else "road distance times the consumption figure you entered, for the drive only"
        ),
        "charging_energy_kwh": charging_kwh,
        "charging_energy_note": charging_note,
        "grid_energy_kwh": grid_kwh,
        "energy_basis_for_cost": basis,
        "scenario_cost": cost,
        "summary": summary,
    }


def _duration(body: TripRequest, deps: dict[str, Any]) -> dict[str, Any]:
    component2 = deps.get("component2")
    if not component2:
        return {
            "status": "unavailable",
            "predicted_charging_duration_min": None,
            "reason": deps.get("errors", {}).get("component2") or DURATION_REASON,
            "used_in_ranking": False,
        }
    features = body.duration_features
    columns = component2["feature_columns"]
    if not features:
        return {
            "status": "unavailable",
            "predicted_charging_duration_min": None,
            "required_features": columns,
            "reason": (
                DURATION_REASON
                + " Provide every training feature, including a location from the training set, "
                "if you want a labelled session-duration estimate. Missing features are not guessed."
            ),
            "used_in_ranking": False,
        }
    missing = [column for column in columns if features.get(column) in (None, "")]
    if missing:
        return {
            "status": "unavailable",
            "predicted_charging_duration_min": None,
            "missing_features": missing,
            "reason": "Duration was not predicted because these inputs were not provided: " + ", ".join(missing) + ".",
            "used_in_ranking": False,
        }
    categories = component2.get("categories") or {}
    for column, allowed in categories.items():
        if str(features.get(column)) not in allowed:
            return {
                "status": "unavailable",
                "predicted_charging_duration_min": None,
                "reason": (
                    f"{column} must be one of the training values {allowed}. "
                    "A different value was not substituted."
                ),
                "used_in_ranking": False,
            }
    try:
        prediction = component2["predict_duration"](
            features, pipeline=component2["pipeline"], meta=component2["meta"]
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Duration prediction failed")
        return {
            "status": "unavailable",
            "predicted_charging_duration_min": None,
            "reason": f"The duration model failed: {exc}",
            "used_in_ranking": False,
        }
    return {
        "status": "predicted",
        "predicted_charging_duration_min": prediction["predicted_charging_duration_min"],
        "raw_prediction_min": prediction["raw_prediction_min"],
        "model_name": prediction["model_name"],
        "metrics": component2.get("metrics"),
        "training_location_used": features.get("Charging Station Location"),
        "used_in_ranking": False,
        "reason": (
            "This is one session-duration prediction from the saved Component 2 model. "
            "The inputs are battery size, charger power, start charge, and requested end charge. "
            "The training duration was generated as that energy divided by power, and it matches the clock."
        ),
    }


def _queue_block(station: dict | None = None, deps: dict | None = None, cache: dict | None = None) -> dict[str, Any]:
    """Forecast from the synthetic town model when this charger is close to one.

    The listing's own queue and wait stay blank. The numbers are the trained
    town's 30-minute forecast, not a count taken at this charger.
    """
    empty = {
        "status": "unavailable",
        "observed_queue_length": None,
        "predicted_queue_length": None,
        "predicted_waiting_time_min": None,
        "predicted_congestion_level": None,
        "horizon_minutes": 30,
        "training_data": "synthetic",
        "basis": "not_applied",
        "trained_station_id": None,
        "trained_area": None,
        "distance_km": None,
        "reason": QUEUE_REASON,
    }
    if station is None or not deps or deps.get("component1") is None:
        return empty
    area = match_trained_area(station)
    if area is None:
        return empty
    store = cache if cache is not None else {}
    key = area["station_id"]
    if key not in store:
        try:
            request = deps["component1"]["StationNowRequest"](
                station_id=key, use_current_time=True, include_llm=False
            )
            response = deps["component1"]["predict_station_now"](request)
            store[key] = response.model_dump()
        except Exception as exc:  # noqa: BLE001 — one town's model failure must not invent a queue
            logger.warning("Area model %s failed: %s", key, exc)
            store[key] = None
    forecast = store.get(key)
    if not forecast:
        failed = dict(empty)
        failed["trained_station_id"] = key
        failed["trained_area"] = area["name"]
        failed["distance_km"] = area["distance_km"]
        failed["reason"] = (
            f"The synthetic model for {area['name']} could not be applied. "
            "No queue, waiting time or congestion was invented."
        )
        return failed
    predictions = forecast.get("predictions") or {}
    queue = predictions.get("queue") or {}
    waiting = predictions.get("waiting_time") or {}
    congestion = predictions.get("congestion") or {}
    return {
        "status": "area_model",
        "observed_queue_length": None,
        "predicted_queue_length": queue.get("predicted_queue_length"),
        "predicted_waiting_time_min": waiting.get("predicted_waiting_time_min"),
        "predicted_congestion_level": congestion.get("predicted_congestion_level"),
        "horizon_minutes": 30,
        "training_data": "synthetic",
        "basis": "synthetic_area_snapshot",
        "trained_station_id": key,
        "trained_area": area["name"],
        "distance_km": area["distance_km"],
        "reason": (
            f"Queue, waiting time and congestion are the synthetic forecast for {area['name']} "
            f"({key}), {area['distance_km']:.2f} km from this charger. "
            "They are not a count taken at this charger."
        ),
    }


def _model_catalog(
    deps: dict[str, Any],
    energy_ctx: dict[str, Any] | None = None,
    stations: list[dict] | None = None,
) -> dict[str, Any]:
    applied = any((station.get("queue_prediction") or {}).get("status") == "area_model" for station in (stations or []))
    component1 = deps.get("component1") or {}
    registry = component1.get("registry")
    status = registry.status() if registry is not None else {}
    metrics = component1.get("metrics") or {}

    def metric_slice(blob: dict | None, key: str) -> dict | None:
        if not blob:
            return None
        return blob.get(key)

    return {
        "queue": {
            "loaded": bool(status.get("queue", {}).get("loaded")),
            "model_name": status.get("queue", {}).get("model_name"),
            "predictor_kind": status.get("queue", {}).get("predictor_kind"),
            "horizon_minutes": 30,
            "training_data": "synthetic",
            "applied_to_listed_stations": bool(applied),
            "test_metrics": metric_slice(metrics.get("queue"), "test_metrics_selected_raw"),
        },
        "waiting_time": {
            "loaded": bool(status.get("waiting_time", {}).get("loaded")),
            "model_name": status.get("waiting_time", {}).get("model_name"),
            "horizon_minutes": 30,
            "training_data": "synthetic",
            "applied_to_listed_stations": bool(applied),
            "test_metrics": metric_slice(metrics.get("waiting_time"), "test_metrics_selected_raw"),
        },
        "congestion": {
            "loaded": bool(status.get("congestion", {}).get("loaded")),
            "model_name": status.get("congestion", {}).get("model_name"),
            "horizon_minutes": 30,
            "training_data": "synthetic",
            "applied_to_listed_stations": bool(applied),
            # A classifier: its report uses test_metrics_selected (accuracy, macro F1), not the regression key.
            "test_metrics": _congestion_metrics(metrics.get("congestion")),
        },
        "duration": {
            "loaded": deps.get("component2") is not None,
            "model_name": (deps.get("component2") or {}).get("selected_model"),
            "test_metrics": (deps.get("component2") or {}).get("metrics"),
            "applied_to_station_charge_time": any(
                station.get("duration_source") == "component2" for station in stations
            ),
        },
        "energy": {
            "loaded": bool((deps.get("component3") or {}).get("energy_model_loaded")),
            "model_name": (deps.get("component3") or {}).get("selected_model"),
            "training_data": "synthetic" if (deps.get("component3") or {}).get("energy_model_loaded") else None,
            "applied_to_this_trip": bool((energy_ctx or {}).get("applied")),
            "test_metrics": ((deps.get("component3") or {}).get("metrics") or {}).get("test_metrics_raw"),
            "excluded_as_leakage": ["soc_end_pct", "energy_consumption_kwh_per_km"],
            "reason": (energy_ctx or {}).get("reason") or (deps.get("component3") or {}).get("energy_model_reason"),
        },
    }


def _weights(body: TripRequest) -> dict[str, float]:
    weights = dict(DEFAULT_WEIGHTS)
    if body.ranking_weights:
        unknown = set(body.ranking_weights) - set(DEFAULT_WEIGHTS)
        if unknown:
            raise ValueError(f"Unknown ranking weights: {sorted(unknown)}")
        if any(value < 0 for value in body.ranking_weights.values()):
            raise ValueError("Ranking weights must be non-negative.")
        weights.update(body.ranking_weights)
        if sum(weights.values()) <= 0:
            raise ValueError("At least one ranking weight must be positive.")
    return weights


def _session_record(battery_kwh: float, rate_kw: float, start_soc: float, end_soc: float) -> dict[str, float]:
    return {
        "Battery Capacity (kWh)": battery_kwh,
        "Charging Rate (kW)": rate_kw,
        "State of Charge (Start %)": start_soc,
        "State of Charge (End %)": end_soc,
    }


def _predict_session_minutes(
    deps: dict[str, Any],
    battery_kwh: float | None,
    rate_kw: float | None,
    start_soc: float | None,
    end_soc: float | None,
) -> tuple[float | None, str]:
    """Ask Component 2 for one session. Missing inputs stay missing."""
    component2 = deps.get("component2")
    if not component2:
        return None, (
            "Charging time was not calculated. The Component 2 duration model is not loaded, "
            "and listed kilowatts were not used instead."
        )
    if None in (battery_kwh, rate_kw, start_soc, end_soc):
        return None, (
            "Charging time was not calculated. Battery size, charger power, or a charge level was missing. "
            "The missing value was not guessed, and listed kilowatts were not used instead."
        )
    record = _session_record(float(battery_kwh), float(rate_kw), float(start_soc), float(end_soc))
    columns = component2.get("feature_columns") or []
    missing = [column for column in columns if record.get(column) in (None, "")]
    if missing:
        return None, (
            "Charging time was not calculated. The duration model still needs: "
            + ", ".join(missing)
            + ". Those values were not guessed."
        )
    try:
        prediction = component2["predict_duration"](
            record, pipeline=component2["pipeline"], meta=component2["meta"]
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Duration model failed for a station")
        return None, f"The duration model failed: {exc}"
    minutes = float(prediction["predicted_charging_duration_min"])
    model_name = prediction.get("model_name") or component2.get("selected_model")
    return minutes, (
        f"Charging time is the Component 2 {model_name} model, using battery size, this charger's power, "
        f"and the rise from {float(start_soc):.0f}% to {float(end_soc):.0f}%. "
        "The training sessions were generated so duration equals the clock and energy equals power times time."
    )


def _plan_session_times(plan: dict | None, deps: dict[str, Any], battery_kwh: float) -> dict | None:
    """Show the Component 2 session length on each planned stop that actually charges.

    The route planner still decides where a stop is needed from battery energy.
    The minutes shown for those stops come from Component 2.
    """
    if not isinstance(plan, dict) or deps.get("component2") is None:
        return plan
    plan = copy.deepcopy(plan)
    old = 0.0
    new = 0.0
    for stop in plan.get("stops") or []:
        previous = stop.get("charging_min")
        if not isinstance(previous, (int, float)) or previous <= 0:
            continue
        minutes, _note = _predict_session_minutes(
            deps,
            battery_kwh,
            stop.get("charging_power_kw"),
            stop.get("arrival_soc_percent"),
            stop.get("departure_soc_percent"),
        )
        if minutes is None:
            continue
        old += float(previous)
        stop["charging_min"] = minutes
        new += minutes
    totals = plan.get("totals")
    if isinstance(totals, dict) and old:
        totals["charging_min"] = float(totals.get("charging_min") or 0) - old + new
        if isinstance(totals.get("total_min"), (int, float)):
            totals["total_min"] = float(totals["total_min"]) - old + new
        text = plan.get("explanation") or ""
        plan["explanation"] = re.sub(
            r"About \d+ min in total: \d+ min driving, \d+ min charging at listed power",
            (
                f"About {totals['total_min']:.0f} min in total: {totals['drive_min']:.0f} min driving, "
                f"{totals['charging_min']:.0f} min charging from the Component 2 duration model"
            ),
            text,
            count=1,
        )
    return plan


def build_recommendation(body: TripRequest, deps: dict[str, Any], explain=True) -> dict[str, Any]:
    if deps.get("component4") is None:
        raise RuntimeError(deps.get("errors", {}).get("component4") or "Route optimizer is not loaded.")
    component4 = deps["component4"]
    weights = _weights(body)
    request_payload = body.model_dump()
    departure = _departure(body)
    body, trip_conditions, planning_consumption = _prepare_energy(body, deps, departure)
    c4_body = component4["RecommendRequest"](
        origin_latitude=body.origin_latitude,
        origin_longitude=body.origin_longitude,
        destination_latitude=body.destination_latitude,
        destination_longitude=body.destination_longitude,
        current_soc_percent=body.current_soc_percent,
        usable_battery_capacity_kwh=body.usable_battery_capacity_kwh,
        # The more cautious of your rate and the energy model's rate for this road, so the station
        # checks and the charging plan agree with the battery figures shown for the trip.
        consumption_kwh_per_100km=planning_consumption,
        minimum_reserve_percent=body.minimum_reserve_percent,
        required_connector=body.required_connector,
        maximum_detour_km=body.maximum_detour_km,
        max_charge_soc_percent=body.max_charge_soc_percent,
        stop_overhead_min=body.stop_overhead_min,
        # Charging energy depends on the SOC at each station, so it is calculated below per station.
        energy_to_add_kwh=None,
    )
    routed = component4["recommend"](c4_body, component4["provider"], component4["load_stations"]())
    routed_data = routed.model_dump()
    duration = _duration(body, deps)
    stations = []
    if routed_data.get("recommended_station"):
        stations.append(routed_data["recommended_station"])
    stations.extend(routed_data.get("alternatives") or [])
    energy_ctx = _apply_energy_model(body, deps, routed_data, stations)
    area_forecasts: dict[str, dict | None] = {}
    for station in stations:
        station["queue_prediction"] = _queue_block(station, deps, area_forecasts)
        plan = _station_plan(body, station)
        station["trip_plan"] = plan
        kwh = plan["charging_energy_kwh"]
        power = station.get("charging_power_kw") or station.get("max_power_kw_listed")
        end_soc = body.target_soc_percent if body.target_soc_percent is not None else plan.get("minimum_target_soc_percent")
        if kwh is not None and kwh <= 0:
            minutes = 0.0
            note = "No session: the battery on arrival is already at the target, so Component 2 was not asked for a charge time."
            source = "not_needed"
        else:
            minutes, note = _predict_session_minutes(
                deps,
                body.usable_battery_capacity_kwh,
                power,
                plan.get("arrival_soc_percent"),
                end_soc,
            )
            source = "component2" if minutes is not None else "unavailable"
        station["estimated_charging_duration_min"] = minutes
        station["estimated_charging_cost_lkr"] = None
        station["listed_power_duration_min"] = minutes
        station["duration_source"] = source
        station["listed_power_duration_note"] = note
        station_energy = _energy_and_cost(body, deps, kwh, CHARGING_NOTE, energy_ctx) if kwh is not None else None
        station_cost = (station_energy or {}).get("scenario_cost")
        station["scenario_cost_lkr"] = station_cost["estimated_total"] if station_cost else None
        station["scenario_cost_note"] = (
            station_energy["summary"] if station_energy else "Cost was not calculated for this station."
        )
        station["live_availability"] = False
        station["factor_contributions"] = []
        station["timeline"] = _timeline(station, departure)
    ranking_summary = rank_candidates(stations, weights)
    ranked = sorted(
        [station for station in stations if station.get("included_in_ranking") and station.get("rank")],
        key=lambda station: station["rank"],
    )
    others = [station for station in stations if station not in ranked]
    recommended = ranked[0] if ranked else None
    warnings = list(routed_data.get("warnings") or [])
    listing_only = " is ranked from listing data only."
    unconfirmed = [warning.split(listing_only)[0] for warning in warnings if listing_only in warning]
    if unconfirmed:
        warnings = [warning for warning in warnings if listing_only not in warning]
        warnings.insert(
            0,
            f"{', '.join(unconfirmed)} {'is' if len(unconfirmed) == 1 else 'are'} ranked from listing data only. "
            "Real-time availability is unknown, not confirmed.",
        )
    if body.target_soc_percent is None:
        charging_kwh, charging_note = None, "Target SOC was not provided, so charging energy was not calculated."
    elif recommended is None:
        charging_kwh, charging_note = None, "No feasible station, so charging energy was not calculated."
    else:
        charging_kwh, charging_note = recommended["trip_plan"]["charging_energy_kwh"], CHARGING_NOTE
    energy = _energy_and_cost(body, deps, charging_kwh, charging_note, energy_ctx)
    energy["charging_energy_station_id"] = recommended["station_id"] if charging_kwh is not None else None
    for station in stations:
        station["plain_summary"] = _plain_station_summary(body, station)
    result = {
        "recommended_station": recommended,
        "alternatives": ranked[1:] + others,
        "direct_route": routed_data.get("direct_route"),
        "recommended_route": _recommended_road(_with_road_shape(recommended, body, deps)),
        "plan_route": _plan_road(routed_data.get("charging_plan"), body, deps),
        "inputs": request_payload,
        "warnings": warnings,
        "ranking_summary": ranking_summary,
        "ranking_weights": weights,
        "charging_duration": duration,
        "energy_and_cost": energy,
        "models": _model_catalog(deps, energy_ctx, stations),
        "data_freshness": routed_data.get("data_freshness"),
        "limitations": list(routed_data.get("limitations") or [])
        + [
            "Road times are OSRM estimates on OpenStreetMap data, not live traffic. © OpenStreetMap contributors.",
            "Queue, waiting time and congestion are synthetic town forecasts when a charger is near Nugegoda, Rajagiriya, Malabe, Pannipitiya or Panadura. They are not a count at that charger. Farther listings stay blank.",
            energy_ctx.get("reason")
            or "The energy model was not applied to this search.",
        ],
        "live_availability": False,
        "live_queue_prediction": False,
        "station_count": len(stations),
        "trip_check": _trip_check(body, routed_data.get("direct_route")),
        # Component 4 route optimisation: multi-stop plan, baseline rules and routing cost.
        "charging_plan": _plan_session_times(
            routed_data.get("charging_plan"), deps, body.usable_battery_capacity_kwh
        ),
        "strategy_comparison": routed_data.get("strategy_comparison"),
        "routing_summary": routed_data.get("routing_summary"),
        "inventory_summary": routed_data.get("inventory_summary"),
        "departure_time": _clock(departure),
        "plan_arrival_time": _plan_arrival(routed_data.get("charging_plan"), departure),
        "trip_conditions": trip_conditions,
        "planning_consumption_kwh_per_100km": planning_consumption,
        "trip_energy": _trip_energy(body, deps, routed_data.get("direct_route"), energy_ctx),
    }
    if not recommended:
        result["warnings"].append(
            "No feasible Colombo station was established. Change the battery, connector or trip inputs, "
            "or supply the missing data. No station was invented."
        )
    else:
        plan = recommended["trip_plan"]
        if plan.get("full_charge_insufficient"):
            result["warnings"].append(
                f"Even a full charge at {recommended['station_id']} may not finish the trip above your reserve."
            )
        elif plan.get("reaches_destination_with_reserve") is False:
            result["warnings"].append(
                f"Your target SOC at {recommended['station_id']} leaves less than your reserve at the destination. "
                f"Charge to at least {plan['minimum_target_soc_percent']:.0f}%."
            )
    result["quick_answer"] = _quick_answer(body, result)
    if explain and body.include_explanation:
        from explain import explain_result

        result["explanation"] = explain_result(result, body.follow_up_question)
    return result
