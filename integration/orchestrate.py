"""Combine the four components. Missing predictions stay missing."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger("integration.orchestrate")

DEFAULT_WEIGHTS = {
    "detour_distance": 0.40,
    "detour_time": 0.30,
    "waiting_time": 0.15,
    "listed_power_duration": 0.15,
    "scenario_cost": 0.10,
}

QUEUE_REASON = (
    "Queue length, waiting time and congestion were not predicted for this Colombo listing. "
    "Component 1 was trained on synthetic stations ST01–ST06. It needs an observed queue and, "
    "for waiting time and congestion, the lag features from that synthetic table. "
    "Those observations are blank in the Colombo CSV and were not replaced with zero. "
    "A value from the synthetic station checker is a separate demonstration, not this station's forecast."
)

DURATION_REASON = (
    "The Component 2 model predicts a charging-session duration from a separate dataset. "
    "Its station locations are US cities, and target SOC is not one of its inputs. "
    "It was not applied to this Colombo station. No duration was invented."
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
    include_explanation: bool = True
    follow_up_question: str | None = None


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
        "Missing values were not set to zero. A lower detour, wait, listed-power duration or scenario cost scores higher. "
        "Listed-power duration is kilowatt-hours divided by the listed kW. It is not the Component 2 model. "
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
    record = {
        "distance_km": distance_km,
        "trip_duration_min": duration_min,
        "average_speed_kmh": distance_km / (duration_min / 60.0),
        "battery_capacity_kwh": body.usable_battery_capacity_kwh,
        "soc_start_pct": soc_start,
        **ctx["conditions"],
    }
    prediction = component3["predict_energy"](record, pipeline=component3["pipeline"], meta=component3["meta"])
    return float(prediction["predicted_energy_kwh"])


def _model_battery(body: TripRequest, energy_kwh: float) -> dict[str, Any]:
    available = body.usable_battery_capacity_kwh * body.current_soc_percent / 100.0
    reserve = body.usable_battery_capacity_kwh * body.minimum_reserve_percent / 100.0
    above = available - reserve
    status = "feasible" if energy_kwh <= above else "infeasible"
    return {
        "status": status,
        "estimated_energy_kwh": energy_kwh,
        "energy_above_reserve_kwh": above,
        "method": "component3_energy_model",
        "assumptions": [
            "Energy is the saved model prediction for this road leg.",
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
        direct["model_energy_kwh"] = direct_kwh
    for station, energy, onward_kwh in prepared:
        battery = _model_battery(body, energy)
        station["battery"] = battery
        station["drive_energy_model"] = {
            "predicted_energy_kwh": energy,
            "model_name": (deps.get("component3") or {}).get("selected_model"),
            "training_data": "synthetic",
        }
        if onward_kwh is not None:
            station["onward_model_energy_kwh"] = onward_kwh
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
        power = station.get("max_power_kw_listed")
        if minutes is not None and power:
            text += f", roughly {minutes:.0f} min at the listed {power:g} kW (real chargers are usually slower)"
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
    station = result.get("recommended_station")
    if station is None:
        lines.append("No station can be recommended from the information supplied.")
        return lines
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
                    "Colombo was not substituted for a US city."
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
            "This is one session-duration prediction from the saved random-forest pipeline. "
            f"The location label sent to the model was {features.get('Charging Station Location')}, "
            "which is a training category, not a Colombo station. Target SOC was not an input. "
            "The same number is not copied onto each Colombo station and is not a ranking factor. "
            "Test R² for this model is negative, so the value is a weak statistical estimate."
        ),
    }


def _queue_block() -> dict[str, Any]:
    return {
        "status": "unavailable",
        "observed_queue_length": None,
        "predicted_queue_length": None,
        "predicted_waiting_time_min": None,
        "predicted_congestion_level": None,
        "horizon_minutes": 30,
        "training_data": "synthetic",
        "basis": "not_applied",
        "reason": QUEUE_REASON,
    }


def _model_catalog(deps: dict[str, Any], energy_ctx: dict[str, Any] | None = None) -> dict[str, Any]:
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
            "applied_to_colombo_stations": False,
            "test_metrics": metric_slice(metrics.get("queue"), "test_metrics_selected_raw"),
        },
        "waiting_time": {
            "loaded": bool(status.get("waiting_time", {}).get("loaded")),
            "model_name": status.get("waiting_time", {}).get("model_name"),
            "horizon_minutes": 30,
            "training_data": "synthetic",
            "applied_to_colombo_stations": False,
            "test_metrics": metric_slice(metrics.get("waiting_time"), "test_metrics_selected_raw"),
        },
        "congestion": {
            "loaded": bool(status.get("congestion", {}).get("loaded")),
            "model_name": status.get("congestion", {}).get("model_name"),
            "horizon_minutes": 30,
            "training_data": "synthetic",
            "applied_to_colombo_stations": False,
            "test_metrics": metric_slice(metrics.get("congestion"), "test_metrics_selected_raw"),
        },
        "duration": {
            "loaded": deps.get("component2") is not None,
            "model_name": (deps.get("component2") or {}).get("selected_model"),
            "test_metrics": (deps.get("component2") or {}).get("metrics"),
            "applied_per_colombo_station": False,
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


def build_recommendation(body: TripRequest, deps: dict[str, Any], explain=True) -> dict[str, Any]:
    if deps.get("component4") is None:
        raise RuntimeError(deps.get("errors", {}).get("component4") or "Route optimizer is not loaded.")
    component4 = deps["component4"]
    weights = _weights(body)
    request_payload = body.model_dump()
    c4_body = component4["RecommendRequest"](
        origin_latitude=body.origin_latitude,
        origin_longitude=body.origin_longitude,
        destination_latitude=body.destination_latitude,
        destination_longitude=body.destination_longitude,
        current_soc_percent=body.current_soc_percent,
        usable_battery_capacity_kwh=body.usable_battery_capacity_kwh,
        consumption_kwh_per_100km=body.consumption_kwh_per_100km,
        minimum_reserve_percent=body.minimum_reserve_percent,
        required_connector=body.required_connector,
        maximum_detour_km=body.maximum_detour_km,
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
    for station in stations:
        station["queue_prediction"] = _queue_block()
        plan = _station_plan(body, station)
        station["trip_plan"] = plan
        kwh = plan["charging_energy_kwh"]
        power = station.get("max_power_kw_listed")
        minutes = kwh / power * 60.0 if kwh is not None and power else None
        station["estimated_charging_duration_min"] = minutes
        station["estimated_charging_cost_lkr"] = None
        station["listed_power_duration_min"] = minutes
        station["listed_power_duration_note"] = (
            "Minutes equal charging kWh divided by the listed maximum kW, assuming that power is delivered continuously. "
            "Real chargers taper, so expect longer. This is not the Component 2 model."
            if minutes is not None
            else "Listed-power duration was not calculated."
        )
        station_energy = _energy_and_cost(body, deps, kwh, CHARGING_NOTE, energy_ctx) if kwh is not None else None
        station_cost = (station_energy or {}).get("scenario_cost")
        station["scenario_cost_lkr"] = station_cost["estimated_total"] if station_cost else None
        station["scenario_cost_note"] = (
            station_energy["summary"] if station_energy else "Cost was not calculated for this station."
        )
        station["live_availability"] = False
        station["factor_contributions"] = []
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
        "recommended_route": _recommended_road(recommended),
        "inputs": request_payload,
        "warnings": warnings,
        "ranking_summary": ranking_summary,
        "ranking_weights": weights,
        "charging_duration": duration,
        "energy_and_cost": energy,
        "models": _model_catalog(deps, energy_ctx),
        "data_freshness": routed_data.get("data_freshness"),
        "limitations": list(routed_data.get("limitations") or [])
        + [
            "Road times are OSRM estimates on OpenStreetMap data, not live traffic. © OpenStreetMap contributors.",
            "Component 1 predictions are withheld for ST001–ST004 because the required observations do not exist.",
            energy_ctx.get("reason")
            or "The energy model was not applied to this search.",
        ],
        "live_availability": False,
        "live_queue_prediction": False,
        "station_count": len(stations),
        "trip_check": _trip_check(body, routed_data.get("direct_route")),
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
