# Component 2 dataset quality report

- Path: `C:\Users\Charuka\Desktop\thanuka resarch\system\EV Charging Duration Prediction\data\raw\component2_charging_duration_sri_lanka_5_stations.csv`
- Shape: 1320 rows × 24 columns
- Duplicate rows: 0
- Target: `Charging Duration (hours)` in **hours**, modelled as **minutes**
- Conversion: charging_duration_min = Charging Duration (hours) * 60
- Duration hours min/median/max: 0.007 / 0.860 / 40.662
- Non-positive durations: 0
- SOC start outside 0–100: 0
- SOC end outside 0–100: 0
- SOC end below start: 0
- Coverage: 2024-01-01 00:00:00 → 2024-02-24 23:00:00 (55 dates)

## Missing values

- `Distance Driven (since last charge) (km)`: 66

## Limitations

- Place names are five Sri Lankan labels: Pannipitiya (264), Malabe (264), Nugegoda LECO (264), Panadura (264), Rajagiriya (264). Each label has the same number of rows, which is a generated balance, not evidence of equal real demand.
- Labelled duration matches Charging End Time minus Charging Start Time (correlation 1.000). The duration column is that clock difference.
- Energy consumed matches charging rate times labelled duration (correlation 1.000). Both identities were generated from battery capacity, the SOC rise, and charging rate. This is not a meter log from those chargers.
- SOC start outside 0–100: 0. SOC end outside 0–100: 0. SOC end below start: 0.
- A low error means the model recovered that generated formula. It does not mean the minutes were measured at the chargers.
