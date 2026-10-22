"""Train duration models and select the best one on validation MAE."""

from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, RegressorMixin
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import (  # noqa: E402
    META_PATH,
    MODELS_DIR,
    PIPELINE_PATH,
    PROCESSED_DIR,
    RANDOM_SEED,
    RESULTS_DIR,
    TARGET_COL,
)
from src.prepare_data import prepare  # noqa: E402

warnings.filterwarnings("ignore", category=UserWarning)


class MedianBaseline(BaseEstimator, RegressorMixin):
    """Predict the training-set median duration (minutes)."""

    def fit(self, X, y):
        self.median_ = float(np.median(np.asarray(y, dtype=float)))
        return self

    def predict(self, X):
        n = len(X) if hasattr(X, "__len__") else X.shape[0]
        return np.full(n, self.median_, dtype=float)


def regression_metrics(y_true, y_pred) -> dict:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    return {
        "mae_min": float(mean_absolute_error(y_true, y_pred)),
        "rmse_min": float(np.sqrt(mean_squared_error(y_true, y_pred))),
        "r2": float(r2_score(y_true, y_pred)),
        "n": int(len(y_true)),
    }


def make_preprocessor(numeric: list[str], categorical: list[str], scale: bool) -> ColumnTransformer:
    num_steps = [("imputer", SimpleImputer(strategy="median"))]
    if scale:
        num_steps.append(("scaler", StandardScaler()))
    numeric_pipe = Pipeline(num_steps)
    try:
        encoder = OneHotEncoder(handle_unknown="ignore", sparse_output=False)
    except TypeError:
        encoder = OneHotEncoder(handle_unknown="ignore", sparse=False)
    categorical_pipe = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("onehot", encoder),
        ]
    )
    transformers = [("num", numeric_pipe, numeric)]
    if categorical:
        transformers.append(("cat", categorical_pipe, categorical))
    return ColumnTransformer(transformers)


def build_pipeline(model, numeric: list[str], categorical: list[str], scale: bool) -> Pipeline:
    return Pipeline(
        [
            ("pre", make_preprocessor(numeric, categorical, scale=scale)),
            ("model", model),
        ]
    )


def _xy(df: pd.DataFrame, features: list[str]):
    return df[features].copy(), df[TARGET_COL].to_numpy(dtype=float)


