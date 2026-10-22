# Station recommendation and charging-stop planning

Component 4 of the research project **AI-Based Intelligent EV Charging Prediction and Decision Support Framework**.

For a trip, this component ranks the listed charging stations by road route and battery. It also plans the least-time sequence of charging stops when one stop is not enough. It is not a machine-learning classifier. It does not claim live charger availability.

## Data

| File | What it is |
| --- | --- |
| `data/raw/ocm_pages/` | Open Charge Map detail pages for all 68 Sri Lankan listings, saved 2026-10-22 (CC BY 4.0) |
| `data/raw/ocm_sri_lanka_snapshot.json` | The same pages parsed to JSON: `python -m src.ocm_snapshot --offline` |
| `data/raw/sri_lanka_ev_stations.csv` | **The inventory the service uses**: `python -m src.build_inventory` |
| `data/raw/colombo_ev_stations.csv` | The original four Colombo listings. Unchanged; used as a fixed test fixture |

The OCM JSON API now requires a key. `src/ocm_snapshot.py` reads the public HTML pages instead. Run it without `--offline` to download fresh pages.

The inventory has **67 stations** (68 listings; one is a duplicate). 18 are within 20 km of Colombo Fort, 37 have DC fast charging, and 66 are listed as operational. Each station has these fields from its listing:

- per-connector count, kW and AC/DC
- number of points
- usage type
- phone
- opening hours, when stated

Tariffs are the operator rates quoted in the listing (chargeNET: L3 DC 120, L2 AC 70 LKR/kWh). They are stored per supply type and used only for the plug you choose. CEB listings quote no rate, so their rate stays unknown.

Live availability, queue length and waiting time are not published. They stay blank and are never set to zero.

`results/data_completeness_report.md` compares the original CSV with the rebuilt inventory, field by field. Rebuilding also corrected the original rows. The CHAdeMO units are 24 kW (ST003: 18 kW), not the 30 kW from the comment text, and ST004's AC rate is now listed as 70 LKR/kWh.

## Routing

`src/routing_provider.py` calls OSRM (default `https://router.project-osrm.org`; set `OSRM_BASE_URL` for your own server). The recommender sends:

1. one direct route,
2. **one table request** for road km and minutes between the origin, the destination and every candidate station,
3. road shapes for the top three ranked stations only (for the map).

That is about 8 requests per trip. Routing each station separately took 71. A pair OSRM cannot route stays missing; it is never replaced with a straight line.

## Battery check and ranking

```
leg_kwh = road_km * consumption_kwh_per_100km / 100
```

A station is ranked only if:

- its road route exists,
- the requested connector is listed,
- the listing says "Operational",
- the detour is within the optional maximum,
- it can be reached above the reserve.

Default weights are detour distance 0.40, extra time 0.30, waiting time 0.15 and listed tariff for your plug 0.15. A factor is compared only when at least two stations have it, and missing factors are dropped and the remaining weights renormalized.

## Charging-stop planner

`src/charging_plan.py` finds the least total trip time: driving, plus charging at the listed kW of your plug, plus a fixed overhead per stop (default 5 min). The plan has these limits:

- charging capped at 80%,
- every leg finishes above the reserve,
- at most 4 stops.

The search is label-setting over (place, battery level) states. At each stop it either charges just enough for the next leg or charges to the cap. That choice contains an optimal plan when charging time is linear in energy (Khuller, Malekian and Mestre, *To fill or not to fill: the gas station problem*, 2011).

Each response also contains:

- `strategy_comparison`: the optimised plan against three simple rules (nearest station, minimum detour, top of the weighted ranking), all scored with the same trip model.
- `pareto_optimal` per station: whether any other station is both faster overall and cheaper at listed rates.

## Evaluation

```powershell
python -m src.evaluate_routing                  # uses the saved road matrix
python -m src.evaluate_routing --refresh-matrix # one new OSRM table request
```

There are 3,420 scenarios: every ordered pair of 20 towns × 3 Nissan Leaf variants (CHAdeMO) × start charge 30/50/80%, with a 10% reserve. 2,415 of them need charging:

| Strategy | Trips completed |
| --- | ---: |
| Nearest station | 34.4% |
| Minimum detour | 46.1% |
| Weighted ranking | 38.6% |
| **Optimised plan** | **80.4%** |

- The planner completes 816 trips that no single-stop rule completes.
- It is never slower than a single-stop rule on the same trip.
- 474 trips cannot be completed with the listed stations at all.

Outputs are in `results/`: `routing_evaluation.md`, `routing_evaluation_summary.json`, per-scenario `routing_evaluation_scenarios.csv`, and three figures.

## API

```powershell
python -m uvicorn api.main:app --reload --port 8004
```

- `GET /health`
- `GET /api/v1/stations`
- `POST /api/v1/recommend-station` (optional: `max_charge_soc_percent`, `stop_overhead_min`, `max_stops`)
- `GET /api/v1/research`: completeness report and evaluation summary

## Tests

Tests use mock routers labelled `provider: "mock"`. They do not call OSRM.

```powershell
python -m pytest -q
```

## Limits

- Listings are not live data and may be outdated. Confirm with the operator.
- Charging minutes assume listed kW at full power; real chargers taper, so they are a lower bound.
- The evaluation's vehicles, start levels and town coordinates are scenario assumptions.
- Road times are OSRM estimates on OpenStreetMap data, not live traffic.
