# Congestion Label Quality Report (Model 3)

**Experiment label:** SIMULATION-BASED

- Allowed classes: ['Low', 'Medium', 'High']
- Source column: `congestion_level_now`
- Future target: `target_congestion_level_30min` reconstructed as `congestion_level_now` at t+30 (exact match).
- CSV pre-computed future congestion matched reconstructed labels at 100% on valid pairs in inspection.
- Unmatched end-of-series rows: 12
- Missing current congestion values: none in raw CSV inspection.
- Labels treated as synthetic/rule-derived station categories.

## Class counts after preparation

```json
{
  "train": {
    "High": 21595,
    "Low": 20489,
    "Medium": 6276
  },
  "val": {
    "High": 4590,
    "Low": 4464,
    "Medium": 1314
  },
  "test": {
    "High": 4531,
    "Low": 4514,
    "Medium": 1299
  }
}
```

## Limitation

Predicting these labels evaluates foresight of the synthetic congestion categories; it does not establish independent real-world congestion sensing accuracy.
