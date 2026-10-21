"""Load the three selected Component 1 model artifacts once at startup."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import joblib

logger = logging.getLogger("api.model_loader")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODELS_DIR = PROJECT_ROOT / "models"
REPORTS_DIR = PROJECT_ROOT / "reports"

# Selected artifacts produced by the training pipelines (do not invent alternatives)
QUEUE_MODEL_PATH = MODELS_DIR / "best_model.joblib"
QUEUE_META_PATH = MODELS_DIR / "best_model_meta.joblib"
WAITING_MODEL_PATH = MODELS_DIR / "waiting_time_best_model.joblib"
WAITING_META_PATH = MODELS_DIR / "waiting_time_best_model_meta.joblib"
CONGESTION_MODEL_PATH = MODELS_DIR / "congestion_best_model.joblib"
CONGESTION_META_PATH = MODELS_DIR / "congestion_best_model_meta.joblib"

FORECAST_HORIZON_MINUTES = 30


@dataclass
class LoadedModel:
    name: str
    path: Path
    meta_path: Path
    artifact: Any = None
    meta: dict = field(default_factory=dict)
    loaded: bool = False
    error: str | None = None


@dataclass
class ModelRegistry:
    queue: LoadedModel
    waiting_time: LoadedModel
    congestion: LoadedModel

    def all_loaded(self) -> bool:
        return self.queue.loaded and self.waiting_time.loaded and self.congestion.loaded

    def status(self) -> dict:
        return {
            "queue": {
                "loaded": self.queue.loaded,
                "path": str(self.queue.path),
                "error": self.queue.error,
                "model_name": self.queue.meta.get("model_name") if self.queue.loaded else None,
                "predictor_kind": self.queue.meta.get("predictor_kind")
                if self.queue.loaded
                else None,
            },
            "waiting_time": {
                "loaded": self.waiting_time.loaded,
                "path": str(self.waiting_time.path),
                "error": self.waiting_time.error,
                "model_name": self.waiting_time.meta.get("model_name")
                if self.waiting_time.loaded
                else None,
                "predictor_kind": self.waiting_time.meta.get("predictor_kind")
                if self.waiting_time.loaded
                else None,
            },
            "congestion": {
                "loaded": self.congestion.loaded,
                "path": str(self.congestion.path),
                "error": self.congestion.error,
                "model_name": self.congestion.meta.get("model_name")
                if self.congestion.loaded
                else None,
                "predictor_kind": self.congestion.meta.get("predictor_kind")
                if self.congestion.loaded
                else None,
            },
        }


_registry: ModelRegistry | None = None


def _load_one(name: str, model_path: Path, meta_path: Path) -> LoadedModel:
    item = LoadedModel(name=name, path=model_path, meta_path=meta_path)
    try:
        if not model_path.exists():
            raise FileNotFoundError(
                f"Missing model artifact: {model_path}. "
                f"Generate it with the corresponding training script."
            )
        if not meta_path.exists():
            raise FileNotFoundError(
                f"Missing model metadata: {meta_path}. "
                f"Generate it with the corresponding training script."
            )
        item.artifact = joblib.load(model_path)
        item.meta = joblib.load(meta_path)
        item.loaded = True
        logger.info("Loaded %s from %s (%s)", name, model_path.name, item.meta.get("model_name"))
    except Exception as exc:  # noqa: BLE001 — surface load errors in /health
        item.loaded = False
        item.error = str(exc)
        logger.exception("Failed to load %s", name)
    return item


def load_registry(force: bool = False) -> ModelRegistry:
    global _registry
    if _registry is not None and not force:
        return _registry
    _registry = ModelRegistry(
        queue=_load_one("queue", QUEUE_MODEL_PATH, QUEUE_META_PATH),
        waiting_time=_load_one("waiting_time", WAITING_MODEL_PATH, WAITING_META_PATH),
        congestion=_load_one("congestion", CONGESTION_MODEL_PATH, CONGESTION_META_PATH),
    )
    return _registry


def get_registry() -> ModelRegistry:
    if _registry is None:
        return load_registry()
    return _registry


def clear_registry() -> None:
    global _registry
    _registry = None


def _read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build_models_catalog(registry: ModelRegistry) -> list[dict]:
    """Metadata + evaluation metrics from existing reports (no fabricated metrics)."""
    queue_metrics = _read_json(REPORTS_DIR / "test_metrics.json") or {}
    wait_metrics = _read_json(REPORTS_DIR / "waiting_time_test_metrics.json") or {}
    cong_metrics = _read_json(REPORTS_DIR / "congestion_test_metrics.json") or {}

    return [
        {
            "key": "queue",
            "name": registry.queue.meta.get("model_name") if registry.queue.loaded else None,
            "artifact": str(QUEUE_MODEL_PATH),
            "prediction_target": "target_queue_length_30min",
            "prediction_horizon_minutes": FORECAST_HORIZON_MINUTES,
            "model_type": "regression",
            "predictor_kind": registry.queue.meta.get("predictor_kind")
            if registry.queue.loaded
            else None,
            "loaded": registry.queue.loaded,
            "evaluation_metrics": queue_metrics.get("test_metrics_selected_raw")
            or queue_metrics.get("test_comparison", {}).get(
                queue_metrics.get("selected_model", ""), None
            ),
            "notes": (
                "Selected overall model from Model 1 validation MAE. "
                "If predictor_kind is persistence, only current_queue_length is used. "
                "Best learned model artifact (unused by default): models/best_ml_model.joblib"
            ),
            "preprocessing_embedded": registry.queue.meta.get("predictor_kind")
            == "sklearn_pipeline",
        },
        {
            "key": "waiting_time",
            "name": registry.waiting_time.meta.get("model_name")
            if registry.waiting_time.loaded
            else None,
            "artifact": str(WAITING_MODEL_PATH),
            "prediction_target": "target_waiting_time_30min_min",
            "prediction_horizon_minutes": FORECAST_HORIZON_MINUTES,
            "model_type": "regression",
            "unit": "minutes",
            "predictor_kind": registry.waiting_time.meta.get("predictor_kind")
            if registry.waiting_time.loaded
            else None,
            "model_version": registry.waiting_time.meta.get("model_version")
            if registry.waiting_time.loaded
            else None,
            "loaded": registry.waiting_time.loaded,
            "evaluation_metrics": wait_metrics.get("test_metrics_selected_raw"),
            "notes": "Sklearn Pipeline includes OneHotEncoder preprocessing fitted on training data.",
            "preprocessing_embedded": True,
        },
        {
            "key": "congestion",
            "name": registry.congestion.meta.get("model_name")
            if registry.congestion.loaded
            else None,
            "artifact": str(CONGESTION_MODEL_PATH),
            "prediction_target": "target_congestion_level_30min",
            "prediction_horizon_minutes": FORECAST_HORIZON_MINUTES,
            "model_type": "classification",
            "classes": registry.congestion.meta.get("classes", ["Low", "Medium", "High"])
            if registry.congestion.loaded
            else ["Low", "Medium", "High"],
            "predictor_kind": registry.congestion.meta.get("predictor_kind")
            if registry.congestion.loaded
            else None,
            "model_version": registry.congestion.meta.get("model_version")
            if registry.congestion.loaded
            else None,
            "loaded": registry.congestion.loaded,
            "evaluation_metrics": {
                "accuracy": (cong_metrics.get("test_metrics_selected") or {}).get("accuracy"),
                "macro_f1": (cong_metrics.get("test_metrics_selected") or {}).get("macro_f1"),
                "n": (cong_metrics.get("test_metrics_selected") or {}).get("n"),
                "per_class": (cong_metrics.get("test_metrics_selected") or {}).get("per_class"),
            },
            "notes": (
                "Sklearn Pipeline includes preprocessing. Labels are synthetic/rule-derived. "
                "XGBoost uses integer class encoding Low=0, Medium=1, High=2."
            ),
            "preprocessing_embedded": True,
        },
    ]
