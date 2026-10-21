"""Run Component 2 inspection, training, evaluation, and tests."""

from __future__ import annotations

import json
import subprocess
import sys
from importlib import metadata
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))


def main() -> None:
    from src.evaluate_models import evaluate
    from src.inspect_dataset import inspect, load_raw, write_report
    from src.prepare_data import prepare
    from src.train_models import train

    versions = {"python": sys.version}
    for name in (
        "pandas",
        "numpy",
        "scikit-learn",
        "xgboost",
        "joblib",
        "matplotlib",
        "openpyxl",
        "pytest",
    ):
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = None
    (PROJECT_ROOT / "results").mkdir(parents=True, exist_ok=True)
    (PROJECT_ROOT / "results" / "environment_versions.json").write_text(
        json.dumps(versions, indent=2), encoding="utf-8"
    )
    print(json.dumps(versions, indent=2))
    write_report(inspect(load_raw()))
    prepare(save=True)
    train(use_cached_splits=True)
    evaluate()
    subprocess.check_call([sys.executable, "-m", "pytest", "-q", "tests"], cwd=PROJECT_ROOT)


if __name__ == "__main__":
    main()
