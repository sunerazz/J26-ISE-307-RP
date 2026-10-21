"""Request and response models for the Colombo station recommender."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

FeasibilityStatus = Literal["feasible", "infeasible", "unknown"]
AvailabilityStatus = Literal["unknown", "available", "unavailable"]


class LatLon(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)


class RecommendRequest(BaseModel):
    origin_latitude: float = Field(..., ge=-90, le=90)
    origin_longitude: float = Field(..., ge=-180, le=180)
    destination_latitude: float = Field(..., ge=-90, le=90)
    destination_longitude: float = Field(..., ge=-180, le=180)
    current_soc_percent: float = Field(..., ge=0, le=100)
    usable_battery_capacity_kwh: float = Field(..., gt=0)
    consumption_kwh_per_100km: float = Field(..., gt=0)
    minimum_reserve_percent: float = Field(..., ge=0, le=100)
    required_connector: str | None = None
    maximum_detour_km: float | None = Field(default=None, gt=0)
    energy_to_add_kwh: float | None = Field(default=None, gt=0)
    ranking_weights: dict[str, float] | None = None

    @field_validator("ranking_weights")
    @classmethod
    def _weights_non_negative(cls, value: dict[str, float] | None):
        if value is None:
            return value
        allowed = {"detour_distance", "detour_time", "waiting_time", "tariff"}
        unknown = set(value) - allowed
        if unknown:
            raise ValueError(f"Unknown ranking weights: {sorted(unknown)}")
        if any(weight < 0 for weight in value.values()):
            raise ValueError("Ranking weights must be non-negative.")
        if sum(value.values()) <= 0:
            raise ValueError("At least one ranking weight must be positive.")
        return value


class RouteLeg(BaseModel):
    distance_km: float
    duration_min: float
    provider: str
    # Road shape as [latitude, longitude] pairs from the routing provider.
    # None means the provider did not return a road line. Do not invent one.
    geometry: list[list[float]] | None = None


class BatteryAssessment(BaseModel):
    status: FeasibilityStatus
    estimated_energy_kwh: float | None
    energy_above_reserve_kwh: float | None
    assumptions: list[str]


class StationRecommendation(BaseModel):
    station_id: str
    station_name: str
    address: str
    area: str
    latitude: float
    longitude: float
    rank: int | None
    score: float | None
    included_in_ranking: bool
    exclusion_reason: str | None
    connector_types_listed: list[str]
    connector_compatible: bool | None
    max_power_kw_listed: float | None
    tariff_lkr_per_kwh_listed: float | None
    tariff_status: str
    tariff_raw: str | None
    availability_status: AvailabilityStatus
    queue_length_current: float | None
    waiting_time_min: float | None
    operational_listing: str | None
    confirmed_operational: bool
    origin_to_station: RouteLeg | None
    station_to_destination: RouteLeg | None
    detour_distance_km: float | None
    detour_duration_min: float | None
    battery: BatteryAssessment
    estimated_charging_duration_min: float | None
    estimated_charging_cost_lkr: float | None
    ranking_explanation: str
    source_url: str | None
    source_note: str | None


class RecommendResponse(BaseModel):
    recommended_station: StationRecommendation | None
    alternatives: list[StationRecommendation]
    direct_route: RouteLeg | None
    ranking_formula: str
    weights_used: dict[str, float]
    warnings: list[str]
    data_freshness: str
    limitations: list[str]
    live_availability: bool = False
    live_queue_prediction: bool = False


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    stations_loaded: int
    routing_provider: str
    live_availability: bool = False
    detail: str


class StationListResponse(BaseModel):
    count: int
    stations: list[dict[str, Any]]
    note: str
