"""Run the full reproducible EV queue-length prediction experiment."""

from __future__ import annotations

import json
import subprocess
import sys
from importlib import metadata
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))


def _versions() -> dict:
    pkgs = [
        "pandas",
        "numpy",
        "scikit-learn",
        "xgboost",
        "joblib",
        "matplotlib",
        "pytest",
    ]
    out = {"python": sys.version}
    for name in pkgs:
        try:
            out[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            out[name] = None
    return out


def main() -> None:
    from src.evaluate_model import evaluate
    from src.inspect_data import inspect_dataset, load_raw, write_report
    from src.prepare_data import prepare
    from src.train_queue_model import train

    print("=== Package versions ===")
    versions = _versions()
    print(json.dumps(versions, indent=2))
    (PROJECT_ROOT / "reports").mkdir(parents=True, exist_ok=True)
    with open(PROJECT_ROOT / "reports" / "environment_versions.json", "w", encoding="utf-8") as f:
        json.dump(versions, f, indent=2)

    print("\n=== 1) Inspect data ===")
    report = inspect_dataset(load_raw())
    write_report(report)
    if not report["supports_queue_length_prediction"]:
        raise SystemExit(
            "Dataset does not support a valid future queue-length target. Stopping."
        )

    print("\n=== 2) Prepare data ===")
    prepare(save=True)

    print("\n=== 3) Train models ===")
    train(use_cached_splits=True)

    print("\n=== 4) Evaluate on test set ===")
    evaluate()

    print("\n=== 5) Unit tests ===")
    subprocess.check_call([sys.executable, "-m", "pytest", "-q", "tests"], cwd=PROJECT_ROOT)

    print("\nPipeline complete.")
    print("Key outputs:")
    print(" - reports/dataset_quality_report.md")
    print(" - reports/feature_target_definitions.md")
    print(" - reports/training_summary.json")
    print(" - reports/test_metrics.json")
    print(" - reports/research_results_summary.md")
    print(" - models/best_model.joblib")
    print(" - plots/")


if __name__ == "__main__":
    main()
