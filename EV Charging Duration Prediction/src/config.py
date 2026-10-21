"""Paths and experiment constants for Component 2 only."""

from pathlib import Path

RANDOM_SEED = 42
PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DATA_PATH = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "Component 2 ev_charging_patterns (2).xlsx"
)
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
MODELS_DIR = PROJECT_ROOT / "models"
RESULTS_DIR = PROJECT_ROOT / "results"
PIPELINE_PATH = MODELS_DIR / "charging_duration_pipeline.joblib"
META_PATH = MODELS_DIR / "charging_duration_pipeline_meta.joblib"

TARGET_HOURS_COL = "Charging Duration (hours)"
TARGET_COL = "charging_duration_min"
HOURS_TO_MINUTES = 60.0
START_TIME_COL = "Charging Start Time"

TRAIN_FRAC = 0.70
VAL_FRAC = 0.15
TEST_FRAC = 0.15

# Known at charging start. Temperature column is resolved at runtime
# because the degree symbol in the Excel header is not ASCII-stable.
NUMERIC_FEATURES = [
    "Battery Capacity (kWh)",
    "Charging Rate (kW)",
    "State of Charge (Start %)",
    "Distance Driven (since last charge) (km)",
    "Vehicle Age (years)",
]
CATEGORICAL_FEATURES = [
    "Vehicle Model",
    "Charging Station Location",
    "Time of Day",
    "Day of Week",
    "Charger Type",
    "User Type",
]

# Not used as model inputs.
EXCLUDED_FEATURES = {
    "Charging Duration (hours)": "Target source column (hours). Converted to minutes; never an input.",
    "charging_duration_min": "Modelling target.",
    "Charging End Time": "Known only when the session finishes; would reveal duration.",
    "State of Charge (End %)": "Observed after charging completes.",
    "Energy Consumed (kWh)": "Session energy is an outcome, not known when charging starts. 66 values are missing.",
    "Charging Cost (USD)": "Billing result of the session, not an input available as a duration cause at start.",
    "User ID": "Unique row identifier (1,320 distinct values). Not a generalisable feature.",
    "Charging Station ID": "462 sparse station IDs. Known at start, but too high-cardinality to generalise; excluded.",
    "Charging Start Time": "Used only to order the chronological split, not as a raw model feature. Time of day and day of week are used instead.",
}
