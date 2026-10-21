"""Evaluate Model 2 waiting-time predictors on the untouched chronological test set."""

from __future__ import annotations

import json

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
    PROJECT_ROOT,
    REPORTS_DIR,
    STATION_COL,
    TIMESTAMP_COL,
    WAIT_COL,
    WAITING_PROCESSED_DIR,
    WAITING_TARGET_COL,
)
from src.prepare_waiting_time_data import waiting_feature_columns


def metrics(y_true, y_pred) -> dict:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    return {
        "mae_min": float(mean_absolute_error(y_true, y_pred)),
        "rmse_min": float(np.sqrt(mean_squared_error(y_true, y_pred))),
        "r2": float(r2_score(y_true, y_pred)),
        "n": int(len(y_true)),
    }


def _predict_selected(artifact, meta: dict, test: pd.DataFrame) -> np.ndarray:
    kind = meta.get("predictor_kind", "sklearn_pipeline")
    if kind == "sklearn_pipeline":
        return np.asarray(
            artifact.predict(test[waiting_feature_columns()]), dtype=float
        )
    if kind == "persistence":
        return test[WAIT_COL].to_numpy(dtype=float)
    if kind == "historical_median":
        return np.full(len(test), float(artifact["median"]), dtype=float)
    raise ValueError(f"Unknown predictor_kind: {kind}")


