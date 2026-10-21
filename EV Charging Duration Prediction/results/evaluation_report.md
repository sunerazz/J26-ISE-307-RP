# Charging duration evaluation

Selected model (lowest validation MAE): **random_forest**.

Metrics are in **minutes** and were computed from model predictions. Raw regression metrics are unclipped.

## Validation

```json
{
  "median_baseline": {
    "mae_min": 56.19339210954555,
    "rmse_min": 69.98052151951805,
    "r2": -0.0007335350582950984,
    "n": 192
  },
  "linear_regression": {
    "mae_min": 56.515904373853736,
    "rmse_min": 71.24266498714852,
    "r2": -0.03715679678173789,
    "n": 192
  },
  "random_forest": {
    "mae_min": 56.038786752949534,
    "rmse_min": 69.90180148541161,
    "r2": 0.0015166187940626186,
    "n": 192
  },
  "xgboost": {
    "mae_min": 56.8923150247001,
    "rmse_min": 71.59993199856477,
    "r2": -0.047585126608338246,
    "n": 192
  }
}
```

## Untouched test set (selected model)

```json
{
  "mae_min": 53.639470500286734,
  "rmse_min": 62.59605044048705,
  "r2": -0.048412952620795924,
  "n": 216
}
```

Share of negative raw predictions: 0.0.
Operational predictions from `predict_duration` are clipped at 0 minutes. Clipped test metrics:

```json
{
  "mae_min": 53.639470500286734,
  "rmse_min": 62.59605044048705,
  "r2": -0.048412952620795924,
  "n": 216
}
```

## Limitations

- 1,320 sessions and about eight weeks of dates are a small sample.
- Duration does not match clock end−start, and energy is nearly uncorrelated with duration, so the table looks noisy or synthetic.
- SOC values above 100% and a few extreme battery capacities were kept.
- A high R² should be read together with MAE in minutes and the median baseline.
- This model does not predict queue length, waiting time, or congestion.

Saved pipeline: `C:\Users\Charuka\Desktop\thanuka resarch\system\component2_charging_duration\models\charging_duration_pipeline.joblib`
