"""Paths and experiment constants for Component 2 only."""

from pathlib import Path

RANDOM_SEED = 42
PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DATA_PATH = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "component2_charging_duration_sri_lanka_5_stations.csv"
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

# The recreated session length is battery × SOC rise / charging rate.
# These four values are known when the driver chooses a charger and a target charge.
NUMERIC_FEATURES = [
    "Battery Capacity (kWh)",
    "Charging Rate (kW)",
    "State of Charge (Start %)",
    "State of Charge (End %)",
]
CATEGORICAL_FEATURES = []

# Not used as model inputs.
EXCLUDED_FEATURES = {
    "Charging Duration (hours)": "Target source column (hours). Converted to minutes; never an input.",
    "Charging Duration (minutes)": "Same target already stored in hours. Not an input.",
    "charging_duration_min": "Modelling target.",
    "Charging End Time": "Set to start time plus the generated duration, so it would reveal the target.",
    "Energy Consumed (kWh)": "Generated as charging rate times duration. It is the same information as the target.",
    "Charging Cost (USD)": "Billing result of the session, not an input available as a duration cause at start.",
    "Illustrative Tariff (LKR/kWh)": "Constant 120 in this table, and not a cause of session length.",
    "Illustrative Charging Cost (LKR)": "Derived from energy and the illustrative tariff. Energy is an outcome.",
    "User ID": "Unique row identifier (1,320 distinct values). Not a generalisable feature.",
    "Station ID": "One-to-one with the place name. Not a model feature.",
    "Charging Station ID": "462 sparse station IDs. Not a model feature.",
    "Charging Start Time": "Used only to order the chronological split, not as a model feature.",
    "Distance Driven (since last charge) (km)": "Not used. This table's duration does not depend on distance.",
    "Vehicle Age (years)": "Not used. This table's duration does not depend on vehicle age.",
    "Vehicle Model": "Not used. Duration is defined from the battery size, not the model name.",
    "Charging Station Location": "Place label only. Duration does not depend on which of the five names is stored.",
    "Station Area": "One-to-one with Charging Station Location. Not a model feature.",
    "Time of Day": "Set from the start clock for the table. Not a cause of the generated duration.",
    "Day of Week": "Set from the start date. Not a cause of the generated duration.",
    "Charger Type": "The charging rate already carries the power. The type name is not a second feature.",
    "User Type": "Not a cause of the generated duration.",
    "Temperature (°C)": "Not a cause of the generated duration. The file header may show a broken degree sign.",
}
