# Research Results Summary — Queue Length Prediction (Component 1)

## Verdict

This is a **simulation-based** experiment on synthetic EV charging snapshots. The validation-selected **overall** method is **persistence**.

Best learned model by validation MAE: **random_forest**.

## Test metrics (selected overall method, raw predictions)

```json
{
  "mae": 0.77861562258314,
  "rmse": 1.378699410663977,
  "r2": 0.999967657901868,
  "n": 10344
}
```

## Baseline vs ML comparison (test)

```json
{
  "persistence": {
    "mae": 0.77861562258314,
    "rmse": 1.378699410663977,
    "r2": 0.999967657901868,
    "n": 10344
  },
  "historical_median": {
    "mae": 110.8796403712297,
    "rmse": 266.58275440444817,
    "r2": -0.20918600598418746,
    "n": 10344
  },
  "random_forest": {
    "mae": 21.239446336482153,
    "rmse": 51.400199874419215,
    "r2": 0.9550470055967265,
    "n": 10344
  },
  "xgboost": {
    "mae": 22.541374222279508,
    "rmse": 54.59827464905571,
    "r2": 0.9492791120069592,
    "n": 10344
  }
}
```

## Best ML model (test)

```json
{
  "persistence_test_metrics_excluding_ST05": {
    "mae": 0.7107888631090488,
    "rmse": 1.3545917442179694,
    "r2": 0.9238449125587981,
    "n": 8620
  },
  "best_ml_test_metrics": {
    "mae": 21.239446336482146,
    "rmse": 51.4001998744192,
    "r2": 0.9550470055967266,
    "n": 10344
  },
  "best_ml_test_metrics_excluding_ST05": {
    "mae": 0.4976338421561838,
    "rmse": 0.904545636503902,
    "r2": 0.9660419269517793,
    "n": 8620
  },
  "best_ml_by_station": {
    "ST01": {
      "mae": 0.5965771705784917,
      "rmse": 0.9422676974493882,
      "r2": 0.9698611245900376,
      "n": 1724
    },
    "ST02": {
      "mae": 0.9621719106534841,
      "rmse": 1.3334240907339614,
      "r2": 0.9630691622685336,
      "n": 1724
    },
    "ST03": {
      "mae": 0.07440094481176099,
      "rmse": 0.2706404139559698,
      "r2": 0.5052526730513648,
      "n": 1724
    },
    "ST04": {
      "mae": 0.3053845612612464,
      "rmse": 0.5543822720662659,
      "r2": 0.8765375149560299,
      "n": 1724
    },
    "ST05": {
      "mae": 124.94850880811198,
      "rmse": 125.88801479385903,
      "r2": -66.10088192059861,
      "n": 1724
    },
    "ST06": {
      "mae": 0.5496346234759356,
      "rmse": 1.0220273410909164,
      "r2": 0.914245549107839,
      "n": 1724
    }
  }
}
```

## Performance by station (selected overall method)

```json
{
  "ST01": {
    "mae": 0.8723897911832946,
    "rmse": 1.4329564784533868,
    "r2": 0.9302981287237653,
    "n": 1724
  },
  "ST02": {
    "mae": 1.4153132250580047,
    "rmse": 2.004056211612824,
    "r2": 0.9165795818272855,
    "n": 1724
  },
  "ST03": {
    "mae": 0.09164733178654293,
    "rmse": 0.4361825540042075,
    "r2": -0.2850935403523447,
    "n": 1724
  },
  "ST04": {
    "mae": 0.45591647331786544,
    "rmse": 0.8770071443965014,
    "r2": 0.6910255209429381,
    "n": 1724
  },
  "ST05": {
    "mae": 1.1177494199535962,
    "rmse": 1.4934116720696213,
    "r2": 0.990556814064363,
    "n": 1724
  },
  "ST06": {
    "mae": 0.718677494199536,
    "rmse": 1.4647838227300936,
    "r2": 0.8238515962551025,
    "n": 1724
  }
}
```

## Peak vs off-peak

Peak hours: [7, 8, 9, 17, 18, 19, 20, 21]

```json
{
  "peak": {
    "mae": 0.9898726851851852,
    "rmse": 1.6084448723557196,
    "r2": 0.999956067829105,
    "n": 3456
  },
  "off_peak": {
    "mae": 0.6726190476190477,
    "rmse": 1.2475876839068285,
    "r2": 0.9999734898636665,
    "n": 6888
  }
}
```

## Limitations

- Synthetic labels/features; not independently observed real-world queues.
- Does **not** predict waiting time or congestion (separate future tasks).
- Station ST05 has extreme synthetic queue magnitudes that dominate ML absolute errors.
- On this 15-minute synthetic grid, queue length is strongly autocorrelated at +30 minutes, so a persistence baseline can outperform complex models.
- Pre-computed CSV target differed from observational `current_queue_length@t+30`; this study uses the reconstructed observational target.
- High R² can coexist with operationally meaningful absolute errors; always read MAE/RMSE vs baselines.

## Plots

- `plots/actual_vs_predicted_scatter.png`
- `plots/error_distribution.png`
- `plots/timeseries_actual_vs_predicted.png`
- `plots/best_ml_*` figures when the overall winner differs from the best ML model
