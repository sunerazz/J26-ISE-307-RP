"""Evaluate baselines and the validation-selected model on the untouched test set."""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from src.config import (
    FORECAST_HORIZON_MINUTES,
    MODELS_DIR,
    PEAK_HOURS,
    PLOTS_DIR,
    PROCESSED_DIR,
    PROJECT_ROOT,
    QUEUE_COL,
    REPORTS_DIR,
    STATION_COL,
    TARGET_COL,
    TIMESTAMP_COL,
)
from src.prepare_data import feature_columns


def metrics(y_true, y_pred) -> dict:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    return {
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "rmse": float(np.sqrt(mean_squared_error(y_true, y_pred))),
        "r2": float(r2_score(y_true, y_pred)),
        "n": int(len(y_true)),
    }


def baseline_predict(name: str, artifact: dict, df: pd.DataFrame) -> np.ndarray:
    if name == "persistence":
        return df[QUEUE_COL].to_numpy(dtype=float)
    if name == "historical_median":
        return np.full(len(df), float(artifact["median"]), dtype=float)
    raise ValueError(name)


def _predict_selected(best_artifact, best_meta: dict, test: pd.DataFrame) -> np.ndarray:
    kind = best_meta.get("predictor_kind", "sklearn_pipeline")
    if kind == "sklearn_pipeline":
        return np.asarray(best_artifact.predict(test[feature_columns()]), dtype=float)
    if kind == "persistence":
        return test[QUEUE_COL].to_numpy(dtype=float)
    if kind == "historical_median":
        return np.full(len(test), float(best_artifact["median"]), dtype=float)
    raise ValueError(f"Unknown predictor_kind: {kind}")


