# Component 2 — EV charging duration prediction

Independent regression project for the research title **AI-Based Intelligent EV Charging Prediction and Decision Support Framework**.

This folder does not modify Component 1.

## Objective

Predict the expected charging duration in **minutes** from information available when charging starts.

## Dataset

- File: `data/raw/Component 2 ev_charging_patterns (2).xlsx`
- Verified size: 1,320 rows × 20 columns
- Source duration column: `Charging Duration (hours)`
- Model target: `charging_duration_min` = hours × 60

The table is noisy: labelled duration does not match end time minus start time, and energy is almost uncorrelated with duration. SOC values above 100% were kept. Do not treat scores as real-world charging-meter accuracy.

## Leakage

Inputs are limited to features known at session start (vehicle, start SOC, charger type, charging rate, temperature, age, location, time of day, day of week, user type, distance since last charge).

Excluded: duration itself, end time, end SOC, energy consumed, charging cost, user ID, station ID, and the raw start timestamp (used only to order the split).

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
| Median baseline | 56.19 | 69.98 | −0.001 |
| Linear regression | 56.52 | 71.24 | −0.037 |
| **Random forest (selected)** | **56.04** | **69.90** | **0.002** |
| XGBoost | 56.89 | 71.60 | −0.048 |

Held-out test, random forest, n = 216: MAE 53.64 minutes, RMSE 62.60 minutes, R² −0.048.

The forest wins validation by a fraction of a minute over the median. R² near or below zero means the features in this table do not explain charging duration. That matches the data-quality finding that duration, energy, and clock time are almost unrelated.

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
