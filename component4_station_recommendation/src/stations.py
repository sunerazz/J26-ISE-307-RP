"""Load and normalize the station inventory. Blank fields stay unknown."""

from __future__ import annotations

import csv
import re
from pathlib import Path

from src.schemas import AvailabilityStatus

PROJECT_ROOT = Path(__file__).resolve().parents[1]
# Built from the Open Charge Map snapshot by src/build_inventory.py.
RAW_CSV = PROJECT_ROOT / "data" / "raw" / "sri_lanka_ev_stations.csv"
# The original four Colombo listings. Kept unchanged as a fixed test fixture.
LEGACY_CSV = PROJECT_ROOT / "data" / "raw" / "colombo_ev_stations.csv"
PROCESSED_CSV = PROJECT_ROOT / "data" / "processed" / "stations_normalized.csv"

UNKNOWN_TOKENS = {"", "unknown", "n/a", "na", "none", "null"}


def _blank(value: str | None) -> bool:
    return value is None or value.strip().lower() in UNKNOWN_TOKENS


def _float_or_none(value: str | None) -> float | None:
    if _blank(value):
        return None
    return float(value.strip())


def parse_connectors(value: str | None) -> list[str]:
    if _blank(value):
        return []
    return [part.strip() for part in value.split(";") if part.strip()]


def parse_listed_tariff(value: str | None) -> tuple[float | None, str]:
    """Use a tariff number only when the listing is a single unambiguous value.

    Text such as '120 DC; 70 AC' or '80 listed; verify current tariff' stays unknown.
    Unknown is never stored as zero.
    """
    if _blank(value):
        return None, "missing"
    text = value.strip()
    if re.fullmatch(r"\d+(\.\d+)?", text):
        return float(text), "single_number_listed_unverified"
    return None, "ambiguous_or_unverified_listing"


def connector_matches(required: str | None, listed: list[str]) -> bool | None:
    if required is None or not required.strip():
        return None
    needle = required.strip().lower()
    return any(needle in item.lower() for item in listed)


def connector_supply(connector: str) -> str | None:
    """DC for fast-charge plugs, AC for Type 1/Type 2 sockets, None when the name says neither."""
    name = connector.lower()
    if "chademo" in name or "ccs" in name or "gb/t dc" in name:
        return "DC"
    if "type 1" in name or "j1772" in name or "type 2" in name:
        return "AC"
    return None


def parse_connector_details(value: str | None) -> list[dict]:
    """'CHAdeMO|2|24|DC; Type 1 (J1772)|2|6.6|AC' -> one dict per connector line."""
    if _blank(value):
        return []
    details = []
    for part in value.split(";"):
        fields = [item.strip() for item in part.split("|")]
        if not fields or not fields[0]:
            continue
        fields += [""] * (4 - len(fields))
        details.append(
            {
                "connector": fields[0],
                "quantity": int(fields[1]) if fields[1].isdigit() else None,
                "power_kw": _float_or_none(fields[2]),
                "supply": fields[3] or connector_supply(fields[0]),
            }
        )
    return details


def power_for_connector(station: dict, required: str | None) -> float | None:
    """Listed kW of the plug the driver will use. Falls back to the station maximum when no plug is named."""
    if required and required.strip():
        needle = required.strip().lower()
        matching = [
            item["power_kw"]
            for item in station.get("connector_details") or []
            if needle in item["connector"].lower() and item["power_kw"] is not None
        ]
        if matching:
            return max(matching)
        if station.get("connector_details"):
            return None
    return station.get("max_power_kw_listed")


def tariff_for_connector(station: dict, required: str | None) -> tuple[float | None, str]:
    """Listed LKR/kWh for the plug's supply type (DC or AC). Unknown stays None, never zero."""
    supply = connector_supply(required) if required and required.strip() else None
    if supply == "DC" and station.get("tariff_dc_lkr_per_kwh") is not None:
        return station["tariff_dc_lkr_per_kwh"], "listed DC rate, unverified"
    if supply == "AC" and station.get("tariff_ac_lkr_per_kwh") is not None:
        return station["tariff_ac_lkr_per_kwh"], "listed AC rate, unverified"
    if supply is None:
        rates = {value for value in (station.get("tariff_dc_lkr_per_kwh"), station.get("tariff_ac_lkr_per_kwh")) if value is not None}
        if len(rates) == 1:
            return rates.pop(), "single listed rate, unverified"
    if station.get("tariff_lkr_per_kwh_listed") is not None:
        return station["tariff_lkr_per_kwh_listed"], "single_number_listed_unverified"
    return None, "missing or not listed for this plug type"


def availability_status(value: str | None) -> AvailabilityStatus:
    if _blank(value):
        return "unknown"
    token = value.strip().lower()
    if token in {"available", "free", "open"}:
        return "available"
    if token in {"unavailable", "offline", "closed", "occupied"}:
        return "unavailable"
    return "unknown"


