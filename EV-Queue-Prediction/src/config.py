"""Shared configuration for the EV queue-length prediction experiment."""

from pathlib import Path

RANDOM_SEED = 42

# Project paths (repository root = parent of src/)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DATA_PATH = PROJECT_ROOT / "data" / "raw" / "component1_ev_queue_prediction_sri_lanka.csv"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
REPORTS_DIR = PROJECT_ROOT / "reports"
MODELS_DIR = PROJECT_ROOT / "models"
PLOTS_DIR = PROJECT_ROOT / "plots"

# Temporal settings
SAMPLING_INTERVAL_MINUTES = 15
FORECAST_HORIZON_MINUTES = 30
FORECAST_STEPS = FORECAST_HORIZON_MINUTES // SAMPLING_INTERVAL_MINUTES  # 2
TIMESTAMP_TOLERANCE_MINUTES = 0  # exact 30-minute match required for labels

# Chronological split fractions (by unique calendar dates)
TRAIN_FRAC = 0.70
VAL_FRAC = 0.15
TEST_FRAC = 0.15

# Column names in the synthetic CSV
TIMESTAMP_COL = "timestamp"
STATION_COL = "station_id"
QUEUE_COL = "current_queue_length"
TARGET_COL = "target_queue_length_30min"

# Pre-computed future columns in the CSV (never use as model inputs)
CSV_FUTURE_COLUMNS = [
    "target_queue_length_30min",
    "target_waiting_time_30min_min",
    "target_congestion_level_30min",
]

# Features available at prediction time (before lag engineering)
NUMERIC_BASE_FEATURES = [
    "is_weekend",
    "hour",
    "minute",
    "temperature_C",
    "traffic_index",
    "vehicle_arrivals_15min",
    "estimated_arrival_rate_vehicles_per_hour",
    "current_queue_length",
    "queue_after_current_arrivals",
    "total_chargers",
    "active_chargers",
    "available_chargers",
    "busy_chargers",
    "charger_power_kW",
    "average_charging_duration_min",
    "station_utilization",
    "station_load",
    "estimated_waiting_time_now_min",
]

CATEGORICAL_BASE_FEATURES = [
    "station_id",
    "location_type",
    "day_of_week",
    "time_slot",
    "weather_condition",
    "traffic_level",
    "congestion_level_now",
]

# Lag / rolling engineered feature names (created in prepare_data)
ENGINEERED_FEATURES = [
    "queue_lag_1",
    "queue_lag_2",
    "queue_lag_4",
    "queue_roll_mean_4",
    "queue_roll_mean_8",
    "queue_roll_std_4",
    "queue_delta_1",
    "arrivals_lag_1",
    "arrivals_lag_2",
    "arrivals_roll_mean_4",
]

PEAK_HOURS = {7, 8, 9, 17, 18, 19, 20, 21}

# ---------------------------------------------------------------------------
# Model 2 — waiting-time prediction (keeps Model 1 constants unchanged)
# ---------------------------------------------------------------------------
WAIT_COL = "estimated_waiting_time_now_min"
WAITING_TARGET_COL = "target_waiting_time_30min_min"
WAITING_PROCESSED_DIR = PROCESSED_DIR / "waiting_time"
WAITING_MODEL_VERSION = "waiting_time_v1"

WAITING_ENGINEERED_FEATURES = [
    "queue_lag_1",
    "queue_lag_2",
    "queue_lag_4",
    "queue_roll_mean_4",
    "queue_roll_mean_8",
    "queue_roll_std_4",
    "queue_delta_1",
    "arrivals_lag_1",
    "arrivals_lag_2",
    "arrivals_roll_mean_4",
    "wait_lag_1",
    "wait_lag_2",
    "wait_lag_4",
    "wait_roll_mean_4",
    "wait_roll_mean_8",
    "wait_delta_1",
]

# ---------------------------------------------------------------------------
# Model 3 — congestion classification (keeps Models 1–2 constants unchanged)
# ---------------------------------------------------------------------------
CONGESTION_COL = "congestion_level_now"
CONGESTION_TARGET_COL = "target_congestion_level_30min"
CONGESTION_CLASSES = ("Low", "Medium", "High")
CONGESTION_PROCESSED_DIR = PROCESSED_DIR / "congestion"
CONGESTION_MODEL_VERSION = "congestion_v1"

CONGESTION_ENGINEERED_FEATURES = list(WAITING_ENGINEERED_FEATURES)
