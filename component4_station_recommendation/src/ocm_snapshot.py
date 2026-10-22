"""Download and parse the public Open Charge Map listing pages for Sri Lanka.

The OCM JSON API now needs a key, so this reads the public HTML detail pages
(CC BY 4.0). The parsed snapshot is saved with its retrieval date so the
inventory can be rebuilt offline. Nothing is filled in that the page does not say.

    python -m src.ocm_snapshot            # fetch pages and write the snapshot
    python -m src.ocm_snapshot --offline  # re-parse pages already saved
"""

from __future__ import annotations

import argparse
import html
import json
import re
import time
from datetime import date
from pathlib import Path
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PAGES_DIR = PROJECT_ROOT / "data" / "raw" / "ocm_pages"
SNAPSHOT_JSON = PROJECT_ROOT / "data" / "raw" / "ocm_sri_lanka_snapshot.json"

BASE = "https://openchargemap.io"
SRI_LANKA_COUNTRY_ID = 211
USER_AGENT = "colombo-ev-research/1.0 (academic project)"


def _get(url: str) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8")


def _clean(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", text)).strip()


def _dd(page: str, label: str) -> str | None:
    match = re.search(r"<dt[^>]*>\s*" + re.escape(label) + r"\s*</dt>\s*<dd[^>]*>(.*?)</dd>", page, re.S)
    return _clean(match.group(1)) if match else None


def listing_ids() -> list[int]:
    page = _get(f"{BASE}/poi?CountryIDs={SRI_LANKA_COUNTRY_ID}&CountryName=srilanka")
    return sorted({int(item) for item in re.findall(r"/poi/details/(\d+)", page)})


def fetch_pages(delay_seconds: float = 1.0) -> list[Path]:
    PAGES_DIR.mkdir(parents=True, exist_ok=True)
    saved = []
    for ocm_id in listing_ids():
        path = PAGES_DIR / f"{ocm_id}.html"
        path.write_text(_get(f"{BASE}/poi/details/{ocm_id}"), encoding="utf-8")
        saved.append(path)
        time.sleep(delay_seconds)
    return saved


def parse_equipment(page: str) -> list[dict]:
    body = page.split('id="tab-comments"')[0]
    equipment = []
    for card in body.split("ocm-equipment-card")[1:]:
        connector = re.search(r"connectionType[^>]*>(.*?)</span>", card, re.S)
        quantity = re.search(r">(\d+) present<", card)
        status = re.search(r"statusType[^>]*>(.*?)</span>", card, re.S)
        specs = {unit: float(value) for value, unit in re.findall(r"ocm-equipment-value\">([\d.]+)</span>\s*(kW|V|A)", card)}
        supply = re.search(r"supplyType[^>]*>(.*?)</div>", card, re.S)
        equipment.append(
            {
                "connector": _clean(connector.group(1)) if connector else None,
                "quantity": int(quantity.group(1)) if quantity else None,
                "status": _clean(status.group(1)) if status else None,
                "power_kw": specs.get("kW"),
                "voltage_v": specs.get("V"),
                "current_a": specs.get("A"),
                "supply": _clean(supply.group(1)) if supply else None,
            }
        )
    return equipment


def parse_page(page: str, ocm_id: int) -> dict:
    title = _clean(re.search(r"<title>(.*?)</title>", page, re.S).group(1))
    title = title.split(f"OCM-{ocm_id}", 1)[-1].strip()
    address = re.search(r"<address[^>]*>(.*?)</address>", page, re.S)
    lines = [_clean(item) for item in re.findall(r"<div>(.*?)</div>", address.group(1), re.S)] if address else []
    phone = re.search(r"fa-phone[^>]*></i>\s*([^<]+)<", page)
    phone_text = phone.group(1).strip() if phone else None
    general = re.search(r"General Information</h2>\s*<p[^>]*>(.*?)</p>", page, re.S)
    operator = re.search(r"Network/Operator</h2>\s*<div class=\"fw-semibold\">(.*?)</div>", page, re.S)
    quality = re.search(r"ocm-quality-score[^>]*>(\d+)<", page)
    latitude = _dd(page, "Latitude")
    longitude = _dd(page, "Longitude")
    points = _dd(page, "Number Of Stations/Bays")
    return {
        "ocm_id": ocm_id,
        "title": title,
        # Phone numbers are shown inside the address block; they are kept separately.
        "address_lines": [line for line in lines if line and not re.fullmatch(r"[\d +()-]{7,}", line)],
        "phone": phone_text,
        "number_of_points": int(points) if points and points.isdigit() else None,
        "usage": _dd(page, "Usage"),
        "status": _dd(page, "Operational Status"),
        "latitude": float(latitude) if latitude else None,
        "longitude": float(longitude) if longitude else None,
        "operator": _clean(operator.group(1)) if operator else None,
        "general_info": _clean(general.group(1)) if general else None,
        "data_quality_score": int(quality.group(1)) if quality else None,
        "not_recently_verified": "has not been recently verified" in page,
        "equipment": parse_equipment(page),
        "source_url": f"{BASE}/poi/details/{ocm_id}",
    }


def parse_pages(pages_dir: Path = PAGES_DIR) -> list[dict]:
    records = []
    for path in sorted(pages_dir.glob("*.html"), key=lambda item: int(item.stem)):
        records.append(parse_page(path.read_text(encoding="utf-8"), int(path.stem)))
    return records


def write_snapshot(records: list[dict], retrieved_on: str, path: Path = SNAPSHOT_JSON) -> Path:
    payload = {
        "source": "Open Charge Map public location pages, country Sri Lanka",
        "source_url": f"{BASE}/poi?CountryIDs={SRI_LANKA_COUNTRY_ID}&CountryName=srilanka",
        "license": "Creative Commons Attribution 4.0 International (CC BY 4.0), © Open Charge Map contributors",
        "retrieved_on": retrieved_on,
        "record_count": len(records),
        "records": records,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="Parse pages already in data/raw/ocm_pages.")
    parser.add_argument("--retrieved-on", default=None, help="Date to record for --offline (default: today).")
    args = parser.parse_args()
    if not args.offline:
        fetch_pages()
    records = parse_pages()
    path = write_snapshot(records, args.retrieved_on or date.today().isoformat())
    print(f"Wrote {len(records)} listings to {path}")


if __name__ == "__main__":
    main()
