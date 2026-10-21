"""Train baselines, Random Forest, and XGBoost; select best model on validation."""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from src.config import (
    CATEGORICAL_BASE_FEATURES,
    ENGINEERED_FEATURES,
    MODELS_DIR,
    NUMERIC_BASE_FEATURES,
    PROCESSED_DIR,
    PROJECT_ROOT,
    QUEUE_COL,
    RANDOM_SEED,
    REPORTS_DIR,
    TARGET_COL,
)
from src.prepare_data import feature_columns, prepare

warnings.filterwarnings("ignore", category=UserWarning)


def regression_metrics(y_true, y_pred) -> dict:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    return {
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "rmse": float(np.sqrt(mean_squared_error(y_true, y_pred))),
        "r2": float(r2_score(y_true, y_pred)),
        "n": int(len(y_true)),
    }


def build_preprocessor(categorical: list[str], numeric: list[str]) -> ColumnTransformer:
    # Tree models do not need scaling; handle unknown categories safely.
    try:
        encoder = OneHotEncoder(handle_unknown="ignore", sparse_output=False)
    except TypeError:  # older sklearn
        encoder = OneHotEncoder(handle_unknown="ignore", sparse=False)
    return ColumnTransformer(
        transformers=[
            ("cat", encoder, categorical),
            ("num", "passthrough", numeric),
        ],
        remainder="drop",
    )


def get_xy(df: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray]:
    cols = feature_columns()
    return df[cols].copy(), df[TARGET_COL].to_numpy(dtype=float)


def train_persistence(train: pd.DataFrame, val: pd.DataFrame) -> dict:
    """Baseline 1: predict future queue = most recent known queue."""
    pred_val = val[QUEUE_COL].to_numpy(dtype=float)
    metrics = regression_metrics(val[TARGET_COL], pred_val)
    return {
        "name": "persistence",
        "val_metrics": metrics,
        "artifact": {"type": "persistence", "feature": QUEUE_COL},
    }


def train_historical_median(train: pd.DataFrame, val: pd.DataFrame) -> dict:
    """Baseline 2: constant training-set median target."""
    median = float(np.median(train[TARGET_COL].to_numpy(dtype=float)))
    pred_val = np.full(len(val), median, dtype=float)
    metrics = regression_metrics(val[TARGET_COL], pred_val)
    return {
        "name": "historical_median",
        "val_metrics": metrics,
        "artifact": {"type": "historical_median", "median": median},
        "median": median,
    }


def train_random_forest(
    train: pd.DataFrame, val: pd.DataFrame
) -> dict:
    X_train, y_train = get_xy(train)
    X_val, y_val = get_xy(val)
    cat = [c for c in CATEGORICAL_BASE_FEATURES if c in X_train.columns]
    num = [c for c in (NUMERIC_BASE_FEATURES + ENGINEERED_FEATURES) if c in X_train.columns]

    # Small validation-based hyperparameter search (reproducible)
    candidates = [
        {"n_estimators": 200, "max_depth": 12, "min_samples_leaf": 2},
        {"n_estimators": 300, "max_depth": 16, "min_samples_leaf": 2},
        {"n_estimators": 300, "max_depth": 20, "min_samples_leaf": 4},
    ]
    best = None
    for params in candidates:
        pipe = Pipeline(
            steps=[
                ("pre", build_preprocessor(cat, num)),
                (
                    "model",
                    RandomForestRegressor(
                        random_state=RANDOM_SEED,
                        n_jobs=-1,
                        **params,
                    ),
                ),
            ]
        )
        pipe.fit(X_train, y_train)
        pred = pipe.predict(X_val)
        metrics = regression_metrics(y_val, pred)
        record = {
            "name": "random_forest",
            "params": params,
            "val_metrics": metrics,
            "pipeline": pipe,
            "categorical": cat,
            "numeric": num,
        }
        if best is None or metrics["mae"] < best["val_metrics"]["mae"]:
            best = record
    return best


def train_xgboost(train: pd.DataFrame, val: pd.DataFrame) -> dict | None:
    try:
        from xgboost import XGBRegressor
    except ImportError:
        return {
            "name": "xgboost",
            "available": False,
            "error": "xgboost not installed",
            "val_metrics": None,
        }

    X_train, y_train = get_xy(train)
    X_val, y_val = get_xy(val)
    cat = [c for c in CATEGORICAL_BASE_FEATURES if c in X_train.columns]
    num = [c for c in (NUMERIC_BASE_FEATURES + ENGINEERED_FEATURES) if c in X_train.columns]

    candidates = [
        {
            "n_estimators": 300,
            "max_depth": 6,
            "learning_rate": 0.05,
            "subsample": 0.9,
            "colsample_bytree": 0.9,
        },
        {
            "n_estimators": 500,
            "max_depth": 8,
            "learning_rate": 0.05,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
        },
        {
            "n_estimators": 400,
            "max_depth": 5,
            "learning_rate": 0.08,
            "subsample": 0.9,
            "colsample_bytree": 0.9,
        },
    ]
    best = None
    for params in candidates:
        model = XGBRegressor(
            objective="reg:squarederror",
            random_state=RANDOM_SEED,
            n_jobs=-1,
            **params,
        )
        pipe = Pipeline(
            steps=[
                ("pre", build_preprocessor(cat, num)),
                ("model", model),
            ]
        )
        pipe.fit(X_train, y_train)
        pred = pipe.predict(X_val)
        metrics = regression_metrics(y_val, pred)
        record = {
            "name": "xgboost",
            "available": True,
            "params": params,
            "val_metrics": metrics,
            "pipeline": pipe,
            "categorical": cat,
            "numeric": num,
        }
        if best is None or metrics["mae"] < best["val_metrics"]["mae"]:
            best = record
    return best


