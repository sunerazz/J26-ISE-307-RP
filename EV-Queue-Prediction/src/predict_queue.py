"""Reusable prediction interface for 30-minute-ahead queue length."""

from __future__ import annotations

from typing import Any, Mapping

import joblib
import numpy as np
import pandas as pd

from src.config import (
    FORECAST_HORIZON_MINUTES,
    MODELS_DIR,
    PROJECT_ROOT,
    QUEUE_COL,
    STATION_COL,
    TIMESTAMP_COL,
)
from src.prepare_data import feature_columns


REQUIRED_FEATURES = feature_columns()


def load_model(model_path=None, meta_path=None):
    model_path = model_path or (MODELS_DIR / "best_model.joblib")
    meta_path = meta_path or (MODELS_DIR / "best_model_meta.joblib")
    artifact = joblib.load(model_path)
    meta = joblib.load(meta_path)
    return artifact, meta


def _validate_record(
    record: Mapping[str, Any],
    predictor_kind: str,
) -> tuple[pd.DataFrame, pd.Timestamp | None]:
    if predictor_kind == "persistence":
        if QUEUE_COL not in record:
            raise ValueError(
                f"Persistence predictor requires '{QUEUE_COL}' at prediction time."
            )
        try:
            queue_val = float(pd.to_numeric(record[QUEUE_COL], errors="raise"))
        except Exception as exc:
            raise TypeError(
                f"Feature '{QUEUE_COL}' must be numeric; got {record[QUEUE_COL]!r}"
            ) from exc
        df = pd.DataFrame([{QUEUE_COL: queue_val}])
    elif predictor_kind == "historical_median":
        df = pd.DataFrame([{}])
    else:
        missing = [c for c in REQUIRED_FEATURES if c not in record]
        if missing:
            raise ValueError(
                "Missing required features available at prediction time: "
                + ", ".join(missing)
            )
        row = {c: record[c] for c in REQUIRED_FEATURES}
        df = pd.DataFrame([row])
        numeric_like = [
            c
            for c in REQUIRED_FEATURES
            if c
            not in {
                "station_id",
                "location_type",
                "day_of_week",
                "time_slot",
                "weather_condition",
                "traffic_level",
                "congestion_level_now",
            }
        ]
        for c in numeric_like:
            try:
                df[c] = pd.to_numeric(df[c], errors="raise")
            except Exception as exc:
                raise TypeError(
                    f"Feature '{c}' must be numeric; got {record[c]!r}"
                ) from exc

    forbidden = [
        "target_queue_length_30min",
        "target_waiting_time_30min_min",
        "target_congestion_level_30min",
        "y_true",
        "future_queue",
    ]
    present_forbidden = [c for c in forbidden if c in record]
    if present_forbidden:
        raise ValueError(
            "Future/target fields must not be supplied to the predictor: "
            + ", ".join(present_forbidden)
        )

    if TIMESTAMP_COL in record:
        ts = pd.to_datetime(record[TIMESTAMP_COL], errors="raise")
    else:
        ts = None
    return df, ts


def _score(artifact, meta: dict, X: pd.DataFrame) -> float:
    kind = meta.get("predictor_kind", "sklearn_pipeline")
    if kind == "sklearn_pipeline":
        return float(artifact.predict(X)[0])
    if kind == "persistence":
        return float(X.iloc[0][QUEUE_COL])
    if kind == "historical_median":
        return float(artifact["median"])
    raise ValueError(f"Unknown predictor_kind: {kind}")


def predict_queue(
    record: Mapping[str, Any],
    model=None,
    meta: dict | None = None,
    clip_non_negative: bool = True,
    round_for_display: bool = False,
) -> dict:
    """Predict queue length 30 minutes ahead from a current feature record.

    Parameters
    ----------
    record:
        Mapping of features known at the prediction timestamp. For sklearn models,
        must include all columns from ``feature_columns()``. Persistence only needs
        ``current_queue_length``. Optional ``timestamp`` enriches the output.
    clip_non_negative:
        If True, clip continuous prediction at 0 for operational output.
    round_for_display:
        If True, round to nearest integer for display only.

    Returns
    -------
    dict with station_id, prediction_timestamp, forecast_timestamp,
    predicted_queue_length_30min, and raw_prediction.
    """
    if model is None or meta is None:
        loaded_model, loaded_meta = load_model()
        model = loaded_model if model is None else model
        meta = loaded_meta if meta is None else meta

    kind = meta.get("predictor_kind", "sklearn_pipeline")
    X, ts = _validate_record(record, predictor_kind=kind)
    raw = _score(model, meta, X)
    value = raw
    if clip_non_negative:
        value = max(0.0, value)
    if round_for_display:
        value = float(int(np.rint(value)))

    station_id = record.get(STATION_COL)
    if ts is None:
        prediction_timestamp = None
        forecast_timestamp = None
    else:
        prediction_timestamp = ts.isoformat(sep=" ")
        forecast_timestamp = (
            ts + pd.Timedelta(minutes=FORECAST_HORIZON_MINUTES)
        ).isoformat(sep=" ")

    return {
        "station_id": station_id,
        "prediction_timestamp": prediction_timestamp,
        "forecast_timestamp": forecast_timestamp,
        "predicted_queue_length_30min": value,
        "raw_prediction": raw,
        "forecast_horizon_minutes": FORECAST_HORIZON_MINUTES,
        "model_name": meta.get("model_name"),
    }


def predict_from_processed_row(row: pd.Series, **kwargs) -> dict:
    record = row.to_dict()
    # Strip labels/future fields that exist in evaluation tables
    for key in (
        "target_queue_length_30min",
        "target_waiting_time_30min_min",
        "target_congestion_level_30min",
        "y_pred",
        "error",
        "abs_error",
        "forecast_timestamp",
    ):
        record.pop(key, None)
    return predict_queue(record, **kwargs)


def main() -> None:
    """Demo: score the first test row if available."""
    test_path = PROJECT_ROOT / "data" / "processed" / "test.csv"
    if not test_path.exists():
        raise SystemExit("Processed test.csv not found. Run prepare + train first.")
    test = pd.read_csv(test_path, parse_dates=[TIMESTAMP_COL])
    row = test.iloc[0]
    result = predict_from_processed_row(row, round_for_display=False)
    print(result)


if __name__ == "__main__":
    import sys

    sys.path.insert(0, str(PROJECT_ROOT))
    main()
