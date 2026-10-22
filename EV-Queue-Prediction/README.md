# EV Charging Prediction — Component 1

**Research title:** AI-Based Intelligent EV Charging Prediction and Decision Support Framework  
**Component:** AI-Based Queue Length, Waiting Time and Congestion Prediction

| Task | Status | Entry point |
|---|---|---|
| Model 1 — Queue length (+30 min) | Implemented | `python run_pipeline.py` |
| Model 2 — Waiting time (+30 min) | Implemented | `python run_waiting_time_pipeline.py` |
| Model 3 — Congestion (+30 min) | Implemented | `python run_congestion_pipeline.py` |

> **Experiment label: SIMULATION-BASED.**  
> Source CSV: `data/raw/component1_ev_queue_prediction_sri_lanka.csv`. Station names are Sri Lankan places. The 15-minute queue, wait and congestion values are generated snapshots, not a field log.

## Dataset support

- Regular **15-minute** station snapshots (5 stations: Nugegoda LECO, Rajagiriya, Malabe, Pannipitiya, Panadura; 2025-01-01 → 2025-04-30).
- **Queue:** reconstruct `current_queue_length` at t+30 (CSV pre-computed target matched `queue_after_current_arrivals@t+30` instead).
- **Waiting time:** reconstruct `estimated_waiting_time_now_min` at t+30 (CSV pre-computed `target_waiting_time_30min_min` matches this at **100%**). Values are **estimated/synthetic** station waits (often capped near 240 min), not measured arrival→charge-start session times.
- **Congestion:** reconstruct `congestion_level_now` ∈ {Low, Medium, High} at t+30 (CSV pre-computed target matches at **100%**). Labels are **synthetic / rule-derived** (strongly tied to wait/queue), not independently observed real-world congestion audits.

## Project structure

```text
EV-Queue-Prediction/
  data/raw/
  data/processed/                 # Model 1 splits
  data/processed/waiting_time/    # Model 2 splits
  data/processed/congestion/      # Model 3 splits
  reports/
  models/                         # Model 1 + waiting_time_* + congestion_*
  plots/
  src/
    inspect_data.py
    prepare_data.py               # Model 1
    train_queue_model.py
    evaluate_model.py
    predict_queue.py
    prepare_waiting_time_data.py  # Model 2
    train_waiting_time_model.py
    evaluate_waiting_time_model.py
    predict_waiting_time.py
    prepare_congestion_data.py    # Model 3
    train_congestion_model.py
    evaluate_congestion_model.py
    predict_congestion.py
  tests/
  run_pipeline.py
  run_waiting_time_pipeline.py
  run_congestion_pipeline.py
  requirements.txt
  README.md
```

Each model keeps **separate** code, metrics, plots and saved artifacts.

## Setup

```bash
cd EV-Queue-Prediction
python -m venv .venv
.\.venv\Scripts\Activate.ps1   # Windows PowerShell
pip install -r requirements.txt
```

Random seed: `42`.

## Reproduce Model 1 (queue length)

```bash
python run_pipeline.py
```

## Reproduce Model 2 (waiting time)

```bash
python run_waiting_time_pipeline.py
```

Or step-by-step:

```bash
python -m src.prepare_waiting_time_data
python -m src.train_waiting_time_model
python -m src.evaluate_waiting_time_model
python -m src.predict_waiting_time
python -m pytest -q tests/test_waiting_time_model.py
```

### Model 2 selection

Persistence / historical median / Random Forest / XGBoost — overall best and best ML chosen by **validation MAE**; test evaluated once.

### Model 2 prediction interface

```python
from src.predict_waiting_time import predict_waiting_time, load_waiting_time_model

model, meta = load_waiting_time_model()
result = predict_waiting_time(feature_record, model=model, meta=meta)
# station_id, prediction_timestamp, forecast_timestamp,
# predicted_waiting_time_min, model_name, model_version
```

### Model 2 key outputs

- `reports/waiting_time_feature_target_definitions.md`
- `reports/waiting_time_training_summary.json`
- `reports/waiting_time_model_comparison.csv`
- `reports/waiting_time_evaluation.md`
- `reports/waiting_time_test_metrics.json`
- `models/waiting_time_best_model.joblib`
- `models/waiting_time_random_forest.joblib`
- `models/waiting_time_xgboost.joblib`
- `plots/waiting_time_actual_vs_predicted.png`
- `plots/waiting_time_residuals.png`
- `plots/waiting_time_test_timeseries.png`

## Reproduce Model 3 (congestion)

```bash
python run_congestion_pipeline.py
```

Or step-by-step:

```bash
python -m src.prepare_congestion_data
python -m src.train_congestion_model
python -m src.evaluate_congestion_model
python -m src.predict_congestion
python -m pytest -q tests/test_congestion_model.py
```

Selection uses **validation macro-F1** (not accuracy alone). Class imbalance handled with RF `class_weight='balanced'` and XGBoost training sample weights (no SMOTE).

```python
from src.predict_congestion import predict_congestion, load_congestion_model

model, meta = load_congestion_model()
result = predict_congestion(feature_record, model=model, meta=meta)
# predicted_congestion_level, class_probabilities, model_name, model_version
```

### Model 3 key outputs

- `reports/congestion_label_quality_report.md`
- `reports/congestion_feature_target_definitions.md`
- `reports/congestion_model_comparison.csv`
- `reports/congestion_evaluation.md`
- `models/congestion_best_model.joblib`
- `models/congestion_random_forest.joblib`
- `models/congestion_xgboost.joblib`
- `plots/congestion_confusion_matrix.png`
- `plots/congestion_class_metrics.png`
- `plots/congestion_test_timeseries.png`

## FastAPI (serve all three models)

See [`api/README.md`](api/README.md).

```bash
pip install -r api/requirements.txt
uvicorn api.main:app --reload --port 8000
```

Swagger UI: http://127.0.0.1:8000/docs

```bash
pytest -q api/tests
```

## Vite frontend (model tester)

The UI lives **outside** this model folder: [`../frontend`](../frontend).

```bash
# terminal 1 (from EV-Queue-Prediction)
uvicorn api.main:app --reload --port 8000

# terminal 2 (from system/)
cd ../frontend
npm install
npm run dev
```

UI: http://127.0.0.1:5173
