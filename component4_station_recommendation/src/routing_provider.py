"""Road-routing providers. Distances come only from a successful provider response."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from src.schemas import LatLon, RouteLeg


class RoutingError(RuntimeError):
    """The routing service did not return a usable road route."""


class RoutingProvider(Protocol):
    name: str

    def route(self, origin: LatLon, destination: LatLon) -> RouteLeg:
        """Return road distance in km and travel time in minutes."""


@dataclass
class OsrmRoutingProvider:
    """OSRM driving routes.

    The public demo at https://router.project-osrm.org has no service guarantee.
    It is rate-limited and is not for production traffic. Set OSRM_BASE_URL to
    your own OSRM server when you have one. This client does not invent a
    distance when the request fails.
    """

    base_url: str | None = None
    timeout_seconds: float = 12.0
    name: str = "osrm"

    def __post_init__(self) -> None:
        configured = self.base_url or os.getenv("OSRM_BASE_URL") or "https://router.project-osrm.org"
        self.base_url = configured.rstrip("/")

    def route(self, origin: LatLon, destination: LatLon) -> RouteLeg:
        url = (
            f"{self.base_url}/route/v1/driving/"
            f"{origin.longitude},{origin.latitude};"
            f"{destination.longitude},{destination.latitude}"
            "?overview=full&geometries=geojson"
        )
        request = Request(url, headers={"User-Agent": "colombo-ev-route-prototype/1.0"})
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                status = getattr(response, "status", 200)
                if status == 429:
                    raise RoutingError(
                        "OSRM rate limit reached (HTTP 429). Wait and retry, or use your own OSRM server."
                    )
                if status >= 400:
                    raise RoutingError(f"OSRM returned HTTP {status}. No road distance was estimated.")
                payload = json.loads(response.read().decode("utf-8"))
        except RoutingError:
            raise
        except HTTPError as exc:
            if exc.code == 429:
                raise RoutingError(
                    "OSRM rate limit reached (HTTP 429). Wait and retry, or use your own OSRM server."
                ) from exc
            raise RoutingError(
                f"OSRM request failed with HTTP {exc.code}. Routing is unavailable; no distance was fabricated."
            ) from exc
        except URLError as exc:
            raise RoutingError(
                "Could not reach the OSRM routing service (network timeout or connection error). "
                "Check internet access and OSRM_BASE_URL. No driving distance was estimated."
            ) from exc
        except TimeoutError as exc:
            raise RoutingError(
                "OSRM timed out. No driving distance was estimated."
            ) from exc
        except json.JSONDecodeError as exc:
            raise RoutingError("OSRM returned a response that was not valid JSON.") from exc
        return parse_osrm_payload(payload, provider=self.name, require_geometry=True)


def _geometry_lat_lon(route: dict) -> list[list[float]] | None:
    geometry = route.get("geometry")
    if not isinstance(geometry, dict):
        return None
    coordinates = geometry.get("coordinates")
    if not isinstance(coordinates, list) or len(coordinates) < 2:
        return None
    points: list[list[float]] = []
    for pair in coordinates:
        if not isinstance(pair, (list, tuple)) or len(pair) < 2:
            return None
        try:
            longitude = float(pair[0])
            latitude = float(pair[1])
        except (TypeError, ValueError):
            return None
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            return None
        points.append([latitude, longitude])
    return points


def parse_osrm_payload(payload: dict, provider: str = "osrm", require_geometry: bool = False) -> RouteLeg:
    if not isinstance(payload, dict):
        raise RoutingError("OSRM response was not an object.")
    code = payload.get("code")
    routes = payload.get("routes") or []
    if code != "Ok" or not routes:
        message = payload.get("message") or code or "no route"
        raise RoutingError(f"OSRM could not produce a road route ({message}).")
    route = routes[0]
    try:
        distance_m = float(route["distance"])
        duration_s = float(route["duration"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RoutingError("OSRM route did not include numeric distance and duration.") from exc
    if distance_m < 0 or duration_s < 0:
        raise RoutingError("OSRM returned a negative distance or duration.")
    geometry = _geometry_lat_lon(route)
    if require_geometry and geometry is None:
        raise RoutingError(
            "OSRM did not return a road geometry. No driving line was estimated."
        )
    return RouteLeg(
        distance_km=distance_m / 1000.0,
        duration_min=duration_s / 60.0,
        provider=provider,
        geometry=geometry,
    )