def evaluate() -> dict:
    test = pd.read_csv(PROCESSED_DIR / "test.csv", parse_dates=[TIMESTAMP_COL])
    y_true = test[TARGET_COL].to_numpy(dtype=float)

    baselines = joblib.load(MODELS_DIR / "baselines.joblib")
    best_artifact = joblib.load(MODELS_DIR / "best_model.joblib")
    best_meta = joblib.load(MODELS_DIR / "best_model_meta.joblib")

    X_test = test[feature_columns()]
    y_best = _predict_selected(best_artifact, best_meta, test)
    # Operational non-negativity for reporting of clipped predictions (metrics use raw)
    y_best_clip = np.maximum(y_best, 0.0)

    results = {
        "experiment_label": "SIMULATION-BASED",
        "selected_model": best_meta["model_name"],
        "selected_params": best_meta.get("params"),
        "best_ml_model_by_validation": best_meta.get("best_ml_model"),
        "test_metrics_selected_raw": metrics(y_true, y_best),
        "test_metrics_selected_clipped_at_0": metrics(y_true, y_best_clip),
        "interpretation": (
            "Model outputs are continuous estimates of queue length. "
            "Regression metrics above use raw (possibly fractional) predictions. "
            "For operational display, round to nearest integer and clip at 0. "
            "High R² alone is not sufficient; compare MAE/RMSE to baselines."
        ),
        "baselines_test": {},
        "by_station": {},
        "by_peak": {},
    }

    for name, art in baselines.items():
        pred = baseline_predict(name, art, test)
        results["baselines_test"][name] = metrics(y_true, pred)

    # Full comparison table (selection already finalized on validation)
    comparison = {
        "persistence": results["baselines_test"]["persistence"],
        "historical_median": results["baselines_test"]["historical_median"],
    }
    for model_file, label in (
        ("random_forest.joblib", "random_forest"),
        ("xgboost.joblib", "xgboost"),
    ):
        path = MODELS_DIR / model_file
        if path.exists():
            pipe = joblib.load(path)
            comparison[label] = metrics(y_true, pipe.predict(X_test))
    results["test_comparison"] = comparison

    # Sensitivity: exclude extreme synthetic station ST05
    no_st05 = test[test[STATION_COL] != "ST05"]
    if len(no_st05):
        results["persistence_test_metrics_excluding_ST05"] = metrics(
            no_st05[TARGET_COL], no_st05[QUEUE_COL]
        )

    # Best ML model diagnostics (even if overall winner is a baseline)
    best_ml_path = MODELS_DIR / "best_ml_model.joblib"
    if best_ml_path.exists():
        y_ml = joblib.load(best_ml_path).predict(X_test)
        results["best_ml_test_metrics"] = metrics(y_true, y_ml)
        test_ml = test.copy()
        test_ml["y_pred_ml"] = y_ml
        results["best_ml_by_station"] = {
            str(sid): metrics(g[TARGET_COL], g["y_pred_ml"])
            for sid, g in test_ml.groupby(STATION_COL)
        }
        no_st05_ml = test_ml[test_ml[STATION_COL] != "ST05"]
        if len(no_st05_ml):
            results["best_ml_test_metrics_excluding_ST05"] = metrics(
                no_st05_ml[TARGET_COL], no_st05_ml["y_pred_ml"]
            )

    # Per station for selected overall model
    test = test.copy()
    test["y_pred"] = y_best
    test["error"] = test["y_pred"] - test[TARGET_COL]
    test["abs_error"] = test["error"].abs()
    for station_id, g in test.groupby(STATION_COL):
        results["by_station"][str(station_id)] = metrics(
            g[TARGET_COL], g["y_pred"]
        )

    peak = test["hour"].isin(PEAK_HOURS)
    results["by_peak"]["peak"] = metrics(
        test.loc[peak, TARGET_COL], test.loc[peak, "y_pred"]
    )
    results["by_peak"]["off_peak"] = metrics(
        test.loc[~peak, TARGET_COL], test.loc[~peak, "y_pred"]
    )
    results["peak_hours_definition"] = sorted(PEAK_HOURS)
    results["error_distribution"] = {
        "mean_error": float(test["error"].mean()),
        "std_error": float(test["error"].std()),
        "median_abs_error": float(test["abs_error"].median()),
        "p90_abs_error": float(test["abs_error"].quantile(0.90)),
        "p95_abs_error": float(test["abs_error"].quantile(0.95)),
        "min_error": float(test["error"].min()),
        "max_error": float(test["error"].max()),
        "fraction_negative_raw_preds": float((y_best < 0).mean()),
    }

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(REPORTS_DIR / "test_metrics.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)

    pred_out = test[
        [TIMESTAMP_COL, STATION_COL, QUEUE_COL, TARGET_COL, "y_pred", "error", "abs_error", "hour"]
    ].copy()
    pred_out["forecast_timestamp"] = pred_out[TIMESTAMP_COL] + pd.Timedelta(
        minutes=FORECAST_HORIZON_MINUTES
    )
    pred_out.to_csv(PROCESSED_DIR / "test_predictions.csv", index=False)

    _make_plots(test, y_true, y_best, best_meta["model_name"])
    # Also plot best ML model if different from overall selected
    if (MODELS_DIR / "best_ml_model.joblib").exists() and best_meta.get(
        "best_ml_model"
    ) not in {None, best_meta["model_name"]}:
        y_ml = joblib.load(MODELS_DIR / "best_ml_model.joblib").predict(X_test)
        test_ml_plot = test.copy()
        test_ml_plot["y_pred"] = y_ml
        _make_plots(
            test_ml_plot,
            y_true,
            y_ml,
            best_meta["best_ml_model"],
            prefix="best_ml_",
        )
    _write_results_summary(results)
    print(json.dumps(results["test_comparison"], indent=2))
    print(f"Selected overall test metrics: {results['test_metrics_selected_raw']}")
    if "best_ml_test_metrics" in results:
        print(f"Best ML test metrics: {results['best_ml_test_metrics']}")
    return results


def _make_plots(
    test: pd.DataFrame,
    y_true,
    y_pred,
    model_name: str,
    prefix: str = "",
) -> None:
    # Scatter
    fig, ax = plt.subplots(figsize=(7, 7))
    ax.scatter(y_true, y_pred, alpha=0.15, s=8, edgecolors="none")
    lim = max(float(np.max(y_true)), float(np.max(y_pred)), 1.0)
    ax.plot([0, lim], [0, lim], color="black", linewidth=1, label="ideal")
    ax.set_xlabel("Actual queue length (+30 min)")
    ax.set_ylabel("Predicted queue length (+30 min)")
    ax.set_title(f"Actual vs Predicted — {model_name} (test)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / f"{prefix}actual_vs_predicted_scatter.png", dpi=140)
    plt.close(fig)

    # Error histogram
    fig, ax = plt.subplots(figsize=(8, 4))
    errors = y_pred - y_true
    ax.hist(errors, bins=60, color="#2c6e49", alpha=0.85)
    ax.set_xlabel("Prediction error (pred - actual)")
    ax.set_ylabel("Count")
    ax.set_title(f"Test error distribution — {model_name}")
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / f"{prefix}error_distribution.png", dpi=140)
    plt.close(fig)

    # Time series for representative stations / period
    stations = sorted(test[STATION_COL].unique())
    # Prefer a moderate-queue station if present
    preferred = [s for s in ("ST01", "ST02", "ST06", "ST04") if s in stations]
    plot_stations = (preferred + stations)[:2]
    # Use first 7 days of test for readability
    t0 = test[TIMESTAMP_COL].min()
    t1 = t0 + pd.Timedelta(days=7)
    window = test[(test[TIMESTAMP_COL] >= t0) & (test[TIMESTAMP_COL] < t1)]

    fig, axes = plt.subplots(len(plot_stations), 1, figsize=(11, 3.2 * len(plot_stations)), sharex=True)
    if len(plot_stations) == 1:
        axes = [axes]
    for ax, sid in zip(axes, plot_stations):
        g = window[window[STATION_COL] == sid].sort_values(TIMESTAMP_COL)
        ax.plot(g[TIMESTAMP_COL], g[TARGET_COL], label="Actual (+30m)", linewidth=1.5)
        ax.plot(g[TIMESTAMP_COL], g["y_pred"], label="Predicted", linewidth=1.2, alpha=0.85)
        ax.set_ylabel("Queue length")
        ax.set_title(f"Station {sid} — first 7 test days")
        ax.legend(loc="upper right")
    axes[-1].set_xlabel("Prediction timestamp")
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / f"{prefix}timeseries_actual_vs_predicted.png", dpi=140)
    plt.close(fig)

    # ST05 overlay if extreme station exists (limitation visualization)
    if "ST05" in stations:
        g = window[window[STATION_COL] == "ST05"].sort_values(TIMESTAMP_COL)
        if len(g):
            fig, ax = plt.subplots(figsize=(11, 3.5))
            ax.plot(g[TIMESTAMP_COL], g[TARGET_COL], label="Actual (+30m)")
            ax.plot(g[TIMESTAMP_COL], g["y_pred"], label="Predicted", alpha=0.85)
            ax.set_title(
                f"Station ST05 (extreme synthetic queues) — {model_name}, first 7 test days"
            )
            ax.set_ylabel("Queue length")
            ax.legend()
            fig.tight_layout()
            fig.savefig(PLOTS_DIR / f"{prefix}timeseries_st05_extreme.png", dpi=140)
            plt.close(fig)


