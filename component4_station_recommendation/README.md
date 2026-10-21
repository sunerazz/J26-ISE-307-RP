# Colombo EV charging station recommendation

Component 4 of the research project **AI-Based Intelligent EV Charging Prediction and Decision Support Framework**.

This folder recommends a charging stop for a driver passing through Colombo. It uses four station listings and road routes. It is not a machine-learning classifier, and it does not claim live charger availability.

## Data

The original file is `data/raw/colombo_ev_stations.csv`. Do not edit it. On API startup the service writes a normalized copy to `data/processed/stations_normalized.csv`.

Blank availability, queue length, and waiting time stay unknown. They are never filled with zero. Connector types, power, and tariffs are listing text from Open Charge Map and still need verification. Only a tariff that is a single number (station ST003, `120`) is parsed. Values such as `120 DC; 70 AC` and `80 listed; verify current tariff` stay unknown.

## Routing

`src/routing_provider.py` calls OSRM. The default base URL is the public demo:

`https://router.project-osrm.org`

Set `OSRM_BASE_URL` to your own OSRM server if you have one. The public demo has no uptime promise, is not meant for heavy traffic, and may return HTTP 429. This project does not replace a failed route with a straight-line distance.

OSRM coordinate order is longitude, then latitude.

## Battery check

```
estimated_energy_kwh = route_distance_km * consumption_kwh_per_100km / 100
```

A station is infeasible when that energy is greater than the energy above the minimum reserve. If the road distance is missing, feasibility is `unknown`. This is not a promise that the car will arrive.

## Ranking

Default weights:

| Factor | Weight |
| --- | ---: |
| Detour distance | 0.40 |
| Extra driving time | 0.30 |
| Waiting time | 0.15 |
| Listed tariff | 0.15 |

Among feasible stations, a factor is used only when at least two stations have a value. Each used value is scaled from 1 (best, lowest value) to 0 (worst). The score is the weighted average of factors present for that station. If waiting time or tariff is missing, that factor is dropped and the other weights are scaled to sum to 1. A single listed tariff is not compared, because there is no second value to rank against. Missing values are not replaced with zero.

A station is recommended only when the road route exists, the listed connector matches when one was requested, the listing text starts with "Operational", the detour is within an optional maximum, and the battery check is feasible. Unknown live availability is reported as unknown. It does not block the listing match, and it is not described as available.

## API

From this folder:

```powershell
python -m uvicorn api.main:app --reload --port 8004
```

- `GET /health`
- `GET /api/v1/stations`
- `POST /api/v1/recommend-station`

Docs: `http://127.0.0.1:8004/docs`

Example body:

```json
{
  "origin_latitude": 6.9271,
  "origin_longitude": 79.8612,
  "destination_latitude": 6.8649,
  "destination_longitude": 79.8997,
  "current_soc_percent": 80,
  "usable_battery_capacity_kwh": 40,
  "consumption_kwh_per_100km": 15,
  "minimum_reserve_percent": 10,
  "required_connector": "CHAdeMO"
}
```

## Tests

Unit tests use `FakeRouter` and label routes with `provider: "mock"`. They do not call OSRM.

```powershell
python -m pip install -r requirements.txt
python -m pytest tests/test_route_optimizer.py -q
```

## Limits

Four records cannot support a trained station-choice model. No synthetic visit labels are created here. Charging duration is estimated only when `energy_to_add_kwh` is sent, and that estimate assumes the listed kilowatts are delivered continuously.
