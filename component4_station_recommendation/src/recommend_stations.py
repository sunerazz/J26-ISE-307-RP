"""Filter listed Colombo stations and rank those that can be justified."""

from __future__ import annotations

from src.battery_feasibility import assess_reachability
from src.route_optimizer import safe_route_via_station
from src.routing_provider import RoutingError, RoutingProvider
from src.schemas import LatLon, RecommendRequest, RecommendResponse, StationRecommendation
from src.stations import connector_matches

DEFAULT_WEIGHTS = {
    "detour_distance": 0.40,
    "detour_time": 0.30,
    "waiting_time": 0.15,
    "tariff": 0.15,
}

LIMITATIONS = [
    "The inventory has four Open Charge Map listings. It is not a live station feed.",
    "Availability, queue length, and waiting time are unknown in this CSV and are never treated as zero.",
    "Connector, power, and tariff fields are reported listing text and may be outdated.",
    "No station is marked confirmed operational because each listing says it was not recently verified.",
    "Battery reachability is an approximation from road distance and the supplied consumption rate.",
    "This service does not predict live queues and does not train a classifier on four records.",
]

FORMULA = (
    "For each feasible station, numeric factors are min-max normalized across the feasible set. "
    "A factor score is 1 at the best (lowest) value and 0 at the worst. "
    "A factor is compared only when at least two feasible stations have a value and its weight is positive. "
    "The station score is the weighted average of the compared factors that exist for that station. "
    "Missing waiting time or tariff is omitted and the remaining weights are renormalized. "
    "Higher score is better."
)


def _weights(request: RecommendRequest) -> dict[str, float]:
    weights = dict(DEFAULT_WEIGHTS)
    if request.ranking_weights:
        weights.update(request.ranking_weights)
    return weights


def _charging_estimates(station: dict, energy_to_add_kwh: float | None) -> tuple[float | None, float | None, str]:
    if energy_to_add_kwh is None:
        return None, None, "Charging duration and cost were not estimated because energy to add was not supplied."
    duration = None
    cost = None
    notes = []
    power = station["max_power_kw_listed"]
    if power is not None and power > 0:
        duration = energy_to_add_kwh / power * 60.0
        notes.append(
            "Duration assumes the listed maximum kW is delivered continuously at 100 percent, which real chargers do not do."
        )
    else:
        notes.append("Listed power is missing, so charging duration was not estimated.")
    tariff = station["tariff_lkr_per_kwh_listed"]
    if tariff is not None:
        cost = energy_to_add_kwh * tariff
        notes.append("Cost uses the single listed LKR/kWh figure and is not a verified bill.")
    else:
        notes.append("Tariff is missing or ambiguous, so charging cost was not estimated and was not set to zero.")
    return duration, cost, " ".join(notes)


def _normalize_penalty(value: float, values: list[float]) -> float:
    low = min(values)
    high = max(values)
    if high == low:
        return 0.0
    return (value - low) / (high - low)


def rank_feasible(rows: list[dict], weights: dict[str, float]) -> None:
    """Attach score and explanation. Mutates feasible rows only."""
    pool = [row for row in rows if row["eligible"]]
    if not pool:
        return
    present_for = []
    for row in pool:
        station = row["station"]
        present_for.append(
            {
                "detour_distance": row["detour_distance_km"],
                "detour_time": row["detour_duration_min"],
                "waiting_time": station["waiting_time_min"],
                "tariff": station["tariff_lkr_per_kwh_listed"],
            }
        )
    comparable: dict[str, list[float]] = {}
    for name in ("detour_distance", "detour_time", "waiting_time", "tariff"):
        if weights.get(name, 0.0) <= 0:
            continue
        values = [item[name] for item in present_for if item[name] is not None]
        if len(values) >= 2:
            comparable[name] = values
    for row, present in zip(pool, present_for):
        active = {
            name: weights[name]
            for name in comparable
            if present[name] is not None
        }
        total = sum(active.values())
        parts = []
        if total <= 0:
            row["score"] = None
            row["ranking_explanation"] = "Ranking could not be completed because every weighted factor is missing."
            continue
        score = 0.0
        for name, weight in active.items():
            penalty = _normalize_penalty(present[name], comparable[name])
            factor_score = 1.0 - penalty
            share = weight / total
            score += share * factor_score
            parts.append(f"{name} score {factor_score:.3f} with renormalized weight {share:.3f}")
        dropped = [name for name, value in present.items() if value is None and weights.get(name, 0.0) > 0]
        skipped = [name for name in present if name not in comparable and present[name] is not None and weights.get(name, 0.0) > 0]
        row["score"] = score
        extra = ""
        if dropped:
            extra += " Omitted missing factors (not treated as zero): " + ", ".join(dropped) + "."
        if skipped:
            extra += " Not compared because fewer than two feasible stations have a value: " + ", ".join(skipped) + "."
        row["ranking_explanation"] = "Weighted score " + f"{score:.3f}. " + "; ".join(parts) + "." + extra
    ordered = sorted(pool, key=lambda row: (-(row["score"] or -1), row["station"]["station_id"]))
    for index, row in enumerate(ordered, start=1):
        row["rank"] = index


