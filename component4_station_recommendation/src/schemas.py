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
    # Multi-stop planner settings. Charging above about 80% is slow on DC chargers.
    max_charge_soc_percent: float = Field(default=80, gt=0, le=100)
    stop_overhead_min: float = Field(default=5, ge=0, le=60)
    max_stops: int = Field(default=4, ge=1, le=8)
    # Road shapes are fetched for this many top-ranked stations; the rest keep table distances only.
    geometry_for_top: int = Field(default=3, ge=1, le=10)

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
    # Listing detail from the rebuilt inventory. None when the listing does not state it.
    city: str | None = None
    province: str | None = None
    number_of_points: int | None = None
    connector_details: list[dict[str, Any]] = []
    usage_type: str | None = None
    access_note: str | None = None
    opening_hours_listed: str | None = None
    phone: str | None = None
    # Power and listed rate of the plug the driver asked for (DC or AC side of the station).
    charging_power_kw: float | None = None
    tariff_for_connector_lkr_per_kwh: float | None = None
    tariff_basis: str | None = None
    # Drive there, charge just enough to finish above the reserve, drive on.
    single_stop: dict[str, Any] | None = None
    # True when no other station is both faster overall and cheaper at listed tariffs.
    pareto_optimal: bool | None = None


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
    charging_plan: dict[str, Any] | None = None
    strategy_comparison: dict[str, Any] | None = None
    routing_summary: dict[str, Any] | None = None
    inventory_summary: dict[str, Any] | None = None


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
