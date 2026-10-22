# Feature and Target Definitions

## Experiment label

**SIMULATION-BASED** — synthetic EV charging snapshot dataset.

## Target

- Name: `target_queue_length_30min`
- Definition: `current_queue_length` at the **same** `station_id` exactly **30 minutes** after the prediction timestamp.
- Construction: exact timestamp match (`t + 30 min`).
- Unmatched rows dropped (never filled with 0): **10**.
- Current queue is **not** used as the future target.

## Selected features (known at prediction time)

- `is_weekend`
- `hour`
- `minute`
- `temperature_C`
- `traffic_index`
- `vehicle_arrivals_15min`
- `estimated_arrival_rate_vehicles_per_hour`
- `current_queue_length`
- `queue_after_current_arrivals`
- `total_chargers`
- `active_chargers`
- `available_chargers`
- `busy_chargers`
- `charger_power_kW`
- `average_charging_duration_min`
- `station_utilization`
- `station_load`
- `estimated_waiting_time_now_min`
- `station_id`
- `location_type`
- `day_of_week`
- `time_slot`
- `weather_condition`
- `traffic_level`
- `congestion_level_now`
- `queue_lag_1`
- `queue_lag_2`
- `queue_lag_4`
- `queue_roll_mean_4`
- `queue_roll_mean_8`
- `queue_roll_std_4`
- `queue_delta_1`
- `arrivals_lag_1`
- `arrivals_lag_2`
- `arrivals_roll_mean_4`

## Excluded / not used as inputs

- **target_waiting_time_30min_min**: Future waiting-time label; not available at prediction time; out of scope.
- **target_congestion_level_30min**: Future congestion label; leakage risk; out of scope.
- **CSV target_queue_length_30min (original)**: Overwritten. Original CSV definition equals queue_after_current_arrivals@t+30, not current_queue_length@t+30. Modelling target is reconstructed from observations.
- **timestamp (raw)**: Used for ordering/splitting only; time encoded via hour/minute/day features.
- **Full-dataset statistics**: Never computed before split; training statistics only.
- **Future arrivals / completions**: Not present as usable known-at-prediction features beyond current interval.

## Cleaning operations

1. Parse timestamps; abort if invalid.
2. Overwrite target with reconstructed same-station +30 min queue.
3. Drop rows lacking a matched future queue observation.
4. Engineer per-station lag/rolling features from past rows only.
5. Drop rows where required lag features are still NaN (warm-up).
6. Chronological date split (no shuffling).
7. No SMOTE; no imputation of unknown queue with zero.
8. No feature scaling (tree models).

## Chronological split

```json
{
  "n_unique_dates": 120,
  "n_train_dates": 84,
  "n_val_dates": 18,
  "n_test_dates": 18,
  "train_date_start": "2025-01-01",
  "train_date_end": "2025-03-25",
  "val_date_start": "2025-03-26",
  "val_date_end": "2025-04-12",
  "test_date_start": "2025-04-13",
  "test_date_end": "2025-04-30",
  "overlap_train_val": [],
  "overlap_train_test": [],
  "overlap_val_test": [],
  "dropped_no_target": 10,
  "dropped_lag_warmup": 20,
  "unmatched_target_rows": 10,
  "n_train_rows": 40300,
  "n_val_rows": 8640,
  "n_test_rows": 8620,
  "feature_columns": [
    "is_weekend",
    "hour",
    "minute",
    "temperature_C",
    "traffic_index",
    "vehicle_arrivals_15min",
    "estimated_arrival_rate_vehicles_per_hour",
    "current_queue_length",
    "queue_after_current_arrivals",
    "total_chargers",
    "active_chargers",
    "available_chargers",
    "busy_chargers",
    "charger_power_kW",
    "average_charging_duration_min",
    "station_utilization",
    "station_load",
    "estimated_waiting_time_now_min",
    "station_id",
    "location_type",
    "day_of_week",
    "time_slot",
    "weather_condition",
    "traffic_level",
    "congestion_level_now",
    "queue_lag_1",
    "queue_lag_2",
    "queue_lag_4",
    "queue_roll_mean_4",
    "queue_roll_mean_8",
    "queue_roll_std_4",
    "queue_delta_1",
    "arrivals_lag_1",
    "arrivals_lag_2",
    "arrivals_roll_mean_4"
  ]
}
```

## Leakage controls

- Fit preprocessing only on training data (see train script).
- Lags/rolling computed within station and using shifted windows only.
- Validation used for model selection; test evaluated once.
