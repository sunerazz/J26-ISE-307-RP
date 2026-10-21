"""Train Model 3: congestion classifiers (baseline, Random Forest, XGBoost)."""

from __future__ import annotations

import json
import warnings

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    precision_recall_fscore_support,
)
from sklearn.pipeline import Pipeline

from src.config import (
    CATEGORICAL_BASE_FEATURES,
    CONGESTION_CLASSES,
    CONGESTION_COL,
    CONGESTION_ENGINEERED_FEATURES,
    CONGESTION_MODEL_VERSION,
    CONGESTION_PROCESSED_DIR,
    CONGESTION_TARGET_COL,
    MODELS_DIR,
    NUMERIC_BASE_FEATURES,
    PROJECT_ROOT,
    RANDOM_SEED,
    REPORTS_DIR,
)
from src.prepare_congestion_data import congestion_feature_columns, prepare_congestion
from src.train_queue_model import build_preprocessor

warnings.filterwarnings("ignore", category=UserWarning)

CLASS_ORDER = list(CONGESTION_CLASSES)


def classification_metrics(y_true, y_pred, labels=CLASS_ORDER) -> dict:
    y_true = np.asarray(y_true)
    y_pred = np.asarray(y_pred)
    present = [c for c in labels if c in set(y_true) or c in set(y_pred)]
    precision, recall, f1, support = precision_recall_fscore_support(
        y_true,
        y_pred,
        labels=present,
        average=None,
        zero_division=0,
    )
    per_class = {
        str(cls): {
            "precision": float(p),
            "recall": float(r),
            "f1": float(f),
            "support": int(s),
        }
        for cls, p, r, f, s in zip(present, precision, recall, f1, support)
    }
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "macro_f1": float(
            f1_score(y_true, y_pred, average="macro", labels=present, zero_division=0)
        ),
        "n": int(len(y_true)),
        "labels_evaluated": present,
        "per_class": per_class,
    }


def get_xy(df: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray]:
    return (
        df[congestion_feature_columns()].copy(),
        df[CONGESTION_TARGET_COL].astype(str).to_numpy(),
    )


def _feature_groups(X: pd.DataFrame) -> tuple[list[str], list[str]]:
    cat = [c for c in CATEGORICAL_BASE_FEATURES if c in X.columns]
    num = [
        c
        for c in (NUMERIC_BASE_FEATURES + CONGESTION_ENGINEERED_FEATURES)
        if c in X.columns
    ]
    return cat, num


def train_most_frequent(train: pd.DataFrame, val: pd.DataFrame) -> dict:
    majority = (
        train[CONGESTION_TARGET_COL]
        .astype(str)
        .value_counts()
        .idxmax()
    )
    pred = np.full(len(val), majority, dtype=object)
    return {
        "name": "most_frequent",
        "val_metrics": classification_metrics(val[CONGESTION_TARGET_COL], pred),
        "artifact": {"type": "most_frequent", "class": majority},
        "majority_class": majority,
    }


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
                    RandomForestClassifier(
                        random_state=RANDOM_SEED,
                        n_jobs=-1,
                        class_weight="balanced",
                        **params,
                    ),
                ),
            ]
        )
        pipe.fit(X_train, y_train)
        metrics = classification_metrics(y_val, pipe.predict(X_val))
        record = {
            "name": "random_forest",
            "params": {**params, "class_weight": "balanced"},
            "val_metrics": metrics,
            "pipeline": pipe,
            "categorical": cat,
            "numeric": num,
        }
        if best is None or metrics["macro_f1"] > best["val_metrics"]["macro_f1"]:
            best = record
    return best


def train_xgboost(train: pd.DataFrame, val: pd.DataFrame) -> dict:
    try:
        from xgboost import XGBClassifier
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

    # XGBoost needs integer labels internally; map via sklearn-compatible classes_
    class_to_idx = {c: i for i, c in enumerate(CLASS_ORDER)}
    idx_to_class = {i: c for c, i in class_to_idx.items()}
    y_train_i = np.array([class_to_idx[str(v)] for v in y_train])
    # sample weights approx class balance on training only
    counts = pd.Series(y_train).value_counts()
    weight_map = {c: len(y_train) / (len(counts) * counts[c]) for c in counts.index}
    sample_weight = np.array([weight_map[str(v)] for v in y_train])

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
        model = XGBClassifier(
            objective="multi:softprob",
            num_class=len(CLASS_ORDER),
            random_state=RANDOM_SEED,
            n_jobs=-1,
            eval_metric="mlogloss",
            **params,
        )
        pipe = Pipeline(
            steps=[
                ("pre", build_preprocessor(cat, num)),
                ("model", model),
            ]
        )
        pipe.fit(X_train, y_train_i, model__sample_weight=sample_weight)
        pred_i = pipe.predict(X_val)
        pred = np.array([idx_to_class[int(i)] for i in pred_i])
        metrics = classification_metrics(y_val, pred)
        record = {
            "name": "xgboost",
            "available": True,
            "params": params,
            "val_metrics": metrics,
            "pipeline": pipe,
            "categorical": cat,
            "numeric": num,
            "class_to_idx": class_to_idx,
            "idx_to_class": idx_to_class,
            "label_encoding": "integer_via_CLASS_ORDER",
        }
        if best is None or metrics["macro_f1"] > best["val_metrics"]["macro_f1"]:
            best = record
    return best


def select_best(models: list[dict]) -> dict:
    candidates = [
        m
        for m in models
        if m.get("val_metrics") is not None and m.get("available", True) is not False
    ]
    if not candidates:
        raise RuntimeError("No congestion model produced validation metrics.")
    return max(candidates, key=lambda m: m["val_metrics"]["macro_f1"])


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
    return max(candidates, key=lambda m: m["val_metrics"]["macro_f1"])