def train(use_cached_splits: bool = True) -> dict:
    if use_cached_splits and (PROCESSED_DIR / "train.csv").exists():
        train_df = pd.read_csv(PROCESSED_DIR / "train.csv", parse_dates=["Charging Start Time"])
        val_df = pd.read_csv(PROCESSED_DIR / "val.csv", parse_dates=["Charging Start Time"])
        split_meta = json.loads((PROCESSED_DIR / "split_meta.json").read_text(encoding="utf-8"))
    else:
        train_df, val_df, _test, split_meta = prepare(save=True)

    features = split_meta["feature_columns"]
    numeric = split_meta["numeric_features"]
    categorical = split_meta["categorical_features"]
    X_train, y_train = _xy(train_df, features)
    X_val, y_val = _xy(val_df, features)

    candidates: list[dict] = []

    median_pipe = build_pipeline(MedianBaseline(), numeric, categorical, scale=False)
    median_pipe.fit(X_train, y_train)
    candidates.append(
        {
            "name": "median_baseline",
            "params": {"statistic": "training_median"},
            "pipeline": median_pipe,
            "val_metrics": regression_metrics(y_val, median_pipe.predict(X_val)),
        }
    )

    lin = build_pipeline(LinearRegression(), numeric, categorical, scale=True)
    lin.fit(X_train, y_train)
    candidates.append(
        {
            "name": "linear_regression",
            "params": {},
            "pipeline": lin,
            "val_metrics": regression_metrics(y_val, lin.predict(X_val)),
        }
    )

    rf_grid = [
        {"n_estimators": 200, "max_depth": 8, "min_samples_leaf": 2},
        {"n_estimators": 300, "max_depth": 12, "min_samples_leaf": 2},
        {"n_estimators": 300, "max_depth": 16, "min_samples_leaf": 4},
    ]
    best_rf = None
    for params in rf_grid:
        pipe = build_pipeline(
            RandomForestRegressor(random_state=RANDOM_SEED, n_jobs=-1, **params),
            numeric,
            categorical,
            scale=False,
        )
        pipe.fit(X_train, y_train)
        metrics = regression_metrics(y_val, pipe.predict(X_val))
        record = {"name": "random_forest", "params": params, "pipeline": pipe, "val_metrics": metrics}
        if best_rf is None or metrics["mae_min"] < best_rf["val_metrics"]["mae_min"]:
            best_rf = record
    candidates.append(best_rf)

    try:
        from xgboost import XGBRegressor
    except ImportError:
        xgb_record = {
            "name": "xgboost",
            "available": False,
            "error": "xgboost is not installed",
            "val_metrics": None,
        }
    else:
        xgb_grid = [
            {"n_estimators": 200, "max_depth": 4, "learning_rate": 0.05, "subsample": 0.9, "colsample_bytree": 0.9},
            {"n_estimators": 300, "max_depth": 6, "learning_rate": 0.05, "subsample": 0.8, "colsample_bytree": 0.8},
        ]
        best_xgb = None
        for params in xgb_grid:
            pipe = build_pipeline(
                XGBRegressor(
                    objective="reg:squarederror",
                    random_state=RANDOM_SEED,
                    n_jobs=-1,
                    **params,
                ),
                numeric,
                categorical,
                scale=False,
            )
            pipe.fit(X_train, y_train)
            metrics = regression_metrics(y_val, pipe.predict(X_val))
            record = {
                "name": "xgboost",
                "available": True,
                "params": params,
                "pipeline": pipe,
                "val_metrics": metrics,
            }
            if best_xgb is None or metrics["mae_min"] < best_xgb["val_metrics"]["mae_min"]:
                best_xgb = record
        xgb_record = best_xgb
    candidates.append(xgb_record)

    selectable = [c for c in candidates if c.get("val_metrics")]
    best = min(selectable, key=lambda c: c["val_metrics"]["mae_min"])

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(best["pipeline"], PIPELINE_PATH)
    meta = {
        "selected_model": best["name"],
        "selected_params": best.get("params"),
        "selection_rule": "lowest validation MAE in minutes",
        "random_seed": RANDOM_SEED,
        "target": TARGET_COL,
        "target_unit": "minutes",
        "feature_columns": features,
        "numeric_features": numeric,
        "categorical_features": categorical,
        "negative_prediction_policy": (
            "Regression metrics use raw predictions, including negatives if a model produces them. "
            "src.predict_duration.predict_duration clips operational output at 0 minutes."
        ),
        "fit_scope": "Winning pipeline was fit on the training dates only. Validation was used for selection, not for fitting.",
    }
    joblib.dump(meta, META_PATH)

    rows = []
    for c in candidates:
        vm = c.get("val_metrics") or {}
        rows.append(
            {
                "split": "validation",
                "model": c["name"],
                "mae_min": vm.get("mae_min"),
                "rmse_min": vm.get("rmse_min"),
                "r2": vm.get("r2"),
                "n": vm.get("n"),
                "available": c.get("available", True),
                "params": json.dumps(c.get("params"), default=str),
            }
        )
    pd.DataFrame(rows).to_csv(RESULTS_DIR / "model_comparison.csv", index=False)
    summary = {
        "selected_model": best["name"],
        "selected_params": best.get("params"),
        "validation": {c["name"]: c.get("val_metrics") for c in candidates},
        "split_meta": split_meta,
    }
    (RESULTS_DIR / "training_summary.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8"
    )
    print(json.dumps({"selected": best["name"], "validation": summary["validation"]}, indent=2, default=str))
    return summary


def main() -> None:
    train(use_cached_splits=True)


if __name__ == "__main__":
    main()
