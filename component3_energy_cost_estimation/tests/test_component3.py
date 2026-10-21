"""Tests for the energy table, leakage exclusions, and charging-cost arithmetic."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.calculate_charging_cost import estimate_charging_cost  # noqa: E402
from src.config import LEAKED_COLUMNS, TARGET_COL  # noqa: E402
from src.dataset_checks import find_energy_column, inspect_frame, load_dataset  # noqa: E402
from src.predict_energy import predict_energy  # noqa: E402
from src.prepare_data import prepare  # noqa: E402


def test_energy_table_loads_and_names_the_target():
    frame, path = load_dataset()
    assert path.name == "energy_consumption.csv"
    assert len(frame) == 5000
    assert frame.shape[1] == 16
    assert find_energy_column(list(frame.columns)) == TARGET_COL
    report = inspect_frame(frame, path)
    assert report["target_status"] == "present_in_file"
    assert report["why_training_stopped"] is None
    assert report["label_matches_soc_drop_times_capacity"]["max_abs_kwh"] < 0.02


def test_prepare_excludes_label_rearrangements():
    _train, _val, _test, meta = prepare(save=False)
    assert meta["counts"] == {"train": 3500, "validation": 750, "test": 750}
    for leaked in LEAKED_COLUMNS:
        assert leaked not in meta["feature_columns"]
    assert TARGET_COL not in meta["feature_columns"]
    assert "trip_id" not in meta["feature_columns"]


def test_saved_model_predicts_and_rejects_the_end_state_of_charge():
    frame, _path = load_dataset()
    row = frame.iloc[0].to_dict()
    with pytest.raises(ValueError, match="reconstruct the target"):
        predict_energy(row)
    record = {key: row[key] for key in row if key not in set(LEAKED_COLUMNS) | {TARGET_COL, "trip_id"}}
    result = predict_energy(record)
    assert result["predicted_energy_kwh"] > 0
    assert result["unit"] == "kWh"
    assert result["training_data"] == "synthetic"


def test_cost_known_example_without_hidden_tariff():
    result = estimate_charging_cost(
        12.5,
        40.0,
        currency="LKR",
        tariff_category="domestic",
        extra_fixed_fees=15.0,
    )
    assert result["energy_charge_unrounded"] == pytest.approx(500.0)
    assert result["estimated_total_unrounded"] == pytest.approx(515.0)
    assert result["estimated_total"] == 515.00
    assert result["currency"] == "LKR"
    assert result["tariff_category"] == "domestic"
    assert "tariff_per_kwh" in result


def test_negative_energy_is_rejected():
    with pytest.raises(ValueError, match="greater than or equal to 0"):
        estimate_charging_cost(-1.0, 50.0)
    with pytest.raises(ValueError):
        estimate_charging_cost(10.0, -2.0)


def test_zero_energy_is_a_zero_energy_charge():
    result = estimate_charging_cost(0.0, 87.5, currency="LKR")
    assert result["energy_charge"] == 0.0
    assert result["estimated_total"] == 0.0
