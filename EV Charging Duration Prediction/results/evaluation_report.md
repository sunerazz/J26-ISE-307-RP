# Charging duration evaluation

Selected model (lowest validation MAE): **xgboost**.

Metrics are in **minutes** and were computed from model predictions. Raw regression metrics are unclipped.

## Validation

```json
{
  "median_baseline": {
    "mae_min": 78.97174180153492,
    "rmse_min": 214.26150625680552,
    "r2": -0.0677469877514012,
    "n": 192
  },
  "linear_regression": {
    "mae_min": 60.30207167586999,
    "rmse_min": 169.5556630181521,
    "r2": 0.33134107401576085,
    "n": 192
  },
  "random_forest": {
    "mae_min": 24.81084439273401,
    "rmse_min": 107.63712764388048,
    "r2": 0.730533831479379,
    "n": 192
  },
  "xgboost": {
    "mae_min": 22.495923622429615,
    "rmse_min": 97.22305739890808,
    "r2": 0.7801539858408545,
    "n": 192
  }
}
```

## Untouched test set (selected model)

```json
{
  "mae_min": 13.261844058922373,
  "rmse_min": 36.90297856307612,
  "r2": 0.8876449841222401,
  "n": 216
}
```

Share of negative raw predictions: 0.032407407407407406.
Operational predictions from `predict_duration` are clipped at 0 minutes. Clipped test metrics:

```json
{
  "mae_min": 13.107318329681178,
  "rmse_min": 36.8775965965067,
  "r2": 0.8877994871262319,
  "n": 216
}
```

## Limitations

- 1,320 sessions and about eight weeks of dates are a small sample.
- Duration does not match clock end−start, and energy is nearly uncorrelated with duration, so the table looks noisy or synthetic.
- SOC values above 100% and a few extreme battery capacities were kept.
- A high R² should be read together with MAE in minutes and the median baseline.
- This model does not predict queue length, waiting time, or congestion.

Saved pipeline: `C:\Users\Charuka\Desktop\thanuka resarch\system\EV Charging Duration Prediction\models\charging_duration_pipeline.joblib`