def save_artifacts(
    best: dict,
    best_ml: dict | None,
    all_models: list[dict],
    split_meta: dict,
) -> None:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    if "pipeline" in best:
        joblib.dump(best["pipeline"], MODELS_DIR / "congestion_best_model.joblib")
        kind = "sklearn_pipeline"
    else:
        joblib.dump(best["artifact"], MODELS_DIR / "congestion_best_model.joblib")
        kind = best["artifact"]["type"]

    for m in all_models:
        if m["name"] == "random_forest" and "pipeline" in m:
            joblib.dump(m["pipeline"], MODELS_DIR / "congestion_random_forest.joblib")
            joblib.dump(
                {
                    "class_to_idx": None,
                    "idx_to_class": None,
                    "label_encoding": "native_strings",
                },
                MODELS_DIR / "congestion_random_forest_meta.joblib",
            )
        if m["name"] == "xgboost" and m.get("available") and "pipeline" in m:
            joblib.dump(m["pipeline"], MODELS_DIR / "congestion_xgboost.joblib")
            joblib.dump(
                {
                    "class_to_idx": m["class_to_idx"],
                    "idx_to_class": m["idx_to_class"],
                    "label_encoding": m["label_encoding"],
                },
                MODELS_DIR / "congestion_xgboost_meta.joblib",
            )
    if best_ml is not None and "pipeline" in best_ml:
        joblib.dump(best_ml["pipeline"], MODELS_DIR / "congestion_best_ml_model.joblib")

    joblib.dump(
        {m["name"]: m["artifact"] for m in all_models if "artifact" in m},
        MODELS_DIR / "congestion_baselines.joblib",
    )

    meta = {
        "task": "congestion_30min",
        "model_name": best["name"],
        "model_version": CONGESTION_MODEL_VERSION,
        "predictor_kind": kind,
        "params": best.get("params"),
        "feature_columns": congestion_feature_columns(),
        "categorical": best.get("categorical"),
        "numeric": best.get("numeric"),
        "target": CONGESTION_TARGET_COL,
        "classes": CLASS_ORDER,
        "current_congestion_feature": CONGESTION_COL,
        "random_seed": RANDOM_SEED,
        "best_ml_model": None if best_ml is None else best_ml["name"],
        "best_ml_params": None if best_ml is None else best_ml.get("params"),
        "class_to_idx": best.get("class_to_idx"),
        "idx_to_class": best.get("idx_to_class"),
        "label_encoding": best.get("label_encoding", "native_strings"),
        "selection_metric": "validation_macro_f1",
        "does_not_predict": ["queue_length", "waiting_time"],
        "label_provenance": "synthetic_rule_derived",
    }
    joblib.dump(meta, MODELS_DIR / "congestion_best_model_meta.joblib")

    summary = {
        "experiment_label": "SIMULATION-BASED",
        "task": "congestion_30min",
        "model_version": CONGESTION_MODEL_VERSION,
        "selection_rule": "highest validation macro-F1 among most_frequent, RF, XGBoost",
        "selected_overall": best["name"],
        "selected_params": best.get("params"),
        "best_ml_model_by_validation": None if best_ml is None else best_ml["name"],
        "best_ml_val_metrics": None if best_ml is None else best_ml.get("val_metrics"),
        "validation_metrics": {m["name"]: m.get("val_metrics") for m in all_models},
        "split_meta": split_meta,
        "notes": [
            "Congestion labels are synthetic/rule-derived station categories.",
            "Class imbalance handled with class_weight='balanced' (RF) and "
            "training-set inverse-frequency sample weights (XGBoost). SMOTE not used.",
            "This model does not predict queue length or waiting time.",
        ],
    }
    with open(
        REPORTS_DIR / "congestion_training_summary.json", "w", encoding="utf-8"
    ) as f:
        json.dump(summary, f, indent=2, default=str)

    rows = []
    for m in all_models:
        vm = m.get("val_metrics") or {}
        rows.append(
            {
                "split": "validation",
                "model": m["name"],
                "accuracy": vm.get("accuracy"),
                "macro_f1": vm.get("macro_f1"),
                "n": vm.get("n"),
                "available": m.get("available", True),
            }
        )
    pd.DataFrame(rows).to_csv(
        REPORTS_DIR / "congestion_model_comparison.csv", index=False
    )


def train(use_cached_splits: bool = True) -> dict:
    train_path = CONGESTION_PROCESSED_DIR / "train.csv"
    val_path = CONGESTION_PROCESSED_DIR / "val.csv"
    if use_cached_splits and train_path.exists() and val_path.exists():
        train_df = pd.read_csv(train_path, parse_dates=["timestamp"])
        val_df = pd.read_csv(val_path, parse_dates=["timestamp"])
        with open(CONGESTION_PROCESSED_DIR / "split_meta.json", encoding="utf-8") as f:
            split_meta = json.load(f)
    else:
        train_df, val_df, _test_df, split_meta = prepare_congestion(save=True)

    most_freq = train_most_frequent(train_df, val_df)
    rf = train_random_forest(train_df, val_df)
    xgb = train_xgboost(train_df, val_df)
    all_models = [most_freq, rf, xgb]
    best = select_best(all_models)
    best_ml = select_best_ml(all_models)
    save_artifacts(best, best_ml, all_models, split_meta)

    print(
        json.dumps(
            {
                "selected_overall": best["name"],
                "selected_overall_val_macro_f1": best["val_metrics"]["macro_f1"],
                "selected_best_ml": None if best_ml is None else best_ml["name"],
                "selected_best_ml_val_macro_f1": (
                    None if best_ml is None else best_ml["val_metrics"]["macro_f1"]
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
