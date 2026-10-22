# Component 3 viva practice

Use this beside the code. Cover the model answers in section 7 and say them aloud before you uncover them.

Folder: `component3_energy_cost_estimation/`

This component predicts how many **kilowatt-hours a drive will use**. It does not predict the charging-session minutes, and it does not predict the rupee bill. The bill is energy times a tariff the user types.

## 20-minute practice

1. Say the one-sentence answer in section 1.
2. Open `results/test_metrics.json` lines 2–20 and `results/training_summary.json` lines 10–34.
3. Answer the eight questions in section 7.
4. If you said the station’s charging kWh is this model, or that the cost is an official tariff, start section 5 again.

## 1. What Component 3 is

The question is: for this road leg, how many kWh does the car use?

The target column is `energy_consumption_kwh`. Code: `src/config.py` line 23 and `src/prepare_data.py` lines 27–32.

One sentence:

> Component 3 predicts driving energy in kWh with XGBoost, chosen because it had the lowest validation error. On the held-out trips the average miss is about 1.47 kWh and R² is 0.91. That score is on a synthetic table whose label is the battery drop, not a meter on a Sri Lankan road. Charging cost is that energy, or the charging energy, times a tariff the user types.

Open:

- `README.md` lines 1–29
- `src/config.py` lines 19–48

## 2. The table

File: `data/raw/energy_consumption.csv` (the same rows as `component3_energy_consumption.csv`).

Checked in `results/dataset_quality_report.md`:

- 5,000 rows and 16 columns. No duplicate rows. No missing values.
- No dates. The file has `trip_id` only.
- Target: `energy_consumption_kwh`.
- Traffic levels: low, medium, high. Road types: highway, mixed, urban. `results/training_summary.json` lines 85–94.
- The project labels the table synthetic (`results/test_metrics.json` line 29). It is not a log from Sri Lankan roads.

The important data check is in `src/dataset_checks.py` lines 76–85 and `results/training_summary.json` lines 79–83:

- `energy_consumption_kwh` matches `(soc_start_pct - soc_end_pct) / 100 × battery_capacity_kwh`.
- Mean absolute gap: 0.002 kWh. Largest gap: 0.008 kWh. That is rounding, not a second measurement.
- So the label is the battery drop written in kWh. `soc_end_pct` is that label written as a percentage. `energy_consumption_kwh_per_km` is that label divided by distance. Both are excluded.

## 3. What goes in, and what is kept out

Known for a trip (`src/config.py` lines 32–47):

| Kind | Fields |
|---|---|
| Numbers | Distance (km), average speed (km/h), trip duration (min), battery capacity (kWh), start SOC (%), elevation gain (m), elevation loss (m), temperature (°C), air conditioning (0 or 1), vehicle mass (kg) |
| Categories | Traffic level, road type |

Excluded (`src/config.py` lines 27–30):

| Column | Why it is excluded |
|---|---|
| `soc_end_pct` | The target written as an ending percentage. Using it would leak the answer. |
| `energy_consumption_kwh_per_km` | The target divided by distance. |
| `energy_consumption_kwh` | The target itself. |
| `trip_id` | The row identifier. It is used only to order the split. |

`src/predict_energy.py` lines 37–41 reject a request that sends a leaked field. Lines 46–49 reject a missing feature. A missing feature is not filled with zero. Lines 50–53 reject a traffic level or road type that was not in the training set. Lines 57–61 reject a negative or non-finite prediction. It is not turned into 0 kWh.

## 4. How it was trained and why XGBoost won

There is no timestamp, so the split follows `trip_id` order (`src/prepare_data.py` lines 37–51). Seed 42 is only the random state of the forest and XGBoost. The split itself is not shuffled (`split_meta.random_seed` is null).

| Block | Rows |
|---|---|
| Train, first 70% | 3,500 |
| Validation, next 15% | 750 |
| Test, last 15% | 750 |

Four candidates. The rule is the lowest validation MAE in kWh (`src/train_models.py` line 161 and line 169):

| Model | Validation MAE (kWh) | Validation R² |
|---|---|---|
| XGBoost, 200 trees, depth 4, learning rate 0.05 | 1.52 | 0.904 |
| Random forest, 300 trees, depth 16, min leaf 4 | 1.59 | 0.893 |
| Linear regression | 1.70 | 0.882 |
| Median of the training energies (9.1 kWh) | 5.34 | −0.046 |

XGBoost wins by about 0.07 kWh over the best forest. The median is far worse, which is the opposite of Component 2. Here the features do explain the label.

The test block was scored once, after selection (`src/evaluate_models.py` lines 30–33):

| | Test, 750 trips |
|---|---|
| MAE | 1.47 kWh |
| RMSE | 2.13 kWh |
| R² | 0.909 |

The training median, scored on the same test block and not used for selection, has MAE 5.21 kWh and R² −0.049 (`results/test_metrics.json` lines 16–22). XGBoost beats that baseline by a wide margin on this table.

R² of 0.91 means the model tracks the battery-drop label on later rows of the same generated file. It does not mean the number was measured on a Sri Lankan road.

Saved files:

- `models/energy_consumption_pipeline.joblib`
- `models/energy_consumption_pipeline_meta.joblib`

Rebuild from this folder: `python -m src.train_models` then `python -m src.evaluate_models`.

## 5. What the phone uses this model for

Two different energies appear on a trip. Do not mix them up.

**Drive energy** can come from this model. `integration/orchestrate.py` `_energy_context` at line 376 allows the call only when elevation, temperature, air conditioning, traffic, road type, and vehicle mass are all present. `_predict_leg_kwh` at line 442 builds one record per road leg: distance and duration from the router, speed as distance divided by duration, battery size and start SOC from the trip. Climb measured on the whole direct route is shared across legs by distance (lines 454–459).

