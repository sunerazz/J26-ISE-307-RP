# EV Charging Prediction API (Component 1)

FastAPI backend that exposes the three **already trained** Component 1 models:

| Endpoint | Model artifact | Target | Horizon |
|---|---|---|---|
| `POST /api/v1/predict/queue` | `models/best_model.joblib` | queue length | 30 min |
| `POST /api/v1/predict/waiting-time` | `models/waiting_time_best_model.joblib` | waiting time (minutes) | 30 min |
| `POST /api/v1/predict/congestion` | `models/congestion_best_model.joblib` | Low / Medium / High | 30 min |

Also:

- `GET /health`
- `GET /api/v1/models`
- Swagger UI: `/docs`
- ReDoc: `/redoc`

## Artifact notes (from training)

- **Queue (selected):** `persistence` — request needs `station_id`, `current_queue_length`, optional `timestamp`. Preprocessing pipeline is **not** required for this artifact. Best learned RF remains at `models/best_ml_model.joblib` (not loaded by default).
- **Waiting time (selected):** XGBoost `sklearn` Pipeline with embedded OneHotEncoder — requires the full 41-feature station snapshot.
- **Congestion (selected):** XGBoost `sklearn` Pipeline with embedded preprocessing — same 41-feature schema; returns class probabilities.

If an artifact is missing, regenerate with:

```bash
python run_pipeline.py
python run_waiting_time_pipeline.py
python run_congestion_pipeline.py
```

## Install

From the **project root** (`EV-Queue-Prediction/`):

```bash
pip install -r requirements.txt
pip install -r api/requirements.txt
```

## Run the server

Always start from the project root so `src/` and `models/` resolve correctly:

```bash
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

Open Swagger UI: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

### CORS (React)

Set explicit origins (comma-separated). Wildcard `*` is rejected.

```powershell
$env:CORS_ORIGINS="http://localhost:3000,http://localhost:5173"
uvicorn api.main:app --reload --port 8000
```

Defaults already include common local React ports (`3000`, `5173`).

## Run API tests

```bash
pytest -q api/tests
```

## Example requests

### Queue

```bash
curl -X POST http://127.0.0.1:8000/api/v1/predict/queue ^
  -H "Content-Type: application/json" ^
  -d "{\"station_id\":\"ST01\",\"current_queue_length\":3,\"timestamp\":\"2025-04-13T00:00:00\"}"
```

### Waiting time / congestion

Send the full prediction-time feature record (see OpenAPI schema `StationFeatureRequest` in `/docs`). Do **not** include future target fields (`target_*`).

## Response post-processing

- **Queue:** clip at 0, round to nearest integer for `predicted_queue_length`; `raw_prediction` also returned.
- **Waiting time:** unit is **minutes**; clip at 0 for operational `predicted_waiting_time_min`; `raw_prediction_min` returned.
- **Congestion:** class in `{Low, Medium, High}` plus `class_probabilities` when supported.
