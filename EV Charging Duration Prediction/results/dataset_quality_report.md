# Component 2 dataset quality report

- Path: `C:\Users\Charuka\Desktop\thanuka resarch\system\component2_charging_duration\data\raw\Component 2 ev_charging_patterns (2).xlsx`
- Shape: 1320 rows × 20 columns
- Duplicate rows: 0
- Target: `Charging Duration (hours)` in **hours**, modelled as **minutes**
- Conversion: charging_duration_min = Charging Duration (hours) * 60
- Duration hours min/median/max: 0.095 / 2.258 / 7.635
- Non-positive durations: 0
- SOC start outside 0–100: 9
- SOC end outside 0–100: 23
- SOC end below start: 268
- Coverage: 2024-01-01 00:00:00 → 2024-02-24 23:00:00 (55 dates)

## Missing values

- `Energy Consumed (kWh)`: 66
- `Charging Rate (kW)`: 66
- `Distance Driven (since last charge) (km)`: 66

## Limitations

- Duration in hours does not match Charging End Time minus Charging Start Time (near-zero correlation). The labelled duration column is used as the target, not the clock difference.
- Energy consumed is almost uncorrelated with duration, and charging rate is not equal to energy/duration. Treat the table as a noisy or synthetic session table, not a physically consistent meter log.
- A small number of SOC values exceed 100 percent and some end SOC values are below start SOC.
- 1,320 sessions over about eight weeks and five vehicle models is a small sample for strong generalisation claims.
