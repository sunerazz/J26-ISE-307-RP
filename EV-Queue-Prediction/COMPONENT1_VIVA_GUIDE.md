# Component 1 viva practice

Use this beside the code. Each claim below is tied to a file and a line. Cover the model answers in section 8 and say them aloud before you uncover them.

Folder: `EV-Queue-Prediction/`

Experiment label: **SIMULATION-BASED**. The five station names are Sri Lankan places. The 15-minute queue, wait, and congestion numbers are generated snapshots, not a log taken at the chargers.

## 30-minute practice

1. Say the one-sentence answer in section 1.
2. Open the three metric files in section 5 and read only the selected-model block.
3. Answer the ten questions in section 8 with the pages closed.
4. If you said “99% accurate” for congestion, start section 5 again. Accuracy is the wrong headline.

## 1. What Component 1 is

Component 1 predicts three things, each **30 minutes ahead**, for five named stations:

| Model | Question | Target |
|---|---|---|
| 1 Queue | How many vehicles will be in the queue? | `current_queue_length` at the same station, 30 minutes later |
| 2 Waiting time | How many minutes will the wait be? | `estimated_waiting_time_now_min` at t+30 |
| 3 Congestion | Will the level be Low, Medium, or High? | `congestion_level_now` at t+30 |

Stations in `data/raw/component1_ev_queue_prediction_sri_lanka.csv`:

| ID | Place | Type | Chargers | Power |
|---|---|---|---|---|
| ST01 | Nugegoda LECO | Urban | 4 | 50 kW |
| ST02 | Rajagiriya | Urban | 4 | 50 kW |
| ST03 | Malabe | Suburban | 3 | 50 kW |
| ST04 | Pannipitiya | Suburban | 3 | 50 kW |
| ST05 | Panadura | Suburban | 3 | 50 kW |

One sentence:

> Component 1 forecasts queue length, waiting time, and congestion 30 minutes ahead with XGBoost, chosen on a time-ordered validation set and checked once on a later test block. The table is a simulated 15-minute grid for five Sri Lankan place names, not a live charger feed.

Open:

- `README.md` lines 1–20
- `src/config.py` lines 5–9 (seed 42 and the CSV path) and lines 16–18 (15-minute samples, 30-minute horizon)
- `src/inspect_data.py` lines 53–60 (why the table is labelled a simulation)

## 2. The data, and what you must not claim

- 57,590 rows. Five stations, each with 11,518 rows.
- Every 15 minutes from 1 January 2025 00:00 to 30 April 2025 23:15. No missing cells.
- Queue length never goes above 12 vehicles. The training-set median queue is 12 (`reports/training_summary.json` line 59).
- Waiting time is capped at 180 minutes. The column is `estimated_waiting_time_now_min`. It is not a stopwatch from arrival to the start of charging.
- Congestion is High on 57,135 of 57,590 rows. Medium is 274. Low is 181. Those labels follow the queue and wait in the generated table. They are not a separate congestion survey.

The CSV also contains pre-computed future columns. They are not model inputs:

- `target_queue_length_30min`
- `target_waiting_time_30min_min`
- `target_congestion_level_30min`

The queue target used for training is rebuilt from the observed queue 30 minutes later. The CSV’s own queue target matched `queue_after_current_arrivals` at t+30, which is a different definition. Code: `src/prepare_data.py` `reconstruct_target` at line 44. The finding is written by `src/inspect_data.py` around lines 161–167.

`index` and `station_name` are not features. `station_name` is constant for each `station_id`.

## 3. How a row becomes a training example

Open `src/prepare_data.py`.

1. Parse `timestamp`. An invalid time aborts the run (lines 38–40).
2. For each station, set the target to that station’s queue exactly 30 minutes later (lines 44–77). The last two snapshots of each station have no future row. They are dropped, never filled with zero. That is 10 rows (`reports/training_summary.json`, `dropped_no_target`).
3. Build lags from past rows of that station only (`add_lag_rolling_features`, line 88): queue lag 1, 2, and 4 steps (15, 30, and 60 minutes), rolling mean of 4 and 8, rolling standard deviation of 4, the change from the previous queue, and the same idea for arrivals. Waiting-time and congestion models add wait lags. See `src/config.py` lines 72–123.
4. Drop the warm-up rows whose lags are still empty (20 rows).
5. Split by calendar date, not by shuffling rows (`chronological_date_split`, line 113). All five stations stay together on each date, so one station’s future cannot leak into another station’s past.

| Block | Dates | Days | Rows |
|---|---|---|---|
| Train 70% | 1 Jan 2025 – 25 Mar 2025 | 84 | 40,300 |
| Validation 15% | 26 Mar 2025 – 12 Apr 2025 | 18 | 8,640 |
| Test 15% | 13 Apr 2025 – 30 Apr 2025 | 18 | 8,620 |

The three date ranges do not overlap (`reports/training_summary.json` lines 71–73). Seed 42 is the model `random_state` only. It does not shuffle the dates. Fractions are `src/config.py` lines 22–24.

