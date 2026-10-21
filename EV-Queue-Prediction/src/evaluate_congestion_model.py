"""Evaluate Model 3 congestion classifiers on the untouched chronological test set."""

from __future__ import annotations

import json

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import ConfusionMatrixDisplay, confusion_matrix

from src.config import (
    CONGESTION_CLASSES,
    CONGESTION_COL,
    CONGESTION_PROCESSED_DIR,
    CONGESTION_TARGET_COL,
    FORECAST_HORIZON_MINUTES,
    MODELS_DIR,
    PLOTS_DIR,
    PROJECT_ROOT,
    REPORTS_DIR,
    STATION_COL,
    TIMESTAMP_COL,
)
from src.prepare_congestion_data import congestion_feature_columns
from src.train_congestion_model import CLASS_ORDER, classification_metrics


def _decode_predictions(pipe, meta: dict | None, X: pd.DataFrame) -> np.ndarray:
    raw = pipe.predict(X)
    if meta and meta.get("label_encoding") == "integer_via_CLASS_ORDER":
        idx_to_class = {int(k): v for k, v in meta["idx_to_class"].items()}
        return np.array([idx_to_class[int(i)] for i in raw])
    return np.asarray(raw).astype(str)


def _predict_proba(pipe, meta: dict | None, X: pd.DataFrame) -> np.ndarray | None:
    if not hasattr(pipe, "predict_proba"):
        return None
    try:
        proba = pipe.predict_proba(X)
    except Exception:
        return None
    if meta and meta.get("label_encoding") == "integer_via_CLASS_ORDER":
        # columns already follow 0..K-1 = CLASS_ORDER
        return proba
    # sklearn RF: columns follow pipe.classes_
    model = pipe.named_steps.get("model", pipe)
    classes = list(getattr(model, "classes_", CLASS_ORDER))
    aligned = np.zeros((len(X), len(CLASS_ORDER)), dtype=float)
    for j, cls in enumerate(classes):
        if cls in CLASS_ORDER:
            aligned[:, CLASS_ORDER.index(cls)] = proba[:, j]
    return aligned


def _predict_selected(artifact, meta: dict, test: pd.DataFrame) -> np.ndarray:
    kind = meta.get("predictor_kind", "sklearn_pipeline")
    if kind == "most_frequent":
        return np.full(len(test), str(artifact["class"]), dtype=object)
    if kind == "sklearn_pipeline":
        return _decode_predictions(
            artifact, meta, test[congestion_feature_columns()]
        )
    raise ValueError(f"Unknown predictor_kind: {kind}")


