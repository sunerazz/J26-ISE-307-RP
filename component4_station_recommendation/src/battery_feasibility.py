"""Approximate whether the current battery can reach a station by road."""

from __future__ import annotations

from src.schemas import BatteryAssessment


def assess_reachability(
    route_distance_km: float | None,
    current_soc_percent: float,
    usable_battery_capacity_kwh: float,
    consumption_kwh_per_100km: float,
    minimum_reserve_percent: float,
) -> BatteryAssessment:
    """Compare road energy need with energy above the requested reserve.

    estimated_energy_kwh = route_distance_km * consumption_kwh_per_100km / 100

    This is an approximation. It is not a guarantee of arrival. It ignores
    traffic, hills beyond the consumption figure, temperature, and battery limits.
    """
    assumptions = [
        "Energy use is proportional to road distance and the supplied kWh/100 km figure.",
        "Only energy above the minimum reserve is treated as available for driving to the station.",
        "This does not certify that the vehicle can safely arrive.",
    ]
    if route_distance_km is None:
        return BatteryAssessment(
            status="unknown",
            estimated_energy_kwh=None,
            energy_above_reserve_kwh=None,
            assumptions=assumptions + ["Road distance is missing, so feasibility is unknown."],
        )
    if route_distance_km < 0 or consumption_kwh_per_100km <= 0 or usable_battery_capacity_kwh <= 0:
        return BatteryAssessment(
            status="unknown",
            estimated_energy_kwh=None,
            energy_above_reserve_kwh=None,
            assumptions=assumptions + ["Inputs are not usable, so feasibility is unknown."],
        )
    energy_kwh = route_distance_km * consumption_kwh_per_100km / 100.0
    available_kwh = usable_battery_capacity_kwh * current_soc_percent / 100.0
    reserve_kwh = usable_battery_capacity_kwh * minimum_reserve_percent / 100.0
    above_reserve = available_kwh - reserve_kwh
    status = "feasible" if energy_kwh <= above_reserve else "infeasible"
    return BatteryAssessment(
        status=status,
        estimated_energy_kwh=energy_kwh,
        energy_above_reserve_kwh=above_reserve,
        assumptions=assumptions,
    )