def evaluate() -> dict:
    test = pd.read_csv(
        WAITING_PROCESSED_DIR / "test.csv", parse_dates=[TIMESTAMP_COL]
    )
    y_true = test[WAITING_TARGET_COL].to_numpy(dtype=float)
    X_test = test[waiting_feature_columns()]

    baselines = joblib.load(MODELS_DIR / "waiting_time_baselines.joblib")
    best_artifact = joblib.load(MODELS_DIR / "waiting_time_best_model.joblib")
    best_meta = joblib.load(MODELS_DIR / "waiting_time_best_model_meta.joblib")

    y_best = _predict_selected(best_artifact, best_meta, test)
    y_best_clip = np.maximum(y_best, 0.0)

    results = {
        "experiment_label": "SIMULATION-BASED",
        "task": "waiting_time_30min",
        "target_unit": "minutes",
        "selected_model": best_meta["model_name"],
        "model_version": best_meta.get("model_version"),
        "selected_params": best_meta.get("params"),
        "best_ml_model_by_validation": best_meta.get("best_ml_model"),
        "test_metrics_selected_raw": metrics(y_true, y_best),
        "test_metrics_selected_clipped_at_0": metrics(y_true, y_best_clip),
        "interpretation": (
            "Predictions are continuous waiting times in minutes. "
            "Raw regression metrics use unclipped (possibly fractional/negative) "
            "outputs. For operational display, clip at 0 and optionally round. "
            "R² is not percentage accuracy."
        ),
        "baselines_test": {},
        "by_station": {},
        "by_peak": {},
        "zero_and_long_wait_analysis": {},
    }

    results["baselines_test"]["persistence"] = metrics(
        y_true, test[WAIT_COL].to_numpy(dtype=float)
    )
    results["baselines_test"]["historical_median"] = metrics(
        y_true,
        np.full(len(test), float(baselines["historical_median"]["median"])),
    )

    comparison = {
        "persistence": results["baselines_test"]["persistence"],
        "historical_median": results["baselines_test"]["historical_median"],
    }
    for fname, label in (
        ("waiting_time_random_forest.joblib", "random_forest"),
        ("waiting_time_xgboost.joblib", "xgboost"),
    ):
        path = MODELS_DIR / fname
        if path.exists():
            comparison[label] = metrics(y_true, joblib.load(path).predict(X_test))
    results["test_comparison"] = comparison

    # Append test metrics to comparison CSV without overwriting Model 1 files
    rows = []
    for name, m in comparison.items():
        rows.append(
            {
                "split": "test",
                "model": name,
                "mae_min": m["mae_min"],
                "rmse_min": m["rmse_min"],
                "r2": m["r2"],
                "n": m["n"],
            }
        )
    val_csv = REPORTS_DIR / "waiting_time_model_comparison.csv"
    if val_csv.exists():
        prev = pd.read_csv(val_csv)
        prev = prev[prev["split"] != "test"]
        out = pd.concat([prev, pd.DataFrame(rows)], ignore_index=True)
    else:
        out = pd.DataFrame(rows)
    out.to_csv(val_csv, index=False)

    best_ml_path = MODELS_DIR / "waiting_time_best_ml_model.joblib"
    if best_ml_path.exists():
        y_ml = joblib.load(best_ml_path).predict(X_test)
        results["best_ml_test_metrics"] = metrics(y_true, y_ml)
        test_ml = test.copy()
        test_ml["y_pred_ml"] = y_ml
        results["best_ml_by_station"] = {
            str(sid): metrics(g[WAITING_TARGET_COL], g["y_pred_ml"])
            for sid, g in test_ml.groupby(STATION_COL)
        }
        no_st05 = test_ml[test_ml[STATION_COL] != "ST05"]
        if len(no_st05):
            results["best_ml_test_metrics_excluding_ST05"] = metrics(
                no_st05[WAITING_TARGET_COL], no_st05["y_pred_ml"]
            )
            results["persistence_test_metrics_excluding_ST05"] = metrics(
                no_st05[WAITING_TARGET_COL], no_st05[WAIT_COL]
            )

    test = test.copy()
    test["y_pred"] = y_best
    test["error"] = test["y_pred"] - test[WAITING_TARGET_COL]
    test["abs_error"] = test["error"].abs()

    for sid, g in test.groupby(STATION_COL):
        results["by_station"][str(sid)] = metrics(g[WAITING_TARGET_COL], g["y_pred"])

    peak = test["hour"].isin(PEAK_HOURS)
    results["by_peak"]["peak"] = metrics(
        test.loc[peak, WAITING_TARGET_COL], test.loc[peak, "y_pred"]
    )
    results["by_peak"]["off_peak"] = metrics(
        test.loc[~peak, WAITING_TARGET_COL], test.loc[~peak, "y_pred"]
    )
    results["peak_hours_definition"] = sorted(PEAK_HOURS)

    zero_mask = test[WAITING_TARGET_COL] == 0
    long_mask = test[WAITING_TARGET_COL] >= 60
    results["zero_and_long_wait_analysis"] = {
        "n_zero_actual": int(zero_mask.sum()),
        "fraction_zero_actual": float(zero_mask.mean()),
        "metrics_on_zero_actual": metrics(
            test.loc[zero_mask, WAITING_TARGET_COL], test.loc[zero_mask, "y_pred"]
        )
        if zero_mask.any()
        else None,
        "n_long_wait_ge_60min": int(long_mask.sum()),
        "fraction_long_wait_ge_60min": float(long_mask.mean()),
        "metrics_on_long_wait_ge_60min": metrics(
            test.loc[long_mask, WAITING_TARGET_COL], test.loc[long_mask, "y_pred"]
        )
        if long_mask.any()
        else None,
        "actual_max_min": float(test[WAITING_TARGET_COL].max()),
        "note": "Difficult cases retained; no selective deletion for better scores.",
    }

    results["error_distribution"] = {
        "mean_error_min": float(test["error"].mean()),
        "std_error_min": float(test["error"].std()),
        "median_abs_error_min": float(test["abs_error"].median()),
        "p90_abs_error_min": float(test["abs_error"].quantile(0.90)),
        "p95_abs_error_min": float(test["abs_error"].quantile(0.95)),
        "min_error_min": float(test["error"].min()),
        "max_error_min": float(test["error"].max()),
        "fraction_negative_raw_preds": float((y_best < 0).mean()),
    }

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(REPORTS_DIR / "waiting_time_test_metrics.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)

    pred_out = test[
        [
            TIMESTAMP_COL,
            STATION_COL,
            WAIT_COL,
            WAITING_TARGET_COL,
            "y_pred",
            "error",
            "abs_error",
            "hour",
        ]
    ].copy()
    pred_out["forecast_timestamp"] = pred_out[TIMESTAMP_COL] + pd.Timedelta(
        minutes=FORECAST_HORIZON_MINUTES
    )
    pred_out.to_csv(WAITING_PROCESSED_DIR / "test_predictions.csv", index=False)

    _make_plots(test, y_true, y_best, best_meta["model_name"])
    if best_ml_path.exists() and best_meta.get("best_ml_model") not in {
        None,
        best_meta["model_name"],
    }:
        y_ml = joblib.load(best_ml_path).predict(X_test)
        test_ml_plot = test.copy()
        test_ml_plot["y_pred"] = y_ml
        _make_plots(
            test_ml_plot,
            y_true,
            y_ml,
            best_meta["best_ml_model"],
            prefix="waiting_time_best_ml_",
        )

    _write_evaluation_md(results)
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
    prefix: str = "waiting_time_",
) -> None:
    fig, ax = plt.subplots(figsize=(7, 7))
    ax.scatter(y_true, y_pred, alpha=0.15, s=8, edgecolors="none")
    lim = max(float(np.max(y_true)), float(np.max(y_pred)), 1.0)
    ax.plot([0, lim], [0, lim], color="black", linewidth=1, label="ideal")
    ax.set_xlabel("Actual waiting time +30 min (minutes)")
    ax.set_ylabel("Predicted waiting time +30 min (minutes)")
    ax.set_title(f"Waiting time — actual vs predicted ({model_name}, test)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / f"{prefix}actual_vs_predicted.png", dpi=140)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.hist(y_pred - y_true, bins=60, color="#1b4965", alpha=0.85)
    ax.set_xlabel("Residual (pred - actual), minutes")
    ax.set_ylabel("Count")
    ax.set_title(f"Waiting-time residuals — {model_name}")
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / f"{prefix}residuals.png", dpi=140)
    plt.close(fig)

    stations = sorted(test[STATION_COL].unique())
    preferred = [s for s in ("ST01", "ST02", "ST06", "ST04") if s in stations]
    plot_stations = (preferred + stations)[:2]
    t0 = test[TIMESTAMP_COL].min()
    window = test[
        (test[TIMESTAMP_COL] >= t0)
        & (test[TIMESTAMP_COL] < t0 + pd.Timedelta(days=7))
    ]

    fig, axes = plt.subplots(
        len(plot_stations), 1, figsize=(11, 3.2 * len(plot_stations)), sharex=True
    )
    if len(plot_stations) == 1:
        axes = [axes]
    for ax, sid in zip(axes, plot_stations):
        g = window[window[STATION_COL] == sid].sort_values(TIMESTAMP_COL)
        ax.plot(
            g[TIMESTAMP_COL],
            g[WAITING_TARGET_COL],
            label="Actual wait (+30m)",
            linewidth=1.5,
        )
        ax.plot(
            g[TIMESTAMP_COL], g["y_pred"], label="Predicted", linewidth=1.2, alpha=0.85
        )
        ax.set_ylabel("Minutes")
        ax.set_title(f"Station {sid} — waiting time, first 7 test days")
        ax.legend(loc="upper right")
    axes[-1].set_xlabel("Prediction timestamp")
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / f"{prefix}test_timeseries.png", dpi=140)
    plt.close(fig)

    if "ST05" in stations:
        g = window[window[STATION_COL] == "ST05"].sort_values(TIMESTAMP_COL)
        if len(g):
            fig, ax = plt.subplots(figsize=(11, 3.5))
            ax.plot(g[TIMESTAMP_COL], g[WAITING_TARGET_COL], label="Actual (+30m)")
            ax.plot(g[TIMESTAMP_COL], g["y_pred"], label="Predicted", alpha=0.85)
            ax.set_title(f"ST05 waiting time — {model_name}, first 7 test days")
            ax.set_ylabel("Minutes")
            ax.legend()
            fig.tight_layout()
            fig.savefig(PLOTS_DIR / f"{prefix}st05_timeseries.png", dpi=140)
            plt.close(fig)