def evaluate() -> dict:
    test = pd.read_csv(
        CONGESTION_PROCESSED_DIR / "test.csv", parse_dates=[TIMESTAMP_COL]
    )
    y_true = test[CONGESTION_TARGET_COL].astype(str).to_numpy()
    X_test = test[congestion_feature_columns()]

    baselines = joblib.load(MODELS_DIR / "congestion_baselines.joblib")
    best_artifact = joblib.load(MODELS_DIR / "congestion_best_model.joblib")
    best_meta = joblib.load(MODELS_DIR / "congestion_best_model_meta.joblib")

    with open(CONGESTION_PROCESSED_DIR / "split_meta.json", encoding="utf-8") as f:
        split_meta = json.load(f)

    y_best = _predict_selected(best_artifact, best_meta, test)

    results = {
        "experiment_label": "SIMULATION-BASED",
        "task": "congestion_30min",
        "label_provenance": "synthetic_rule_derived",
        "selected_model": best_meta["model_name"],
        "model_version": best_meta.get("model_version"),
        "selected_params": best_meta.get("params"),
        "best_ml_model_by_validation": best_meta.get("best_ml_model"),
        "test_metrics_selected": classification_metrics(y_true, y_best),
        "class_distribution": {
            "train": split_meta.get("class_counts_train"),
            "validation": split_meta.get("class_counts_val"),
            "test": split_meta.get("class_counts_test"),
        },
        "baselines_test": {},
        "by_station": {},
        "interpretation": (
            "Macro-F1 is the primary selection metric. Accuracy alone can be "
            "misleading under class imbalance. Labels are synthetic/rule-derived."
        ),
    }

    maj = baselines["most_frequent"]["class"]
    results["baselines_test"]["most_frequent"] = classification_metrics(
        y_true, np.full(len(test), maj, dtype=object)
    )

    comparison = {"most_frequent": results["baselines_test"]["most_frequent"]}
    for fname, label, meta_name in (
        (
            "congestion_random_forest.joblib",
            "random_forest",
            "congestion_random_forest_meta.joblib",
        ),
        (
            "congestion_xgboost.joblib",
            "xgboost",
            "congestion_xgboost_meta.joblib",
        ),
    ):
        path = MODELS_DIR / fname
        if path.exists():
            pipe = joblib.load(path)
            meta = joblib.load(MODELS_DIR / meta_name)
            pred = _decode_predictions(pipe, meta, X_test)
            comparison[label] = classification_metrics(y_true, pred)
    results["test_comparison"] = comparison

    rows = []
    for name, m in comparison.items():
        rows.append(
            {
                "split": "test",
                "model": name,
                "accuracy": m["accuracy"],
                "macro_f1": m["macro_f1"],
                "n": m["n"],
            }
        )
    cmp_path = REPORTS_DIR / "congestion_model_comparison.csv"
    if cmp_path.exists():
        prev = pd.read_csv(cmp_path)
        prev = prev[prev["split"] != "test"]
        out = pd.concat([prev, pd.DataFrame(rows)], ignore_index=True)
    else:
        out = pd.DataFrame(rows)
    out.to_csv(cmp_path, index=False)

    test = test.copy()
    test["y_pred"] = y_best
    for sid, g in test.groupby(STATION_COL):
        results["by_station"][str(sid)] = classification_metrics(
            g[CONGESTION_TARGET_COL].astype(str), g["y_pred"].astype(str)
        )

    # Confusion matrix (only classes present in y_true or y_pred)
    present = [c for c in CLASS_ORDER if c in set(y_true) or c in set(y_best)]
    cm = confusion_matrix(y_true, y_best, labels=present)
    results["confusion_matrix"] = {
        "labels": present,
        "matrix": cm.tolist(),
    }
    absent = [c for c in CLASS_ORDER if c not in set(y_true)]
    results["classes_absent_from_test"] = absent
    if absent:
        results["absent_class_note"] = (
            f"Classes absent from test labels: {absent}. "
            "No fabricated per-class metrics were created for missing classes "
            "beyond zero_division-safe sklearn outputs on evaluated labels."
        )

    # Feature importance for tree models
    results["feature_importance_top"] = _feature_importance(best_artifact, best_meta)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(REPORTS_DIR / "congestion_test_metrics.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)

    pred_out = test[
        [TIMESTAMP_COL, STATION_COL, CONGESTION_COL, CONGESTION_TARGET_COL, "y_pred"]
    ].copy()
    pred_out["forecast_timestamp"] = pred_out[TIMESTAMP_COL] + pd.Timedelta(
        minutes=FORECAST_HORIZON_MINUTES
    )
    pred_out.to_csv(CONGESTION_PROCESSED_DIR / "test_predictions.csv", index=False)

    _make_plots(test, y_true, y_best, present, results)
    _write_evaluation_md(results)
    print(json.dumps(results["test_comparison"], indent=2, default=str))
    print(f"Selected test metrics: {results['test_metrics_selected']}")
    return results


def _feature_importance(artifact, meta: dict) -> list[dict] | None:
    if meta.get("predictor_kind") != "sklearn_pipeline":
        return None
    try:
        pre = artifact.named_steps["pre"]
        model = artifact.named_steps["model"]
        if not hasattr(model, "feature_importances_"):
            return None
        names = list(pre.get_feature_names_out())
        imps = model.feature_importances_
        order = np.argsort(imps)[::-1][:15]
        return [
            {"feature": str(names[i]), "importance": float(imps[i])} for i in order
        ]
    except Exception:
        return None


def _make_plots(test, y_true, y_pred, labels, results: dict) -> None:
    fig, ax = plt.subplots(figsize=(6, 5))
    ConfusionMatrixDisplay.from_predictions(
        y_true, y_pred, labels=labels, ax=ax, colorbar=True
    )
    ax.set_title(f"Congestion confusion matrix — {results['selected_model']}")
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / "congestion_confusion_matrix.png", dpi=140)
    plt.close(fig)

    # Per-class metrics bar chart
    per = results["test_metrics_selected"]["per_class"]
    classes = list(per.keys())
    metrics_names = ["precision", "recall", "f1"]
    x = np.arange(len(classes))
    width = 0.25
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for i, mname in enumerate(metrics_names):
        vals = [per[c][mname] for c in classes]
        ax.bar(x + i * width, vals, width, label=mname)
    ax.set_xticks(x + width)
    ax.set_xticklabels(classes)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("Score")
    ax.set_title("Congestion per-class precision / recall / F1 (test)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / "congestion_class_metrics.png", dpi=140)
    plt.close(fig)

    # Time series for representative stations
    stations = sorted(test[STATION_COL].unique())
    preferred = [s for s in ("ST01", "ST02", "ST06", "ST04") if s in stations]
    plot_stations = (preferred + stations)[:2]
    t0 = test[TIMESTAMP_COL].min()
    window = test[
        (test[TIMESTAMP_COL] >= t0)
        & (test[TIMESTAMP_COL] < t0 + pd.Timedelta(days=7))
    ]
    level_map = {c: i for i, c in enumerate(CONGESTION_CLASSES)}

    fig, axes = plt.subplots(
        len(plot_stations), 1, figsize=(11, 3.2 * len(plot_stations)), sharex=True
    )
    if len(plot_stations) == 1:
        axes = [axes]
    for ax, sid in zip(axes, plot_stations):
        g = window[window[STATION_COL] == sid].sort_values(TIMESTAMP_COL)
        ax.step(
            g[TIMESTAMP_COL],
            g[CONGESTION_TARGET_COL].map(level_map),
            where="post",
            label="Actual",
            linewidth=1.5,
        )
        ax.step(
            g[TIMESTAMP_COL],
            g["y_pred"].map(level_map),
            where="post",
            label="Predicted",
            linewidth=1.2,
            alpha=0.85,
        )
        ax.set_yticks(list(level_map.values()))
        ax.set_yticklabels(list(level_map.keys()))
        ax.set_title(f"Station {sid} — congestion, first 7 test days")
        ax.legend(loc="upper right")
    axes[-1].set_xlabel("Prediction timestamp")
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / "congestion_test_timeseries.png", dpi=140)
    plt.close(fig)


