# Component 3 dataset quality report

- Path inspected: `C:\Users\Charuka\Desktop\thanuka resarch\system\component3_energy_cost_estimation\data\raw\energy_consumption.csv`
- Shape: 5000 rows × 16 columns
- Duplicate rows: 0
- Missing values: none
- Energy target column: energy_consumption_kwh
- Target status: present_in_file

## Columns

- `trip_id` (object)
- `distance_km` (float64)
- `average_speed_kmh` (float64)
- `trip_duration_min` (float64)
- `battery_capacity_kwh` (float64)
- `soc_start_pct` (float64)
- `soc_end_pct` (float64)
- `elevation_gain_m` (float64)
- `elevation_loss_m` (float64)
- `ambient_temperature_c` (float64)
- `ac_on` (int64)
- `traffic_level` (object)
- `road_type` (object)
- `vehicle_mass_kg` (float64)
- `energy_consumption_kwh` (float64)
- `energy_consumption_kwh_per_km` (float64)

## Decision

energy_consumption_kwh is present. soc_end_pct and energy_consumption_kwh_per_km match that label and are excluded from training. Charging cost is still calculate_charging_cost with a tariff you supply.
