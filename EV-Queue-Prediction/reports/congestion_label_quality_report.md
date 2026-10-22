# Congestion Label Quality Report (Model 3)

**Experiment label:** SIMULATION-BASED

- Allowed classes: ['Low', 'Medium', 'High']
- Source column: `congestion_level_now`
- Future target: `target_congestion_level_30min` reconstructed as `congestion_level_now` at t+30 (exact match).
- CSV pre-computed future congestion matched reconstructed labels at 100% on valid pairs in inspection.
- Unmatched end-of-series rows: 10
- Missing current congestion values: none in raw CSV inspection.
- Labels treated as synthetic/rule-derived station categories.

## Class counts after preparation

```json
{
  "train": {
    "High": 39990,
    "Medium": 194,
    "Low": 116
  },
  "val": {
    "High": 8567,
    "Medium": 51,
    "Low": 22
  },
  "test": {
    "High": 8575,
    "Medium": 28,
    "Low": 17
  }
}
```

## Limitation

Predicting these labels evaluates foresight of the synthetic congestion categories; it does not establish independent real-world congestion sensing accuracy.
