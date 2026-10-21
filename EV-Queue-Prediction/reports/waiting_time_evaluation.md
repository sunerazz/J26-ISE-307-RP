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
  "mae_min": 8.083732929722974,
  "rmse_min": 14.564999256498956,
  "r2": 0.9743883937153289,
  "n": 10344
}
```

## Baseline vs Random Forest vs XGBoost (test)

```json
{
  "persistence": {
    "mae_min": 8.510261020881671,
    "rmse_min": 17.26804898863611,
    "r2": 0.9640000060712518,
    "n": 10344
  },
  "historical_median": {
    "mae_min": 64.11678847641146,
    "rmse_min": 104.14099171514437,
    "r2": -0.3093606998507943,
    "n": 10344
  },
  "random_forest": {
    "mae_min": 8.154879230080107,
    "rmse_min": 14.839735106155784,
    "r2": 0.973413070690175,
    "n": 10344
  },
  "xgboost": {
    "mae_min": 8.083732929722974,
    "rmse_min": 14.564999256498956,
    "r2": 0.9743883937153289,
    "n": 10344
  }
}
```

## Best ML diagnostics

```json
{
  "best_ml_test_metrics": {
    "mae_min": 8.083732929722974,
    "rmse_min": 14.564999256498956,
    "r2": 0.9743883937153289,
    "n": 10344
  },
  "best_ml_test_metrics_excluding_ST05": {
    "mae_min": 9.633426222204871,
    "rmse_min": 15.953506857205943,
    "r2": 0.9012660024288215,
    "n": 8620
  },
  "persistence_test_metrics_excluding_ST05": {
    "mae_min": 10.212313225058004,
    "rmse_min": 18.916199910360536,
    "r2": 0.8611895427861417,
    "n": 8620
  }
}
```

## By station / peak / zero & long waits

```json
{
  "by_station": {
    "ST01": {
      "mae_min": 12.88591184230221,
      "rmse_min": 18.874426153487725,
      "r2": 0.8972787412499623,
      "n": 1724
    },
    "ST02": {
      "mae_min": 13.584797014520955,
      "rmse_min": 18.142218719786214,
      "r2": 0.9240257348242283,
      "n": 1724
    },
    "ST03": {
      "mae_min": 1.962748755117948,
      "rmse_min": 4.631873375310695,
      "r2": 0.09584833593225794,
      "n": 1724
    },
    "ST04": {
      "mae_min": 14.567899238244607,
      "rmse_min": 22.25291477627917,
      "r2": 0.7322237647173868,
      "n": 1724
    },
    "ST05": {
      "mae_min": 0.3352664673134788,
      "rmse_min": 0.5131421209621267,
      "r2": 0.0,
      "n": 1724
    },
    "ST06": {
      "mae_min": 5.16577426083864,
      "rmse_min": 8.398891326199335,
      "r2": 0.8354430282730578,
      "n": 1724
    }
  },
  "by_peak": {
    "peak": {
      "mae_min": 9.928657942103976,
      "rmse_min": 16.934226258487545,
      "r2": 0.9656530741212765,
      "n": 3456
    },
    "off_peak": {
      "mae_min": 7.158056268458636,
      "rmse_min": 13.217215295502093,
      "r2": 0.9785869293306714,
      "n": 6888
    }
  },
  "zero_and_long_wait_analysis": {
    "n_zero_actual": 4516,
    "fraction_zero_actual": 0.4365815931941222,
    "metrics_on_zero_actual": {
      "mae_min": 3.9369875451224203,
      "rmse_min": 6.688255692382625,
      "r2": 0.0,
      "n": 4516
    },
    "n_long_wait_ge_60min": 3277,
    "fraction_long_wait_ge_60min": 0.31680201082753284,
    "metrics_on_long_wait_ge_60min": {
      "mae_min": 9.973342393932453,
      "rmse_min": 19.585014636861025,
      "r2": 0.9187159888718727,
      "n": 3277
    },
    "actual_max_min": 240.0,
    "note": "Difficult cases retained; no selective deletion for better scores."
  },
  "error_distribution": {
    "mean_error_min": 0.29111134860498983,
    "std_error_min": 14.562793679241219,
    "median_abs_error_min": 3.07030557632447,
    "p90_abs_error_min": 22.737875556945806,
    "p95_abs_error_min": 31.47968575668337,
    "min_error_min": -140.25690460205078,
    "max_error_min": 86.57376159667969,
    "fraction_negative_raw_preds": 0.04717710750193349
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
- ST05 waiting times are frequently capped near 240 minutes.
- Strong autocorrelation at +30 minutes can favour persistence on this grid.

## Artifacts

- `models/waiting_time_best_model.joblib`
- `models/waiting_time_random_forest.joblib`
- `models/waiting_time_xgboost.joblib`
- `plots/waiting_time_actual_vs_predicted.png`
- `plots/waiting_time_residuals.png`
- `plots/waiting_time_test_timeseries.png`
- `reports/waiting_time_model_comparison.csv`
