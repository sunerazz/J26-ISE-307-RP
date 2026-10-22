"""Build the station inventory CSV from the Open Charge Map snapshot.

    python -m src.build_inventory

Fields are copied or parsed from the listing. A field the listing does not
state stays blank. Live availability, queue length and waiting time are not
published by OCM, so they stay blank. The report in results/ counts, field by
field, what the original four-row CSV had and what the rebuilt inventory has.
"""

from __future__ import annotations

import csv
import json
import math
import re
from pathlib import Path

from src.stations import LEGACY_CSV, PROJECT_ROOT, RAW_CSV, connector_supply

SNAPSHOT_JSON = PROJECT_ROOT / "data" / "raw" / "ocm_sri_lanka_snapshot.json"
RESULTS = PROJECT_ROOT / "results"

COLOMBO_FORT = (6.9344, 79.8428)
GREATER_COLOMBO_KM = 20.0

# The four stations in the original CSV keep their IDs and display names.
LEGACY_IDS = {263889: "ST001", 263892: "ST002", 263890: "ST003", 263887: "ST004"}

PROVINCES = {
    "western": "Western",
    "southern": "Southern",
    "southren": "Southern",
    "central": "Central",
    "north central": "North Central",
    "nort central": "North Central",
    "eastern": "Eastern",
    "north western": "North Western",
    "sabaragamuwa": "Sabaragamuwa",
    "uva": "Uva",
    "northern": "Northern",
}

FIELDNAMES = [
    "station_id",
    "station_name",
    "address",
    "area",
    "city",
    "province",
    "latitude",
    "longitude",
    "distance_from_colombo_fort_km",
    "in_greater_colombo",
    "operator",
    "usage_type",
    "number_of_points",
    "connector_types_listed",
    "connector_details",
    "max_power_kw_listed",
    "dc_max_power_kw",
    "ac_max_power_kw",
    "tariff_lkr_per_kwh_listed",
    "tariff_dc_lkr_per_kwh",
    "tariff_ac_lkr_per_kwh",
    "tariff_source",
    "access_note",
    "opening_hours_listed",
    "phone",
    "availability_realtime",
    "queue_length_current",
    "waiting_time_min",
    "operational_status_listing",
    "ocm_id",
    "ocm_data_quality_score",
    "duplicate_of",
    "source_url",
    "source_note",
    "retrieved_on",
]


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def _province(lines: list[str]) -> str:
    for line in lines:
        key = line.lower().replace("province", "").strip()
        if key in PROVINCES:
            return PROVINCES[key]
    return ""


# Town names for two listings whose address lines put the town in an unusual position.
CITY_OVERRIDES = {474960: "Mirigama", 509581: "Kovinna"}

ROAD_WORDS = re.compile(r"\b(road|rd|mawatha|lane|street|expy|complex)\b", re.I)


def _place(text: str) -> str:
    text = re.sub(r"\s*\d{5}\b", "", text).strip(" .,")
    return text.title() if text.isupper() else text


def _city(record: dict) -> str:
    if record["ocm_id"] in CITY_OVERRIDES:
        return CITY_OVERRIDES[record["ocm_id"]]
    candidates = []
    for line in record["address_lines"][1:]:
        if line == "Sri Lanka" or re.fullmatch(r"\d{5}", line) or _province([line]):
            break
        if not ROAD_WORDS.search(line):
            candidates.append(_place(line))
    return candidates[-1] if candidates else ""


def _area(lines: list[str], city: str) -> str:
    first = lines[0] if lines else ""
    match = re.search(r"Colombo\s*0?(\d{1,2})\b", first)
    if match:
        return f"Colombo {int(match.group(1)):02d}"
    if "00700" in lines:
        return "Colombo 07"
    parts = [_place(part) for part in first.split(",")]
    for part in reversed(parts[1:]):
        lower = part.lower()
        if len(part) > 3 and not re.search(r"\d", part) and "colomb" not in lower and lower != "sri lanka" and not ROAD_WORDS.search(part):
            return part
    return city


