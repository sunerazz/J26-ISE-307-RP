# Congestion Model Evaluation (Model 3)

## Dataset and label validation

- **Experiment label:** SIMULATION-BASED.
- Congestion categories Low / Medium / High are synthetic/rule-derived station snapshot labels (`congestion_level_now`).
- Target `target_congestion_level_30min` = same-station congestion at t+30 (exact timestamp match; CSV pre-computed target matched 100%).
- Missing future labels were dropped, never filled as Low.

## Selected models

- Overall (validation macro-F1): **xgboost** (`congestion_v1`)
- Best learned model: **xgboost**

## Class distributions

```json
{
  "train": {
    "High": 39990,
    "Medium": 194,
    "Low": 116
  },
  "validation": {
    "High": 8567,
    "Medium": 51,
    "Low": 22
  },
  "test": {
    "High": 8575,
    "Medium": 28,
    "Low": 17
  }
}
```

## Test metrics — selected model

```json
{
  "accuracy": 0.9945475638051045,
  "macro_f1": 0.709649458265791,
  "n": 8620,
  "labels_evaluated": [
    "Low",
    "Medium",
    "High"
  ],
  "per_class": {
    "Low": {
      "precision": 0.8666666666666667,
      "recall": 0.7647058823529411,
      "f1": 0.8125,
      "support": 17
    },
    "Medium": {
      "precision": 0.2682926829268293,
      "recall": 0.39285714285714285,
      "f1": 0.3188405797101449,
      "support": 28
    },
    "High": {
      "precision": 0.9982484820177487,
      "recall": 0.9969679300291545,
      "f1": 0.997607795087228,
      "support": 8575
    }
  }
}
```

## Baseline vs Random Forest vs XGBoost (test)

```json
{
  "most_frequent": {
    "accuracy": 0.9947795823665894,
    "macro_f1": 0.332460986720946,
    "n": 8620,
    "labels_evaluated": [
      "Low",
      "Medium",
      "High"
    ],
    "per_class": {
      "Low": {
        "precision": 0.0,
        "recall": 0.0,
        "f1": 0.0,
        "support": 17
      },
      "Medium": {
        "precision": 0.0,
        "recall": 0.0,
        "f1": 0.0,
        "support": 28
      },
      "High": {
        "precision": 0.9947795823665894,
        "recall": 1.0,
        "f1": 0.997382960162838,
        "support": 8575
      }
    }
  },
  "random_forest": {
    "accuracy": 0.9954756380510441,
    "macro_f1": 0.7025557872417405,
    "n": 8620,
    "labels_evaluated": [
      "Low",
      "Medium",
      "High"
    ],
    "per_class": {
      "Low": {
        "precision": 0.7647058823529411,
        "recall": 0.7647058823529411,
        "f1": 0.7647058823529411,
        "support": 17
      },
      "Medium": {
        "precision": 0.3333333333333333,
        "recall": 0.35714285714285715,
        "f1": 0.3448275862068966,
        "support": 28
      },
      "High": {
        "precision": 0.9982503207745247,
        "recall": 0.9980174927113703,
        "f1": 0.9981338931653837,
        "support": 8575
      }
    }
  },
  "xgboost": {
    "accuracy": 0.9945475638051045,
    "macro_f1": 0.709649458265791,
    "n": 8620,
    "labels_evaluated": [
      "Low",
      "Medium",
      "High"
    ],
    "per_class": {
      "Low": {
        "precision": 0.8666666666666667,
        "recall": 0.7647058823529411,
        "f1": 0.8125,
        "support": 17
      },
      "Medium": {
        "precision": 0.2682926829268293,
        "recall": 0.39285714285714285,
        "f1": 0.3188405797101449,
        "support": 28
      },
      "High": {
        "precision": 0.9982484820177487,
        "recall": 0.9969679300291545,
        "f1": 0.997607795087228,
        "support": 8575
      }
    }
  }
}
```

## Confusion matrix

```json
{
  "labels": [
    "Low",
    "Medium",
    "High"
  ],
  "matrix": [
    [
      13,
      4,
      0
    ],
    [
      2,
      11,
      15
    ],
    [
      0,
      26,
      8549
    ]
  ]
}
```

## Feature importance (top)

```json
[
  {
    "feature": "num__queue_after_current_arrivals",
    "importance": 0.2597842812538147
  },
  {
    "feature": "cat__congestion_level_now_Medium",
    "importance": 0.16495203971862793
  },
  {
    "feature": "num__estimated_waiting_time_now_min",
    "importance": 0.12641294300556183
  },
  {
    "feature": "num__station_load",
    "importance": 0.03798114135861397
  },
  {
    "feature": "cat__congestion_level_now_Low",
    "importance": 0.026556340977549553
  },
  {
    "feature": "num__current_queue_length",
    "importance": 0.022779863327741623
  },
  {
    "feature": "num__queue_roll_mean_8",
    "importance": 0.016409939154982567
  },
  {
    "feature": "num__active_chargers",
    "importance": 0.014580093324184418
  },
  {
    "feature": "cat__traffic_level_Low",
    "importance": 0.0141060221940279
  },
  {
    "feature": "num__queue_lag_1",
    "importance": 0.01378925796598196
  },
  {
    "feature": "cat__time_slot_Overnight",
    "importance": 0.013176226057112217
  },
  {
    "feature": "num__queue_roll_mean_4",
    "importance": 0.012881604954600334
  },
  {
    "feature": "cat__time_slot_Morning",
    "importance": 0.011601708829402924
  },
  {
    "feature": "cat__day_of_week_Tuesday",
    "importance": 0.01151310559362173
  },
  {
    "feature": "num__wait_lag_4",
    "importance": 0.01121312566101551
  }
]
```

## Leakage prevention

- Only prediction-time features used.
- Future congestion / queue / waiting-time labels excluded.
- Lags computed per station on past rows only.
- Preprocessing and class weights fit/derived from training data only.
- Model selected on validation macro-F1; test evaluated once.

## Limitations

- Synthetic/rule-derived labels; not independent real-world congestion audits.
- Model approximates foresight of those categories, not absolute physical congestion truth.
- Does **not** predict queue length or waiting time.
- Medium class is minority; accuracy alone is insufficient.

## Artifacts

- `models/congestion_best_model.joblib`
- `models/congestion_random_forest.joblib`
- `models/congestion_xgboost.joblib`
- `plots/congestion_confusion_matrix.png`
- `plots/congestion_class_metrics.png`
- `plots/congestion_test_timeseries.png`
- `reports/congestion_model_comparison.csv`