def _write_results_summary(results: dict) -> None:
    lines = [
        "# Research Results Summary — Queue Length Prediction (Component 1)",
        "",
        "## Verdict",
        "",
        f"This is a **simulation-based** experiment on synthetic EV charging snapshots. "
        f"The validation-selected **overall** method is **{results['selected_model']}**.",
        "",
        f"Best learned model by validation MAE: **{results.get('best_ml_model_by_validation')}**.",
        "",
        "## Test metrics (selected overall method, raw predictions)",
        "",
        "```json",
        json.dumps(results["test_metrics_selected_raw"], indent=2),
        "```",
        "",
        "## Baseline vs ML comparison (test)",
        "",
        "```json",
        json.dumps(results["test_comparison"], indent=2),
        "```",
        "",
        "## Best ML model (test)",
        "",
        "```json",
        json.dumps(
            {
                "persistence_test_metrics_excluding_ST05": results.get(
                    "persistence_test_metrics_excluding_ST05"
                ),
                "best_ml_test_metrics": results.get("best_ml_test_metrics"),
                "best_ml_test_metrics_excluding_ST05": results.get(
                    "best_ml_test_metrics_excluding_ST05"
                ),
                "best_ml_by_station": results.get("best_ml_by_station"),
            },
            indent=2,
        ),
        "```",
        "",
        "## Performance by station (selected overall method)",
        "",
        "```json",
        json.dumps(results["by_station"], indent=2),
        "```",
        "",
        "## Peak vs off-peak",
        "",
        f"Peak hours: {results['peak_hours_definition']}",
        "",
        "```json",
        json.dumps(results["by_peak"], indent=2),
        "```",
        "",
        "## Limitations",
        "",
        "- Synthetic labels/features; not independently observed real-world queues.",
        "- Does **not** predict waiting time or congestion (separate future tasks).",
        "- Station ST05 has extreme synthetic queue magnitudes that dominate ML absolute errors.",
        "- On this 15-minute synthetic grid, queue length is strongly autocorrelated at +30 minutes, "
        "so a persistence baseline can outperform complex models.",
        "- Pre-computed CSV target differed from observational `current_queue_length@t+30`; "
        "this study uses the reconstructed observational target.",
        "- High R² can coexist with operationally meaningful absolute errors; always read MAE/RMSE vs baselines.",
        "",
        "## Plots",
        "",
        "- `plots/actual_vs_predicted_scatter.png`",
        "- `plots/error_distribution.png`",
        "- `plots/timeseries_actual_vs_predicted.png`",
        "- `plots/best_ml_*` figures when the overall winner differs from the best ML model",
        "",
    ]
    (REPORTS_DIR / "research_results_summary.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )


def main() -> None:
    evaluate()


if __name__ == "__main__":
    import sys

    sys.path.insert(0, str(PROJECT_ROOT))
    main()