The phone does not ask the user to type those conditions. `integration/conditions.py` `automatic_conditions` at line 144 reads temperature and elevation from Open-Meteo along the road. Traffic is a stated clock rule, not a live count: weekday 07:00–09:30 and 16:30–19:00 are high, 22:00–05:00 is low, otherwise medium (`traffic_rule`, line 124). Road type follows the routed speed: 60 km/h or more is highway, under 30 km/h is urban, otherwise mixed (`road_type_rule`, line 135). Vehicle mass and air conditioning come from the car in the app. If weather or elevation does not answer, the conditions stay missing and the model is not called (lines 175–183).

Battery checks use the **larger** of the model kWh and the driver’s own kWh-per-100 km times the road distance (`_model_battery`, line 472, and `_prepare_energy`, lines 237–242). A low model prediction cannot make a trip look possible when the car’s own rate says it is not.

**Charging energy** on the station card is not this model. `CHARGING_NOTE` at lines 354–358: usable capacity times the rise from the SOC on arrival to the target SOC. That is battery energy for the charge, not a Component 3 prediction and not grid energy.

**Cost** is not a model. `src/calculate_charging_cost.py` lines 4–6 and 70–83:

`estimated_total = energy_kwh × tariff_per_kwh + extra_fixed_fees`

The tariff is whatever the user typed. No official LKR rate is stored. If efficiency is supplied, the priced kWh is battery kWh divided by that efficiency (`integration/orchestrate.py` `_energy_and_cost`, lines 849–880). If no tariff was typed, the cost stays empty. A listed station price is not used as the bill.

## 6. How it was checked

1. `src/dataset_checks.py` `inspect_frame` (line 53) records shape, missing cells, and whether the energy column matches the SOC drop. A file with no energy column stops training (lines 99–101).
2. Negative energy labels abort the split (`src/prepare_data.py` lines 41–42). They are not clipped.
3. The trip-id blocks do not overlap (`src/prepare_data.py` lines 45–51).
4. The median, a linear model, a forest, and XGBoost are compared on validation MAE only (`src/train_models.py` lines 88–161).
5. The winner is scored once on the last 750 trips (`src/evaluate_models.py`).
6. `src/predict_energy.py` refuses leaked fields, missing fields, unknown categories, and a negative prediction.
7. `tests/test_component3.py` checks those controls.

## 7. Practice questions

**1. What is the target, and in which unit?**

Kilowatt-hours of a trip. Column `energy_consumption_kwh`. Code: `src/config.py` line 23.

**2. Why XGBoost, not the median or a random forest?**

It had the lowest validation MAE, 1.52 kWh, against 1.59 for the forest, 1.70 for linear regression, and 5.34 for the training median. Rule: `src/train_models.py` line 161. The selected settings are 200 trees, depth 4, learning rate 0.05.

**3. Is the model accurate?**

On this table, yes, relative to the median. Test MAE is 1.47 kWh and test R² is 0.909, against 5.21 kWh and R² −0.049 for the training median. Say the next sentence as well: the label is the battery drop on synthetic trips, so 0.91 is not a measurement from Sri Lankan roads. Source: `results/test_metrics.json` lines 10–22.

**4. Why were end SOC and kWh per km removed?**

They are the same label written another way. The energy column matches start SOC minus end SOC, times battery capacity, within 0.008 kWh. `src/dataset_checks.py` lines 76–85. Prediction refuses them at `src/predict_energy.py` lines 37–41.

**5. What happens if the model predicts a negative kWh?**

The request fails. The value is not replaced with zero. `src/predict_energy.py` lines 57–61. The cost function rejects a negative kWh the same way (`src/calculate_charging_cost.py` lines 59–62).

**6. Does Component 3 decide the charging kWh and the bill?**

No. Charging kWh is battery capacity times the SOC rise at the station (`integration/orchestrate.py` lines 354–358). The bill is that energy, or grid energy if the user supplied an efficiency, times the tariff the user typed. The model predicts drive energy on a road leg.

**7. When does a search actually call the model?**

Only when elevation, temperature, air conditioning, traffic, road type, and vehicle mass are all present (`_energy_context`, line 376). The app fills them from the road, Open-Meteo, the departure clock, and the selected car. If one is missing, drive energy stays at the kWh per 100 km the driver entered. The battery gate then uses the larger of the model and that rate.

**8. Why is the split by trip id instead of by date?**

The file has no timestamps. Holding out the last 15% of `trip_id` order keeps a later block of the generated table out of training. It is not a future season. `src/prepare_data.py` lines 61–63.

## 8. Files, in the order to open them

1. `README.md` lines 1–29 — the result in one page.
2. `results/dataset_quality_report.md` — 5,000 rows and the energy column.
3. `src/dataset_checks.py` lines 76–85 — why end SOC is leakage.
4. `src/config.py` lines 23–60 — target, inputs, conditions.
5. `src/prepare_data.py` lines 37–72 — trip-id split.
6. `src/train_models.py` lines 119–169 — the four candidates and the MAE rule.
7. `results/training_summary.json` lines 1–34 — who won.
8. `results/test_metrics.json` lines 10–22 — the one test score and the median baseline.
9. `src/predict_energy.py` lines 31–67 — what a request must contain.
10. `src/calculate_charging_cost.py` lines 29–89 — the bill is arithmetic.
11. `integration/orchestrate.py` lines 354–358 and 376–469 — charging energy versus drive energy.
12. `integration/conditions.py` lines 124–193 — where temperature, climb, traffic, and road type come from.
