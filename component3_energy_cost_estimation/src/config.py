"""Paths and columns for the Component 3 energy model."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
ENERGY_DATA_PATH = RAW_DIR / "energy_consumption.csv"
# The same file as supplied at the workspace root.
DISCOVERED_ENERGY_PATH = PROJECT_ROOT.parent / "component3_energy_consumption.csv"
# Earlier trip file. It has no kWh column and is not the training source.
LEGACY_DATA_PATH = RAW_DIR / "dataset.csv"
DISCOVERED_LEGACY_PATH = PROJECT_ROOT.parent / "dataset.csv"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
MODELS_DIR = PROJECT_ROOT / "models"
RESULTS_DIR = PROJECT_ROOT / "results"
PIPELINE_PATH = MODELS_DIR / "energy_consumption_pipeline.joblib"
META_PATH = MODELS_DIR / "energy_consumption_pipeline_meta.joblib"

RANDOM_SEED = 42
TRAIN_FRACTION = 0.70
VAL_FRACTION = 0.15

TARGET_COL = "energy_consumption_kwh"
ID_COL = "trip_id"

# These reconstruct or rescale the target. They are never model inputs.
LEAKED_COLUMNS = (
    "soc_end_pct",
    "energy_consumption_kwh_per_km",
)

NUMERIC_FEATURES = [
    "distance_km",
    "average_speed_kmh",
    "trip_duration_min",
    "battery_capacity_kwh",
    "soc_start_pct",
    "elevation_gain_m",
    "elevation_loss_m",
    "ambient_temperature_c",
    "ac_on",
    "vehicle_mass_kg",
]
CATEGORICAL_FEATURES = [
    "traffic_level",
    "road_type",
]
FEATURE_COLUMNS = NUMERIC_FEATURES + CATEGORICAL_FEATURES

# Supplied by the caller. Distance, duration, speed, battery size, and start SOC
# come from the routed leg and the trip request.
CONDITION_FEATURES = [
    "elevation_gain_m",
    "elevation_loss_m",
    "ambient_temperature_c",
    "ac_on",
    "traffic_level",
    "road_type",
    "vehicle_mass_kg",
]

ENERGY_COLUMN_CANDIDATES = (
    "energy_consumption_kwh",
    "energy_kwh",
    "Energy Consumed (kWh)",
    "Energy Consumption (kWh)",
    "kWh",
)
