# Component 2 viva practice

Use this beside the code. Cover the model answers in section 7 and say them aloud before you uncover them.

Folder: `EV Charging Duration Prediction/`

This component predicts how many **minutes a charging session will last**. The phone uses that prediction as the charging time.

## 20-minute practice

1. Say the one-sentence answer in section 1.
2. Open `results/dataset_quality_report.md` lines 21–25 and `results/test_metrics.json` lines 10–21.
3. Answer the eight questions in section 7.
4. If you say the old table was inconsistent, or that the minutes were measured at the chargers, start section 2 again.

## 1. What Component 2 is

The question is: when a car plugs in, how many minutes will that session take?

The source column is `Charging Duration (hours)`. The model target is `charging_duration_min`, which is that column times 60. Code: `src/config.py` lines 19–21 and `src/prepare_data.py` `add_target` at line 42.

One sentence:

> Component 2 predicts charging duration in minutes with XGBoost, chosen because it had the lowest validation error. On the later test days the average miss is about 13 minutes and R² is 0.89. The table was generated so duration equals the clock and energy equals power times time, so that score recovers the formula. It is not a measurement from the chargers.

Open:

- `README.md` lines 11–24 and 52–65
- `src/config.py` lines 19–36

## 2. The table

File: `data/raw/component2_charging_duration_sri_lanka_5_stations.csv`

Rebuilt by `src/rebuild_physical_sessions.py`. The place names, vehicles, and start times stay. The session length is generated as:

```text
energy_kwh = battery_kwh × (end SOC − start SOC) / 100
duration_hours = energy_kwh / charging_rate_kw
end_time = start_time + duration_hours
```

Checked in `results/dataset_quality_report.md`:

- 1,320 rows and 24 columns. No duplicate rows.
- Dates: 1 January 2024 to 24 February 2024. That is 55 days.
- Five place names, 264 rows each: Nugegoda LECO, Rajagiriya, Malabe, Pannipitiya, and Panadura. Equal counts are a generated balance, not measured demand.
- Duration matches end time minus start time. Correlation **1.000**.
- Energy matches charging rate times duration. Correlation **1.000**.
- SOC values are inside 0–100, and end SOC is never below start SOC.
- Median duration is 0.860 hours, about 52 minutes. The longest generated session is about 41 hours, because some original rates are small beside a large battery.

Say this, and do not say the old two findings. Those described the table before it was rebuilt. `results/dataset_quality_report.md` lines 22–23 are the current checks.

## 3. What goes in, and what is kept out

The model uses only the four values that define the generated session (`src/config.py` lines 30–36):

| Field | Why it is an input |
|---|---|
| Battery capacity (kWh) | Part of the energy |
| Charging rate (kW) | Divides that energy to give hours |
| Start SOC (%) | Charge when the session starts |
| End SOC (%) | Requested end charge, set before the duration is calculated |

Kept out (`src/config.py` lines 39–61):

| Column | Why it is excluded |
|---|---|
| Duration in hours and minutes | The target |
| Charging end time | Start time plus the duration, so it would reveal the answer |
| Energy consumed | Rate times duration, the same information as the target |
| Illustrative tariff and cost | The cost is energy times 120 LKR. It does not cause the duration |
| Place, vehicle, charger type, time of day, day, age, distance | Stored in the file, but the generated duration does not depend on them |

`src/predict_duration.py` lines 47–49 reject a request that sends the duration, the end time, or the energy. Lines 54–57 reject a missing feature. A missing feature is not filled with zero. A negative raw prediction is clipped to zero for serving (lines 62–68). The published test MAE uses the raw number.

## 4. How it was trained and why XGBoost won

Split by calendar date, not by shuffling (`src/prepare_data.py` `chronological_split`, line 56). Seed 42 is the model random state only.

| Block | Dates | Rows |
|---|---|---|
| Train 70% | 1 Jan 2024 – 7 Feb 2024 | 912 |
| Validation 15% | 8 Feb 2024 – 15 Feb 2024 | 192 |
| Test 15% | 16 Feb 2024 – 24 Feb 2024 | 216 |

Four candidates. The rule is the lowest validation MAE in minutes (`src/train_models.py` line 197 and line 205):

| Model | Validation MAE (minutes) | Validation R² |
|---|---|---|
| XGBoost, 200 trees, depth 4, learning rate 0.05 | 22.50 | 0.780 |
| Random forest, 300 trees, depth 12, min leaf 2 | 24.81 | 0.731 |
| Linear regression | 60.30 | 0.331 |
| Median of the training durations | 78.97 | −0.068 |

XGBoost wins. A straight line and a constant cannot represent battery × SOC rise / rate. The forest is close. The median is far behind.

The test set was scored once, after selection (`src/evaluate_models.py`):

| | Test, 216 sessions |
|---|---|
| MAE | 13.26 minutes |
| RMSE | 36.90 minutes |
| R² | 0.888 |

