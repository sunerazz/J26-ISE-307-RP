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
    "High": 21595,
    "Low": 20489,
    "Medium": 6276
  },
  "validation": {
    "High": 4590,
    "Low": 4464,
    "Medium": 1314
  },
  "test": {
    "High": 4531,
    "Low": 4514,
    "Medium": 1299
  }
}
```

## Test metrics — selected model

```json
{
  "accuracy": 0.8160286156225831,
  "macro_f1": 0.7330586259418309,
  "n": 10344,
  "labels_evaluated": [
    "Low",
    "Medium",
    "High"
  ],
  "per_class": {
    "Low": {
      "precision": 0.8567609712630876,
      "recall": 0.8520159503766062,
      "f1": 0.8543818727090969,
      "support": 4514
    },
    "Medium": {
      "precision": 0.38412142440163455,
      "recall": 0.5065434949961509,
      "f1": 0.43691899070385126,
      "support": 1299
    },
    "High": {
      "precision": 0.9505070014485756,
      "recall": 0.8689031118958287,
      "f1": 0.9078750144125447,
      "support": 4531
    }
  }
}
```

## Baseline vs Random Forest vs XGBoost (test)

```json
{
  "most_frequent": {
    "accuracy": 0.43803170920340295,
    "macro_f1": 0.20307002801120447,
    "n": 10344,
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
        "support": 4514
      },
      "Medium": {
        "precision": 0.0,
        "recall": 0.0,
        "f1": 0.0,
        "support": 1299
      },
      "High": {
        "precision": 0.43803170920340295,
        "recall": 1.0,
        "f1": 0.6092100840336134,
        "support": 4531
      }
    }
  },
  "random_forest": {
    "accuracy": 0.8240525908739366,
    "macro_f1": 0.7406672998643405,
    "n": 10344,
    "labels_evaluated": [
      "Low",
      "Medium",
      "High"
    ],
    "per_class": {
      "Low": {
        "precision": 0.8517560870502047,
        "recall": 0.8757199822773594,
        "f1": 0.8635718186783179,
        "support": 4514
      },
      "Medium": {
        "precision": 0.40991839296924043,
        "recall": 0.5026943802925328,
        "f1": 0.4515905947441217,
        "support": 1299
      },
      "High": {
        "precision": 0.9532846715328467,
        "recall": 0.8647097770911498,
        "f1": 0.9068394861705821,
        "support": 4531
      }
    }
  },
  "xgboost": {
    "accuracy": 0.8160286156225831,
    "macro_f1": 0.7330586259418309,
    "n": 10344,
    "labels_evaluated": [
      "Low",
      "Medium",
      "High"
    ],
    "per_class": {
      "Low": {
        "precision": 0.8567609712630876,
        "recall": 0.8520159503766062,
        "f1": 0.8543818727090969,
        "support": 4514
      },
      "Medium": {
        "precision": 0.38412142440163455,
        "recall": 0.5065434949961509,
        "f1": 0.43691899070385126,
        "support": 1299
      },
      "High": {
        "precision": 0.9505070014485756,
        "recall": 0.8689031118958287,
        "f1": 0.9078750144125447,
        "support": 4531
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
      3846,
      635,
      33
    ],
    [
      469,
      658,
      172
    ],
    [
      174,
      420,
      3937
    ]
  ]
}
```

## Feature importance (top)

```json
[
  {
    "feature": "num__estimated_waiting_time_now_min",
    "importance": 0.1489410698413849
  },
  {
    "feature": "num__station_load",
    "importance": 0.12124747037887573
  },
  {
    "feature": "cat__congestion_level_now_Low",
    "importance": 0.08908601850271225
  },
  {
    "feature": "num__station_utilization",
    "importance": 0.061616163700819016
  },
  {
    "feature": "num__queue_after_current_arrivals",
    "importance": 0.05857359617948532
  },
  {
    "feature": "cat__location_type_Highway",
    "importance": 0.049835797399282455
  },
  {
    "feature": "cat__congestion_level_now_High",
    "importance": 0.020372359082102776
  },
  {
    "feature": "num__total_chargers",
    "importance": 0.01748587004840374
  },
  {
    "feature": "cat__station_id_ST06",
    "importance": 0.01523090060800314
  },
  {
    "feature": "cat__station_id_ST01",
    "importance": 0.014717447571456432
  },
  {
    "feature": "cat__time_slot_Overnight",
    "importance": 0.014157001860439777
  },
  {
    "feature": "cat__station_id_ST03",
    "importance": 0.013595672324299812
  },
  {
    "feature": "cat__location_type_Urban",
    "importance": 0.01303162332624197
  },
  {
    "feature": "num__average_charging_duration_min",
    "importance": 0.012887382879853249
  },
  {
    "feature": "num__available_chargers",
    "importance": 0.01124898437410593
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
