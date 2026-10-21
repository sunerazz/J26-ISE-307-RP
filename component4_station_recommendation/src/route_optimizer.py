"""Road-route comparison for a direct trip and station detours."""

from __future__ import annotations

from src.routing_provider import RoutingError, RoutingProvider
from src.schemas import LatLon, RouteLeg


def detour(direct: RouteLeg, via_station_km: float, via_station_min: float) -> tuple[float, float]:
    """Extra road distance and time versus the direct driving route.

    Values are differences of provider results. A small negative detour can
    occur if the via-station path is shorter than the returned direct route.
    """
    return via_station_km - direct.distance_km, via_station_min - direct.duration_min


def route_via_station(
    provider: RoutingProvider,
    origin: LatLon,
    station: LatLon,
    destination: LatLon,
    direct: RouteLeg,
) -> dict:
    to_station = provider.route(origin, station)
    to_destination = provider.route(station, destination)
    extra_km, extra_min = detour(
        direct,
        to_station.distance_km + to_destination.distance_km,
        to_station.duration_min + to_destination.duration_min,
    )
    return {
        "origin_to_station": to_station,
        "station_to_destination": to_destination,
        "detour_distance_km": extra_km,
        "detour_duration_min": extra_min,
        "error": None,
    }


def safe_route_via_station(
    provider: RoutingProvider,
    origin: LatLon,
    station: LatLon,
    destination: LatLon,
    direct: RouteLeg,
) -> dict:
    try:
        return route_via_station(provider, origin, station, destination, direct)
    except RoutingError as exc:
        return {
            "origin_to_station": None,
            "station_to_destination": None,
            "detour_distance_km": None,
            "detour_duration_min": None,
            "error": str(exc),
        }
