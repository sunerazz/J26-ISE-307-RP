# Component 4 viva practice

Use this beside the code. Each section is one of the three viva answers, then the file and lines to open, then a question you should answer without looking.

Folder: `component4_station_recommendation/`

## 30-minute practice

1. Read section 1 aloud once.
2. Open each file named in section 2 and find the line. Do not skip this.
3. Cover the model answers in section 6 and answer the ten questions.
4. Uncover and mark anything you said that is stronger than the code.

## 1. What Component 4 is

Component 4 is the station-recommendation and charging-stop planner in the project **AI-Based Intelligent EV Charging Prediction and Decision Support Framework**.

For one trip it answers two questions:

- Which listed Sri Lankan charger can this car reach?
- If one stop is not enough, which sequence of stops finishes the trip in the least time?

This component does not train a model. Queue length, waiting time, and congestion are Component 1. Component 4 uses a wait or a tariff only when that number is already in the data. A blank stays blank and is never stored as zero.

Say this in one sentence:

> Component 4 has no predictive model. OSRM measures the road, and a shortest-path search chooses the charging stops that satisfy the battery and plug constraints in the least time.

Open:

- `README.md` lines 1–7 (purpose) and 114–119 (limits)
- `src/recommend_stations.py` lines 25–33 (what the service refuses to claim)

## 2. What was used

### Station data

Open Charge Map public listing pages for Sri Lanka, saved on 22 October 2026, licence CC BY 4.0. The JSON API needs a key, so the HTML pages were saved instead.

| File | Role |
|---|---|
| `data/raw/ocm_pages/` | The saved listing pages |
| `data/raw/ocm_sri_lanka_snapshot.json` | Those pages parsed to JSON |
| `data/raw/sri_lanka_ev_stations.csv` | The inventory the service loads: 67 stations |
| `data/raw/colombo_ev_stations.csv` | The original four Colombo rows, kept as a fixed test |

68 listings were saved. One is a duplicate and is skipped, so the service uses 67. Eighteen are within 20 km of Colombo Fort. Thirty-seven have DC fast charging. Sixty-six are listed as operational.

Fields kept from each listing: name, address, coordinates, operator, plug types, plug power, phone, and opening hours when the page states them. chargeNET quotes 120 LKR/kWh DC and 70 LKR/kWh AC. Those rates are stored and marked unverified. A CEB listing with no rate stays unknown. Live availability, queue length, and waiting time are empty on every row.

Open:

- `src/ocm_snapshot.py` lines 51–67 (`fetch_pages`, `parse_equipment`) and 85–116 (`parse_page`)
- `src/build_inventory.py` lines 174–283 (`build_rows`) and 136–146 (tariff and hours)
- `src/stations.py` lines 13–15 (which CSV is live, which is the old test file)
- `src/stations.py` lines 132–168 (`load_stations`: skip a duplicate, refuse a bad coordinate, keep a blank as unknown)
- `src/stations.py` lines 37–48 (a tariff is used only when it is one clear number)
- `results/data_completeness_report.md` (what changed from the old four-row file)

Power correction you should remember: the CHAdeMO units are 24 kW, and ST003 is 18 kW. The old 30 kW figure came from a comment, not from the equipment record. ST004’s AC rate is the listed 70 LKR/kWh.

### Roads

OSRM, the Open Source Routing Machine, on OpenStreetMap. Default server: `https://router.project-osrm.org`. Set `OSRM_BASE_URL` if you run your own server.

### Car inputs

The driver supplies these. They are the fields of `RecommendRequest`.

Open `src/schemas.py` lines 18–36:

- `origin_latitude`, `origin_longitude`
- `destination_latitude`, `destination_longitude`
- `current_soc_percent`
- `usable_battery_capacity_kwh`
- `consumption_kwh_per_100km`
- `minimum_reserve_percent`
- `required_connector`
- `maximum_detour_km` (optional)
- `max_charge_soc_percent` (default 80)
- `stop_overhead_min` (default 5)
- `max_stops` (default 4)

## 3. How it was created

Do these in order if an examiner asks you to rebuild it.

1. Save the Open Charge Map pages: `src/ocm_snapshot.py` `fetch_pages` (line 51). Offline parse: `parse_pages` (line 118).
2. Build the CSV: `python -m src.build_inventory`. The writer is `write_inventory` at `src/build_inventory.py` line 290. The completeness comparison is `completeness_report` at line 323.
3. Load that CSV in the recommender: `src/stations.py` line 13 and `load_stations` at line 132.
4. Ask OSRM for roads: `src/routing_provider.py` class `OsrmRoutingProvider` at line 32.
5. Rank stations that pass the gates: `src/recommend_stations.py` `recommend` at line 213.
6. If one stop is not enough, search a stop sequence: `src/charging_plan.py` `plan_charging` at line 120.
7. Score that search against three simple rules: `src/evaluate_routing.py` lines 1–18, run with `python -m src.evaluate_routing`.

