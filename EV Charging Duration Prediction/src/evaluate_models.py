"""Evaluate the validation-selected duration pipeline once on the test set."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import (  # noqa: E402
    META_PATH,
    MODELS_DIR,
    PIPELINE_PATH,
    PROCESSED_DIR,
    RESULTS_DIR,
    TARGET_COL,
)
from src.train_models import regression_metrics  # noqa: E402


def evaluate() -> dict:
    if not PIPELINE_PATH.exists():
        raise FileNotFoundError(
            f"Missing {PIPELINE_PATH}. Run: python -m src.train_models"
        )
    test = pd.read_csv(PROCESSED_DIR / "test.csv")
    meta = joblib.load(META_PATH)
    pipe = joblib.load(PIPELINE_PATH)
    features = meta["feature_columns"]
    y_true = test[TARGET_COL].to_numpy(dtype=float)
    y_pred = np.asarray(pipe.predict(test[features]), dtype=float)
    y_clip = np.maximum(y_pred, 0.0)

    # Also score the other saved comparison is validation-only.
    # Recompute median/linear/rf/xgb is not required; test the selected model once.
    comparison_path = RESULTS_DIR / "model_comparison.csv"
    comparison = pd.read_csv(comparison_path) if comparison_path.exists() else pd.DataFrame()

    selected = regression_metrics(y_true, y_pred)
    selected_clipped = regression_metrics(y_true, y_clip)
    test_row = {
        "split": "test",
        "model": meta["selected_model"],
        "mae_min": selected["mae_min"],
        "rmse_min": selected["rmse_min"],
        "r2": selected["r2"],
        "n": selected["n"],
        "available": True,
        "params": json.dumps(meta.get("selected_params"), default=str),
    }
    if not comparison.empty:
        comparison = comparison[comparison["split"] != "test"]
        comparison = pd.concat([comparison, pd.DataFrame([test_row])], ignore_index=True)
    else:
        comparison = pd.DataFrame([test_row])
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    comparison.to_csv(RESULTS_DIR / "model_comparison.csv", index=False)

    pred_out = test[["Charging Start Time", TARGET_COL]].copy()
    pred_out["predicted_duration_min_raw"] = y_pred
    pred_out["predicted_duration_min_clipped"] = y_clip
    pred_out["residual_min"] = y_pred - y_true
    pred_out.to_csv(RESULTS_DIR / "test_predictions.csv", index=False)

    fig, ax = plt.subplots(figsize=(6.5, 6.5))
    ax.scatter(y_true, y_pred, s=16, alpha=0.55)
    lim = max(float(np.max(y_true)), float(np.max(y_pred)), 1.0)
    ax.plot([0, lim], [0, lim], color="black", linewidth=1)
    ax.set_xlabel("Actual duration (minutes)")
    ax.set_ylabel("Predicted duration (minutes)")
    ax.set_title(f"Actual vs predicted — {meta['selected_model']}")
    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "actual_vs_predicted.png", dpi=140)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    ax.hist(y_pred - y_true, bins=40, color="#1b4965")
    ax.set_xlabel("Residual (predicted − actual), minutes")
    ax.set_ylabel("Count")
    ax.set_title("Test residual distribution")
    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "residuals.png", dpi=140)
    plt.close(fig)

    training = {}
    summary_path = RESULTS_DIR / "training_summary.json"
    if summary_path.exists():
        training = json.loads(summary_path.read_text(encoding="utf-8"))

    result = {
        "selected_model": meta["selected_model"],
        "selected_params": meta.get("selected_params"),
        "test_metrics_raw": selected,
        "test_metrics_clipped_at_0": selected_clipped,
        "fraction_negative_raw_predictions": float((y_pred < 0).mean()),
        "validation_metrics": training.get("validation"),
        "target_unit": "minutes",
        "n_test": int(len(test)),
        "artifact": str(PIPELINE_PATH),
    }
    (RESULTS_DIR / "test_metrics.json").write_text(
        json.dumps(result, indent=2, default=str), encoding="utf-8"
    )
    _write_report(result)
    print(json.dumps(result["test_metrics_raw"], indent=2))
    return result


def _write_report(result: dict) -> None:
    val = result.get("validation_metrics") or {}
    lines = [
        "# Charging duration evaluation",
        "",
        f"Selected model (lowest validation MAE): **{result['selected_model']}**.",
        "",
        "Metrics are in **minutes** and were computed from model predictions. Raw regression metrics are unclipped.",
        "",
        "## Validation",
        "",
        "```json",
        json.dumps(val, indent=2, default=str),
        "```",
        "",
        "## Untouched test set (selected model)",
        "",
        "```json",
        json.dumps(result["test_metrics_raw"], indent=2),
        "```",
        "",
        f"Share of negative raw predictions: {result['fraction_negative_raw_predictions']}.",
        "Operational predictions from `predict_duration` are clipped at 0 minutes. Clipped test metrics:",
        "",
        "```json",
        json.dumps(result["test_metrics_clipped_at_0"], indent=2),
        "```",
        "",
        "## Limitations",
        "",
        "- 1,320 sessions and about eight weeks of dates are a small sample.",
        "- Duration does not match clock end−start, and energy is nearly uncorrelated with duration, so the table looks noisy or synthetic.",
        "- SOC values above 100% and a few extreme battery capacities were kept.",
        "- A high R² should be read together with MAE in minutes and the median baseline.",
        "- This model does not predict queue length, waiting time, or congestion.",
        "",
        f"Saved pipeline: `{result['artifact']}`",
        "",
    ]
    (RESULTS_DIR / "evaluation_report.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    evaluate()


if __name__ == "__main__":
    main()
