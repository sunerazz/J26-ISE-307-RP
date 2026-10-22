"""Offline evaluation of station choice and charging-stop planning.

    python -m src.evaluate_routing                  # uses the cached road matrix
    python -m src.evaluate_routing --refresh-matrix # asks OSRM once for a new one

One OSRM table request gives road km and minutes between 20 Sri Lankan towns and
every station. The matrix is saved, so the evaluation is reproducible offline.
Each scenario then runs the real recommender (src.recommend_stations.recommend)
against that saved matrix and scores four strategies with one trip model:

- nearest_station:  nearest station by road from the start
- minimum_detour:   smallest extra road distance among stations you can reach
- weighted_ranking: the recommender's top-ranked station
- optimised_plan:   the multi-stop planner (least total time)

Trips that can be driven without charging are counted but not scored.
Vehicles, start charge levels and town coordinates are scenario assumptions,
stated in the report. Road data are OSRM estimates on OpenStreetMap, not live traffic.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import time
from pathlib import Path

from src.recommend_stations import recommend
from src.routing_provider import OsrmRoutingProvider, RoutingError
from src.schemas import LatLon, RecommendRequest, RouteLeg
from src.stations import PROJECT_ROOT, load_stations

MATRIX_JSON = PROJECT_ROOT / "data" / "processed" / "osrm_evaluation_matrix.json"
RESULTS = PROJECT_ROOT / "results"

# Approximate town-centre coordinates (latitude, longitude).
PLACES = {
    "Colombo Fort": (6.9344, 79.8428),
    "Nugegoda": (6.8649, 79.8997),
    "Dehiwala": (6.8511, 79.8653),
    "Negombo": (7.2083, 79.8358),
    "Gampaha": (7.0917, 79.9997),
    "Kalutara": (6.5854, 79.9607),
    "Avissawella": (6.9553, 80.2042),
    "Kandy": (7.2906, 80.6337),
    "Kurunegala": (7.4863, 80.3647),
    "Galle": (6.0535, 80.2210),
    "Matara": (5.9549, 80.5550),
    "Ratnapura": (6.6828, 80.3992),
    "Anuradhapura": (8.3114, 80.4037),
    "Dambulla": (7.8731, 80.6511),
    "Nuwara Eliya": (6.9497, 80.7891),
    "Puttalam": (8.0362, 79.8283),
    "Chilaw": (7.5758, 79.7953),
    "Hambantota": (6.1241, 81.1185),
    "Trincomalee": (8.5874, 81.2152),
    "Batticaloa": (7.7310, 81.6747),
}
COLOMBO_AREA = {"Colombo Fort", "Nugegoda", "Dehiwala"}

# Nissan Leaf variants: the CHAdeMO cars most common in Sri Lanka. Usable kWh, kWh/100 km.
VEHICLES = {
    "Leaf 24 kWh": (21.0, 15.0),
    "Leaf 40 kWh": (37.0, 16.0),
    "Leaf e+ 62 kWh": (56.0, 17.0),
}
START_SOC = (30.0, 50.0, 80.0)
RESERVE = 10.0
CONNECTOR = "CHAdeMO"

STRATEGY_ORDER = ["nearest_station", "minimum_detour", "weighted_ranking", "optimised_plan"]
STRATEGY_LABELS = {
    "nearest_station": "Nearest station",
    "minimum_detour": "Minimum detour",
    "weighted_ranking": "Weighted ranking",
    "optimised_plan": "Optimised plan",
}


def _key(point: LatLon) -> tuple[float, float]:
    return round(point.latitude, 6), round(point.longitude, 6)


class MatrixProvider:
    """Serves road legs from the saved OSRM matrix. Legs outside it raise RoutingError."""

    name = "osrm-cached"

    def __init__(self, matrix: dict):
        self.index = {(round(lat, 6), round(lon, 6)): i for i, (lat, lon) in enumerate(matrix["points"])}
        self.km = matrix["km"]
        self.minutes = matrix["minutes"]
        self.route_calls = 0
        self.table_calls = 0

    def route(self, origin: LatLon, destination: LatLon) -> RouteLeg:
        self.route_calls += 1
        i, j = self.index.get(_key(origin)), self.index.get(_key(destination))
        if i is None or j is None or self.km[i][j] is None:
            raise RoutingError("Leg is not in the saved matrix.")
        return RouteLeg(distance_km=self.km[i][j], duration_min=self.minutes[i][j], provider=self.name)

    def table(self, points: list[LatLon]):
        self.table_calls += 1
        rows = [self.index.get(_key(point)) for point in points]
        if any(row is None for row in rows):
            raise RoutingError("A point is not in the saved matrix.")
        km = [[self.km[i][j] for j in rows] for i in rows]
        minutes = [[self.minutes[i][j] for j in rows] for i in rows]
        return km, minutes


def refresh_matrix(stations: list[dict]) -> dict:
    points = [list(coords) for coords in PLACES.values()] + [[s["latitude"], s["longitude"]] for s in stations]
    provider = OsrmRoutingProvider(timeout_seconds=60)
    km, minutes = provider.table([LatLon(latitude=lat, longitude=lon) for lat, lon in points])
    payload = {
        "source": f"OSRM table service at {provider.base_url} (OpenStreetMap data)",
        "retrieved_on": time.strftime("%Y-%m-%d"),
        "places": list(PLACES),
        "station_ids": [s["station_id"] for s in stations],
        "points": points,
        "km": km,
        "minutes": minutes,
    }
    MATRIX_JSON.parent.mkdir(parents=True, exist_ok=True)
    MATRIX_JSON.write_text(json.dumps(payload), encoding="utf-8")
    return payload


def run_scenarios(stations: list[dict], matrix: dict) -> list[dict]:
    provider = MatrixProvider(matrix)
    rows = []
    for origin_name, origin in PLACES.items():
        for destination_name, destination in PLACES.items():
            if origin_name == destination_name:
                continue
            for vehicle, (usable, consumption) in VEHICLES.items():
                for soc in START_SOC:
                    request = RecommendRequest(
                        origin_latitude=origin[0],
                        origin_longitude=origin[1],
                        destination_latitude=destination[0],
                        destination_longitude=destination[1],
                        current_soc_percent=soc,
                        usable_battery_capacity_kwh=usable,
                        consumption_kwh_per_100km=consumption,
                        minimum_reserve_percent=RESERVE,
                        required_connector=CONNECTOR,
                    )
                    provider.route_calls = provider.table_calls = 0
                    response = recommend(request, provider, stations)
                    plan = response.charging_plan
                    base = {
                        "origin": origin_name,
                        "destination": destination_name,
                        "colombo_origin": origin_name in COLOMBO_AREA,
                        "vehicle": vehicle,
                        "start_soc_percent": soc,
                        "direct_km": response.direct_route.distance_km,
                        "direct_min": response.direct_route.duration_min,
                        "needs_charging": plan["status"] != "no_charge_needed",
                        "requests_matrix_method": response.routing_summary["total_requests"],
                        "requests_per_station_method": response.routing_summary["per_station_requests_equivalent"],
                    }
                    for row in response.strategy_comparison["rows"]:
                        rows.append(
                            {
                                **base,
                                "strategy": row["strategy"],
                                "station_ids": " ".join(row["station_ids"]),
                                "feasible": row["feasible"],
                                "stops": row.get("stops"),
                                "total_trip_min": row.get("total_trip_min"),
                                "charging_min": row.get("charging_min"),
                                "detour_km": row.get("detour_km"),
                                "listed_cost_lkr": row.get("listed_cost_lkr"),
                            }
                        )
    return rows


def _mean(values: list[float]) -> float | None:
    return round(statistics.fmean(values), 2) if values else None


def summarize(rows: list[dict]) -> dict:
    trips = {}
    for row in rows:
        key = (row["origin"], row["destination"], row["vehicle"], row["start_soc_percent"])
        trips.setdefault(key, {})[row["strategy"]] = row
    all_trips = list(trips.values())
    charging = [trip for trip in all_trips if trip["optimised_plan"]["needs_charging"]]
    strategies = {}
    for name in STRATEGY_ORDER:
        feasible = [trip[name] for trip in charging if trip[name]["feasible"]]
        paired = [trip for trip in charging if trip[name]["feasible"] and trip["optimised_plan"]["feasible"]]
        extra = [trip[name]["total_trip_min"] - trip["optimised_plan"]["total_trip_min"] for trip in paired]
        strategies[name] = {
            "label": STRATEGY_LABELS[name],
            "trips_scored": len(charging),
            "trips_completed": len(feasible),
            "success_rate": round(len(feasible) / len(charging), 4) if charging else None,
            "mean_total_trip_min": _mean([row["total_trip_min"] for row in feasible]),
            "mean_charging_min": _mean([row["charging_min"] for row in feasible]),
            "mean_detour_km": _mean([row["detour_km"] for row in feasible if row["detour_km"] is not None]),
            "mean_minutes_slower_than_optimised": _mean(extra),
            "max_minutes_slower_than_optimised": round(max(extra), 2) if extra else None,
        }
    optimised_ok = [trip for trip in charging if trip["optimised_plan"]["feasible"]]
    single_names = STRATEGY_ORDER[:-1]
    rescued = [trip for trip in optimised_ok if not any(trip[name]["feasible"] for name in single_names)]
    best_single = []
    for trip in optimised_ok:
        options = [trip[name]["total_trip_min"] for name in single_names if trip[name]["feasible"]]
        if options:
            best_single.append(min(options) - trip["optimised_plan"]["total_trip_min"])
    stops = [trip["optimised_plan"]["stops"] for trip in optimised_ok]
    colombo = [trip for trip in charging if trip["optimised_plan"]["colombo_origin"]]
    first = [trip["optimised_plan"] for trip in all_trips]
    return {
        "scenarios": len(all_trips),
        "places": len(PLACES),
        "vehicles": {name: {"usable_kwh": v[0], "kwh_per_100km": v[1]} for name, v in VEHICLES.items()},
        "start_soc_percent": list(START_SOC),
        "reserve_percent": RESERVE,
        "connector": CONNECTOR,
        "trips_without_charging": len(all_trips) - len(charging),
        "trips_needing_charging": len(charging),
        "trips_from_colombo_needing_charging": len(colombo),
        "strategies": strategies,
        "optimised_plan": {
            "completed": len(optimised_ok),
            "infeasible_with_listed_stations": len(charging) - len(optimised_ok),
            "rescued_trips": len(rescued),
            "rescued_note": "Trips the optimised plan completes where none of the single-stop rules does.",
            "stops_distribution": {str(n): stops.count(n) for n in sorted(set(stops))},
            "mean_minutes_saved_vs_best_single_stop": _mean(best_single),
            "trips_where_best_single_stop_is_slower_by_5_min_or_more": sum(value >= 5 for value in best_single),
        },
        "routing_requests": {
            "mean_matrix_method": _mean([row["requests_matrix_method"] for row in first]),
            "mean_per_station_method": _mean([row["requests_per_station_method"] for row in first]),
            "note": (
                "Per trip, the matrix method sends one direct route, one table request and road shapes for the top "
                "three stations. The per-station method used before sends one direct route plus two routes per station."
            ),
        },
    }


def write_outputs(rows: list[dict], summary: dict, stations: list[dict], matrix: dict) -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    with (RESULTS / "routing_evaluation_scenarios.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary["matrix_source"] = matrix["source"]
    summary["matrix_retrieved_on"] = matrix["retrieved_on"]
    (RESULTS / "routing_evaluation_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    lines = [
        "# Component 4 evaluation: station choice and charging-stop planning",
        "",
        f"{summary['scenarios']} scenarios: every ordered pair of {summary['places']} towns, "
        f"{len(summary['vehicles'])} Nissan Leaf variants ({CONNECTOR}), start charge "
        f"{', '.join(f'{s:g}%' for s in START_SOC)}, reserve {RESERVE:g}%. Road legs: {matrix['source']}, "
        f"retrieved {matrix['retrieved_on']}. Charging minutes use listed kW (a lower bound); 5 min per stop overhead; "
        "charging capped at 80%.",
        "",
        f"- Trips that need no charging: {summary['trips_without_charging']}",
        f"- Trips that need charging (scored below): **{summary['trips_needing_charging']}**",
        "",
        "| Strategy | Trips completed | Success rate | Mean trip time (min) | Mean min slower than optimised | Mean detour (km) |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name in STRATEGY_ORDER:
        item = summary["strategies"][name]
        lines.append(
            f"| {item['label']} | {item['trips_completed']}/{item['trips_scored']} | {item['success_rate']:.1%} "
            f"| {item['mean_total_trip_min']} | {item['mean_minutes_slower_than_optimised']} | {item['mean_detour_km']} |"
        )
    plan = summary["optimised_plan"]
    lines += [
        "",
        "Mean times are over the trips each strategy completes, so they are not directly comparable across rows; "
        "the 'slower than optimised' column is paired on the same trips.",
        "",
        "## Optimised plan",
        "",
        f"- Completed: {plan['completed']}; not possible with the listed stations: {plan['infeasible_with_listed_stations']}",
        f"- Rescued trips (no single-stop rule completes them): **{plan['rescued_trips']}**",
        f"- Stops per completed trip: {plan['stops_distribution']}",
        f"- Mean minutes saved against the best single-stop rule on the same trip: {plan['mean_minutes_saved_vs_best_single_stop']}",
        "",
        "## Routing requests per trip",
        "",
        f"- Matrix method (this version): {summary['routing_requests']['mean_matrix_method']}",
        f"- Per-station method (previous version): {summary['routing_requests']['mean_per_station_method']}",
        "",
        summary["routing_requests"]["note"],
        "",
        "Figures: `station_inventory_map.png`, `strategy_success_rate.png`, `optimised_time_saving.png`.",
        "",
    ]
    (RESULTS / "routing_evaluation.md").write_text("\n".join(lines), encoding="utf-8")
    _plots(rows, summary, stations)


# Reference palette (dataviz skill), light mode.
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
GRID = "#e4e3df"
DC_COLOR = "#2a78d6"
AC_COLOR = "#eb6834"


def _axes(ax) -> None:
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=INK_2, labelsize=9)
    ax.grid(color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def _plots(rows: list[dict], summary: dict, stations: list[dict]) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({"font.size": 10, "text.color": INK, "axes.labelcolor": INK_2})

    operational = [s for s in stations if s["listed_word_operational"]]
    fig, ax = plt.subplots(figsize=(6.4, 8.4), facecolor=SURFACE)
    _axes(ax)
    for label, color, test in (
        ("DC fast charging", DC_COLOR, lambda s: s["dc_max_power_kw"] is not None),
        ("AC only", AC_COLOR, lambda s: s["dc_max_power_kw"] is None),
    ):
        chosen = [s for s in operational if test(s)]
        ax.scatter(
            [s["longitude"] for s in chosen],
            [s["latitude"] for s in chosen],
            s=[20 + min(s["max_power_kw_listed"] or 3, 60) * 2.0 for s in chosen],
            color=color,
            edgecolor=SURFACE,
            linewidth=1.2,
            label=f"{label} ({len(chosen)})",
            zorder=3,
        )
    for name, (lat, lon) in PLACES.items():
        if name in COLOMBO_AREA and name != "Colombo Fort":
            continue
        ax.plot(lon, lat, marker="s", markersize=3.5, color=INK_2, zorder=2)
        ax.annotate("Colombo" if name == "Colombo Fort" else name, (lon, lat), xytext=(-6, 4), textcoords="offset points",
                    fontsize=7.5, color=INK_2, ha="right" if name in ("Colombo Fort", "Negombo") else "left")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_aspect("equal")
    ax.set_title(f"{len(operational)} operational listed stations (marker size = listed kW)", fontsize=10.5, loc="left")
    legend = ax.legend(frameon=False, loc="upper left", fontsize=9)
    for handle in legend.legend_handles:
        handle.set_sizes([60])
    fig.tight_layout()
    fig.savefig(RESULTS / "station_inventory_map.png", dpi=160)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7.2, 3.2), facecolor=SURFACE)
    _axes(ax)
    ax.grid(axis="y", visible=False)
    labels = [summary["strategies"][name]["label"] for name in STRATEGY_ORDER][::-1]
    rates = [summary["strategies"][name]["success_rate"] * 100 for name in STRATEGY_ORDER][::-1]
    bars = ax.barh(labels, rates, color=DC_COLOR, height=0.55, edgecolor=SURFACE, linewidth=2)
    for bar, rate in zip(bars, rates):
        ax.text(bar.get_width() + 1, bar.get_y() + bar.get_height() / 2, f"{rate:.1f}%", va="center", fontsize=9, color=INK)
    ax.set_xlim(0, 110)
    ax.set_xlabel("Trips completed above the reserve (%)")
    ax.set_title(f"Success on {summary['trips_needing_charging']} trips that need charging", fontsize=10.5, loc="left")
    fig.tight_layout()
    fig.savefig(RESULTS / "strategy_success_rate.png", dpi=160)
    plt.close(fig)

    trips = {}
    for row in rows:
        trips.setdefault((row["origin"], row["destination"], row["vehicle"], row["start_soc_percent"]), {})[row["strategy"]] = row
    savings = []
    for trip in trips.values():
        plan = trip["optimised_plan"]
        if not plan["needs_charging"] or not plan["feasible"]:
            continue
        options = [trip[name]["total_trip_min"] for name in STRATEGY_ORDER[:-1] if trip[name]["feasible"]]
        if options:
            savings.append(min(options) - plan["total_trip_min"])
    bands = [("< 1", 0, 1), ("1-5", 1, 5), ("5-10", 5, 10), ("10-20", 10, 20), ("20-40", 20, 40), ("40+", 40, float("inf"))]
    counts = [sum(low <= value < high for value in savings) for _, low, high in bands]
    fig, ax = plt.subplots(figsize=(7.2, 3.2), facecolor=SURFACE)
    _axes(ax)
    ax.grid(axis="x", visible=False)
    bars = ax.bar([band[0] for band in bands], counts, color=DC_COLOR, width=0.6, edgecolor=SURFACE, linewidth=2)
    for bar, count in zip(bars, counts):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + max(counts) * 0.02, str(count), ha="center", fontsize=9, color=INK)
    ax.set_xlabel("Minutes saved by the optimised plan vs the best single-stop rule (same trip)")
    ax.set_ylabel("Trips")
    ax.set_title(f"Time saved on {len(savings)} trips where a single stop also works", fontsize=10.5, loc="left")
    fig.tight_layout()
    fig.savefig(RESULTS / "optimised_time_saving.png", dpi=160)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--refresh-matrix", action="store_true", help="Request a new road matrix from OSRM.")
    args = parser.parse_args()
    stations = load_stations()
    if args.refresh_matrix or not MATRIX_JSON.exists():
        matrix = refresh_matrix(stations)
    else:
        matrix = json.loads(MATRIX_JSON.read_text(encoding="utf-8"))
        if matrix["station_ids"] != [s["station_id"] for s in stations]:
            raise SystemExit("The saved matrix was built for a different inventory. Run with --refresh-matrix.")
    started = time.time()
    rows = run_scenarios(stations, matrix)
    summary = summarize(rows)
    summary["runtime_seconds"] = round(time.time() - started, 1)
    write_outputs(rows, summary, stations, matrix)
    print(json.dumps({k: summary[k] for k in ("scenarios", "trips_needing_charging", "optimised_plan", "routing_requests")}, indent=2))
    for name in STRATEGY_ORDER:
        item = summary["strategies"][name]
        print(f"{item['label']:18} {item['success_rate']:.1%}  slower by {item['mean_minutes_slower_than_optimised']} min")


if __name__ == "__main__":
    main()
