"""Train energy models and keep the one with the lowest validation MAE."""

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

from src.config import META_PATH, MODELS_DIR, PIPELINE_PATH, RANDOM_SEED, RESULTS_DIR, TARGET_COL  # noqa: E402
from src.prepare_data import prepare  # noqa: E402

warnings.filterwarnings("ignore", category=UserWarning)


class MedianBaseline(BaseEstimator, RegressorMixin):
    """Predict the training-set median energy."""

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
        "mae_kwh": float(mean_absolute_error(y_true, y_pred)),
        "rmse_kwh": float(np.sqrt(mean_squared_error(y_true, y_pred))),
        "r2": float(r2_score(y_true, y_pred)),
        "n": int(len(y_true)),
    }


def make_preprocessor(numeric: list[str], categorical: list[str], scale: bool) -> ColumnTransformer:
    num_steps = [("imputer", SimpleImputer(strategy="median"))]
    if scale:
        num_steps.append(("scaler", StandardScaler()))
    try:
        encoder = OneHotEncoder(handle_unknown="ignore", sparse_output=False)
    except TypeError:
        encoder = OneHotEncoder(handle_unknown="ignore", sparse=False)
    return ColumnTransformer(
        [
            ("num", Pipeline(num_steps), numeric),
            (
                "cat",
                Pipeline(
                    [
                        ("imputer", SimpleImputer(strategy="most_frequent")),
                        ("onehot", encoder),
                    ]
                ),
                categorical,
            ),
        ]
    )


def build_pipeline(model, numeric: list[str], categorical: list[str], scale: bool) -> Pipeline:
    return Pipeline([("pre", make_preprocessor(numeric, categorical, scale=scale)), ("model", model)])


def _xy(df: pd.DataFrame, features: list[str]):
    return df[features].copy(), df[TARGET_COL].to_numpy(dtype=float)


def train() -> dict:
    train_df, val_df, _test, split_meta = prepare(save=True)
    features = split_meta["feature_columns"]
    numeric = split_meta["numeric_features"]
    categorical = split_meta["categorical_features"]
    X_train, y_train = _xy(train_df, features)
    X_val, y_val = _xy(val_df, features)
    candidates: list[dict] = []

    median_pipe = Pipeline([("model", MedianBaseline())])
    median_pipe.fit(X_train, y_train)
    candidates.append(
        {
            "name": "median_baseline",
            "params": {"statistic": "training_median"},
            "pipeline": median_pipe,
            "val_metrics": regression_metrics(y_val, median_pipe.predict(X_val)),
        }
    )

    linear = build_pipeline(LinearRegression(), numeric, categorical, scale=True)
    linear.fit(X_train, y_train)
    candidates.append(
        {
            "name": "linear_regression",
            "params": {},
            "pipeline": linear,
            "val_metrics": regression_metrics(y_val, linear.predict(X_val)),
        }
    )

    best_rf = None
    for params in (
        {"n_estimators": 200, "max_depth": 12, "min_samples_leaf": 2},
        {"n_estimators": 300, "max_depth": 16, "min_samples_leaf": 4},
    ):
        pipe = build_pipeline(
            RandomForestRegressor(random_state=RANDOM_SEED, n_jobs=-1, **params),
            numeric,
            categorical,
            scale=False,
        )
        pipe.fit(X_train, y_train)
        metrics = regression_metrics(y_val, pipe.predict(X_val))
        record = {"name": "random_forest", "params": params, "pipeline": pipe, "val_metrics": metrics}
        if best_rf is None or metrics["mae_kwh"] < best_rf["val_metrics"]["mae_kwh"]:
            best_rf = record
    candidates.append(best_rf)

    try:
        from xgboost import XGBRegressor
    except ImportError:
        candidates.append({"name": "xgboost", "available": False, "error": "xgboost is not installed", "val_metrics": None})
    else:
        best_xgb = None
        for params in (
            {"n_estimators": 200, "max_depth": 4, "learning_rate": 0.05, "subsample": 0.9, "colsample_bytree": 0.9},
            {"n_estimators": 300, "max_depth": 6, "learning_rate": 0.05, "subsample": 0.8, "colsample_bytree": 0.8},
        ):
            pipe = build_pipeline(
                XGBRegressor(objective="reg:squarederror", random_state=RANDOM_SEED, n_jobs=-1, **params),
                numeric,
                categorical,
                scale=False,
            )
            pipe.fit(X_train, y_train)
            metrics = regression_metrics(y_val, pipe.predict(X_val))
            record = {"name": "xgboost", "available": True, "params": params, "pipeline": pipe, "val_metrics": metrics}
            if best_xgb is None or metrics["mae_kwh"] < best_xgb["val_metrics"]["mae_kwh"]:
                best_xgb = record
        candidates.append(best_xgb)

    selectable = [item for item in candidates if item.get("val_metrics")]
    best = min(selectable, key=lambda item: item["val_metrics"]["mae_kwh"])

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(best["pipeline"], PIPELINE_PATH)
    meta = {
        "selected_model": best["name"],
        "selected_params": best.get("params"),
        "selection_rule": "lowest validation MAE in kWh",
        "random_seed": RANDOM_SEED,
        "target": TARGET_COL,
        "target_unit": "kWh",
        "feature_columns": features,
        "numeric_features": numeric,
        "categorical_features": categorical,
        "categories": split_meta["categories"],
        "excluded_as_leakage": split_meta["excluded_as_leakage"],
        "training_data": "synthetic",
        "source": "component3_energy_consumption.csv",
        "negative_prediction_policy": (
            "Validation metrics use raw predictions. "
            "src.predict_energy.predict_energy rejects a negative or non-finite prediction "
            "instead of treating it as zero energy."
        ),
        "fit_scope": "The winning pipeline was fit on the training block only. Validation was used for selection, not for fitting.",
    }
    joblib.dump(meta, META_PATH)
    rows = []
    for item in candidates:
        metrics = item.get("val_metrics") or {}
        rows.append(
            {
                "split": "validation",
                "model": item["name"],
                "mae_kwh": metrics.get("mae_kwh"),
                "rmse_kwh": metrics.get("rmse_kwh"),
                "r2": metrics.get("r2"),
                "n": metrics.get("n"),
                "available": item.get("available", True),
                "params": json.dumps(item.get("params"), default=str),
            }
        )
    pd.DataFrame(rows).to_csv(RESULTS_DIR / "model_comparison.csv", index=False)
    summary = {
        "selected_model": best["name"],
        "selected_params": best.get("params"),
        "validation": {item["name"]: item.get("val_metrics") for item in candidates},
        "split_meta": split_meta,
    }
    (RESULTS_DIR / "training_summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"selected": best["name"], "validation_mae_kwh": best["val_metrics"]["mae_kwh"]}, indent=2))
    return summary


def main() -> None:
    train()


if __name__ == "__main__":
    main()
