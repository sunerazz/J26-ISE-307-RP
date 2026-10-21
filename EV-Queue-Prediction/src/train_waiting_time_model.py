"""Train Model 2: baselines + Random Forest + XGBoost for waiting-time forecast."""

from __future__ import annotations

import json
import warnings

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline

from src.config import (
    CATEGORICAL_BASE_FEATURES,
    MODELS_DIR,
    NUMERIC_BASE_FEATURES,
    PROJECT_ROOT,
    RANDOM_SEED,
    REPORTS_DIR,
    WAIT_COL,
    WAITING_ENGINEERED_FEATURES,
    WAITING_MODEL_VERSION,
    WAITING_PROCESSED_DIR,
    WAITING_TARGET_COL,
)
from src.prepare_waiting_time_data import prepare_waiting_time, waiting_feature_columns
from src.train_queue_model import build_preprocessor

warnings.filterwarnings("ignore", category=UserWarning)


def regression_metrics(y_true, y_pred) -> dict:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    return {
        "mae_min": float(mean_absolute_error(y_true, y_pred)),
        "rmse_min": float(np.sqrt(mean_squared_error(y_true, y_pred))),
        "r2": float(r2_score(y_true, y_pred)),
        "n": int(len(y_true)),
    }


def get_xy(df: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray]:
    cols = waiting_feature_columns()
    return df[cols].copy(), df[WAITING_TARGET_COL].to_numpy(dtype=float)


def train_persistence(_train: pd.DataFrame, val: pd.DataFrame) -> dict:
    """Baseline: most recent station waiting-time observation."""
    pred = val[WAIT_COL].to_numpy(dtype=float)
    return {
        "name": "persistence",
        "val_metrics": regression_metrics(val[WAITING_TARGET_COL], pred),
        "artifact": {"type": "persistence", "feature": WAIT_COL},
    }


def train_historical_median(train: pd.DataFrame, val: pd.DataFrame) -> dict:
    median = float(np.median(train[WAITING_TARGET_COL].to_numpy(dtype=float)))
    pred = np.full(len(val), median, dtype=float)
    return {
        "name": "historical_median",
        "val_metrics": regression_metrics(val[WAITING_TARGET_COL], pred),
        "artifact": {"type": "historical_median", "median": median},
        "median": median,
    }


def _feature_groups(X: pd.DataFrame) -> tuple[list[str], list[str]]:
    cat = [c for c in CATEGORICAL_BASE_FEATURES if c in X.columns]
    num = [
        c
        for c in (NUMERIC_BASE_FEATURES + WAITING_ENGINEERED_FEATURES)
        if c in X.columns
    ]
    return cat, num


def train_random_forest(train: pd.DataFrame, val: pd.DataFrame) -> dict:
    X_train, y_train = get_xy(train)
    X_val, y_val = get_xy(val)
    cat, num = _feature_groups(X_train)
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
                        random_state=RANDOM_SEED, n_jobs=-1, **params
                    ),
                ),
            ]
        )
        pipe.fit(X_train, y_train)
        metrics = regression_metrics(y_val, pipe.predict(X_val))
        record = {
            "name": "random_forest",
            "params": params,
            "val_metrics": metrics,
            "pipeline": pipe,
            "categorical": cat,
            "numeric": num,
        }
        if best is None or metrics["mae_min"] < best["val_metrics"]["mae_min"]:
            best = record
    return best


def train_xgboost(train: pd.DataFrame, val: pd.DataFrame) -> dict:
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
    cat, num = _feature_groups(X_train)
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
        pipe = Pipeline(
            steps=[
                ("pre", build_preprocessor(cat, num)),
                (
                    "model",
                    XGBRegressor(
                        objective="reg:squarederror",
                        random_state=RANDOM_SEED,
                        n_jobs=-1,
                        **params,
                    ),
                ),
            ]
        )
        pipe.fit(X_train, y_train)
        metrics = regression_metrics(y_val, pipe.predict(X_val))
        record = {
            "name": "xgboost",
            "available": True,
            "params": params,
            "val_metrics": metrics,
            "pipeline": pipe,
            "categorical": cat,
            "numeric": num,
        }
        if best is None or metrics["mae_min"] < best["val_metrics"]["mae_min"]:
            best = record
    return best


def select_best(models: list[dict]) -> dict:
    candidates = [
        m
        for m in models
        if m.get("val_metrics") is not None and m.get("available", True) is not False
    ]
    if not candidates:
        raise RuntimeError("No waiting-time model produced validation metrics.")
    return min(candidates, key=lambda m: m["val_metrics"]["mae_min"])


def select_best_ml(models: list[dict]) -> dict | None:
    candidates = [
        m
        for m in models
        if m.get("val_metrics") is not None
        and m["name"] in {"random_forest", "xgboost"}
        and m.get("available", True) is not False
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda m: m["val_metrics"]["mae_min"])


