"""Filter listed stations, rank those that can be justified, and plan charging stops."""

from __future__ import annotations

import math

from src.battery_feasibility import assess_reachability
from src.charging_plan import DESTINATION, ORIGIN, PlannerSettings, Vehicle, compare_strategies, pareto_flags, plan_charging, single_stop
from src.route_optimizer import RoadMatrix, build_matrix
from src.routing_provider import RoutingError, RoutingProvider
from src.schemas import LatLon, RecommendRequest, RecommendResponse, RouteLeg, StationRecommendation
from src.stations import connector_matches, power_for_connector, tariff_for_connector

DEFAULT_WEIGHTS = {
    "detour_distance": 0.40,
    "detour_time": 0.30,
    "waiting_time": 0.15,
    "tariff": 0.15,
}

# Pairwise fallback asks for every station-to-station leg only for small inventories.
PAIRWISE_ALL_PAIRS_LIMIT = 12


def limitations(count: int) -> list[str]:
    return [
        f"The inventory has {count} Open Charge Map listings. It is not a live station feed.",
        "Availability, queue length, and waiting time are not published for these stations and are never treated as zero.",
        "Connector, power, and tariff fields are listing data and may be outdated.",
        "No station is marked confirmed operational because each listing says it was not recently verified.",
        "Battery reachability is an approximation from road distance and the supplied consumption rate.",
        "Charging minutes assume the listed kW is delivered continuously; real chargers taper.",
        "This service does not predict live queues and does not train a classifier on station listings.",
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


def _charging_estimates(
    station: dict, energy_to_add_kwh: float | None, connector: str | None
) -> tuple[float | None, float | None, str]:
    if energy_to_add_kwh is None:
        return None, None, "Charging duration and cost were not estimated because energy to add was not supplied."
    duration = None
    cost = None
    notes = []
    power = power_for_connector(station, connector)
    if power is not None and power > 0:
        duration = energy_to_add_kwh / power * 60.0
        notes.append(
            "Duration assumes the listed maximum kW is delivered continuously at 100 percent, which real chargers do not do."
        )
    else:
        notes.append("Listed power is missing, so charging duration was not estimated.")
    tariff, _ = tariff_for_connector(station, connector)
    if tariff is not None:
        cost = energy_to_add_kwh * tariff
        notes.append("Cost uses the listed LKR/kWh figure for this plug type and is not a verified bill.")
    else:
        notes.append("Tariff is missing or ambiguous, so charging cost was not estimated and was not set to zero.")
    return duration, cost, " ".join(notes)


def _normalize_penalty(value: float, values: list[float]) -> float:
    low = min(values)
    high = max(values)
    if high == low:
        return 0.0
    return (value - low) / (high - low)


def rank_feasible(rows: list[dict], weights: dict[str, float], connector: str | None = None) -> None:
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
                "tariff": tariff_for_connector(station, connector)[0],
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


def _haversine_km(a: LatLon, b: LatLon) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (a.latitude, a.longitude, b.latitude, b.longitude))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def _point(station: dict) -> LatLon:
    return LatLon(latitude=station["latitude"], longitude=station["longitude"])


def _exclude(base: dict, reason: str) -> None:
    base["exclusion_reason"] = reason
    base["ranking_explanation"] = reason


def _road_matrix(
    provider: RoutingProvider, origin: LatLon, destination: LatLon, candidates: list[dict]
) -> tuple[RoadMatrix, list[dict]]:
    """One road matrix for the origin, the destination and the candidate stations.

    If there are more candidates than one table request allows, the stations with
    the smallest straight-line detour are kept. The rest are reported as not
    routed; no distance is guessed for them.
    """
    limit = getattr(provider, "max_table_points", None)
    dropped: list[dict] = []
    if limit is not None and len(candidates) + 2 > limit:
        ordered = sorted(
            candidates,
            key=lambda station: _haversine_km(origin, _point(station)) + _haversine_km(_point(station), destination),
        )
        candidates, dropped = ordered[: limit - 2], ordered[limit - 2 :]
    points = {ORIGIN: origin, DESTINATION: destination}
    points.update({station["station_id"]: _point(station) for station in candidates})
    pairs = None
    if len(points) > PAIRWISE_ALL_PAIRS_LIMIT:
        pairs = [(ORIGIN, DESTINATION)]
        for station in candidates:
            pairs += [(ORIGIN, station["station_id"]), (station["station_id"], DESTINATION)]
    return build_matrix(provider, points, pairs), dropped