def _write_evaluation_md(results: dict) -> None:
    lines = [
        "# Congestion Model Evaluation (Model 3)",
        "",
        "## Dataset and label validation",
        "",
        "- **Experiment label:** SIMULATION-BASED.",
        "- Congestion categories Low / Medium / High are synthetic/rule-derived "
        "station snapshot labels (`congestion_level_now`).",
        "- Target `target_congestion_level_30min` = same-station congestion at t+30 "
        "(exact timestamp match; CSV pre-computed target matched 100%).",
        "- Missing future labels were dropped, never filled as Low.",
        "",
        "## Selected models",
        "",
        f"- Overall (validation macro-F1): **{results['selected_model']}** "
        f"(`{results.get('model_version')}`)",
        f"- Best learned model: **{results.get('best_ml_model_by_validation')}**",
        "",
        "## Class distributions",
        "",
        "```json",
        json.dumps(results["class_distribution"], indent=2),
        "```",
        "",
        "## Test metrics — selected model",
        "",
        "```json",
        json.dumps(results["test_metrics_selected"], indent=2),
        "```",
        "",
        "## Baseline vs Random Forest vs XGBoost (test)",
        "",
        "```json",
        json.dumps(results["test_comparison"], indent=2),
        "```",
        "",
        "## Confusion matrix",
        "",
        "```json",
        json.dumps(results["confusion_matrix"], indent=2),
        "```",
        "",
        "## Feature importance (top)",
        "",
        "```json",
        json.dumps(results.get("feature_importance_top"), indent=2),
        "```",
        "",
        "## Leakage prevention",
        "",
        "- Only prediction-time features used.",
        "- Future congestion / queue / waiting-time labels excluded.",
        "- Lags computed per station on past rows only.",
        "- Preprocessing and class weights fit/derived from training data only.",
        "- Model selected on validation macro-F1; test evaluated once.",
        "",
        "## Limitations",
        "",
        "- Synthetic/rule-derived labels; not independent real-world congestion audits.",
        "- Model approximates foresight of those categories, not absolute physical congestion truth.",
        "- Does **not** predict queue length or waiting time.",
        "- Medium class is minority; accuracy alone is insufficient.",
        "",
        "## Artifacts",
        "",
        "- `models/congestion_best_model.joblib`",
        "- `models/congestion_random_forest.joblib`",
        "- `models/congestion_xgboost.joblib`",
        "- `plots/congestion_confusion_matrix.png`",
        "- `plots/congestion_class_metrics.png`",
        "- `plots/congestion_test_timeseries.png`",
        "- `reports/congestion_model_comparison.csv`",
        "",
    ]
    (REPORTS_DIR / "congestion_evaluation.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )


def main() -> None:
    evaluate()


if __name__ == "__main__":
    import sys

    sys.path.insert(0, str(PROJECT_ROOT))
    main()
