# Component 3 — EV energy consumption and charging cost

The training file is `component3_energy_consumption.csv` (copied to `data/raw/energy_consumption.csv`). It has 5,000 synthetic trips and a column `energy_consumption_kwh`.

That column matches `(soc_start_pct - soc_end_pct) / 100 * battery_capacity_kwh` within rounding. `soc_end_pct` and `energy_consumption_kwh_per_km` are the same quantity written another way, so both are excluded. `trip_id` is excluded as an identifier.

Features used: distance, average speed, duration, battery capacity, start SOC, elevation gain and loss, temperature, air conditioning, traffic level, road type, and vehicle mass.

The split follows trip id order: 70% train, 15% validation, 15% test. The model with the lowest validation MAE in kWh is saved. A negative prediction is rejected rather than turned into 0 kWh.

```bash
cd component3_energy_cost_estimation
pip install -r requirements.txt
python -m src.train_models
python -m src.evaluate_models
python -m pytest -q tests
```

The saved files are `models/energy_consumption_pipeline.joblib` and `models/energy_consumption_pipeline_meta.joblib`.

## Charging cost

Cost stays a separate calculation. No official tariff is stored in the code.

```text
estimated_total = energy_kwh × tariff_per_kwh + extra_fixed_fees
```

The integration API calls this model only when a search supplies elevation, temperature, air conditioning, traffic, road type, and vehicle mass. Distance and duration then come from the road route, and speed is distance divided by that duration. A Colombo search that omits those conditions keeps using the kWh per 100 km figure the driver entered.
