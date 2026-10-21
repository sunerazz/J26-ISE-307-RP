"""Reusable prediction interface for 30-minute-ahead congestion (Model 3)."""

from __future__ import annotations

from typing import Any, Mapping

import joblib
import numpy as np
import pandas as pd

from src.config import (
    CONGESTION_CLASSES,
    CONGESTION_MODEL_VERSION,
    FORECAST_HORIZON_MINUTES,
    MODELS_DIR,
    PROJECT_ROOT,
    STATION_COL,
    TIMESTAMP_COL,
)
from src.prepare_congestion_data import congestion_feature_columns

REQUIRED_FEATURES = congestion_feature_columns()
CLASS_ORDER = list(CONGESTION_CLASSES)


def load_congestion_model(model_path=None, meta_path=None):
    model_path = model_path or (MODELS_DIR / "congestion_best_model.joblib")
    meta_path = meta_path or (MODELS_DIR / "congestion_best_model_meta.joblib")
    return joblib.load(model_path), joblib.load(meta_path)


def _validate_record(
    record: Mapping[str, Any],
    predictor_kind: str,
) -> tuple[pd.DataFrame, pd.Timestamp | None]:
    forbidden = [
        "target_congestion_level_30min",
        "target_queue_length_30min",
        "target_waiting_time_30min_min",
        "y_true",
        "future_congestion",
    ]
    present_forbidden = [c for c in forbidden if c in record]
    if present_forbidden:
        raise ValueError(
            "Future/target fields must not be supplied to the predictor: "
            + ", ".join(present_forbidden)
        )

    if predictor_kind == "most_frequent":
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
        if "congestion_level_now" in df.columns:
            val = str(df.iloc[0]["congestion_level_now"])
            if val not in CLASS_ORDER:
                raise ValueError(
                    f"Invalid congestion_level_now '{val}'. "
                    f"Allowed: {CLASS_ORDER}"
                )
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


def _decode_label(raw, meta: dict) -> str:
    if meta.get("label_encoding") == "integer_via_CLASS_ORDER":
        idx_to_class = {int(k): v for k, v in meta["idx_to_class"].items()}
        return str(idx_to_class[int(raw)])
    return str(raw)


def _class_probabilities(artifact, meta: dict, X: pd.DataFrame) -> dict | None:
    if meta.get("predictor_kind") == "most_frequent":
        maj = str(artifact["class"])
        return {c: (1.0 if c == maj else 0.0) for c in CLASS_ORDER}
    if not hasattr(artifact, "predict_proba"):
        return None
    try:
        proba = artifact.predict_proba(X)[0]
    except Exception:
        return None
    if meta.get("label_encoding") == "integer_via_CLASS_ORDER":
        return {CLASS_ORDER[i]: float(proba[i]) for i in range(len(CLASS_ORDER))}
    model = artifact.named_steps.get("model", artifact)
    classes = list(getattr(model, "classes_", CLASS_ORDER))
    out = {c: 0.0 for c in CLASS_ORDER}
    for j, cls in enumerate(classes):
        if cls in out:
            out[str(cls)] = float(proba[j])
    return out


def predict_congestion(
    record: Mapping[str, Any],
    model=None,
    meta: dict | None = None,
) -> dict:
    """Predict congestion class (Low/Medium/High) 30 minutes ahead."""
    if model is None or meta is None:
        loaded_model, loaded_meta = load_congestion_model()
        model = loaded_model if model is None else model
        meta = loaded_meta if meta is None else meta

    kind = meta.get("predictor_kind", "sklearn_pipeline")
    X, ts = _validate_record(record, predictor_kind=kind)

    if kind == "most_frequent":
        pred = str(model["class"])
    else:
        raw = model.predict(X)[0]
        pred = _decode_label(raw, meta)

    if pred not in CLASS_ORDER:
        raise ValueError(f"Model returned invalid class '{pred}'")

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
        "predicted_congestion_level": pred,
        "class_probabilities": _class_probabilities(model, meta, X),
        "forecast_horizon_minutes": FORECAST_HORIZON_MINUTES,
        "model_name": meta.get("model_name"),
        "model_version": meta.get("model_version", CONGESTION_MODEL_VERSION),
        "allowed_classes": CLASS_ORDER,
    }


def predict_from_processed_row(row: pd.Series, **kwargs) -> dict:
    record = row.to_dict()
    for key in (
        "target_congestion_level_30min",
        "target_queue_length_30min",
        "target_waiting_time_30min_min",
        "y_pred",
        "forecast_timestamp",
    ):
        record.pop(key, None)
    return predict_congestion(record, **kwargs)


def main() -> None:
    test_path = PROJECT_ROOT / "data" / "processed" / "congestion" / "test.csv"
    if not test_path.exists():
        raise SystemExit(
            "Processed congestion/test.csv not found. Run prepare + train first."
        )
    test = pd.read_csv(test_path, parse_dates=[TIMESTAMP_COL])
    print(predict_from_processed_row(test.iloc[0]))


if __name__ == "__main__":
    import sys

    sys.path.insert(0, str(PROJECT_ROOT))
    main()