def recommend(request: RecommendRequest, provider: RoutingProvider, stations: list[dict]) -> RecommendResponse:
    origin = LatLon(latitude=request.origin_latitude, longitude=request.origin_longitude)
    destination = LatLon(latitude=request.destination_latitude, longitude=request.destination_longitude)
    weights = _weights(request)
    warnings: list[str] = []
    try:
        direct = provider.route(origin, destination)
    except RoutingError as exc:
        raise RoutingError(
            "Routing is unavailable, so no station can be recommended. " + str(exc)
        ) from exc

    rows: list[dict] = []
    for station in stations:
        compatible = connector_matches(request.required_connector, station["connector_types_listed"])
        base = {
            "station": station,
            "compatible": compatible,
            "eligible": False,
            "exclusion_reason": None,
            "origin_to_station": None,
            "station_to_destination": None,
            "detour_distance_km": None,
            "detour_duration_min": None,
            "battery": None,
            "rank": None,
            "score": None,
            "ranking_explanation": "",
        }
        if compatible is False:
            base["exclusion_reason"] = (
                f"Listed connectors do not include the required connector '{request.required_connector}'."
            )
            base["ranking_explanation"] = base["exclusion_reason"]
            rows.append(base)
            continue
        if station["availability_status"] == "unavailable":
            base["exclusion_reason"] = "The listing marks this station unavailable."
            base["ranking_explanation"] = base["exclusion_reason"]
            rows.append(base)
            continue
        if not station["listed_word_operational"]:
            base["exclusion_reason"] = "The listing does not say the station is operational."
            base["ranking_explanation"] = base["exclusion_reason"]
            rows.append(base)
            continue

        routed = safe_route_via_station(
            provider,
            origin,
            LatLon(latitude=station["latitude"], longitude=station["longitude"]),
            destination,
            direct,
        )
        base.update(routed)
        if routed["error"]:
            base["exclusion_reason"] = "Road route unavailable for this station. " + routed["error"]
            base["ranking_explanation"] = base["exclusion_reason"]
            rows.append(base)
            continue
        if request.maximum_detour_km is not None and routed["detour_distance_km"] > request.maximum_detour_km:
            base["exclusion_reason"] = (
                f"Detour {routed['detour_distance_km']:.2f} km exceeds the maximum of {request.maximum_detour_km:.2f} km."
            )
            base["ranking_explanation"] = base["exclusion_reason"]
            rows.append(base)
            continue
        battery = assess_reachability(
            routed["origin_to_station"].distance_km,
            request.current_soc_percent,
            request.usable_battery_capacity_kwh,
            request.consumption_kwh_per_100km,
            request.minimum_reserve_percent,
        )
        base["battery"] = battery
        if battery.status != "feasible":
            base["exclusion_reason"] = (
                "Battery feasibility is infeasible."
                if battery.status == "infeasible"
                else "Battery feasibility is unknown, so the station is not recommended as reachable."
            )
            base["ranking_explanation"] = base["exclusion_reason"]
            rows.append(base)
            continue
        if station["availability_status"] != "available":
            warnings.append(
                f"{station['station_id']} is ranked from listing data only. Real-time availability is {station['availability_status']}, not confirmed."
            )
        base["eligible"] = True
        rows.append(base)

    rank_feasible(rows, weights)
    built = [_to_recommendation(row, request) for row in rows]
    ranked = sorted(
        [item for item in built if item.included_in_ranking],
        key=lambda item: (item.rank or 999, item.station_id),
    )
    others = [item for item in built if not item.included_in_ranking]
    if not ranked:
        warnings.append(
            "No station can be recommended. None passed connector, listing, detour, and battery checks with a usable road route."
        )
        recommended = None
        alternatives = others
    else:
        recommended = ranked[0]
        alternatives = ranked[1:] + others
        if recommended.availability_status != "available":
            warnings.append(
                "The top station is a listing match with unknown live availability. It is not a confirmed free charger."
            )
    return RecommendResponse(
        recommended_station=recommended,
        alternatives=alternatives,
        direct_route=direct,
        ranking_formula=FORMULA,
        weights_used=weights,
        warnings=warnings,
        data_freshness="Open Charge Map listings copied into the project CSV. Not a live snapshot.",
        limitations=LIMITATIONS,
        live_availability=False,
        live_queue_prediction=False,
    )


def _to_recommendation(row: dict, request: RecommendRequest) -> StationRecommendation:
    station = row["station"]
    duration, cost, charge_note = _charging_estimates(station, request.energy_to_add_kwh)
    battery = row["battery"] or assess_reachability(
        None,
        request.current_soc_percent,
        request.usable_battery_capacity_kwh,
        request.consumption_kwh_per_100km,
        request.minimum_reserve_percent,
    )
    explanation = row["ranking_explanation"]
    if row["eligible"]:
        explanation = explanation + " " + charge_note
    return StationRecommendation(
        station_id=station["station_id"],
        station_name=station["station_name"],
        address=station["address"],
        area=station["area"],
        latitude=station["latitude"],
        longitude=station["longitude"],
        rank=row["rank"],
        score=row["score"],
        included_in_ranking=row["eligible"] and row["score"] is not None,
        exclusion_reason=row["exclusion_reason"],
        connector_types_listed=station["connector_types_listed"],
        connector_compatible=row["compatible"],
        max_power_kw_listed=station["max_power_kw_listed"],
        tariff_lkr_per_kwh_listed=station["tariff_lkr_per_kwh_listed"],
        tariff_status=station["tariff_status"],
        tariff_raw=station["tariff_raw"],
        availability_status=station["availability_status"],
        queue_length_current=station["queue_length_current"],
        waiting_time_min=station["waiting_time_min"],
        operational_listing=station["operational_listing"],
        confirmed_operational=False,
        origin_to_station=row["origin_to_station"],
        station_to_destination=row["station_to_destination"],
        detour_distance_km=row["detour_distance_km"],
        detour_duration_min=row["detour_duration_min"],
        battery=battery,
        estimated_charging_duration_min=duration if row["eligible"] else None,
        estimated_charging_cost_lkr=cost if row["eligible"] else None,
        ranking_explanation=explanation,
        source_url=station["source_url"] or None,
        source_note=station["source_note"] or None,
    )