def select_best(models: list[dict]) -> dict:
    """Select the overall best method by validation MAE (includes baselines)."""
    candidates = [
        m
        for m in models
        if m.get("val_metrics") is not None and m.get("available", True) is not False
    ]
    if not candidates:
        raise RuntimeError("No model produced validation metrics.")
    return min(candidates, key=lambda m: m["val_metrics"]["mae"])


def select_best_ml(models: list[dict]) -> dict | None:
    """Best learned model among RF/XGBoost by validation MAE (for comparison)."""
    candidates = [
        m
        for m in models
        if m.get("val_metrics") is not None
        and m["name"] in {"random_forest", "xgboost"}
        and m.get("available", True) is not False
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda m: m["val_metrics"]["mae"])


def save_artifacts(
    best: dict,
    best_ml: dict | None,
    baselines: list[dict],
    all_val: list[dict],
    split_meta: dict,
) -> None:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    if "pipeline" in best:
        joblib.dump(best["pipeline"], MODELS_DIR / "best_model.joblib")
        predictor_kind = "sklearn_pipeline"
    else:
        # Baseline selected as best overall
        joblib.dump(best["artifact"], MODELS_DIR / "best_model.joblib")
        predictor_kind = best["artifact"]["type"]

    joblib.dump(
        {
            "model_name": best["name"],
            "predictor_kind": predictor_kind,
            "params": best.get("params"),
            "feature_columns": feature_columns(),
            "categorical": best.get("categorical"),
            "numeric": best.get("numeric"),
            "target": TARGET_COL,
            "random_seed": RANDOM_SEED,
            "best_ml_model": None if best_ml is None else best_ml["name"],
            "best_ml_params": None if best_ml is None else best_ml.get("params"),
        },
        MODELS_DIR / "best_model_meta.joblib",
    )

    # Also save RF and XGB separately when available
    for m in all_val:
        if m["name"] == "random_forest" and "pipeline" in m:
            joblib.dump(m["pipeline"], MODELS_DIR / "random_forest.joblib")
        if m["name"] == "xgboost" and m.get("available") and "pipeline" in m:
            joblib.dump(m["pipeline"], MODELS_DIR / "xgboost.joblib")
    if best_ml is not None and "pipeline" in best_ml:
        joblib.dump(best_ml["pipeline"], MODELS_DIR / "best_ml_model.joblib")

    summary = {
        "random_seed": RANDOM_SEED,
        "selection_rule": (
            "lowest validation MAE among persistence, historical median, "
            "Random Forest, and XGBoost"
        ),
        "selected_model": best["name"],
        "selected_params": best.get("params"),
        "best_ml_model_by_validation": None if best_ml is None else best_ml["name"],
        "best_ml_val_metrics": None if best_ml is None else best_ml.get("val_metrics"),
        "validation_metrics": {
            m["name"]: m.get("val_metrics") for m in all_val
        },
        "baselines": {b["name"]: b.get("val_metrics") for b in baselines},
        "historical_median_value": next(
            (b.get("median") for b in baselines if b["name"] == "historical_median"),
            None,
        ),
        "split_meta": split_meta,
        "notes": [
            "Test-set metrics are computed separately after selection.",
            "Fractional predictions are valid continuous estimates of queue length; "
            "round only for operational display, not before regression metrics.",
            "Predictions should be clipped at 0 for operational non-negativity when serving.",
            "If persistence wins, queues are strongly autocorrelated at the 30-minute horizon "
            "on this synthetic 15-minute grid; ML models are still reported for comparison.",
        ],
    }
    with open(REPORTS_DIR / "training_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)

    # Persist baseline artifacts for evaluation
    joblib.dump(
        {b["name"]: b["artifact"] for b in baselines},
        MODELS_DIR / "baselines.joblib",
    )


def train(use_cached_splits: bool = True) -> dict:
    if (
        use_cached_splits
        and (PROCESSED_DIR / "train.csv").exists()
        and (PROCESSED_DIR / "val.csv").exists()
        and (PROCESSED_DIR / "test.csv").exists()
    ):
        train_df = pd.read_csv(PROCESSED_DIR / "train.csv", parse_dates=["timestamp"])
        val_df = pd.read_csv(PROCESSED_DIR / "val.csv", parse_dates=["timestamp"])
        with open(PROCESSED_DIR / "split_meta.json", encoding="utf-8") as f:
            split_meta = json.load(f)
    else:
        train_df, val_df, _test_df, split_meta = prepare(save=True)

    persistence = train_persistence(train_df, val_df)
    median = train_historical_median(train_df, val_df)
    rf = train_random_forest(train_df, val_df)
    xgb = train_xgboost(train_df, val_df)

    baselines = [persistence, median]
    all_models = [persistence, median, rf, xgb]
    best = select_best(all_models)
    best_ml = select_best_ml(all_models)
    save_artifacts(best, best_ml, baselines, all_models, split_meta)

    print(
        json.dumps(
            {
                "selected_overall": best["name"],
                "selected_overall_val_mae": best["val_metrics"]["mae"],
                "selected_best_ml": None if best_ml is None else best_ml["name"],
                "selected_best_ml_val_mae": (
                    None if best_ml is None else best_ml["val_metrics"]["mae"]
                ),
                "validation": {m["name"]: m.get("val_metrics") for m in all_models},
            },
            indent=2,
            default=str,
        )
    )
    return {
        "best": best,
        "best_ml": best_ml,
        "all": all_models,
        "split_meta": split_meta,
    }


def main() -> None:
    train(use_cached_splits=True)


if __name__ == "__main__":
    import sys

    sys.path.insert(0, str(PROJECT_ROOT))
    main()