def load_stations(path: Path | None = None) -> list[dict]:
    path = path or RAW_CSV
    if not path.exists():
        raise FileNotFoundError(f"Station CSV not found: {path}")
    stations: list[dict] = []
    seen: set[str] = set()
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {
            "station_id",
            "station_name",
            "address",
            "latitude",
            "longitude",
            "connector_types_listed",
        }
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Station CSV is missing columns: {sorted(missing)}")
        for row in reader:
            station_id = (row.get("station_id") or "").strip()
            if not station_id:
                raise ValueError("A station row has no station_id.")
            if not _blank(row.get("duplicate_of")):
                continue
            if station_id in seen:
                raise ValueError(f"Duplicate station_id: {station_id}")
            seen.add(station_id)
            latitude = float(row["latitude"])
            longitude = float(row["longitude"])
            if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
                raise ValueError(f"Invalid coordinates for {station_id}")
            connectors = parse_connectors(row.get("connector_types_listed"))
            tariff_value, tariff_status = parse_listed_tariff(row.get("tariff_lkr_per_kwh_listed"))
            if not _blank(row.get("tariff_dc_lkr_per_kwh")) or not _blank(row.get("tariff_ac_lkr_per_kwh")):
                tariff_status = "per_supply_rates_listed_unverified"
            listing = (row.get("operational_status_listing") or "").strip()
            stations.append(
                {
                    "station_id": station_id,
                    "station_name": row.get("station_name") or "",
                    "address": row.get("address") or "",
                    "area": row.get("area") or "",
                    "latitude": latitude,
                    "longitude": longitude,
                    "operator": row.get("operator") or "",
                    "connector_types_listed": connectors,
                    "max_power_kw_listed": _float_or_none(row.get("max_power_kw_listed")),
                    "tariff_lkr_per_kwh_listed": tariff_value,
                    "tariff_status": tariff_status,
                    "tariff_raw": None if _blank(row.get("tariff_lkr_per_kwh_listed")) else row["tariff_lkr_per_kwh_listed"].strip(),
                    "availability_status": availability_status(row.get("availability_realtime")),
                    "queue_length_current": _float_or_none(row.get("queue_length_current")),
                    "waiting_time_min": _float_or_none(row.get("waiting_time_min")),
                    "operational_listing": listing or None,
                    "confirmed_operational": False,
                    "listed_word_operational": listing.lower().startswith("operational"),
                    "ocm_id": row.get("ocm_id") or "",
                    "source_url": row.get("source_url") or "",
                    "source_note": row.get("source_note") or "",
                    # Columns below exist only in the rebuilt inventory; the original CSV leaves them unknown.
                    "city": row.get("city") or "",
                    "province": row.get("province") or "",
                    "distance_from_colombo_fort_km": _float_or_none(row.get("distance_from_colombo_fort_km")),
                    "in_greater_colombo": (row.get("in_greater_colombo") or "").strip().lower() == "true"
                    if not _blank(row.get("in_greater_colombo"))
                    else None,
                    "usage_type": row.get("usage_type") or None,
                    "number_of_points": int(_float_or_none(row.get("number_of_points")))
                    if _float_or_none(row.get("number_of_points")) is not None
                    else None,
                    "connector_details": parse_connector_details(row.get("connector_details")),
                    "dc_max_power_kw": _float_or_none(row.get("dc_max_power_kw")),
                    "ac_max_power_kw": _float_or_none(row.get("ac_max_power_kw")),
                    "tariff_dc_lkr_per_kwh": _float_or_none(row.get("tariff_dc_lkr_per_kwh")),
                    "tariff_ac_lkr_per_kwh": _float_or_none(row.get("tariff_ac_lkr_per_kwh")),
                    "tariff_source": row.get("tariff_source") or None,
                    "access_note": row.get("access_note") or None,
                    "opening_hours_listed": row.get("opening_hours_listed") or None,
                    "phone": row.get("phone") or None,
                    "ocm_data_quality_score": _float_or_none(row.get("ocm_data_quality_score")),
                    "retrieved_on": row.get("retrieved_on") or None,
                }
            )
    if not stations:
        raise ValueError("Station CSV has no records.")
    return stations


def save_processed(stations: list[dict], path: Path | None = None) -> Path:
    path = path or PROCESSED_CSV
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "station_id",
        "station_name",
        "address",
        "area",
        "latitude",
        "longitude",
        "connector_types_listed",
        "max_power_kw_listed",
        "tariff_lkr_per_kwh_listed",
        "tariff_status",
        "availability_status",
        "queue_length_current",
        "waiting_time_min",
        "confirmed_operational",
        "city",
        "province",
        "number_of_points",
        "dc_max_power_kw",
        "ac_max_power_kw",
        "tariff_dc_lkr_per_kwh",
        "tariff_ac_lkr_per_kwh",
        "source_url",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for station in stations:
            writer.writerow(
                {
                    **{key: station.get(key) for key in fieldnames},
                    "connector_types_listed": "; ".join(station["connector_types_listed"]),
                    "tariff_lkr_per_kwh_listed": ""
                    if station["tariff_lkr_per_kwh_listed"] is None
                    else station["tariff_lkr_per_kwh_listed"],
                    "queue_length_current": ""
                    if station["queue_length_current"] is None
                    else station["queue_length_current"],
                    "waiting_time_min": ""
                    if station["waiting_time_min"] is None
                    else station["waiting_time_min"],
                    "max_power_kw_listed": ""
                    if station["max_power_kw_listed"] is None
                    else station["max_power_kw_listed"],
                }
            )
    return path