def _attach_geometry(provider: RoutingProvider, origin: LatLon, destination: LatLon, row: dict) -> int:
    """Road shapes for one station's two legs. Distances stay the matrix values used for ranking."""
    requests = 0
    station_point = _point(row["station"])
    for key, start, end in (
        ("origin_to_station", origin, station_point),
        ("station_to_destination", station_point, destination),
    ):
        leg = row[key]
        if leg is None:
            continue
        requests += 1
        try:
            shaped = provider.route(start, end)
        except RoutingError:
            continue
        row[key] = RouteLeg(
            distance_km=leg.distance_km, duration_min=leg.duration_min, provider=shaped.provider, geometry=shaped.geometry
        )
    return requests


def _freshness(stations: list[dict]) -> str:
    dates = sorted({station.get("retrieved_on") for station in stations if station.get("retrieved_on")})
    if dates:
        return f"Open Charge Map listings retrieved {dates[-1]}. Not a live snapshot."
    return "Open Charge Map listings copied into the project CSV. Not a live snapshot."


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

    # Checks that need no road distance come first, so only real candidates are routed.
    rows: list[dict] = []
    candidates: list[dict] = []
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
        rows.append(base)
        if compatible is False:
            _exclude(base, f"Listed connectors do not include the required connector '{request.required_connector}'.")
        elif station["availability_status"] == "unavailable":
            _exclude(base, "The listing marks this station unavailable.")
        elif not station["listed_word_operational"]:
            _exclude(base, "The listing does not say the station is operational.")
        else:
            candidates.append(station)

    try:
        matrix, not_routed = _road_matrix(provider, origin, destination, candidates)
    except RoutingError as exc:
        raise RoutingError("Routing is unavailable, so no station can be recommended. " + str(exc)) from exc
    skipped = {station["station_id"] for station in not_routed}

    for base in rows:
        station = base["station"]
        sid = station["station_id"]
        if base["exclusion_reason"]:
            continue
        if sid in skipped:
            _exclude(base, "Not routed: only the stations closest to this trip fit in one road-matrix request.")
            continue
        to_station = matrix.route_leg(ORIGIN, sid)
        onward = matrix.route_leg(sid, DESTINATION)
        if to_station is None or onward is None:
            _exclude(base, "Road route unavailable for this station. The routing provider returned no road leg.")
            continue
        base["origin_to_station"] = to_station
        base["station_to_destination"] = onward
        base["detour_distance_km"] = to_station.distance_km + onward.distance_km - direct.distance_km
        base["detour_duration_min"] = to_station.duration_min + onward.duration_min - direct.duration_min
        if request.maximum_detour_km is not None and base["detour_distance_km"] > request.maximum_detour_km:
            _exclude(
                base,
                f"Detour {base['detour_distance_km']:.2f} km exceeds the maximum of {request.maximum_detour_km:.2f} km.",
            )
            continue
        battery = assess_reachability(
            to_station.distance_km,
            request.current_soc_percent,
            request.usable_battery_capacity_kwh,
            request.consumption_kwh_per_100km,
            request.minimum_reserve_percent,
        )
        base["battery"] = battery
        if battery.status != "feasible":
            _exclude(
                base,
                "Battery feasibility is infeasible."
                if battery.status == "infeasible"
                else "Battery feasibility is unknown, so the station is not recommended as reachable.",
            )
            continue
        base["eligible"] = True

    rank_feasible(rows, weights, request.required_connector)
    ranked_rows = sorted(
        [row for row in rows if row["eligible"] and row["score"] is not None], key=lambda row: row["rank"]
    )
    shape_requests = 0
    for row in ranked_rows[: request.geometry_for_top]:
        shape_requests += _attach_geometry(provider, origin, destination, row)
    listing_only = [row["station"]["station_id"] for row in ranked_rows if row["station"]["availability_status"] != "available"]
    if listing_only:
        warnings.append(
            f"{', '.join(listing_only)} {'is' if len(listing_only) == 1 else 'are'} ranked from listing data only. "
            "Real-time availability is unknown, not confirmed."
        )

    vehicle = Vehicle(
        start_soc_percent=request.current_soc_percent,
        usable_kwh=request.usable_battery_capacity_kwh,
        consumption_kwh_per_100km=request.consumption_kwh_per_100km,
        reserve_percent=request.minimum_reserve_percent,
        max_charge_soc_percent=request.max_charge_soc_percent,
        connector=request.required_connector,
    )
    settings = PlannerSettings(stop_overhead_min=request.stop_overhead_min, max_stops=request.max_stops)
    routable = {station["station_id"]: station for station in candidates if station["station_id"] not in skipped}
    evaluations = {sid: single_stop(matrix, station, vehicle, settings) for sid, station in routable.items()}
    plan = plan_charging(matrix, routable, vehicle, settings)
    top_id = ranked_rows[0]["station"]["station_id"] if ranked_rows else None
    comparison = compare_strategies(matrix, routable, vehicle, settings, plan, top_id, evaluations)
    pareto = pareto_flags([evaluations[row["station"]["station_id"]] for row in ranked_rows])
    for row in rows:
        sid = row["station"]["station_id"]
        row["single_stop"] = evaluations.get(sid)
        row["pareto_optimal"] = pareto.get(sid)

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
    if plan["status"] == "planned" and plan["totals"]["stops"] > 1:
        warnings.append(
            f"This trip needs {plan['totals']['stops']} charging stops. One stop is not enough; see the charging plan."
        )

    uses_table = matrix.provider.endswith("-table")
    table_requests = matrix.requests if uses_table else 0
    route_requests = 1 + shape_requests + (0 if uses_table else matrix.requests)
    routing_summary = {
        "provider": matrix.provider,
        "stations_in_inventory": len(stations),
        "stations_routed": len(routable),
        "table_requests": table_requests,
        "route_requests": route_requests,
        "total_requests": table_requests + route_requests,
        "per_station_requests_equivalent": 1 + 2 * len(routable),
        "road_shapes_for_top": min(request.geometry_for_top, len(ranked_rows)),
        "note": (
            "Distances and times for every station come from one road-matrix request. "
            "Road shapes are fetched only for the top-ranked stations, for the map."
            if uses_table
            else "This provider has no matrix endpoint, so each road leg was requested separately."
        ),
    }
    return RecommendResponse(
        recommended_station=recommended,
        alternatives=alternatives,
        direct_route=direct,
        ranking_formula=FORMULA,
        weights_used=weights,
        warnings=warnings,
        data_freshness=_freshness(stations),
        limitations=limitations(len(stations)),
        live_availability=False,
        live_queue_prediction=False,
        charging_plan=plan,
        strategy_comparison=comparison,
        routing_summary=routing_summary,
        inventory_summary={
            "stations": len(stations),
            "routed_for_this_trip": len(routable),
            "excluded_before_routing": len(stations) - len(candidates),
        },
    )


def _to_recommendation(row: dict, request: RecommendRequest) -> StationRecommendation:
    station = row["station"]
    duration, cost, charge_note = _charging_estimates(station, request.energy_to_add_kwh, request.required_connector)
    tariff, tariff_basis = tariff_for_connector(station, request.required_connector)
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
        city=station.get("city") or None,
        province=station.get("province") or None,
        number_of_points=station.get("number_of_points"),
        connector_details=station.get("connector_details") or [],
        usage_type=station.get("usage_type"),
        access_note=station.get("access_note"),
        opening_hours_listed=station.get("opening_hours_listed"),
        phone=station.get("phone"),
        charging_power_kw=power_for_connector(station, request.required_connector),
        tariff_for_connector_lkr_per_kwh=tariff,
        tariff_basis=tariff_basis,
        single_stop=row.get("single_stop"),
        pareto_optimal=row.get("pareto_optimal"),
    )