Tests use a mock router. They do not call OSRM. See `README.md` lines 106–111.

## 4. How one search works

Follow `recommend` in `src/recommend_stations.py`, starting at line 213.

1. **Direct road.** Line 219 calls `provider.route` for start to destination. If OSRM fails, line 220 stops the search. No station is guessed.
2. **Plug and listing, before any extra routing.** Lines 225–229. A station with the wrong plug is not sent to the road matrix.
3. **One road table.** `src/route_optimizer.py` `build_matrix` at line 39. OSRM’s `table` returns kilometres and minutes for every pair. The public server allows at most 100 points (`src/routing_provider.py` line 55).
4. **Detour.** Lines 275–276:

```
detour km  = (start → station km) + (station → destination km) − direct km
detour min = (start → station min) + (station → destination min) − direct min
```

5. **Battery gate.** `src/battery_feasibility.py` lines 41–45:

```
energy kWh     = road km × (kWh per 100 km) / 100
available kWh  = battery kWh × start charge / 100
reserve kWh    = battery kWh × reserve percent / 100
feasible       = energy kWh ≤ available kWh − reserve kWh
```

A station that fails this gate is not given a score.

6. **Weights**, only among stations that passed. `src/recommend_stations.py` lines 14–19 and `rank_feasible` at line 86.

| Factor | Weight | Field |
|---|---|---|
| Extra kilometres | 0.40 | `detour_distance_km` |
| Extra minutes | 0.30 | `detour_duration_min` |
| Waiting time | 0.15 | `waiting_time_min` |
| Listed price for the chosen plug | 0.15 | `tariff_for_connector_lkr_per_kwh` |

A factor is compared only when at least two stations have a value. A missing factor is dropped and the other weights are scaled. It is not scored as zero. The code says this at `src/recommend_stations.py` lines 27–28 and inside `rank_feasible`.

7. **More than one stop.** `src/charging_plan.py` lines 22–29 state the algorithm. `plan_charging` starts at line 120. Each state is a place plus a battery level. Places are the start, the stations, and the destination. Links are the road legs already in the matrix. At a stop the search tries two choices: charge only enough for the next leg, or charge up to the cap. The first path that reaches the destination is the least total time, when charging time is linear in energy. That result is Khuller, Malekian, and Mestre, *To fill or not to fill: the gas station problem* (2011).

Charging minutes use the listed kW of the driver’s plug (`power_for_connector` in `src/stations.py` line 89): `kWh added ÷ kW`, plus `stop_overhead_min`. Real chargers slow down as the battery fills, so these minutes are a lower bound (`src/charging_plan.py` lines 7–8).

8. **Three simple rules on the same roads.** `src/charging_plan.py` `compare_strategies` at line 342: nearest station, smallest detour, and the weighted rank. The response also marks a station Pareto optimal when no other station is both faster and cheaper (`pareto_flags`, line 298).

## 5. What OSRM means

OSRM means **Open Source Routing Machine**.

- **OpenStreetMap** is the map: roads, junctions, and one-way streets.
- **OSRM** reads that map and answers: which roads a car would drive, how many kilometres, and how many minutes.

You did not train OSRM. The code calls it.

Open `src/routing_provider.py`:

- Lines 32–38: the class, and the warning that the public server is a demo with no service guarantee.
- Lines 50–52: the server is `OSRM_BASE_URL`, or `https://router.project-osrm.org`.
- Lines 57–65: one driving route. Coordinates are sent as longitude, then latitude. The answer includes the road shape (`overview=full`, GeoJSON).
- Lines 67–68: one table request for every pair.
- Line 16: `RoutingError` when the answer is not usable. The caller does not invent a distance.

A missing road stays missing. `src/route_optimizer.py` lines 12–13 and 28–29: a missing pair is `None`, and `leg` returns nothing. It is never a straight line.

The map line in the app is `geometry` on `RouteLeg` (`src/schemas.py` lines 54–60). It is requested only for the top stations (`geometry_for_top` default 3, `src/schemas.py` line 36; attached in `_attach_geometry`, `src/recommend_stations.py` line 184).

Road minutes are map estimates. They are not live traffic.

## 6. Practice questions

Answer aloud, then check the line.

**1. Why is there no model file in Component 4?**

