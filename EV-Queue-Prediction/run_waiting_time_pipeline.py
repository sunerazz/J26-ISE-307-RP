"""Run Model 2 (waiting-time) end-to-end without overwriting Model 1 artifacts."""

from __future__ import annotations

import json
import subprocess
import sys
from importlib import metadata
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))


def main() -> None:
    from src.evaluate_waiting_time_model import evaluate
    from src.prepare_waiting_time_data import prepare_waiting_time
    from src.train_waiting_time_model import train

    versions = {"python": sys.version}
    for name in (
        "pandas",
        "numpy",
        "scikit-learn",
        "xgboost",
        "joblib",
        "matplotlib",
        "pytest",
    ):
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = None
    (PROJECT_ROOT / "reports").mkdir(parents=True, exist_ok=True)
    with open(
        PROJECT_ROOT / "reports" / "waiting_time_environment_versions.json",
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(versions, f, indent=2)
    print(json.dumps(versions, indent=2))

    print("\n=== Prepare waiting-time data ===")
    prepare_waiting_time(save=True)

    print("\n=== Train waiting-time models ===")
    train(use_cached_splits=True)

    print("\n=== Evaluate waiting-time models ===")
    evaluate()

    print("\n=== Unit tests (waiting-time + existing) ===")
    subprocess.check_call(
        [sys.executable, "-m", "pytest", "-q", "tests"],
        cwd=PROJECT_ROOT,
    )
    print("\nModel 2 waiting-time pipeline complete.")


if __name__ == "__main__":
    main()
