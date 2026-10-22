"""Road-route comparison for a direct trip and station detours."""

from __future__ import annotations

from dataclasses import dataclass, field

from src.routing_provider import RoutingError, RoutingProvider
from src.schemas import LatLon, RouteLeg


@dataclass
class RoadMatrix:
    """Road km and minutes between named points. A missing pair is None, never a straight line."""

    keys: list[str]
    km: list[list[float | None]]
    minutes: list[list[float | None]]
    provider: str
    requests: int
    index: dict[str, int] = field(init=False)

    def __post_init__(self) -> None:
        self.index = {key: position for position, key in enumerate(self.keys)}

    def leg(self, start: str, end: str) -> tuple[float, float] | None:
        i, j = self.index[start], self.index[end]
        km, minutes = self.km[i][j], self.minutes[i][j]
        if km is None or minutes is None:
            return None
        return km, minutes

    def route_leg(self, start: str, end: str) -> RouteLeg | None:
        leg = self.leg(start, end)
        if leg is None:
            return None
        return RouteLeg(distance_km=leg[0], duration_min=leg[1], provider=self.provider)


def build_matrix(provider: RoutingProvider, points: dict[str, LatLon], pairwise_pairs: list[tuple[str, str]] | None = None) -> RoadMatrix:
    """One table request when the provider supports it; otherwise one route request per needed pair.

    `pairwise_pairs` limits the fallback to the pairs the caller needs, so a provider
    without a table endpoint is not asked for every station-to-station leg.
    """
    keys = list(points)
    size = len(keys)
    table = getattr(provider, "table", None)
    limit = getattr(provider, "max_table_points", None)
    if callable(table) and (limit is None or size <= limit):
        km, minutes = table([points[key] for key in keys])
        return RoadMatrix(keys, km, minutes, provider=f"{provider.name}-table", requests=1)
    km = [[0.0 if i == j else None for j in range(size)] for i in range(size)]
    minutes = [[0.0 if i == j else None for j in range(size)] for i in range(size)]
    wanted = pairwise_pairs or [(a, b) for a in keys for b in keys if a != b]
    requests = 0
    position = {key: i for i, key in enumerate(keys)}
    for start, end in wanted:
        requests += 1
        try:
            leg = provider.route(points[start], points[end])
        except RoutingError:
            continue
        km[position[start]][position[end]] = leg.distance_km
        minutes[position[start]][position[end]] = leg.duration_min
    return RoadMatrix(keys, km, minutes, provider=provider.name, requests=requests)


def detour(direct: RouteLeg, via_station_km: float, via_station_min: float) -> tuple[float, float]:
    """Extra road distance and time versus the direct driving route.

    Values are differences of provider results. A small negative detour can
    occur if the via-station path is shorter than the returned direct route.
    """
    return via_station_km - direct.distance_km, via_station_min - direct.duration_min
