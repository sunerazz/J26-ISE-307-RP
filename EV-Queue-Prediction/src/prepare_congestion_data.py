"""Prepare Model 3 modelling table for 30-minute-ahead congestion classification.

Does not modify Model 1/2 processed CSVs. Writes under data/processed/congestion/.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.config import (
    CATEGORICAL_BASE_FEATURES,
    CONGESTION_CLASSES,
    CONGESTION_COL,
    CONGESTION_ENGINEERED_FEATURES,
    CONGESTION_PROCESSED_DIR,
    CONGESTION_TARGET_COL,
    FORECAST_HORIZON_MINUTES,
    FORECAST_STEPS,
    NUMERIC_BASE_FEATURES,
    PROJECT_ROOT,
    QUEUE_COL,
    RAW_DATA_PATH,
    REPORTS_DIR,
    STATION_COL,
    TIMESTAMP_COL,
    WAIT_COL,
)
from src.prepare_data import chronological_date_split, load_raw
from src.prepare_waiting_time_data import add_waiting_lag_features


ALLOWED_CLASSES = set(CONGESTION_CLASSES)


def reconstruct_congestion_target(df: pd.DataFrame) -> pd.DataFrame:
    """target_congestion_level_30min = congestion_level_now at same station t+30.

    Exact timestamp match only. Unmatched rows become NaN — never filled as 'Low'.
    """
    if CONGESTION_COL not in df.columns:
        raise ValueError(
            f"Missing '{CONGESTION_COL}'. Cannot construct a future congestion target."
        )

    invalid = set(df[CONGESTION_COL].dropna().unique()) - ALLOWED_CLASSES
    if invalid:
        raise ValueError(f"Unexpected congestion labels: {sorted(invalid)}")

    parts = []
    unmatched = 0
    for station_id, group in df.groupby(STATION_COL, sort=False):
        g = group.sort_values(TIMESTAMP_COL).copy()
        future_ts = g[TIMESTAMP_COL] + pd.Timedelta(minutes=FORECAST_HORIZON_MINUTES)
        future_cong = g.set_index(TIMESTAMP_COL)[CONGESTION_COL]
        g[CONGESTION_TARGET_COL] = future_ts.map(future_cong)

        shift_target = g[CONGESTION_COL].shift(-FORECAST_STEPS)
        shift_delta = (
            g[TIMESTAMP_COL].shift(-FORECAST_STEPS) - g[TIMESTAMP_COL]
        ).dt.total_seconds() / 60.0
        exact = shift_delta == FORECAST_HORIZON_MINUTES
        disagree = (
            g[CONGESTION_TARGET_COL].notna()
            & exact
            & (g[CONGESTION_TARGET_COL] != shift_target)
        )
        if disagree.any():
            raise ValueError(
                f"Congestion target reconstruction disagreement for {station_id}"
            )
        unmatched += int(g[CONGESTION_TARGET_COL].isna().sum())
        parts.append(g)

    out = pd.concat(parts, ignore_index=True)
    out.attrs["unmatched_target_rows"] = unmatched
    return out


def congestion_feature_columns() -> list[str]:
    # congestion_level_now is categorical and already in CATEGORICAL_BASE_FEATURES
    return NUMERIC_BASE_FEATURES + CATEGORICAL_BASE_FEATURES + CONGESTION_ENGINEERED_FEATURES


def _class_counts(series: pd.Series) -> dict:
    counts = series.value_counts(dropna=False).to_dict()
    return {str(k): int(v) for k, v in counts.items()}


def write_congestion_docs(unmatched: int, split_meta: dict) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    md = [
        "# Congestion Feature and Target Definitions (Model 3)",
        "",
        "## Experiment label",
        "",
        "**SIMULATION-BASED** — synthetic EV charging snapshot dataset.",
        "",
        "## Congestion-label provenance",
        "",
        f"- Column `{CONGESTION_COL}` provides station-level categories "
        f"`{', '.join(CONGESTION_CLASSES)}`.",
        "- Labels are **synthetic / rule-derived** (strongly associated with "
        f"`{WAIT_COL}` and queue/utilization state), not independently observed "
        "real-world congestion audits.",
        "- Approximate heuristic association (for interpretation only; not used to "
        "overwrite labels): wait≈0 → Low; short waits → Medium; long waits → High "
        "(~95% agreement with a simple wait threshold; residual cases involve "
        "medium/high boundary ambiguity).",
        "- The modelling target is reconstructed by temporal alignment of the "
        "existing snapshot labels, not by inventing new categories.",
        "",
        "## Target",
        "",
        f"- Name: `{CONGESTION_TARGET_COL}`",
        f"- Definition: `{CONGESTION_COL}` at the **same** `{STATION_COL}` exactly "
        f"**{FORECAST_HORIZON_MINUTES} minutes** later.",
        "- Construction: exact timestamp match (`t + 30 min`).",
        f"- Unmatched rows dropped (never filled as Low): **{unmatched}**.",
        f"- Current `{CONGESTION_COL}` is an input feature, not the future target.",
        "- Future queue and future waiting-time values are **not** used as labels "
        "or features.",
        "",
        "## Selected features (known at prediction time)",
        "",
    ]
    for col in congestion_feature_columns():
        md.append(f"- `{col}`")
    md.extend(
        [
            "",
            "## Excluded inputs",
            "",
            f"- `{CONGESTION_TARGET_COL}` (future label)",
            "- `target_queue_length_30min` (future queue; Model 1)",
            "- `target_waiting_time_30min_min` (future wait; Model 2)",
            "- Any features computed from the future congestion label",
            "",
            "## Leakage note for rule-derived labels",
            "",
            "Because congestion is closely related to wait/queue, current wait and "
            "queue are valid contemporaneous features, but **future** wait/queue "
            "must never enter the feature matrix.",
            "",
            "## Cleaning",
            "",
            "1. Parse timestamps; abort if invalid.",
            "2. Validate allowed class names.",
            "3. Reconstruct future congestion from same-station label@t+30.",
            "4. Drop unmatched future rows (no silent Low imputation).",
            "5. Engineer per-station past-only lag/rolling features.",
            "6. Drop lag warm-up NaNs.",
            "7. Chronological date split 70/15/15 (same policy as Models 1–2).",
            "8. No SMOTE on this time-series classification task.",
            "",
            "## Chronological split",
            "",
            "```json",
            json.dumps(split_meta, indent=2, default=str),
            "```",
            "",
        ]
    )
    (REPORTS_DIR / "congestion_feature_target_definitions.md").write_text(
        "\n".join(md), encoding="utf-8"
    )
    (REPORTS_DIR / "congestion_label_quality_report.md").write_text(
        "\n".join(
            [
                "# Congestion Label Quality Report (Model 3)",
                "",
                "**Experiment label:** SIMULATION-BASED",
                "",
                f"- Allowed classes: {list(CONGESTION_CLASSES)}",
                f"- Source column: `{CONGESTION_COL}`",
                f"- Future target: `{CONGESTION_TARGET_COL}` reconstructed as "
                f"`{CONGESTION_COL}` at t+30 (exact match).",
                "- CSV pre-computed future congestion matched reconstructed labels "
                "at 100% on valid pairs in inspection.",
                f"- Unmatched end-of-series rows: {unmatched}",
                "- Missing current congestion values: none in raw CSV inspection.",
                "- Labels treated as synthetic/rule-derived station categories.",
                "",
                "## Class counts after preparation",
                "",
                "```json",
                json.dumps(
                    {
                        "train": split_meta.get("class_counts_train"),
                        "val": split_meta.get("class_counts_val"),
                        "test": split_meta.get("class_counts_test"),
                    },
                    indent=2,
                ),
                "```",
                "",
                "## Limitation",
                "",
                "Predicting these labels evaluates foresight of the synthetic "
                "congestion categories; it does not establish independent "
                "real-world congestion sensing accuracy.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def prepare_congestion(
    raw_path: Path | None = None,
    save: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    df = load_raw(raw_path or RAW_DATA_PATH)

    if df.duplicated(subset=[STATION_COL, TIMESTAMP_COL]).any():
        raise ValueError("Duplicate station-timestamp records found.")

    for col in (
        "target_queue_length_30min",
        "target_waiting_time_30min_min",
        "target_congestion_level_30min",
    ):
        if col in df.columns:
            df = df.drop(columns=[col])

    df = reconstruct_congestion_target(df)
    unmatched = int(
        df.attrs.get("unmatched_target_rows", df[CONGESTION_TARGET_COL].isna().sum())
    )

    before = len(df)
    df = df[df[CONGESTION_TARGET_COL].notna()].copy()
    dropped_no_target = before - len(df)

    bad = set(df[CONGESTION_TARGET_COL].unique()) - ALLOWED_CLASSES
    if bad:
        raise ValueError(f"Unexpected future congestion labels: {sorted(bad)}")

    # Reuse Model 2 lag engineering (queue/arrivals/wait); does not create future labels
    df = add_waiting_lag_features(df)
    before_warm = len(df)
    df = df.dropna(subset=CONGESTION_ENGINEERED_FEATURES).copy()
    dropped_warmup = before_warm - len(df)

    train, val, test, split_meta = chronological_date_split(df)
    split_meta.update(
        {
            "task": "congestion_30min",
            "congestion_column": CONGESTION_COL,
            "target_column": CONGESTION_TARGET_COL,
            "allowed_classes": list(CONGESTION_CLASSES),
            "label_provenance": "synthetic_rule_derived_station_snapshots",
            "dropped_no_target": int(dropped_no_target),
            "dropped_lag_warmup": int(dropped_warmup),
            "unmatched_target_rows": unmatched,
            "n_train_rows": int(len(train)),
            "n_val_rows": int(len(val)),
            "n_test_rows": int(len(test)),
            "feature_columns": congestion_feature_columns(),
            "class_counts_train": _class_counts(train[CONGESTION_TARGET_COL]),
            "class_counts_val": _class_counts(val[CONGESTION_TARGET_COL]),
            "class_counts_test": _class_counts(test[CONGESTION_TARGET_COL]),
            "queue_available_at_prediction_time": QUEUE_COL in df.columns,
            "wait_available_at_prediction_time": WAIT_COL in df.columns,
        }
    )
    write_congestion_docs(unmatched=unmatched, split_meta=split_meta)

    if save:
        CONGESTION_PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        train.to_csv(CONGESTION_PROCESSED_DIR / "train.csv", index=False)
        val.to_csv(CONGESTION_PROCESSED_DIR / "val.csv", index=False)
        test.to_csv(CONGESTION_PROCESSED_DIR / "test.csv", index=False)
        df.to_csv(CONGESTION_PROCESSED_DIR / "modelling_table.csv", index=False)
        with open(
            CONGESTION_PROCESSED_DIR / "split_meta.json", "w", encoding="utf-8"
        ) as f:
            json.dump(split_meta, f, indent=2, default=str)

    return train, val, test, split_meta


def main() -> None:
    train, val, test, meta = prepare_congestion(save=True)
    print(
        json.dumps(
            {
                "n_train": len(train),
                "n_val": len(val),
                "n_test": len(test),
                "class_counts_train": meta["class_counts_train"],
                "class_counts_val": meta["class_counts_val"],
                "class_counts_test": meta["class_counts_test"],
                "overlaps": {
                    "train_val": meta["overlap_train_val"],
                    "train_test": meta["overlap_train_test"],
                    "val_test": meta["overlap_val_test"],
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    import sys

    sys.path.insert(0, str(PROJECT_ROOT))
    main()
