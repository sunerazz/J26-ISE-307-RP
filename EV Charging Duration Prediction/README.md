# Component 2 — EV charging duration prediction

Independent regression project for the research title **AI-Based Intelligent EV Charging Prediction and Decision Support Framework**.

This folder does not modify Component 1.

## Objective

Predict the expected charging duration in **minutes** from information available when charging starts.

## Dataset

- File: `data/raw/component2_charging_duration_sri_lanka_5_stations.csv`
- Verified size: 1,320 rows × 24 columns
- Source duration column: `Charging Duration (hours)`
- Model target: `charging_duration_min` = hours × 60

Place names are Nugegoda LECO, Rajagiriya, Malabe, Pannipitiya, and Panadura, 264 rows each. The table was rebuilt so labelled duration equals end time minus start time, and energy equals charging rate times that duration. Both come from battery capacity times the SOC rise. This is a generated table, not a meter log.

## Leakage

Inputs are the four values that define the generated session: battery capacity, charging rate, start SOC, and requested end SOC.

Excluded: duration, end time, energy, illustrative tariff and cost, and the other columns (place, vehicle, time of day, charger type, age, distance). Those columns do not define the generated duration. End time and energy would repeat the target.

Details: `results/feature_definitions.md`.

## Split

Chronological by calendar date: first 70% of dates train, next 15% validation, final 15% test. Model choice uses validation MAE only.

## Reproduce

```bash
cd component2_charging_duration
pip install -r requirements.txt
python run_pipeline.py
```

Or step by step:

```bash
python -m src.inspect_dataset
python -m src.prepare_data
python -m src.train_models
python -m src.evaluate_models
python -m pytest -q tests
```

Random seed: 42.

## Results from the executed run

Validation MAE (minutes), n = 192:

| Model | MAE | RMSE | R² |
|---|---:|---:|---:|
| **XGBoost (selected), 200 trees, depth 4, learning rate 0.05** | **22.50** | **97.22** | **0.780** |
| Random forest, 300 trees, depth 12, min leaf 2 | 24.81 | 107.64 | 0.731 |
| Linear regression | 60.30 | 169.56 | 0.331 |
| Median baseline | 78.97 | 214.26 | −0.068 |

Held-out test, XGBoost, n = 216: MAE 13.26 minutes, RMSE 36.90 minutes, R² 0.888. About 3.2% of raw test predictions were negative and are clipped to zero when serving. The published MAE above is the raw figure.

XGBoost wins because the generated duration is battery × SOC rise / rate, which is not a straight line and is not a constant. The low error means the model recovered that formula. It does not mean the minutes were measured at the chargers.

## Outputs

- `models/charging_duration_pipeline.joblib` — selected preprocessing + model
- `models/charging_duration_pipeline_meta.joblib` — feature list and selection metadata
- `results/model_comparison.csv`
- `results/evaluation_report.md`
- `results/actual_vs_predicted.png`
- `results/residuals.png`

Operational predictions clip negative durations at 0 minutes. MAE, RMSE, and R² in the report use raw predictions.

```python
from src.predict_duration import load_pipeline, predict_duration

pipe, meta = load_pipeline()
result = predict_duration(feature_record, pipeline=pipe, meta=meta)
```
