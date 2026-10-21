# Feature and target definitions

## Target

- Source column: `Charging Duration (hours)` (unit: hours).
- Model target: `charging_duration_min` = source × 60.
- Unit used for MAE and RMSE: **minutes**.
- No rows were dropped for outliers or inconsistent SOC.

## Included features

- `Battery Capacity (kWh)`: Vehicle specification known at start. A few values look unrealistic and are retained, not dropped.
- `Charging Rate (kW)`: Treated as charger power available at the start of the session. It is not equal to energy/duration in this file. 66 missing values are imputed from the training fold only.
- `State of Charge (Start %)`: Initial SOC is known when charging starts. Nine values exceed 100% and are retained.
- `Distance Driven (since last charge) (km)`: Known before the new charging session. Missing values are imputed on the training fold only.
- `Vehicle Age (years)`: Vehicle attribute known at prediction time.
- `Temperature (Â°C)`: Ambient temperature recorded with the session and treated as known at prediction time.
- `Vehicle Model`: Known before charging starts.
- `Charging Station Location`: Known when the driver selects a station.
- `Time of Day`: Derived from the start time and available when charging begins.
- `Day of Week`: Derived from the start date and available when charging begins.
- `Charger Type`: Known from the selected charger (Level 1, Level 2, DC Fast Charger).
- `User Type`: Driver category known before the session.

## Excluded columns

- `Charging Duration (hours)`: Target source column (hours). Converted to minutes; never an input.
- `charging_duration_min`: Modelling target.
- `Charging End Time`: Known only when the session finishes; would reveal duration.
- `State of Charge (End %)`: Observed after charging completes.
- `Energy Consumed (kWh)`: Session energy is an outcome, not known when charging starts. 66 values are missing.
- `Charging Cost (USD)`: Billing result of the session, not an input available as a duration cause at start.
- `User ID`: Unique row identifier (1,320 distinct values). Not a generalisable feature.
- `Charging Station ID`: 462 sparse station IDs. Known at start, but too high-cardinality to generalise; excluded.
- `Charging Start Time`: Used only to order the chronological split, not as a raw model feature. Time of day and day of week are used instead.

## Split

```json
{
  "method": "chronological_by_unique_calendar_date",
  "fractions": {
    "train": 0.7,
    "val": 0.15,
    "test": 0.15
  },
  "n_unique_dates": 55,
  "n_train_dates": 38,
  "n_val_dates": 8,
  "n_test_dates": 9,
  "train_date_start": "2024-01-01",
  "train_date_end": "2024-02-07",
  "val_date_start": "2024-02-08",
  "val_date_end": "2024-02-15",
  "test_date_start": "2024-02-16",
  "test_date_end": "2024-02-24",
  "n_train_rows": 912,
  "n_val_rows": 192,
  "n_test_rows": 216,
  "date_overlap_train_val": [],
  "date_overlap_train_test": [],
  "date_overlap_val_test": [],
  "limitation": "Sessions are ordered by charging start date. This is not a random split. The calendar covers only about eight weeks, so the test period is a short future window of the same table.",
  "feature_columns": [
    "Battery Capacity (kWh)",
    "Charging Rate (kW)",
    "State of Charge (Start %)",
    "Distance Driven (since last charge) (km)",
    "Vehicle Age (years)",
    "Temperature (\u00c2\u00b0C)",
    "Vehicle Model",
    "Charging Station Location",
    "Time of Day",
    "Day of Week",
    "Charger Type",
    "User Type"
  ],
  "temperature_column": "Temperature (\u00c2\u00b0C)",
  "numeric_features": [
    "Battery Capacity (kWh)",
    "Charging Rate (kW)",
    "State of Charge (Start %)",
    "Distance Driven (since last charge) (km)",
    "Vehicle Age (years)",
    "Temperature (\u00c2\u00b0C)"
  ],
  "categorical_features": [
    "Vehicle Model",
    "Charging Station Location",
    "Time of Day",
    "Day of Week",
    "Charger Type",
    "User Type"
  ]
}
```
