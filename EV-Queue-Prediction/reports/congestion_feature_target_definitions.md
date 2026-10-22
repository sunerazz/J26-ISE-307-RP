# Congestion Feature and Target Definitions (Model 3)

## Experiment label

**SIMULATION-BASED** — synthetic EV charging snapshot dataset.

## Congestion-label provenance

- Column `congestion_level_now` provides station-level categories `Low, Medium, High`.
- Labels are **synthetic / rule-derived** (strongly associated with `estimated_waiting_time_now_min` and queue/utilization state), not independently observed real-world congestion audits.
- Approximate heuristic association (for interpretation only; not used to overwrite labels): wait≈0 → Low; short waits → Medium; long waits → High (~95% agreement with a simple wait threshold; residual cases involve medium/high boundary ambiguity).
- The modelling target is reconstructed by temporal alignment of the existing snapshot labels, not by inventing new categories.

## Target

- Name: `target_congestion_level_30min`
- Definition: `congestion_level_now` at the **same** `station_id` exactly **30 minutes** later.
- Construction: exact timestamp match (`t + 30 min`).
- Unmatched rows dropped (never filled as Low): **10**.
- Current `congestion_level_now` is an input feature, not the future target.
- Future queue and future waiting-time values are **not** used as labels or features.

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
- `wait_lag_1`
- `wait_lag_2`
- `wait_lag_4`
- `wait_roll_mean_4`
- `wait_roll_mean_8`
- `wait_delta_1`

## Excluded inputs

- `target_congestion_level_30min` (future label)
- `target_queue_length_30min` (future queue; Model 1)
- `target_waiting_time_30min_min` (future wait; Model 2)
- Any features computed from the future congestion label

## Leakage note for rule-derived labels

Because congestion is closely related to wait/queue, current wait and queue are valid contemporaneous features, but **future** wait/queue must never enter the feature matrix.

## Cleaning

1. Parse timestamps; abort if invalid.
2. Validate allowed class names.
3. Reconstruct future congestion from same-station label@t+30.
4. Drop unmatched future rows (no silent Low imputation).
5. Engineer per-station past-only lag/rolling features.
6. Drop lag warm-up NaNs.
7. Chronological date split 70/15/15 (same policy as Models 1–2).
8. No SMOTE on this time-series classification task.

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
  "task": "congestion_30min",
  "congestion_column": "congestion_level_now",
  "target_column": "target_congestion_level_30min",
  "allowed_classes": [
    "Low",
    "Medium",
    "High"
  ],
  "label_provenance": "synthetic_rule_derived_station_snapshots",
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
    "arrivals_roll_mean_4",
    "wait_lag_1",
    "wait_lag_2",
    "wait_lag_4",
    "wait_roll_mean_4",
    "wait_roll_mean_8",
    "wait_delta_1"
  ],
  "class_counts_train": {
    "High": 39990,
    "Medium": 194,
    "Low": 116
  },
  "class_counts_val": {
    "High": 8567,
    "Medium": 51,
    "Low": 22
  },
  "class_counts_test": {
    "High": 8575,
    "Medium": 28,
    "Low": 17
  },
  "queue_available_at_prediction_time": true,
  "wait_available_at_prediction_time": true
}
```
