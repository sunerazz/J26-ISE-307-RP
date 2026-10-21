"""Pydantic request/response schemas matching trained Component 1 feature schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

StationId = Literal["ST01", "ST02", "ST03", "ST04", "ST05", "ST06"]
LocationType = Literal["Urban", "Highway", "Suburban"]
DayOfWeek = Literal[
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"
]
TimeSlot = Literal["Overnight", "Morning", "Afternoon", "Evening"]
WeatherCondition = Literal["Clear", "Rainy", "Cloudy"]
TrafficLevel = Literal["Low", "Medium", "High"]
CongestionLevel = Literal["Low", "Medium", "High"]

FORBIDDEN_FUTURE_FIELDS = {
    "target_queue_length_30min",
    "target_waiting_time_30min_min",
    "target_congestion_level_30min",
    "y_true",
    "future_queue",
    "future_waiting_time",
    "future_congestion",
}


class _ForbidFutureMixin(BaseModel):
    """Reject future/target fields that must never be sent to predictors."""

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _reject_future_fields(cls, data):
        if isinstance(data, dict):
            bad = sorted(FORBIDDEN_FUTURE_FIELDS.intersection(data.keys()))
            if bad:
                raise ValueError(
                    "Future/target fields are not allowed as inputs: " + ", ".join(bad)
                )
        return data


class QueuePredictRequest(_ForbidFutureMixin):
    """Request for the selected queue model (persistence: current_queue_length).

    The validation-selected Model 1 artifact is persistence, which only uses
    current_queue_length. station_id and timestamp are included for response
    metadata. Extra ML features are not required for this selected artifact.
    """

    station_id: StationId
    current_queue_length: int = Field(..., ge=0, description="Vehicles waiting now")
    timestamp: datetime | None = Field(
        default=None,
        description="Prediction timestamp (local station snapshot time)",
    )


class StationFeatureRequest(_ForbidFutureMixin):
    """Full prediction-time feature record used by waiting-time and congestion models."""

    # Numeric base
    is_weekend: int = Field(..., ge=0, le=1)
    hour: int = Field(..., ge=0, le=23)
    minute: int = Field(..., ge=0, le=59)
    temperature_C: float
    traffic_index: float = Field(..., ge=0)
    vehicle_arrivals_15min: int = Field(..., ge=0)
    estimated_arrival_rate_vehicles_per_hour: float = Field(..., ge=0)
    current_queue_length: int = Field(..., ge=0)
    queue_after_current_arrivals: int = Field(..., ge=0)
    total_chargers: int = Field(..., ge=1)
    active_chargers: int = Field(..., ge=0)
    available_chargers: int = Field(..., ge=0)
    busy_chargers: int = Field(..., ge=0)
    charger_power_kW: float = Field(..., gt=0)
    average_charging_duration_min: float = Field(..., ge=0)
    station_utilization: float = Field(..., ge=0)
    station_load: float = Field(..., ge=0)
    estimated_waiting_time_now_min: float = Field(..., ge=0)

    # Categorical
    station_id: StationId
    location_type: LocationType
    day_of_week: DayOfWeek
    time_slot: TimeSlot
    weather_condition: WeatherCondition
    traffic_level: TrafficLevel
    congestion_level_now: CongestionLevel

    # Engineered lags (past-only; must be provided by caller / feature service)
    queue_lag_1: float
    queue_lag_2: float
    queue_lag_4: float
    queue_roll_mean_4: float
    queue_roll_mean_8: float
    queue_roll_std_4: float
    queue_delta_1: float
    arrivals_lag_1: float
    arrivals_lag_2: float
    arrivals_roll_mean_4: float
    wait_lag_1: float
    wait_lag_2: float
    wait_lag_4: float
    wait_roll_mean_4: float
    wait_roll_mean_8: float
    wait_delta_1: float

    timestamp: datetime | None = Field(
        default=None,
        description="Prediction timestamp (optional; used for forecast_timestamp)",
    )

    @field_validator("minute")
    @classmethod
    def _minute_quarter(cls, v: int) -> int:
        # Dataset is a 15-minute grid; warn-level enforcement via allowed values
        if v not in (0, 15, 30, 45):
            # Allow other minutes but document convention; soft check only
            pass
        return v


class QueuePredictResponse(BaseModel):
    station_id: str
    prediction_timestamp: str | None
    forecast_timestamp: str | None
    forecast_horizon_minutes: int = 30
    predicted_queue_length: int = Field(
        ...,
        description=(
            "Operational display value: raw prediction clipped at 0 and rounded "
            "to nearest integer (queue counts are non-negative integers)."
        ),
    )
    raw_prediction: float = Field(
        ...,
        description="Unrounded model output before display clipping/rounding.",
    )
    model_name: str | None
    predictor_kind: str | None
    postprocessing: str = (
        "clip_at_0_then_round_half_up_for_display; metrics in training used raw values"
    )


class WaitingTimePredictResponse(BaseModel):
    station_id: str
    prediction_timestamp: str | None
    forecast_timestamp: str | None
    forecast_horizon_minutes: int = 30
    predicted_waiting_time_min: float = Field(
        ...,
        description="Operational waiting time in minutes (clipped at 0).",
    )
    raw_prediction_min: float
    unit: Literal["minutes"] = "minutes"
    model_name: str | None
    model_version: str | None
    postprocessing: str = (
        "clip_at_0_for_operational_response; training metrics used raw predictions"
    )


class CongestionPredictResponse(BaseModel):
    station_id: str
    prediction_timestamp: str | None
    forecast_timestamp: str | None
    forecast_horizon_minutes: int = 30
    predicted_congestion_level: CongestionLevel
    class_probabilities: dict[str, float] | None
    model_name: str | None
    model_version: str | None
    allowed_classes: list[str]


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    forecast_horizon_minutes: int = 30
    all_models_loaded: bool
    models: dict


class ModelsCatalogResponse(BaseModel):
    forecast_horizon_minutes: int = 30
    models: list[dict]


class ErrorResponse(BaseModel):
    detail: str


class StationNowRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    station_id: StationId
    use_current_time: bool = Field(
        default=True,
        description="If true, match a snapshot using the server's current local clock.",
    )
    timestamp: datetime | None = Field(
        default=None,
        description="Optional override clock time used for snapshot matching.",
    )
    include_llm: bool = Field(
        default=True,
        description="If true, generate a human-readable explanation (LLM if configured).",
    )


class StationNowResponse(BaseModel):
    station_id: str
    location_type: str
    requested_local_time: str
    matched_snapshot_timestamp: str
    forecast_horizon_minutes: int = 30
    match_rule: str
    data_note: str
    predictions: dict
    human_summary: str
    llm_used: bool
    explanation_provider: str | None
    observed_now: dict | None = None
    recorded_outcome_30min: dict | None = None
    typical_error: dict | None = None