def _tariffs(info: str) -> tuple[float | None, float | None]:
    """Read chargeNET's published per-level rates, e.g. 'L3 30kW DCFC - 120LKR/kWh'."""
    dc = re.search(r"L3[^\n\r]*?-\s*(\d+(?:\.\d+)?)\s*LKR/kWh", info, re.I)
    ac = re.search(r"L2[^\n\r]*?-\s*(\d+(?:\.\d+)?)\s*LKR/kWh", info, re.I)
    return (float(dc.group(1)) if dc else None, float(ac.group(1)) if ac else None)


def _hours(info: str) -> str:
    match = re.search(r"\b\d{1,2}(?:[.:]\d{2})?\s*[AP]M\s*(?:to|-)\s*\d{1,2}(?:[.:]\d{2})?\s*[AP]M\b", info, re.I)
    return match.group(0) if match else ""


def _access(info: str) -> str:
    notes = []
    if re.search(r"NFC card|Android app", info, re.I):
        notes.append("chargeNET NFC card or app required")
    if re.search(r"online payment only|pay online", info, re.I):
        notes.append("online payment only")
    if re.search(r"EVO Charge App", info, re.I):
        notes.append("EVO Charge app required")
    return "; ".join(notes)


def _supply(item: dict) -> str | None:
    supply = (item.get("supply") or "").upper()
    if supply.startswith("DC"):
        return "DC"
    if supply.startswith("AC"):
        return "AC"
    return connector_supply(item.get("connector") or "")


def _fmt(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:g}"


def build_rows(snapshot: dict) -> list[dict]:
    records = snapshot["records"]
    legacy = {row["ocm_id"]: row for row in _read_csv(LEGACY_CSV)}
    for record in records:
        record["_km"] = haversine_km(COLOMBO_FORT, (record["latitude"], record["longitude"]))
    records.sort(key=lambda record: (record["ocm_id"] not in LEGACY_IDS, LEGACY_IDS.get(record["ocm_id"], ""), record["_km"]))

    # Two listings at the same place with the same name are one site. The one
    # with fewer listed bays is kept in the file but marked as a duplicate.
    duplicates: dict[int, int] = {}
    for a in records:
        for b in records:
            if a is b or a["title"] != b["title"]:
                continue
            if haversine_km((a["latitude"], a["longitude"]), (b["latitude"], b["longitude"])) < 0.1:
                keep = max((a, b), key=lambda item: (item["number_of_points"] or 0, -item["ocm_id"]))
                drop = b if keep is a else a
                duplicates[drop["ocm_id"]] = keep["ocm_id"]

    rows = []
    next_number = len(LEGACY_IDS) + 1
    ids: dict[int, str] = {}
    for record in records:
        if record["ocm_id"] in LEGACY_IDS:
            ids[record["ocm_id"]] = LEGACY_IDS[record["ocm_id"]]
        else:
            ids[record["ocm_id"]] = f"ST{next_number:03d}"
            next_number += 1

    for record in records:
        ocm_id = record["ocm_id"]
        lines = record["address_lines"]
        city = _city(record)
        info = (record.get("general_info") or "").replace("\r", "")
        equipment = [item for item in record["equipment"] if item.get("connector")]
        connectors: list[str] = []
        details = []
        dc_power = []
        ac_power = []
        for item in equipment:
            if item["connector"] not in connectors:
                connectors.append(item["connector"])
            supply = _supply(item)
            power = item.get("power_kw")
            details.append(f"{item['connector']}|{item.get('quantity') or ''}|{_fmt(power)}|{supply or ''}")
            if power is not None and supply == "DC":
                dc_power.append(power)
            if power is not None and supply == "AC":
                ac_power.append(power)
        powers = [item["power_kw"] for item in equipment if item.get("power_kw") is not None]
        tariff_dc, tariff_ac = _tariffs(info)
        # chargeNET's comment text often quotes both rates; keep only the supply types this site has.
        supplies = {_supply(item) for item in equipment}
        if "DC" not in supplies:
            tariff_dc = None
        if "AC" not in supplies:
            tariff_ac = None
        tariff_text = "; ".join(
            text for text in (
                f"{_fmt(tariff_dc)} DC" if tariff_dc is not None else "",
                f"{_fmt(tariff_ac)} AC" if tariff_ac is not None else "",
            ) if text
        )
        old = legacy.get(str(ocm_id))
        notes = ["Open Charge Map listing; not recently verified" if record["not_recently_verified"] else "Open Charge Map listing"]
        if ocm_id in duplicates:
            notes.append(f"duplicate listing of OCM {duplicates[ocm_id]}")
        rows.append(
            {
                "station_id": ids[ocm_id],
                "station_name": old["station_name"] if old else record["title"],
                "address": ", ".join(line for line in lines if line != "Sri Lanka" and not re.fullmatch(r"\d{5}", line)),
                "area": old["area"] if old else _area(lines, city),
                "city": city,
                "province": _province(lines),
                "latitude": record["latitude"],
                "longitude": record["longitude"],
                "distance_from_colombo_fort_km": round(record["_km"], 2),
                "in_greater_colombo": record["_km"] <= GREATER_COLOMBO_KM,
                "operator": (record.get("operator") or "").replace(" (lk)", "").strip("()") or "",
                "usage_type": record.get("usage") or "",
                "number_of_points": record.get("number_of_points") or "",
                "connector_types_listed": "; ".join(connectors),
                "connector_details": "; ".join(details),
                "max_power_kw_listed": _fmt(max(powers)) if powers else "",
                "dc_max_power_kw": _fmt(max(dc_power)) if dc_power else "",
                "ac_max_power_kw": _fmt(max(ac_power)) if ac_power else "",
                "tariff_lkr_per_kwh_listed": tariff_text,
                "tariff_dc_lkr_per_kwh": _fmt(tariff_dc),
                "tariff_ac_lkr_per_kwh": _fmt(tariff_ac),
                "tariff_source": "operator rate quoted in the OCM listing comments; unverified" if tariff_text else "",
                "access_note": _access(info),
                "opening_hours_listed": _hours(info),
                "phone": record.get("phone") or "",
                "availability_realtime": "unknown",
                "queue_length_current": "",
                "waiting_time_min": "",
                "operational_status_listing": (
                    f"{record['status']}; listing not recently verified" if record["not_recently_verified"] else record["status"]
                ),
                "ocm_id": ocm_id,
                "ocm_data_quality_score": record.get("data_quality_score") or "",
                "duplicate_of": ids[duplicates[ocm_id]] if ocm_id in duplicates else "",
                "source_url": record["source_url"],
                "source_note": "; ".join(notes) + "; verify before real-world use",
                "retrieved_on": snapshot["retrieved_on"],
            }
        )
    return rows