def save_artifacts(
    best: dict,
    best_ml: dict | None,
    all_models: list[dict],
    split_meta: dict,
) -> None:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    if "pipeline" in best:
        joblib.dump(best["pipeline"], MODELS_DIR / "waiting_time_best_model.joblib")
        kind = "sklearn_pipeline"
    else:
        joblib.dump(best["artifact"], MODELS_DIR / "waiting_time_best_model.joblib")
        kind = best["artifact"]["type"]

    for m in all_models:
        if m["name"] == "random_forest" and "pipeline" in m:
            joblib.dump(m["pipeline"], MODELS_DIR / "waiting_time_random_forest.joblib")
        if m["name"] == "xgboost" and m.get("available") and "pipeline" in m:
            joblib.dump(m["pipeline"], MODELS_DIR / "waiting_time_xgboost.joblib")
    if best_ml is not None and "pipeline" in best_ml:
        joblib.dump(best_ml["pipeline"], MODELS_DIR / "waiting_time_best_ml_model.joblib")

    joblib.dump(
        {
            m["name"]: m["artifact"]
            for m in all_models
            if "artifact" in m
        },
        MODELS_DIR / "waiting_time_baselines.joblib",
    )

    meta = {
        "task": "waiting_time_30min",
        "model_name": best["name"],
        "model_version": WAITING_MODEL_VERSION,
        "predictor_kind": kind,
        "params": best.get("params"),
        "feature_columns": waiting_feature_columns(),
        "categorical": best.get("categorical"),
        "numeric": best.get("numeric"),
        "target": WAITING_TARGET_COL,
        "target_unit": "minutes",
        "wait_feature": WAIT_COL,
        "random_seed": RANDOM_SEED,
        "best_ml_model": None if best_ml is None else best_ml["name"],
        "best_ml_params": None if best_ml is None else best_ml.get("params"),
        "does_not_predict": ["queue_length", "congestion"],
    }
    joblib.dump(meta, MODELS_DIR / "waiting_time_best_model_meta.joblib")

    summary = {
        "experiment_label": "SIMULATION-BASED",
        "task": "waiting_time_30min",
        "model_version": WAITING_MODEL_VERSION,
        "selection_rule": (
            "lowest validation MAE among persistence, historical median, "
            "Random Forest, and XGBoost"
        ),
        "selected_overall": best["name"],
        "selected_params": best.get("params"),
        "best_ml_model_by_validation": None if best_ml is None else best_ml["name"],
        "best_ml_val_metrics": None if best_ml is None else best_ml.get("val_metrics"),
        "validation_metrics": {m["name"]: m.get("val_metrics") for m in all_models},
        "split_meta": split_meta,
        "notes": [
            "Waiting times are estimated/synthetic station snapshots, not measured "
            "arrival-to-charge-start stopwatch times from an event log.",
            "Negative raw predictions (if any) are kept for regression metrics; "
            "clip at 0 only for operational display.",
            "This model does not predict queue length or congestion.",
        ],
    }
    with open(REPORTS_DIR / "waiting_time_training_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)

    # Comparison CSV (validation)
    rows = []
    for m in all_models:
        vm = m.get("val_metrics") or {}
        rows.append(
            {
                "split": "validation",
                "model": m["name"],
                "mae_min": vm.get("mae_min"),
                "rmse_min": vm.get("rmse_min"),
                "r2": vm.get("r2"),
                "n": vm.get("n"),
                "available": m.get("available", True),
            }
        )
    pd.DataFrame(rows).to_csv(
        REPORTS_DIR / "waiting_time_model_comparison.csv", index=False
    )


def train(use_cached_splits: bool = True) -> dict:
    train_path = WAITING_PROCESSED_DIR / "train.csv"
    val_path = WAITING_PROCESSED_DIR / "val.csv"
    if use_cached_splits and train_path.exists() and val_path.exists():
        train_df = pd.read_csv(train_path, parse_dates=["timestamp"])
        val_df = pd.read_csv(val_path, parse_dates=["timestamp"])
        with open(WAITING_PROCESSED_DIR / "split_meta.json", encoding="utf-8") as f:
            split_meta = json.load(f)
    else:
        train_df, val_df, _test_df, split_meta = prepare_waiting_time(save=True)

    persistence = train_persistence(train_df, val_df)
    median = train_historical_median(train_df, val_df)
    rf = train_random_forest(train_df, val_df)
    xgb = train_xgboost(train_df, val_df)
    all_models = [persistence, median, rf, xgb]
    best = select_best(all_models)
    best_ml = select_best_ml(all_models)
    save_artifacts(best, best_ml, all_models, split_meta)

    print(
        json.dumps(
            {
                "selected_overall": best["name"],
                "selected_overall_val_mae_min": best["val_metrics"]["mae_min"],
                "selected_best_ml": None if best_ml is None else best_ml["name"],
                "selected_best_ml_val_mae_min": (
                    None if best_ml is None else best_ml["val_metrics"]["mae_min"]
                ),
                "validation": {m["name"]: m.get("val_metrics") for m in all_models},
            },
            indent=2,
            default=str,
        )
    )
    return {"best": best, "best_ml": best_ml, "all": all_models, "split_meta": split_meta}


def main() -> None:
    train(use_cached_splits=True)


if __name__ == "__main__":
    import sys

    sys.path.insert(0, str(PROJECT_ROOT))
    main()