Model answer: A listing is not a labelled set of good and bad station choices. The method is a constraint check plus a shortest-path search. See `src/recommend_stations.py` line 33: the service does not train a classifier on station listings.

**2. What does OSRM stand for, and did you train it?**

Model answer: Open Source Routing Machine. It is called, not trained. Server selection is `src/routing_provider.py` lines 50–52.

**3. Which two numbers come back from OSRM?**

Model answer: `distance_km` and `duration_min` on `RouteLeg` (`src/schemas.py` lines 54–56). The table parser is `parse_osrm_table` at `src/routing_provider.py` line 124.

**4. Write the detour formula.**

Model answer: extra km equals the two legs via the station minus the direct trip. Same for minutes. Code: `src/recommend_stations.py` lines 275–276. The helper `detour` is `src/route_optimizer.py` lines 68–74.

**5. Write the battery check.**

Model answer: energy is road km times kWh per 100 km, divided by 100. The station is feasible only when that energy is no more than the energy above the reserve. Code: `src/battery_feasibility.py` lines 41–45.

**6. Name the four ranking weights.**

Model answer: detour distance 0.40, detour time 0.30, waiting time 0.15, tariff 0.15. Code: `src/recommend_stations.py` lines 14–19.

**7. What happens when waiting time is blank?**

Model answer: It is omitted. The other weights are scaled. It is not treated as zero. Code: `src/recommend_stations.py` lines 27–28, and the blank-queue rule in `src/stations.py` lines 21–28 together with `load_stations`.

**8. What are the planner limits?**

Model answer: charge cap 80 percent, 5 minutes overhead per stop, at most 4 stops, and every leg must finish at or above the reserve. Defaults: `src/schemas.py` lines 32–34 and `src/charging_plan.py` lines 50–52.

**9. Quote the evaluation without mixing up the averages.**

Model answer: 3,420 scenarios. 1,005 need no charge. Of the 2,415 that do, nearest station finishes 34.4 percent, weighted ranking 38.6 percent, minimum detour 46.1 percent, and the optimised plan 80.4 percent. The plan finishes 816 trips that no single-stop rule finishes. 474 trips cannot be finished with the listed stations. Mean trip times are only over the trips that rule completes, so those averages are not compared across rules. Source: `results/routing_evaluation.md` lines 1–22. How the scenarios are built: `src/evaluate_routing.py` lines 1–18.

**10. What must you not claim?**

Model answer, from `README.md` lines 114–119 and `src/recommend_stations.py` lines 25–33:

- The listing is not a live free-charger signal.
- Charging minutes assume full listed power, so they are a lower bound.
- Roads are OSRM on OpenStreetMap, not live traffic.
- Towns, cars, and start charges in the evaluation are scenario assumptions.

## 7. Numbers to memorise

| Item | Value | Where |
|---|---|---|
| Listings saved | 68 | `README.md` line 11 |
| Stations used | 67 | `README.md` line 18 |
| Within 20 km of Colombo Fort | 18 | `README.md` line 18 |
| DC fast charging | 37 | `README.md` line 18 |
| Listed operational | 66 | `README.md` line 18 |
| DC rate quoted by chargeNET | 120 LKR/kWh | `README.md` line 26 |
| AC rate quoted by chargeNET | 70 LKR/kWh | `README.md` line 26 |
| Scenarios | 3,420 | `results/routing_evaluation.md` line 3 |
| Trips that need a charge | 2,415 | `results/routing_evaluation.md` line 6 |
| Optimised plan success | 80.4% (1,941 / 2,415) | `results/routing_evaluation.md` line 13 |
| Trips only the planner finishes | 816 | `results/routing_evaluation.md` line 20 |
| Impossible with these stations | 474 | `results/routing_evaluation.md` line 19 |
| Old routing requests per trip | about 71 | `results/routing_evaluation.md` line 27 |
| Current routing requests per trip | about 6.5 | `results/routing_evaluation.md` line 26 |

## 8. Files, in the order you would open them in the exam

1. `README.md` — the whole story in six pages.
2. `src/schemas.py` lines 18–60 — inputs and the road result.
3. `src/stations.py` lines 13–48 and 132–168 — inventory rules.
4. `src/routing_provider.py` lines 16–68 — what OSRM is in this project.
5. `src/route_optimizer.py` lines 12–74 — the road matrix and the detour.
6. `src/battery_feasibility.py` lines 8–45 — the energy gate.
7. `src/recommend_stations.py` lines 14–33 and 213–286 — one search.
8. `src/charging_plan.py` lines 1–52 and 120–133 — the stop search.
9. `results/routing_evaluation.md` lines 1–29 — the numbers.
10. `results/data_completeness_report.md` — what the rebuilt inventory changed.
