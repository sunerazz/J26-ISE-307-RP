# Component 4 evaluation: station choice and charging-stop planning

3420 scenarios: every ordered pair of 20 towns, 3 Nissan Leaf variants (CHAdeMO), start charge 30%, 50%, 80%, reserve 10%. Road legs: OSRM table service at https://router.project-osrm.org (OpenStreetMap data), retrieved 2026-10-22. Charging minutes use listed kW (a lower bound); 5 min per stop overhead; charging capped at 80%.

- Trips that need no charging: 1005
- Trips that need charging (scored below): **2415**

| Strategy | Trips completed | Success rate | Mean trip time (min) | Mean min slower than optimised | Mean detour (km) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Nearest station | 832/2415 | 34.4% | 176.69 | 8.47 | 7.63 |
| Minimum detour | 1114/2415 | 46.1% | 192.64 | 5.98 | 0.63 |
| Weighted ranking | 933/2415 | 38.6% | 191.96 | 5.04 | -0.34 |
| Optimised plan | 1941/2415 | 80.4% | 236.35 | 0.0 | 11.04 |

Mean times are over the trips each strategy completes, so they are not directly comparable across rows; the 'slower than optimised' column is paired on the same trips.

## Optimised plan

- Completed: 1941; not possible with the listed stations: 474
- Rescued trips (no single-stop rule completes them): **816**
- Stops per completed trip: {'1': 1169, '2': 550, '3': 151, '4': 71}
- Mean minutes saved against the best single-stop rule on the same trip: 3.13

## Routing requests per trip

- Matrix method (this version): 6.51
- Per-station method (previous version): 71.0

Per trip, the matrix method sends one direct route, one table request and road shapes for the top three stations. The per-station method used before sends one direct route plus two routes per station.

Figures: `station_inventory_map.png`, `strategy_success_rate.png`, `optimised_time_saving.png`.
