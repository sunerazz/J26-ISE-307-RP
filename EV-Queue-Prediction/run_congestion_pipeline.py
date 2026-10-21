"""Run Model 3 (congestion) end-to-end without overwriting Models 1–2 artifacts."""

from __future__ import annotations

import json
import subprocess
import sys
from importlib import metadata
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))


def main() -> None:
    from src.evaluate_congestion_model import evaluate
    from src.prepare_congestion_data import prepare_congestion
    from src.train_congestion_model import train

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
        PROJECT_ROOT / "reports" / "congestion_environment_versions.json",
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(versions, f, indent=2)
    print(json.dumps(versions, indent=2))

    print("\n=== Prepare congestion data ===")
    prepare_congestion(save=True)

    print("\n=== Train congestion models ===")
    train(use_cached_splits=True)

    print("\n=== Evaluate congestion models ===")
    evaluate()

    print("\n=== Unit tests ===")
    subprocess.check_call(
        [sys.executable, "-m", "pytest", "-q", "tests"],
        cwd=PROJECT_ROOT,
    )
    print("\nModel 3 congestion pipeline complete.")


if __name__ == "__main__":
    main()