def _write_evaluation_md(results: dict) -> None:
    lines = [
        "# Waiting-Time Model Evaluation (Model 2)",
        "",
        "## Dataset and target validation",
        "",
        "- **Experiment label:** SIMULATION-BASED (synthetic CSV).",
        "- Waiting column `estimated_waiting_time_now_min` is an **estimated** "
        "station-level waiting time in minutes (not a measured "
        "arrival→charging-start event duration from a session log).",
        "- Target `target_waiting_time_30min_min` reconstructed as same-station "
        "`estimated_waiting_time_now_min` exactly 30 minutes later.",
        "- CSV pre-computed waiting target matched this reconstruction at 100% "
        "on valid pairs; end-of-series unmatched rows were dropped (not zero-filled).",
        "- This is a **station-level 30-minute-ahead forecast**, not a per-vehicle "
        "session waiting-time model.",
        "",
        "## Selected models",
        "",
        f"- Overall (validation MAE): **{results['selected_model']}** "
        f"(version `{results.get('model_version')}`)",
        f"- Best learned model: **{results.get('best_ml_model_by_validation')}**",
        "",
        "## Test metrics — selected overall method (raw predictions, minutes)",
        "",
        "```json",
        json.dumps(results["test_metrics_selected_raw"], indent=2),
        "```",
        "",
        "## Baseline vs Random Forest vs XGBoost (test)",
        "",
        "```json",
        json.dumps(results["test_comparison"], indent=2),
        "```",
        "",
        "## Best ML diagnostics",
        "",
        "```json",
        json.dumps(
            {
                "best_ml_test_metrics": results.get("best_ml_test_metrics"),
                "best_ml_test_metrics_excluding_ST05": results.get(
                    "best_ml_test_metrics_excluding_ST05"
                ),
                "persistence_test_metrics_excluding_ST05": results.get(
                    "persistence_test_metrics_excluding_ST05"
                ),
            },
            indent=2,
        ),
        "```",
        "",
        "## By station / peak / zero & long waits",
        "",
        "```json",
        json.dumps(
            {
                "by_station": results["by_station"],
                "by_peak": results["by_peak"],
                "zero_and_long_wait_analysis": results["zero_and_long_wait_analysis"],
                "error_distribution": results["error_distribution"],
            },
            indent=2,
        ),
        "```",
        "",
        "## Leakage prevention",
        "",
        "- Features limited to information available at the prediction timestamp.",
        "- Future waiting/queue/congestion labels excluded from inputs.",
        "- Lags/rolling windows computed per station on past rows only.",
        "- Preprocessing fitted on training data only.",
        "- Model selection on validation; test evaluated once.",
        "",
        "## Limitations",
        "",
        "- Synthetic/estimated waiting times; not independently observed real-world waits.",
        "- Does **not** predict queue length or congestion (separate tasks).",
        "- ST05 waiting times are frequently capped near 240 minutes.",
        "- Strong autocorrelation at +30 minutes can favour persistence on this grid.",
        "",
        "## Artifacts",
        "",
        "- `models/waiting_time_best_model.joblib`",
        "- `models/waiting_time_random_forest.joblib`",
        "- `models/waiting_time_xgboost.joblib`",
        "- `plots/waiting_time_actual_vs_predicted.png`",
        "- `plots/waiting_time_residuals.png`",
        "- `plots/waiting_time_test_timeseries.png`",
        "- `reports/waiting_time_model_comparison.csv`",
        "",
    ]
    (REPORTS_DIR / "waiting_time_evaluation.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )


def main() -> None:
    evaluate()


if __name__ == "__main__":
    import sys

    sys.path.insert(0, str(PROJECT_ROOT))
    main()
