"""Trip conditions for the energy model, read from free public services.

- Weather now at the start point: Open-Meteo forecast API (no key).
- Ground elevation along the routed road: Open-Meteo elevation API (90 m DEM, no key).
- Traffic level and road type follow stated rules; the app can override both.

A service that fails leaves its values missing. Nothing is filled with a default
except where a rule is stated in `notes`.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

logger = logging.getLogger("integration.conditions")

WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
ELEVATION_URL = "https://api.open-meteo.com/v1/elevation"
USER_AGENT = "ev-decision-support/1.0 (research prototype)"
# Rises and falls smaller than this between samples are treated as DEM noise.
ELEVATION_NOISE_M = 2.0
MAX_ELEVATION_POINTS = 100

# WMO weather interpretation codes used by Open-Meteo.
WEATHER_TEXT = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Fog",
    51: "Light drizzle",
    53: "Drizzle",
    55: "Heavy drizzle",
    61: "Light rain",
    63: "Rain",
    65: "Heavy rain",
    80: "Rain showers",
    81: "Rain showers",
    82: "Violent rain showers",
    95: "Thunderstorm",
    96: "Thunderstorm with hail",
    99: "Thunderstorm with hail",
}


def _get(url: str, timeout: float) -> dict:
    with urlopen(Request(url, headers={"User-Agent": USER_AGENT}), timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_weather(latitude: float, longitude: float, timeout: float = 6.0) -> dict[str, Any] | None:
    url = (
        f"{WEATHER_URL}?latitude={latitude:.4f}&longitude={longitude:.4f}"
        "&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m,is_day&timezone=Asia%2FColombo"
    )
    try:
        current = _get(url, timeout).get("current") or {}
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        logger.warning("Weather lookup failed: %s", exc)
        return None
    if current.get("temperature_2m") is None:
        return None
    code = current.get("weather_code")
    return {
        "temperature_c": float(current["temperature_2m"]),
        "humidity_percent": current.get("relative_humidity_2m"),
        "wind_kmh": current.get("wind_speed_10m"),
        "weather_code": code,
        "weather_text": WEATHER_TEXT.get(code, "Unknown"),
        "is_day": bool(current.get("is_day")),
        "observed_at": current.get("time"),
        "source": "Open-Meteo current weather",
    }


def _sample(points: list[list[float]], limit: int) -> list[list[float]]:
    if len(points) <= limit:
        return points
    step = (len(points) - 1) / (limit - 1)
    return [points[round(i * step)] for i in range(limit)]


def fetch_elevation_profile(geometry: list[list[float]] | None, timeout: float = 6.0) -> dict[str, Any] | None:
    """Climb and descent along a road line of [latitude, longitude] points."""
    if not geometry or len(geometry) < 2:
        return None
    points = _sample(geometry, MAX_ELEVATION_POINTS)
    latitudes = ",".join(f"{lat:.5f}" for lat, _ in points)
    longitudes = ",".join(f"{lon:.5f}" for _, lon in points)
    try:
        heights = _get(f"{ELEVATION_URL}?latitude={latitudes}&longitude={longitudes}", timeout).get("elevation")
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        logger.warning("Elevation lookup failed: %s", exc)
        return None
    if not isinstance(heights, list) or len(heights) != len(points) or any(h is None for h in heights):
        return None
    gain = loss = 0.0
    anchor = float(heights[0])
    for height in heights[1:]:
        change = float(height) - anchor
        if change >= ELEVATION_NOISE_M:
            gain += change
            anchor = float(height)
        elif change <= -ELEVATION_NOISE_M:
            loss -= change
            anchor = float(height)
    return {
        "elevation_start_m": float(heights[0]),
        "elevation_end_m": float(heights[-1]),
        "elevation_max_m": float(max(heights)),
        "elevation_gain_m": round(gain, 1),
        "elevation_loss_m": round(loss, 1),
        "samples": len(points),
        "source": "Open-Meteo elevation (90 m terrain model) sampled along the routed road",
    }


def traffic_rule(departure: datetime) -> str:
    """Colombo peak hours are taken as high traffic, late night as low. A stated rule, not a measurement."""
    minutes = departure.hour * 60 + departure.minute
    weekday = departure.weekday() < 5
    if weekday and (7 * 60 <= minutes < 9 * 60 + 30 or 16 * 60 + 30 <= minutes < 19 * 60):
        return "high"
    if minutes >= 22 * 60 or minutes < 5 * 60:
        return "low"
    return "medium"


def road_type_rule(distance_km: float, duration_min: float) -> str:
    speed = distance_km / (duration_min / 60.0) if duration_min > 0 else 0.0
    if speed >= 60:
        return "highway"
    if speed < 30:
        return "urban"
    return "mixed"


def automatic_conditions(
    origin: tuple[float, float],
    direct_route: dict | None,
    departure: datetime,
    vehicle_mass_kg: float,
    ac_on: bool,
    traffic_level: str | None = None,
    road_type: str | None = None,
    weather_fetcher=fetch_weather,
    elevation_fetcher=fetch_elevation_profile,
) -> tuple[dict | None, dict[str, Any]]:
    """Energy-model inputs for this trip and a record of where each one came from."""
    weather = weather_fetcher(*origin)
    profile = elevation_fetcher((direct_route or {}).get("geometry"))
    notes = []
    traffic = traffic_level or traffic_rule(departure)
    if traffic_level is None:
        notes.append("Traffic level follows a Colombo peak-hour rule (weekdays 7:00–9:30 and 16:30–19:00 high, 22:00–5:00 low).")
    road = road_type
    if road is None and direct_route and direct_route.get("duration_min"):
        road = road_type_rule(direct_route["distance_km"], direct_route["duration_min"])
        notes.append("Road type follows the routed average speed (under 30 km/h urban, 60 km/h and over highway).")
    info: dict[str, Any] = {
        "weather": weather,
        "elevation": profile,
        "traffic_level": traffic,
        "road_type": road,
        "vehicle_mass_kg": vehicle_mass_kg,
        "ac_on": ac_on,
        "notes": notes,
        "missing": [],
    }
    if weather is None:
        info["missing"].append("weather (Open-Meteo did not answer)")
    if profile is None:
        info["missing"].append("elevation (no road line or Open-Meteo did not answer)")
    if road is None:
        info["missing"].append("road type (no routed road)")
    if info["missing"]:
        return None, info
    conditions = {
        "elevation_gain_m": profile["elevation_gain_m"],
        "elevation_loss_m": profile["elevation_loss_m"],
        "ambient_temperature_c": weather["temperature_c"],
        "ac_on": ac_on,
        "traffic_level": traffic,
        "road_type": road,
        "vehicle_mass_kg": vehicle_mass_kg,
    }
    return conditions, info
