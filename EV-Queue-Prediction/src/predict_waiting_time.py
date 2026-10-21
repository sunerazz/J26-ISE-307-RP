"""Reusable prediction interface for 30-minute-ahead waiting time (Model 2)."""

from __future__ import annotations

from typing import Any, Mapping

import joblib
import numpy as np
import pandas as pd

from src.config import (
    FORECAST_HORIZON_MINUTES,
    MODELS_DIR,
    PROJECT_ROOT,
    STATION_COL,
    TIMESTAMP_COL,
    WAIT_COL,
    WAITING_MODEL_VERSION,
)
from src.prepare_waiting_time_data import waiting_feature_columns


REQUIRED_FEATURES = waiting_feature_columns()


def load_waiting_time_model(model_path=None, meta_path=None):
    model_path = model_path or (MODELS_DIR / "waiting_time_best_model.joblib")
    meta_path = meta_path or (MODELS_DIR / "waiting_time_best_model_meta.joblib")
    return joblib.load(model_path), joblib.load(meta_path)


def _validate_record(
    record: Mapping[str, Any],
    predictor_kind: str,
) -> tuple[pd.DataFrame, pd.Timestamp | None]:
    forbidden = [
        "target_waiting_time_30min_min",
        "target_queue_length_30min",
        "target_congestion_level_30min",
        "y_true",
        "future_waiting_time",
    ]
    present_forbidden = [c for c in forbidden if c in record]
    if present_forbidden:
        raise ValueError(
            "Future/target fields must not be supplied to the predictor: "
            + ", ".join(present_forbidden)
        )

    if predictor_kind == "persistence":
        if WAIT_COL not in record:
            raise ValueError(
                f"Persistence predictor requires '{WAIT_COL}' at prediction time."
            )
        try:
            wait_val = float(pd.to_numeric(record[WAIT_COL], errors="raise"))
        except Exception as exc:
            raise TypeError(
                f"Feature '{WAIT_COL}' must be numeric; got {record[WAIT_COL]!r}"
            ) from exc
        if wait_val < 0:
            raise ValueError(f"'{WAIT_COL}' cannot be negative.")
        df = pd.DataFrame([{WAIT_COL: wait_val}])
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

    ts = (
        pd.to_datetime(record[TIMESTAMP_COL], errors="raise")
        if TIMESTAMP_COL in record
        else None
    )
    return df, ts


def _score(artifact, meta: dict, X: pd.DataFrame) -> float:
    kind = meta.get("predictor_kind", "sklearn_pipeline")
    if kind == "sklearn_pipeline":
        return float(artifact.predict(X)[0])
    if kind == "persistence":
        return float(X.iloc[0][WAIT_COL])
    if kind == "historical_median":
        return float(artifact["median"])
    raise ValueError(f"Unknown predictor_kind: {kind}")


def predict_waiting_time(
    record: Mapping[str, Any],
    model=None,
    meta: dict | None = None,
    clip_non_negative: bool = True,
    round_for_display: bool = False,
) -> dict:
    """Predict station waiting time (minutes) 30 minutes ahead.

    Returns station_id, prediction_timestamp, forecast_timestamp,
    predicted_waiting_time_min, model_name, and model_version.
    """
    if model is None or meta is None:
        loaded_model, loaded_meta = load_waiting_time_model()
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

    if ts is None:
        prediction_timestamp = None
        forecast_timestamp = None
    else:
        prediction_timestamp = ts.isoformat(sep=" ")
        forecast_timestamp = (
            ts + pd.Timedelta(minutes=FORECAST_HORIZON_MINUTES)
        ).isoformat(sep=" ")

    return {
        "station_id": record.get(STATION_COL),
        "prediction_timestamp": prediction_timestamp,
        "forecast_timestamp": forecast_timestamp,
        "predicted_waiting_time_min": value,
        "raw_prediction_min": raw,
        "forecast_horizon_minutes": FORECAST_HORIZON_MINUTES,
        "model_name": meta.get("model_name"),
        "model_version": meta.get("model_version", WAITING_MODEL_VERSION),
        "unit": "minutes",
    }


def predict_from_processed_row(row: pd.Series, **kwargs) -> dict:
    record = row.to_dict()
    for key in (
        "target_waiting_time_30min_min",
        "target_queue_length_30min",
        "target_congestion_level_30min",
        "y_pred",
        "error",
        "abs_error",
        "forecast_timestamp",
    ):
        record.pop(key, None)
    return predict_waiting_time(record, **kwargs)


def main() -> None:
    test_path = (
        PROJECT_ROOT / "data" / "processed" / "waiting_time" / "test.csv"
    )
    if not test_path.exists():
        raise SystemExit(
            "Processed waiting_time/test.csv not found. Run prepare + train first."
        )
    test = pd.read_csv(test_path, parse_dates=[TIMESTAMP_COL])
    print(predict_from_processed_row(test.iloc[0]))


if __name__ == "__main__":
    import sys

    sys.path.insert(0, str(PROJECT_ROOT))
    main()