def _read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_inventory(rows: list[dict], path: Path = RAW_CSV) -> Path:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    return path


COMPLETENESS_FIELDS = [
    ("connector_types_listed", "Connector types"),
    ("connector_details", "Per-connector count, kW and AC/DC"),
    ("max_power_kw_listed", "Maximum listed power"),
    ("number_of_points", "Number of charging points"),
    ("tariff_lkr_per_kwh_numeric", "Usable LKR/kWh tariff (for your plug type)"),
    ("usage_type", "Usage / access type"),
    ("phone", "Contact phone"),
    ("opening_hours_listed", "Opening hours"),
    ("availability_realtime_known", "Live availability"),
    ("queue_length_current", "Current queue length"),
    ("waiting_time_min", "Current waiting time"),
]


def _filled(row: dict, field: str) -> bool:
    if field == "tariff_lkr_per_kwh_numeric":
        if row.get("tariff_dc_lkr_per_kwh") or row.get("tariff_ac_lkr_per_kwh"):
            return True
        return bool(re.fullmatch(r"\d+(\.\d+)?", (row.get("tariff_lkr_per_kwh_listed") or "").strip()))
    if field == "availability_realtime_known":
        return (row.get("availability_realtime") or "unknown").strip().lower() not in {"", "unknown"}
    return bool(str(row.get(field) or "").strip())


