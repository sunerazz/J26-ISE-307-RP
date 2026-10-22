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
- `State of Charge (End %)`: Available at charging start.

## Excluded columns

- `Charging Duration (hours)`: Target source column (hours). Converted to minutes; never an input.
- `Charging Duration (minutes)`: Same target already stored in hours. Not an input.
- `charging_duration_min`: Modelling target.
- `Charging End Time`: Set to start time plus the generated duration, so it would reveal the target.
- `Energy Consumed (kWh)`: Generated as charging rate times duration. It is the same information as the target.
- `Charging Cost (USD)`: Billing result of the session, not an input available as a duration cause at start.
- `Illustrative Tariff (LKR/kWh)`: Constant 120 in this table, and not a cause of session length.
- `Illustrative Charging Cost (LKR)`: Derived from energy and the illustrative tariff. Energy is an outcome.
- `User ID`: Unique row identifier (1,320 distinct values). Not a generalisable feature.
- `Station ID`: One-to-one with the place name. Not a model feature.
- `Charging Station ID`: 462 sparse station IDs. Not a model feature.
- `Charging Start Time`: Used only to order the chronological split, not as a model feature.
- `Distance Driven (since last charge) (km)`: Not used. This table's duration does not depend on distance.
- `Vehicle Age (years)`: Not used. This table's duration does not depend on vehicle age.
- `Vehicle Model`: Not used. Duration is defined from the battery size, not the model name.
- `Charging Station Location`: Place label only. Duration does not depend on which of the five names is stored.
- `Station Area`: One-to-one with Charging Station Location. Not a model feature.
- `Time of Day`: Set from the start clock for the table. Not a cause of the generated duration.
- `Day of Week`: Set from the start date. Not a cause of the generated duration.
- `Charger Type`: The charging rate already carries the power. The type name is not a second feature.
- `User Type`: Not a cause of the generated duration.
- `Temperature (°C)`: Not a cause of the generated duration. The file header may show a broken degree sign.

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
    "State of Charge (End %)"
  ],
  "temperature_column": "Temperature (\u00c2\u00b0C)",
  "numeric_features": [
    "Battery Capacity (kWh)",
    "Charging Rate (kW)",
    "State of Charge (Start %)",
    "State of Charge (End %)"
  ],
  "categorical_features": []
}
```