About 3.2% of the raw test predictions were negative (`results/test_metrics.json` line 21). Serving clips those at zero. The raw test MAE is 13.26 minutes. The clipped MAE is 13.11 minutes.

R² of 0.89 means the model tracks the generated formula on later days of the same table. It does not mean a charger was timed.

Saved files:

- `models/charging_duration_pipeline.joblib`
- `models/charging_duration_pipeline_meta.joblib`

Rebuild the table and the model from this folder: `python -m src.rebuild_physical_sessions` then `python run_pipeline.py`.

## 5. What the phone shows

The charging minutes on a station card come from this model.

`integration/orchestrate.py` `_predict_session_minutes` sends battery size, the station's listed power, the arrival charge, and the requested end charge. Each station gets its own prediction, so a slower charger takes longer for the same SOC rise. If the car is already at the target, the time is zero and the model is not called. If the model is not loaded, or power or a charge level is missing, the time stays blank. Listed kilowatts are not used as a second calculation.

The route plan's stop times are replaced with the same model (`_plan_session_times`). The planner still decides where a stop is needed from battery energy.

The kilowatt-hours beside the time are still battery capacity times the SOC rise. That is energy. The minutes are the model.

## 6. How it was checked

1. `src/rebuild_physical_sessions.py` writes duration, end time, and energy from the formula, then prints the two correlations.
2. `src/inspect_dataset.py` records those correlations in `results/dataset_quality_report.md`. Both are 1.000 after the rebuild.
3. Invalid start times or a non-positive duration abort the prepare step (`src/prepare_data.py` lines 47–51).
4. The date split cannot overlap (`src/prepare_data.py` lines 56–69).
5. The median, a linear model, a forest, and XGBoost are compared on validation MAE only (`src/train_models.py` lines 115–197).
6. The winner is scored once on 16–24 February 2024 (`src/evaluate_models.py`).
7. `tests/test_component2.py` checks that end time and energy are not features, and that end SOC is a feature.

## 7. Practice questions

**1. What is the target, and in which unit?**

Minutes. `charging_duration_min = Charging Duration (hours) × 60`. Code: `src/prepare_data.py` lines 42–52.

**2. Why XGBoost, not the median?**

It had the lowest validation MAE, 22.50 minutes, against 24.81 for the forest, 60.30 for linear regression, and 78.97 for the median. Rule: `src/train_models.py` line 197. The duration is a ratio, so a constant and a straight line lose.

**3. Is the model accurate?**

On this generated table, the test MAE is 13.26 minutes and test R² is 0.888. That means it recovered battery × SOC rise / rate on the later days. It is not a timed session from Nugegoda, Rajagiriya, Malabe, Pannipitiya, or Panadura. Source: `results/test_metrics.json` lines 10–14 and `results/dataset_quality_report.md` lines 22–23.

**4. Why do duration and energy now agree with the clock and the power?**

The table was rebuilt. Duration is end time minus start time, correlation 1.000. Energy is charging rate times that duration, correlation 1.000. Both are produced from the battery and the SOC rise. `src/rebuild_physical_sessions.py`.

**5. Which columns would leak the answer?**

End time, energy, and the duration itself. End SOC does not leak: it is the requested end charge used to create the duration, and it is an input. `src/config.py` lines 30–45. Prediction refuses the leaked fields at `src/predict_duration.py` lines 47–49.

**6. Why is the same model used for every station, not only the five names?**

The generated duration does not depend on the place name. The phone sends the battery, that station's power, and the two charge levels. A 22 kW charger and a 50 kW charger therefore get different minutes. `integration/orchestrate.py` `_predict_session_minutes`.

**7. What happens to a negative prediction?**

Serving clips it to zero minutes. The test report still publishes the raw error. On this test block, 3.2% of raw predictions were negative. `src/predict_duration.py` lines 62–68 and `results/test_metrics.json` lines 16–21.

**8. What duration does the app show?**

The Component 2 prediction for that station's battery, power, and charge levels. If no charge is needed, zero. If the model or an input is missing, blank. `integration/orchestrate.py` `_predict_session_minutes`.

## 8. Files, in the order to open them

1. `README.md` lines 11–65 — the result in one page.
2. `src/rebuild_physical_sessions.py` — how duration and energy were rebuilt.
3. `results/dataset_quality_report.md` lines 21–25 — the two correlations, both 1.000.
4. `src/config.py` lines 28–61 — the four inputs and the exclusions.
5. `src/prepare_data.py` lines 42–69 — minutes conversion and the date split.
6. `src/train_models.py` lines 115–205 — the four candidates and the MAE rule.
7. `results/training_summary.json` lines 1–34 — who won.
8. `results/test_metrics.json` lines 10–21 — the one test score.
9. `src/predict_duration.py` lines 38–68 — what a request must contain.
10. `integration/orchestrate.py` `_predict_session_minutes` — the minutes on the phone.