Features known at prediction time are listed in `reports/training_summary.json` lines 80–116: clock and calendar fields, weather, traffic, arrivals, the queue now, charger counts and power, utilization, the wait and congestion now, station id, and the lags above. The future target columns are excluded. Documented in `src/prepare_data.py` `write_feature_docs` at line 158.

## 4. Why XGBoost was selected

The same four candidates are trained for queue and waiting time. Congestion uses three, because the target is a class.

| Candidate | What it predicts | Queue / wait rule | Congestion rule |
|---|---|---|---|
| Persistence | “Same as now” | Lowest validation MAE | Not used |
| Historical median | The training-set median | Lowest validation MAE | Not used |
| Most frequent class | Always predict High | Not used | Highest validation macro-F1 |
| Random Forest | A tree ensemble | Lowest validation MAE | Highest validation macro-F1, with balanced class weights |
| XGBoost | A boosted tree ensemble | Lowest validation MAE | Highest validation macro-F1, with sample weights |

Selection code:

- Queue: `src/train_queue_model.py` line 214, `min` of validation MAE. The written rule is lines 276–277.
- Waiting time: `src/train_waiting_time_model.py` lines 267–268.
- Congestion: `src/train_congestion_model.py` line 237, `max` of validation macro-F1. The written rule is line 326.

The test block is not used to pick the winner. It is scored once after selection. That is the check an examiner will ask about.

All three winners are XGBoost with the same settings: 300 trees, max depth 6, learning rate 0.05, subsample 0.9, column sample 0.9. Random Forest was second and very close. Persistence was clearly worse. The median and the “always High” rule were worse still on the metric used for selection.

Why not accuracy for congestion: 8,575 of 8,620 test rows are already High. A model that always says High is about 99.5% accurate and scores macro-F1 0.33, because Low and Medium score zero. Macro-F1 averages the three classes, so a rare class still counts.

## 5. The numbers to memorise

Round these. Exact values are in the JSON files.

### Queue — `reports/test_metrics.json`

Validation MAE (lower is better), 8,640 rows, `reports/training_summary.json` lines 19–43:

| Method | Validation MAE (vehicles) |
|---|---|
| XGBoost | 0.431 |
| Random Forest | 0.432 |
| Persistence | 0.527 |
| Training median | 0.907 |

Test, 8,620 rows, lines 12–37 of `reports/test_metrics.json`:

| Method | Test MAE | RMSE | R² |
|---|---|---|---|
| XGBoost | 0.44 | 0.66 | 0.82 |
| Persistence | 0.56 | 0.95 | 0.64 |
| Training median | 0.98 | 1.85 | −0.38 |

Say: on average the queue forecast is wrong by about half a vehicle, and it beats “same as now” (0.56) and the median (0.98). R² 0.82 means the forecast tracks the ups and downs. It is not “82% accuracy.”

Per station the test MAE stays between about 0.42 and 0.48 (`reports/test_metrics.json` lines 39–69).

### Waiting time — `reports/waiting_time_test_metrics.json`

| Method | Validation MAE (minutes) | Test MAE (minutes) | Test R² |
|---|---|---|---|
| XGBoost | 14.4 | 14.8 | 0.58 |
| Random Forest | 14.6 | 15.0 | 0.57 |
| Persistence | 18.2 | 19.0 | 0.26 |
| Training median | 24.2 | 24.3 | about 0 |

Say: the typical error is about 15 minutes, against a “same as now” error of 19 minutes. R² 0.58 is only moderate. Do not call this a precise minute-by-minute prediction.

### Congestion — `reports/congestion_test_metrics.json`

Validation macro-F1 (`reports/congestion_training_summary.json`):

| Method | Accuracy | Macro-F1 |
|---|---|---|
| XGBoost | 0.994 | 0.740 |
| Random Forest | 0.994 | 0.736 |
| Always High | 0.992 | 0.332 |

Test (`reports/congestion_test_metrics.json` lines 15–41):

| Class | Test rows | XGBoost F1 |
|---|---|---|
| Low | 17 | 0.81 |
| Medium | 28 | 0.32 |
| High | 8,575 | 1.00 |
| All three, macro-F1 | 8,620 | 0.71 |
| Accuracy | 8,620 | 0.995 |

Say: accuracy is 99.5% because almost every row is High. The selection score is macro-F1 0.71. Medium is weak, and there are only 28 Medium rows in the test block.

## 6. How a forecast is made

Saved files:

- `models/best_model.joblib` and `models/best_model_meta.joblib`
- `models/waiting_time_best_model.joblib`
- `models/congestion_best_model.joblib`

`src/predict_queue.py` `load_model` (line 25) loads the pipeline. A prediction must supply every feature in `feature_columns()`. A missing feature raises an error. It is not filled with zero (`_validate_record`, line 33).

The API looks up a historical snapshot with the same weekday, hour, and 15-minute slot (`api/station_data.py` `find_snapshot_for_station`, line 110), then runs all three models. The note on that function says the match is a synthetic snapshot for the clock pattern, not a live reading (lines 114–117 and 171–173).

