# Waiting-Time Model Evaluation (Model 2)

## Dataset and target validation

- **Experiment label:** SIMULATION-BASED (synthetic CSV).
- Waiting column `estimated_waiting_time_now_min` is an **estimated** station-level waiting time in minutes (not a measured arrival→charging-start event duration from a session log).
- Target `target_waiting_time_30min_min` reconstructed as same-station `estimated_waiting_time_now_min` exactly 30 minutes later.
- CSV pre-computed waiting target matched this reconstruction at 100% on valid pairs; end-of-series unmatched rows were dropped (not zero-filled).
- This is a **station-level 30-minute-ahead forecast**, not a per-vehicle session waiting-time model.

## Selected models

- Overall (validation MAE): **xgboost** (version `waiting_time_v1`)
- Best learned model: **xgboost**

## Test metrics — selected overall method (raw predictions, minutes)

```json
{
  "mae_min": 14.815617735632888,
  "rmse_min": 19.571552782619708,
  "r2": 0.5778121799803958,
  "n": 8620
}
```

## Baseline vs Random Forest vs XGBoost (test)

```json
{
  "persistence": {
    "mae_min": 19.005754060324822,
    "rmse_min": 25.825435701353292,
    "r2": 0.2648931874386823,
    "n": 8620
  },
  "historical_median": {
    "mae_min": 24.27777262180975,
    "rmse_min": 30.138764744893376,
    "r2": -0.0011658565318406477,
    "n": 8620
  },
  "random_forest": {
    "mae_min": 14.997042884786353,
    "rmse_min": 19.771694226148398,
    "r2": 0.5691333264220051,
    "n": 8620
  },
  "xgboost": {
    "mae_min": 14.815617735632888,
    "rmse_min": 19.571552782619708,
    "r2": 0.5778121799803958,
    "n": 8620
  }
}
```

## Best ML diagnostics

```json
{
  "best_ml_test_metrics": {
    "mae_min": 14.815617735632888,
    "rmse_min": 19.571552782619708,
    "r2": 0.5778121799803958,
    "n": 8620
  },
  "best_ml_test_metrics_excluding_ST05": {
    "mae_min": 14.259375994678784,
    "rmse_min": 18.929298626698948,
    "r2": 0.595291694300202,
    "n": 6896
  },
  "persistence_test_metrics_excluding_ST05": {
    "mae_min": 18.3688283062645,
    "rmse_min": 25.022523553326874,
    "r2": 0.29281134414009824,
    "n": 6896
  }
}
```

## By station / peak / zero & long waits

```json
{
  "by_station": {
    "ST01": {
      "mae_min": 11.944442298827205,
      "rmse_min": 16.01633591709802,
      "r2": 0.4578657087796254,
      "n": 1724
    },
    "ST02": {
      "mae_min": 12.45110290063921,
      "rmse_min": 16.489090792052345,
      "r2": 0.4981466033888734,
      "n": 1724
    },
    "ST03": {
      "mae_min": 16.058444111020822,
      "rmse_min": 21.110994685901673,
      "r2": 0.28555191274391034,
      "n": 1724
    },
    "ST04": {
      "mae_min": 16.5835146682279,
      "rmse_min": 21.428629401082755,
      "r2": 0.40904314494938465,
      "n": 1724
    },
    "ST05": {
      "mae_min": 17.040584699449298,
      "rmse_min": 21.95347365724522,
      "r2": 0.4323694498821412,
      "n": 1724
    }
  },
  "by_peak": {
    "peak": {
      "mae_min": 14.047451611995696,
      "rmse_min": 18.587540468186265,
      "r2": 0.5717086300756785,
      "n": 2880
    },
    "off_peak": {
      "mae_min": 15.201039065959561,
      "rmse_min": 20.047084664937124,
      "r2": 0.5714986676777923,
      "n": 5740
    }
  },
  "zero_and_long_wait_analysis": {
    "n_zero_actual": 10,
    "fraction_zero_actual": 0.001160092807424594,
    "metrics_on_zero_actual": {
      "mae_min": 17.591981333494186,
      "rmse_min": 19.451775403021404,
      "r2": 0.0,
      "n": 10
    },
    "n_long_wait_ge_60min": 8499,
    "fraction_long_wait_ge_60min": 0.9859628770301624,
    "metrics_on_long_wait_ge_60min": {
      "mae_min": 14.779958735307899,
      "rmse_min": 19.5692388392907,
      "r2": 0.5351270722943933,
      "n": 8499
    },
    "actual_max_min": 180.0,
    "note": "Difficult cases retained; no selective deletion for better scores."
  },
  "error_distribution": {
    "mean_error_min": 0.01643741957632404,
    "std_error_min": 19.572681219293337,
    "median_abs_error_min": 10.767097320556644,
    "p90_abs_error_min": 34.458737548828125,
    "p95_abs_error_min": 40.353151412963825,
    "min_error_min": -106.61508178710938,
    "max_error_min": 60.56000793457031,
    "fraction_negative_raw_preds": 0.0001160092807424594
  }
}
```

## Leakage prevention

- Features limited to information available at the prediction timestamp.
- Future waiting/queue/congestion labels excluded from inputs.
- Lags/rolling windows computed per station on past rows only.
- Preprocessing fitted on training data only.
- Model selection on validation; test evaluated once.

## Limitations

- Synthetic/estimated waiting times; not independently observed real-world waits.
- Does **not** predict queue length or congestion (separate tasks).
- Waiting times in this file are capped at 180 minutes.
- Strong autocorrelation at +30 minutes can favour persistence on this grid.

## Artifacts

- `models/waiting_time_best_model.joblib`
- `models/waiting_time_random_forest.joblib`
- `models/waiting_time_xgboost.joblib`
- `plots/waiting_time_actual_vs_predicted.png`
- `plots/waiting_time_residuals.png`
- `plots/waiting_time_test_timeseries.png`
- `reports/waiting_time_model_comparison.csv`
