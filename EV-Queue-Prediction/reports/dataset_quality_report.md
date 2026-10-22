# Dataset Quality Report

**Experiment label:** SIMULATION-BASED (named Sri Lankan stations)

- Source: `C:\Users\Charuka\Desktop\thanuka resarch\system\EV-Queue-Prediction\data\raw\component1_ev_queue_prediction_sri_lanka.csv`
- Rows: 57590
- Columns: 31
- Stations: ['ST01', 'ST02', 'ST03', 'ST04', 'ST05']
- Coverage: 2025-01-01 00:00:00 → 2025-04-30 23:15:00 (120 unique dates)
- Missing values: 0
- Duplicate rows: 0
- Duplicate station-timestamp: 0
- Invalid timestamps: 0
- Negative numeric values: none
- Sampling interval: 15 minutes (regular grid)
- Valid reconstructed 30-min targets: 57580
- Rows without future observation: 10

## Target definition finding

The CSV column target_queue_length_30min matches queue_after_current_arrivals at t+30 minutes, not current_queue_length at t+30. For this experiment the modelling target is reconstructed as current_queue_length at the same station exactly 30 minutes later.

- Match rate vs `current_queue_length@t+30`: 0.22742271622091004
- Match rate vs `queue_after_current_arrivals@t+30`: 0.20805835359499827

## Supports prediction task?

**True** — timestamped queue snapshots exist; a same-station +30 minute target can be reconstructed without fabricating labels.

## Limitations

- Station identities are Sri Lankan places. The 15-minute queue, wait and congestion values are generated snapshots, not observed charger logs.
- No raw vehicle arrival / charging-start / cancellation event log is present.
- Queue length in this file does not exceed 12 vehicles at any station.
- congestion_level_now is High on nearly every row, so accuracy alone is not a useful congestion score.
- Last two snapshots per station lack a verifiable 30-minute-ahead observation and are excluded from modelling.
