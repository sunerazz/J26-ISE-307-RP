# Dataset Quality Report

**Experiment label:** SIMULATION-BASED (synthetic dataset)

- Source: `C:\Users\Charuka\Desktop\thanuka resarch\system\EV-Queue-Prediction\data\raw\component1_ev_queue_prediction_synthetic.csv`
- Rows: 69108
- Columns: 29
- Stations: ['ST01', 'ST02', 'ST03', 'ST04', 'ST05', 'ST06']
- Coverage: 2025-01-01 00:00:00 → 2025-04-30 23:15:00 (120 unique dates)
- Missing values: 0
- Duplicate rows: 0
- Duplicate station-timestamp: 0
- Invalid timestamps: 0
- Negative numeric values: none
- Sampling interval: 15 minutes (regular grid)
- Valid reconstructed 30-min targets: 69096
- Rows without future observation: 12

## Target definition finding

The CSV column target_queue_length_30min matches queue_after_current_arrivals at t+30 minutes, not current_queue_length at t+30. For this experiment the modelling target is reconstructed as current_queue_length at the same station exactly 30 minutes later.

- Match rate vs `current_queue_length@t+30`: 0.6274169271737872
- Match rate vs `queue_after_current_arrivals@t+30`: 1.0

## Supports prediction task?

**True** — timestamped queue snapshots exist; a same-station +30 minute target can be reconstructed without fabricating labels.

## Limitations

- Dataset is synthetic/simulated; results do not demonstrate real-world deployment accuracy.
- No raw vehicle arrival / charging-start / cancellation event log is present.
- Station ST05 exhibits extreme queue lengths (median >> other stations), consistent with a synthetic runaway process.
- This component predicts queue length only, not waiting time or congestion.
- Last two snapshots per station lack a verifiable 30-minute-ahead observation and are excluded from modelling.