In the phone recommendation, a Component 4 charger gets this forecast only when it is the named town or within 15 km of Nugegoda, Rajagiriya, Malabe, Pannipitiya, or Panadura. The listing’s own queue stays null. Code: `integration/area_models.py` and `integration/orchestrate.py` `_queue_block`. Far chargers stay blank.

## 7. How it was validated

1. Data checks before training. `src/inspect_data.py` `inspect_dataset` (line 53) counts missing values, duplicate station-times, the 15-minute gap, and whether a 30-minute target can be rebuilt. Training stops if that check fails (`run_pipeline.py` lines 50–53).
2. No shuffle. Dates move forward only (`src/prepare_data.py` lines 113–130).
3. Baselines. Persistence and the training median (queue and wait), or the most frequent class (congestion), are fit on the training block and scored on validation. A boosted tree is kept only when it beats those simple rules on the selection metric.
4. Selection on validation, one look at the test set. The evaluators write `reports/test_metrics.json`, `reports/waiting_time_test_metrics.json`, and `reports/congestion_test_metrics.json`.
5. By station and by peak hours. Peak hours are 7–9 and 17–21 (`src/config.py` `PEAK_HOURS`). Queue error is reported for each station so one station cannot hide inside the average.
6. Unit tests. `tests/test_pipeline.py`, `tests/test_waiting_time_model.py`, and `tests/test_congestion_model.py` check that the target is exactly two steps ahead on the same station, and that one station’s lags do not use another station’s rows.

Rebuild commands, from the folder `EV-Queue-Prediction`:

```powershell
python run_pipeline.py
python run_waiting_time_pipeline.py
python run_congestion_pipeline.py
```

## 8. Practice questions

**1. What are the three tasks, and how far ahead?**

30 minutes. Queue length in vehicles, waiting time in minutes, congestion in Low / Medium / High. Horizon: `src/config.py` lines 16–18.

**2. Why XGBoost and not Random Forest?**

On the validation block it had the lowest MAE for queue (0.431 against 0.432) and for waiting time (14.4 against 14.6 minutes), and the highest macro-F1 for congestion (0.740 against 0.736). The test set was not used to choose. Code: `src/train_queue_model.py` line 214.

**3. Why not report congestion accuracy as the result?**

Always predicting High is already about 99.5% accurate and has macro-F1 0.33. The chosen score is macro-F1 0.71. Medium’s test F1 is 0.32 on 28 rows. File: `reports/congestion_test_metrics.json` lines 15–41.

**4. What does MAE mean here?**

Mean absolute error. For the queue, 0.44 means the average miss on the test block is 0.44 vehicles. For waiting time, 14.8 means 14.8 minutes. It is not a percentage.

**5. What does R² 0.82 not mean?**

It does not mean 82% of queues were exactly right. It means the forecast explains about 82% of the variation around the mean queue, on this simulated test block. The interpretation string is `reports/test_metrics.json` line 24.

**6. Why is the split by date?**

The rows are a time series. A random split would put a later snapshot into training and an earlier one into testing, which leaks the future. `src/prepare_data.py` lines 113–130. Train ends 25 March 2025. Test starts 13 April 2025.

**7. Which columns are forbidden as inputs?**

The three `target_*` columns, because they are the future. Also `index` and `station_name`. List: `src/config.py` lines 33–37, and `src/prepare_data.py` lines 162–171.

**8. Is this a real queue measured in Nugegoda?**

No. The place names are Sri Lankan. The rows are a complete generated 15-minute grid, with estimated waits and a queue that never exceeds 12. `README.md` lines 12–20 and `src/inspect_data.py` lines 53–60.

**9. How does the phone get a number?**

The API matches the clock to a saved snapshot for ST01–ST05 (`api/station_data.py` line 110) and runs the three saved models. A Component 4 charger shows that forecast only when it is near one of those five towns (`integration/area_models.py`). The charger’s own queue cell stays empty.

**10. What will you say if the examiner asks for live accuracy?**

These scores are on the held-out simulated days 13–30 April 2025. They are not an accuracy measured at a real charger, because the CSV has no field log of arrivals or charge starts.

## 9. Files, in the order to open them

1. `README.md` lines 1–20 — the label and the three tasks.
2. `src/config.py` lines 5–37 and 72–123 — horizon, split, forbidden columns, lags.
3. `src/prepare_data.py` lines 44–77 and 113–130 — target and date split.
4. `src/train_queue_model.py` lines 66–228 and 276–277 — the four candidates and the MAE rule.
5. `src/train_congestion_model.py` lines 89–140 and 326 — why macro-F1, not accuracy.
6. `reports/training_summary.json` lines 1–73 — who won on validation, and the dates.
7. `reports/test_metrics.json` lines 12–69 — queue test error.
8. `reports/waiting_time_test_metrics.json` lines 15–32 — wait test error.
9. `reports/congestion_test_metrics.json` lines 15–41 — the class counts behind the 99.5% accuracy.
10. `api/station_data.py` lines 110–173 — the forecast is a matched snapshot, not a live sensor.
