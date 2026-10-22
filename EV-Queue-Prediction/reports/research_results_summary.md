# Research Results Summary — Queue Length Prediction (Component 1)

## Verdict

This is a **simulation-based** experiment on synthetic EV charging snapshots. The validation-selected **overall** method is **xgboost**.

Best learned model by validation MAE: **xgboost**.

## Test metrics (selected overall method, raw predictions)

```json
{
  "mae": 0.4433368963321234,
  "rmse": 0.6621554630665758,
  "r2": 0.8234459294207795,
  "n": 8620
}
```

## Baseline vs ML comparison (test)

```json
{
  "persistence": {
    "mae": 0.5581206496519722,
    "rmse": 0.9495999890538842,
    "r2": 0.6368891686404303,
    "n": 8620
  },
  "historical_median": {
    "mae": 0.9751740139211137,
    "rmse": 1.8531968991717442,
    "r2": -0.3829323364941082,
    "n": 8620
  },
  "random_forest": {
    "mae": 0.4438038315227169,
    "rmse": 0.6642770670631833,
    "r2": 0.8223127275286861,
    "n": 8620
  },
  "xgboost": {
    "mae": 0.4433368963321234,
    "rmse": 0.6621554630665758,
    "r2": 0.8234459294207795,
    "n": 8620
  }
}
```

## Best ML model (test)

```json
{
  "persistence_test_metrics_excluding_ST05": {
    "mae": 0.5443735498839907,
    "rmse": 0.9375821696395394,
    "r2": 0.6227965838308116,
    "n": 6896
  },
  "best_ml_test_metrics": {
    "mae": 0.4433368963321234,
    "rmse": 0.6621554630665758,
    "r2": 0.8234459294207795,
    "n": 8620
  },
  "best_ml_test_metrics_excluding_ST05": {
    "mae": 0.4340509381620624,
    "rmse": 0.6510811690965685,
    "r2": 0.8181023001283396,
    "n": 6896
  },
  "best_ml_by_station": {
    "ST01": {
      "mae": 0.4224854116511732,
      "rmse": 0.6231792760054677,
      "r2": 0.8131333865957999,
      "n": 1724
    },
    "ST02": {
      "mae": 0.44915333293430215,
      "rmse": 0.6840638904603696,
      "r2": 0.8458238259244947,
      "n": 1724
    },
    "ST03": {
      "mae": 0.42381402621966224,
      "rmse": 0.6318553865681504,
      "r2": 0.7363978851155186,
      "n": 1724
    },
    "ST04": {
      "mae": 0.44075098184311196,
      "rmse": 0.6633925754777147,
      "r2": 0.830933236333522,
      "n": 1724
    },
    "ST05": {
      "mae": 0.4804807290123676,
      "rmse": 0.7047145034238612,
      "r2": 0.833925723558181,
      "n": 1724
    }
  }
}
```

## Performance by station (selected overall method)

```json
{
  "ST01": {
    "mae": 0.4224854116511732,
    "rmse": 0.6231792760054677,
    "r2": 0.8131333865957999,
    "n": 1724
  },
  "ST02": {
    "mae": 0.44915333293430215,
    "rmse": 0.6840638904603696,
    "r2": 0.8458238259244947,
    "n": 1724
  },
  "ST03": {
    "mae": 0.42381402621966224,
    "rmse": 0.6318553865681504,
    "r2": 0.7363978851155186,
    "n": 1724
  },
  "ST04": {
    "mae": 0.44075098184311196,
    "rmse": 0.6633925754777147,
    "r2": 0.830933236333522,
    "n": 1724
  },
  "ST05": {
    "mae": 0.4804807290123676,
    "rmse": 0.7047145034238612,
    "r2": 0.833925723558181,
    "n": 1724
  }
}
```

## Peak vs off-peak

Peak hours: [7, 8, 9, 17, 18, 19, 20, 21]

```json
{
  "peak": {
    "mae": 0.33294609483952325,
    "rmse": 0.5435094155095413,
    "r2": 0.7702913525219663,
    "n": 2880
  },
  "off_peak": {
    "mae": 0.49872461554792286,
    "rmse": 0.7142987855092511,
    "r2": 0.82442282089353,
    "n": 5740
  }
}
```

## Limitations

- Synthetic labels/features; not independently observed real-world queues.
- Does **not** predict waiting time or congestion (separate future tasks).
- Queue length in this file does not exceed 12 vehicles at any of the five stations.
- On this 15-minute synthetic grid, queue length is strongly autocorrelated at +30 minutes, so a persistence baseline can outperform complex models.
- Pre-computed CSV target differed from observational `current_queue_length@t+30`; this study uses the reconstructed observational target.
- High R² can coexist with operationally meaningful absolute errors; always read MAE/RMSE vs baselines.

## Plots

- `plots/actual_vs_predicted_scatter.png`
- `plots/error_distribution.png`
- `plots/timeseries_actual_vs_predicted.png`
- `plots/best_ml_*` figures when the overall winner differs from the best ML model
