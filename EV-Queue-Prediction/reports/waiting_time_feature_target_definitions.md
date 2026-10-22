# Waiting-Time Feature and Target Definitions (Model 2)

## Experiment label

**SIMULATION-BASED** — synthetic EV charging snapshot dataset.

## Waiting-time provenance

- Column `estimated_waiting_time_now_min` is an **estimated** station-level waiting time in minutes (name and ≥240 cap pattern indicate a derived/heuristic quantity, not a vehicle-session stopwatch measured from arrival until charging start).
- No raw arrival→charge-start event log is present in the CSV.
- Values are simulated/derived; results are not real-world deployment evidence.

## Target

- Name: `target_waiting_time_30min_min`
- Definition: expected station waiting time (`estimated_waiting_time_now_min`) for a new arrival at the **same** `station_id` exactly **30 minutes** after the prediction timestamp.
- Construction: exact timestamp match (`t + 30 min`).
- Unmatched rows dropped (never filled with 0): **10**.
- Current `estimated_waiting_time_now_min` is a feature, not the future target.
- Future queue length is **not** reused as the waiting-time target.

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

- `target_waiting_time_30min_min` (future label / leakage)
- `target_queue_length_30min` (future queue; separate Model 1 task)
- `target_congestion_level_30min` (future congestion; separate later task)
- Charging start/end times not present; none assumed known in advance
- Full-dataset statistics before chronological split

## Assumptions about real-time information

- `estimated_waiting_time_now_min`, `current_queue_length`, charger counts, utilization, weather and traffic fields are treated as known at the prediction timestamp (consistent with a station telemetry snapshot).

## Cleaning

1. Parse timestamps; abort if invalid.
2. Reconstruct waiting target from same-station wait@t+30.
3. Drop rows without a matched future waiting observation.
4. Engineer per-station past-only lag/rolling features (queue, arrivals, wait).
5. Drop lag warm-up rows with NaN engineered features.
6. Chronological date split (70/15/15), identical policy to Model 1.
7. No SMOTE; no filling unknown waits with zero; no scaling for trees.

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
  "task": "waiting_time_30min",
  "wait_column": "estimated_waiting_time_now_min",
  "target_column": "target_waiting_time_30min_min",
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
  "target_unit": "minutes",
  "target_min_train": 0.0,
  "target_max_train": 180.0,
  "target_zero_fraction_train": 0.0017866004962779156
}
```