def completeness_report(legacy: list[dict], rows: list[dict], snapshot: dict) -> dict:
    active = [row for row in rows if not row["duplicate_of"]]
    by_id = {row["station_id"]: row for row in rows}
    fields = []
    for field, label in COMPLETENESS_FIELDS:
        fields.append(
            {
                "field": field,
                "label": label,
                "original_csv_filled": sum(_filled(row, field) for row in legacy),
                "original_csv_total": len(legacy),
                "same_four_stations_now_filled": sum(_filled(by_id[row["station_id"]], field) for row in legacy),
                "inventory_filled": sum(_filled(row, field) for row in active),
                "inventory_total": len(active),
            }
        )
    corrections = []
    for old in legacy:
        new = by_id[old["station_id"]]
        if old.get("max_power_kw_listed") and new["max_power_kw_listed"] and float(old["max_power_kw_listed"]) != float(new["max_power_kw_listed"]):
            corrections.append(
                {
                    "station_id": old["station_id"],
                    "field": "max_power_kw_listed",
                    "original": old["max_power_kw_listed"],
                    "rebuilt": new["max_power_kw_listed"],
                    "why": "The original value came from the '30kW DCFC' comment text. The listing's equipment record gives the connector power.",
                }
            )
        if (old.get("tariff_lkr_per_kwh_listed") or "") != new["tariff_lkr_per_kwh_listed"]:
            corrections.append(
                {
                    "station_id": old["station_id"],
                    "field": "tariff_lkr_per_kwh_listed",
                    "original": old.get("tariff_lkr_per_kwh_listed"),
                    "rebuilt": new["tariff_lkr_per_kwh_listed"],
                    "why": "Rebuilt from the per-level rates in the current listing comments (L3 = DC, L2 = AC).",
                }
            )
    return {
        "retrieved_on": snapshot["retrieved_on"],
        "source": snapshot["source"],
        "license": snapshot["license"],
        "listings_in_snapshot": len(rows),
        "duplicate_listings": [row["station_id"] for row in rows if row["duplicate_of"]],
        "stations_in_inventory": len(active),
        "operational_listings": sum(row["operational_status_listing"].lower().startswith("operational") for row in active),
        "in_greater_colombo": sum(row["in_greater_colombo"] for row in active),
        "with_dc_fast_charging": sum(bool(row["dc_max_power_kw"]) for row in active),
        "original_station_count": len(legacy),
        "fields": fields,
        "corrections_to_original_rows": corrections,
        "still_unknown": (
            "Live availability, queue length and waiting time are not published by Open Charge Map. "
            "They stay blank and are never set to zero."
        ),
    }


def write_report(report: dict) -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "data_completeness_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Station inventory: data completeness",
        "",
        f"Source: {report['source']}, retrieved {report['retrieved_on']}. {report['license']}.",
        "",
        f"- Listings in the snapshot: {report['listings_in_snapshot']} "
        f"({len(report['duplicate_listings'])} duplicate: {', '.join(report['duplicate_listings']) or 'none'})",
        f"- Stations in the inventory: **{report['stations_in_inventory']}** (original CSV: {report['original_station_count']})",
        f"- Listed as operational: {report['operational_listings']}",
        f"- Within {GREATER_COLOMBO_KM:.0f} km of Colombo Fort: {report['in_greater_colombo']}",
        f"- With DC fast charging: {report['with_dc_fast_charging']}",
        "",
        "| Field | Original CSV | Same 4 stations, rebuilt | Full inventory |",
        "| --- | ---: | ---: | ---: |",
    ]
    for item in report["fields"]:
        lines.append(
            f"| {item['label']} | {item['original_csv_filled']}/{item['original_csv_total']} "
            f"| {item['same_four_stations_now_filled']}/{item['original_csv_total']} "
            f"| {item['inventory_filled']}/{item['inventory_total']} |"
        )
    lines += ["", "## Corrections to the original rows", ""]
    for item in report["corrections_to_original_rows"]:
        lines.append(f"- {item['station_id']} `{item['field']}`: `{item['original']}` → `{item['rebuilt']}`. {item['why']}")
    lines += ["", "## Still unknown", "", report["still_unknown"], ""]
    (RESULTS / "data_completeness_report.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    snapshot = json.loads(SNAPSHOT_JSON.read_text(encoding="utf-8"))
    rows = build_rows(snapshot)
    path = write_inventory(rows)
    legacy = _read_csv(LEGACY_CSV)
    report = completeness_report(legacy, rows, snapshot)
    write_report(report)
    print(f"Wrote {len(rows)} rows to {path}")
    print(f"{report['stations_in_inventory']} stations, {report['in_greater_colombo']} within {GREATER_COLOMBO_KM:.0f} km of Colombo Fort")


if __name__ == "__main__":
    main()
