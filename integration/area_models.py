"""Match a listed charger to one of the five Component 1 training areas.

The queue, waiting-time and congestion models were trained on simulated
15-minute snapshots for these towns, not on a live count at each charger.
"""

from __future__ import annotations

from math import asin, cos, radians, sin, sqrt

# Town centres. Pannipitiya is the mean of the chargers listed there.
# The other four towns have no charger pin in the Component 4 inventory.
TRAINED_AREAS = (
    {"station_id": "ST01", "name": "Nugegoda", "latitude": 6.86490, "longitude": 79.89970},
    {"station_id": "ST02", "name": "Rajagiriya", "latitude": 6.90900, "longitude": 79.89600},
    {"station_id": "ST03", "name": "Malabe", "latitude": 6.90630, "longitude": 79.96960},
    {"station_id": "ST04", "name": "Pannipitiya", "latitude": 6.84284, "longitude": 79.95336},
    {"station_id": "ST05", "name": "Panadura", "latitude": 6.71320, "longitude": 79.90260},
)

# A charger farther than this from every trained town is left without a forecast.
NEAR_KM = 15.0


def _km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1, lon1, lat2, lon2 = (radians(value) for value in (lat1, lon1, lat2, lon2))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    step = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * 6371.0 * asin(sqrt(step))


def match_trained_area(station: dict) -> dict | None:
    """Return the trained town for this charger, or None when none is close.

    A place name in the listing wins over pure distance, so a Pannipitiya
    charger uses the Pannipitiya model even if another town centre is nearer.
    """
    text = " ".join(
        str(station.get(key) or "")
        for key in ("area", "city", "station_name", "address")
    ).casefold()
    latitude = station.get("latitude")
    longitude = station.get("longitude")
    if latitude is None or longitude is None:
        return None
    named = next((area for area in TRAINED_AREAS if area["name"].casefold() in text), None)
    if named is not None:
        distance = _km(latitude, longitude, named["latitude"], named["longitude"])
        return {**named, "distance_km": round(distance, 2), "match": "place_name"}
    nearest = min(
        TRAINED_AREAS,
        key=lambda area: _km(latitude, longitude, area["latitude"], area["longitude"]),
    )
    distance = _km(latitude, longitude, nearest["latitude"], nearest["longitude"])
    if distance > NEAR_KM:
        return None
    return {**nearest, "distance_km": round(distance, 2), "match": "nearest_town"}
