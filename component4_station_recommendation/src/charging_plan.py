"""Charging-stop planning on a road matrix: single stops, multi-stop plans and baselines.

Energy for a road leg uses the same formula as the battery check:

    leg_kwh = road_km * consumption_kwh_per_100km / 100

Charging minutes are kWh added divided by the listed kW of the driver's plug at
that station. Real chargers taper, so these minutes are a lower bound.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass

from src.route_optimizer import RoadMatrix
from src.stations import power_for_connector, tariff_for_connector

ORIGIN = "origin"
DESTINATION = "destination"

ALGORITHM = (
    "Label-setting shortest path over (place, battery level) states. Places are the origin, every "
    "candidate station and the destination; every pair is joined by its road leg. At each stop the "
    "planner either charges just enough for the next leg or charges to the cap. For charging time that "
    "is linear in energy this 'fill or just enough' choice contains an optimal plan (Khuller, Malekian "
    "and Mestre, 'To fill or not to fill: the gas station problem', 2011). A label is dropped when another "
    "label at the same place is no slower, has at least as much battery and no more stops. The first label "
    "to reach the destination has the least total time."
)


@dataclass
class Vehicle:
    start_soc_percent: float
    usable_kwh: float
    consumption_kwh_per_100km: float
    reserve_percent: float
    max_charge_soc_percent: float = 80.0
    connector: str | None = None

    def soc_points(self, km: float) -> float:
        return km * self.consumption_kwh_per_100km / 100.0 / self.usable_kwh * 100.0

    def kwh(self, soc_points: float) -> float:
        return soc_points / 100.0 * self.usable_kwh


@dataclass
class PlannerSettings:
    stop_overhead_min: float = 5.0
    max_stops: int = 4


def assumptions(vehicle: Vehicle, settings: PlannerSettings) -> list[str]:
    return [
        "Leg energy is road km times the consumption figure you entered.",
        f"Every leg must finish at or above your {vehicle.reserve_percent:g}% reserve.",
        f"Charging stops at {vehicle.max_charge_soc_percent:g}% at most.",
        "Charging minutes use the listed kW of your plug, delivered at full power. Real chargers taper, so expect longer.",
        f"Each stop adds {settings.stop_overhead_min:g} minutes to park, plug in and pay.",
        "Live availability and queues are unknown. No waiting time is added.",
        "Listed tariffs are the operator rates quoted in Open Charge Map and are not verified bills.",
    ]


def single_stop(matrix: RoadMatrix, station: dict, vehicle: Vehicle, settings: PlannerSettings) -> dict:
    """Drive to one station, charge just enough to finish above the reserve, then drive on."""
    sid = station["station_id"]
    result = {
        "station_id": sid,
        "feasible": False,
        "reason": None,
        "arrival_soc_percent": None,
        "minimum_departure_soc_percent": None,
        "departure_soc_percent": None,
        "energy_added_kwh": None,
        "charging_power_kw": power_for_connector(station, vehicle.connector),
        "charging_min": None,
        "total_trip_min": None,
        "listed_cost_lkr": None,
    }
    to_station = matrix.leg(ORIGIN, sid)
    onward = matrix.leg(sid, DESTINATION)
    if to_station is None or onward is None:
        result["reason"] = "Road leg missing."
        return result
    arrival = vehicle.start_soc_percent - vehicle.soc_points(to_station[0])
    need = vehicle.reserve_percent + vehicle.soc_points(onward[0])
    result["arrival_soc_percent"] = arrival
    result["minimum_departure_soc_percent"] = need
    if arrival < vehicle.reserve_percent:
        result["reason"] = "Cannot reach this station above the reserve."
        return result
    if need > vehicle.max_charge_soc_percent:
        result["reason"] = f"Even charging to {vehicle.max_charge_soc_percent:g}% here cannot finish the trip above the reserve."
        return result
    power = result["charging_power_kw"]
    depart = max(arrival, need)
    added = vehicle.kwh(depart - arrival)
    if added > 0 and not power:
        result["reason"] = "Listed power for your plug is unknown, so charging time cannot be estimated."
        return result
    charging = added / power * 60.0 if added > 0 else 0.0
    tariff, _ = tariff_for_connector(station, vehicle.connector)
    result.update(
        {
            "feasible": True,
            "departure_soc_percent": depart,
            "energy_added_kwh": added,
            "charging_min": charging,
            "total_trip_min": to_station[1] + onward[1] + settings.stop_overhead_min + charging,
            "listed_cost_lkr": added * tariff if tariff is not None else None,
            "drive_km": to_station[0] + onward[0],
        }
    )
    return result


def plan_charging(matrix: RoadMatrix, stations: dict[str, dict], vehicle: Vehicle, settings: PlannerSettings) -> dict:
    """Least-time plan from origin to destination with zero or more charging stops."""
    power = {sid: power_for_connector(station, vehicle.connector) for sid, station in stations.items()}
    usable = [sid for sid in stations if power[sid]]
    cap = vehicle.max_charge_soc_percent
    # Label: (total_min, sequence, place, soc_on_arrival, stops, parent, step)
    labels: list[tuple] = []
    heap: list[tuple[float, int]] = []
    settled: dict[str, list[tuple[float, float, int]]] = {}

    def push(total: float, place: str, soc: float, stops: int, parent: int | None, step: dict | None) -> None:
        labels.append((total, place, soc, stops, parent, step))
        heapq.heappush(heap, (total, len(labels) - 1))

    def dominated(place: str, total: float, soc: float, stops: int) -> bool:
        return any(t <= total + 1e-9 and s >= soc - 1e-9 and n <= stops for t, s, n in settled.get(place, []))

    push(0.0, ORIGIN, vehicle.start_soc_percent, 0, None, None)
    explored = 0
    best = None
    while heap:
        total, index = heapq.heappop(heap)
        _, place, soc, stops, _, _ = labels[index]
        if dominated(place, total, soc, stops):
            continue
        settled.setdefault(place, []).append((total, soc, stops))
        explored += 1
        if place == DESTINATION:
            best = index
            break
        targets = [DESTINATION] + ([sid for sid in usable if sid != place] if stops < settings.max_stops else [])
        for target in targets:
            leg = matrix.leg(place, target)
            if leg is None:
                continue
            km, minutes = leg
            used = vehicle.soc_points(km)
            if place == ORIGIN:
                if soc - used >= vehicle.reserve_percent:
                    push(total + minutes, target, soc - used, stops + (target != DESTINATION), index, {"depart": soc, "km": km, "min": minutes})
                continue
            need = vehicle.reserve_percent + used
            if need > cap:
                continue
            # Departing at the arrival level (no charge) is kept: the fastest direct road can use
            # more energy than a slightly slower road past this station, as single_stop allows.
            for depart in sorted({max(soc, need), cap}):
                if depart < soc - 1e-9:
                    continue
                added = vehicle.kwh(depart - soc)
                charging = added / power[place] * 60.0
                step = {"depart": depart, "km": km, "min": minutes, "added": added, "charging": charging}
                push(
                    total + settings.stop_overhead_min + charging + minutes,
                    target,
                    depart - used,
                    stops + (target != DESTINATION),
                    index,
                    step,
                )

    direct = matrix.leg(ORIGIN, DESTINATION)
    direct_info = None
    if direct is not None:
        arrival = vehicle.start_soc_percent - vehicle.soc_points(direct[0])
        direct_info = {
            "distance_km": direct[0],
            "duration_min": direct[1],
            "arrival_soc_percent": arrival,
            "feasible_without_charging": arrival >= vehicle.reserve_percent,
        }
    base = {
        "objective": "least total trip time: driving + charging + a fixed overhead per stop",
        "algorithm": ALGORITHM,
        "assumptions": assumptions(vehicle, settings),
        "max_charge_soc_percent": cap,
        "stop_overhead_min": settings.stop_overhead_min,
        "max_stops": settings.max_stops,
        "candidates_considered": len(usable),
        "labels_explored": explored,
        "direct": direct_info,
    }
    if best is None:
        reachable = [
            sid for sid in usable
            if (leg := matrix.leg(ORIGIN, sid)) is not None
            and vehicle.start_soc_percent - vehicle.soc_points(leg[0]) >= vehicle.reserve_percent
        ]
        return {
            **base,
            "status": "infeasible",
            "stops": [],
            "final_leg": None,
            "arrival_soc_at_destination_percent": None,
            "totals": None,
            "explanation": (
                f"No chain of up to {settings.max_stops} listed stations gets you to the destination above your reserve. "
                f"{len(reachable)} of {len(usable)} candidate stations can be reached from the start."
            ),
        }

    chain = []
    index = best
    while index is not None:
        chain.append(labels[index])
        index = labels[index][4]
    chain.reverse()
    stops = []
    for previous, current in zip(chain, chain[1:]):
        place = previous[1]
        step = current[5]
        if place == ORIGIN:
            continue
        station = stations[place]
        tariff, basis = tariff_for_connector(station, vehicle.connector)
        stops.append(
            {
                "stop": len(stops) + 1,
                "station_id": place,
                "station_name": station["station_name"],
                "area": station.get("area") or station.get("city") or "",
                "latitude": station["latitude"],
                "longitude": station["longitude"],
                "arrival_soc_percent": previous[2],
                "departure_soc_percent": step["depart"],
                "energy_added_kwh": step["added"],
                "charging_power_kw": power[place],
                "charging_min": step["charging"],
                "overhead_min": settings.stop_overhead_min,
                "listed_tariff_lkr_per_kwh": tariff,
                "tariff_basis": basis,
                "listed_cost_lkr": step["added"] * tariff if tariff is not None else None,
            }
        )
    # Drive leg into each stop and the last leg into the destination.
    drives = [label[5] for label in chain[1:]]
    for stop, drive in zip(stops, drives):
        stop["drive_km_from_previous"] = drive["km"]
        stop["drive_min_from_previous"] = drive["min"]
    final = drives[-1]
    destination_label = chain[-1]
    costs = [stop["listed_cost_lkr"] for stop in stops]
    totals = {
        "drive_km": sum(drive["km"] for drive in drives),
        "drive_min": sum(drive["min"] for drive in drives),
        "charging_min": sum(stop["charging_min"] for stop in stops),
        "overhead_min": settings.stop_overhead_min * len(stops),
        "total_min": destination_label[0],
        "energy_added_kwh": sum(stop["energy_added_kwh"] for stop in stops),
        "listed_cost_lkr": sum(costs) if costs and all(cost is not None for cost in costs) else (0.0 if not costs else None),
        "listed_cost_complete": all(cost is not None for cost in costs),
        "stops": len(stops),
    }
    if not stops:
        status = "no_charge_needed"
        explanation = (
            f"The direct drive leaves about {destination_label[2]:.0f}% at the destination, above your "
            f"{vehicle.reserve_percent:g}% reserve, so no charging stop is needed."
        )
    else:
        status = "planned"
        names = " → ".join(f"{stop['station_id']} ({stop['area'] or stop['station_name']})" for stop in stops)
        explanation = (
            f"{len(stops)} stop{'s' if len(stops) > 1 else ''}: {names}. About {totals['total_min']:.0f} min in total: "
            f"{totals['drive_min']:.0f} min driving, {totals['charging_min']:.0f} min charging at listed power "
            f"and {totals['overhead_min']:.0f} min stop overhead. You arrive with about {destination_label[2]:.0f}%."
        )
    return {
        **base,
        "status": status,
        "stops": stops,
        "final_leg": {"distance_km": final["km"], "duration_min": final["min"]},
        "arrival_soc_at_destination_percent": destination_label[2],
        "totals": totals,
        "explanation": explanation,
    }


def pareto_flags(evaluations: list[dict]) -> dict[str, bool]:
    """Stations not beaten on both total trip time and listed cost. Unknown cost is not compared."""
    pool = [item for item in evaluations if item["feasible"] and item["listed_cost_lkr"] is not None]
    flags = {}
    for item in pool:
        flags[item["station_id"]] = not any(
            other is not item
            and other["total_trip_min"] <= item["total_trip_min"]
            and other["listed_cost_lkr"] <= item["listed_cost_lkr"]
            and (other["total_trip_min"] < item["total_trip_min"] or other["listed_cost_lkr"] < item["listed_cost_lkr"])
            for other in pool
        )
    return flags


STRATEGIES = {
    "nearest_station": "Nearest station by road from the start (a 'find nearest charger' app)",
    "minimum_detour": "Smallest extra road distance among stations you can reach",
    "weighted_ranking": "Top station of the weighted ranking (detour, time, waiting, tariff)",
    "optimised_plan": "Optimised plan: least total time, one or more stops",
}


def _strategy_row(key: str, evaluation: dict | None, direct_km: float | None, reason: str | None = None) -> dict:
    row = {"strategy": key, "label": STRATEGIES[key], "station_ids": [], "feasible": False, "reason": reason}
    if evaluation is None:
        return row
    row["station_ids"] = [evaluation["station_id"]]
    row["feasible"] = evaluation["feasible"]
    row["reason"] = evaluation["reason"]
    if evaluation["feasible"]:
        row.update(
            {
                "stops": 1,
                "total_trip_min": evaluation["total_trip_min"],
                "charging_min": evaluation["charging_min"],
                "detour_km": evaluation["drive_km"] - direct_km if direct_km is not None else None,
                "energy_added_kwh": evaluation["energy_added_kwh"],
                "listed_cost_lkr": evaluation["listed_cost_lkr"],
            }
        )
    return row


def compare_strategies(
    matrix: RoadMatrix,
    stations: dict[str, dict],
    vehicle: Vehicle,
    settings: PlannerSettings,
    plan: dict,
    ranked_station_id: str | None,
    evaluations: dict[str, dict] | None = None,
) -> dict:
    """Score simple station-choice rules with the same trip model as the optimised plan."""
    evaluations = evaluations or {sid: single_stop(matrix, station, vehicle, settings) for sid, station in stations.items()}
    direct = matrix.leg(ORIGIN, DESTINATION)
    direct_km = direct[0] if direct else None
    rows = []

    by_road = [(leg[0], sid) for sid in stations if (leg := matrix.leg(ORIGIN, sid)) is not None]
    nearest = min(by_road)[1] if by_road else None
    rows.append(_strategy_row("nearest_station", evaluations.get(nearest), direct_km, None if nearest else "No station has a road route."))

    reachable = [
        sid for sid, item in evaluations.items()
        if item["arrival_soc_percent"] is not None and item["arrival_soc_percent"] >= vehicle.reserve_percent
    ]
    detours = [
        (matrix.leg(ORIGIN, sid)[0] + matrix.leg(sid, DESTINATION)[0], sid)
        for sid in reachable
        if matrix.leg(sid, DESTINATION) is not None
    ]
    minimum = min(detours)[1] if detours else None
    rows.append(_strategy_row("minimum_detour", evaluations.get(minimum), direct_km, None if minimum else "No reachable station."))
    rows.append(
        _strategy_row(
            "weighted_ranking",
            evaluations.get(ranked_station_id) if ranked_station_id else None,
            direct_km,
            None if ranked_station_id else "The ranking found no feasible station.",
        )
    )

    optimised = {"strategy": "optimised_plan", "label": STRATEGIES["optimised_plan"], "station_ids": [stop["station_id"] for stop in plan["stops"]]}
    if plan["status"] == "infeasible":
        optimised.update({"feasible": False, "reason": plan["explanation"]})
    else:
        totals = plan["totals"]
        optimised.update(
            {
                "feasible": True,
                "reason": None,
                "stops": totals["stops"],
                "total_trip_min": totals["total_min"],
                "charging_min": totals["charging_min"],
                "detour_km": totals["drive_km"] - direct_km if direct_km is not None else None,
                "energy_added_kwh": totals["energy_added_kwh"],
                "listed_cost_lkr": totals["listed_cost_lkr"] if totals["listed_cost_complete"] else None,
            }
        )
    rows.append(optimised)

    baselines = [row for row in rows[:-1] if row["feasible"]]
    summary = None
    if optimised["feasible"] and baselines:
        best = min(baselines, key=lambda row: row["total_trip_min"])
        saving = best["total_trip_min"] - optimised["total_trip_min"]
        summary = (
            f"The optimised plan takes {optimised['total_trip_min']:.0f} min. The best simple rule "
            f"({best['label'].split(' (')[0].lower()}) takes {best['total_trip_min']:.0f} min"
            + (f", so the plan saves {saving:.0f} min." if saving >= 0.5 else ", the same within a minute.")
        )
    elif optimised["feasible"]:
        summary = "Only the optimised plan finishes the trip above the reserve. No single stop chosen by a simple rule does."
    else:
        summary = "No strategy finishes the trip above the reserve with the listed stations."
    return {"rows": rows, "summary": summary, "note": "Every row uses the same road legs, energy model and charging assumptions."}
