# Integration service

This service is the dashboard backend. It loads the four components in one process:

- Component 1 models from `EV-Queue-Prediction` (synthetic stations ST01–ST06 only).
- Component 2 duration pipeline from `EV Charging Duration Prediction`.
- Component 3 cost function and the energy model trained on `component3_energy_consumption.csv`. The model is used only when the request includes elevation, temperature, air conditioning, traffic, road type, and vehicle mass.
- Component 4 route optimizer and `data/raw/colombo_ev_stations.csv`.

## Configure

Copy `.env.example` into the shell environment before starting:

- `OPENAI_API_KEY` — optional. Used only to explain a result that was already calculated.
- `OPENAI_MODEL` — default `gpt-4o-mini`.
- `OSRM_BASE_URL` — default `https://router.project-osrm.org`.
- `CORS_ORIGINS` — comma-separated frontend origins. Read when the process starts.

Do not put API keys in the frontend.

## Run

```powershell
python -m pip install -r requirements.txt
python -m uvicorn service:app --port 8000
```

From this folder:

```powershell
python -m pytest tests/test_integration.py -q
```

`GET /health` does not call OSRM. `POST /api/v1/recommend` does, unless a test replaces the provider.

## Render

The phone and the web dashboard call only the integration service. The three model services are separate. `render.yaml` wires them:

| Service | What it runs | Environment variable on the integration service |
| --- | --- | --- |
| `ev-queue-api` | Queue, waiting time, congestion | `QUEUE_API_URL` |
| `ev-duration-api` | Charging-duration model | `DURATION_API_URL` |
| `ev-energy-api` | Trip-energy model | `ENERGY_API_URL` |
| `ev-integration-api` | Colombo routes, battery check, ranking | none; this is the URL the app uses |

Leave those three variables empty on a local machine. The integration process then loads the models itself. On Render they are set from the other services' public URLs.

After the blueprint is live, the value to put in the phone is the integration URL:

```powershell
flutter run --dart-define=API_BASE_URL=https://ev-integration-api.onrender.com
```

Use the URL Render shows for `ev-integration-api`. The model URLs stay on the server. They are not put in the phone.

## Railway

The repository root `Dockerfile` and `railway.toml` are the hosting setup. The image copies the integration service, the four component source trees, and only the model files the API loads. The large unused random-forest artifacts are not copied.

On Railway, set:

- `OSRM_BASE_URL` if you are not using the public demo
- `OPENAI_API_KEY` only if you want language-model explanations
- `PORT` is provided by Railway

Health check path: `/health`. The phone app uses the public Railway URL as `API_BASE_URL`.

## Trip plan fields

`POST /api/v1/recommend` also returns:

- `quick_answer` — the few plain-language lines shown first in the dashboard. Every number in them comes from the result.
- `trip_check` — whether the direct trip can be finished above the reserve without charging (same kWh/100 km formula as the battery gate).
- Per station `trip_plan` — SOC on arrival at the station, the minimum target SOC that finishes the trip with the reserve, and, when a target SOC is given, charging energy and SOC at the destination.
- Per station `plain_summary` — one readable paragraph.

Charging energy is `usable_kWh × (target SOC − SOC on arrival at the station) / 100`. The SOC on arrival is used, not the SOC at the start of the trip, because the drive to the station uses energy. Listed-power duration and scenario cost are therefore calculated per station.
