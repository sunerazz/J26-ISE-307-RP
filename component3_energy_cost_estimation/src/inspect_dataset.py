"""Inspect the Component 3 trip CSV and write a quality report."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import RESULTS_DIR  # noqa: E402
from src.dataset_checks import inspect_frame, load_dataset  # noqa: E402


def write_report(report: dict) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    json_path = RESULTS_DIR / "dataset_quality_report.json"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Component 3 dataset quality report",
        "",
        f"- Path inspected: `{report['path']}`",
        f"- Shape: {report['n_rows']} rows × {report['n_columns']} columns",
        f"- Duplicate rows: {report['duplicate_rows']}",
        f"- Missing values: {report['missing_counts'] or 'none'}",
        f"- Energy target column: {report['energy_column'] or '**not present**'}",
        f"- Target status: {report['target_status']}",
        "",
        "## Columns",
        "",
    ]
    for column in report["columns"]:
        lines.append(f"- `{column}` ({report['dtypes'][column]})")
    lines.extend(
        [
            "",
            "## Decision",
            "",
            report["why_training_stopped"]
            or (
                "energy_consumption_kwh is present. soc_end_pct and energy_consumption_kwh_per_km "
                "match that label and are excluded from training. "
                "Charging cost is still calculate_charging_cost with a tariff you supply."
            ),
            "",
        ]
    )
    md_path = RESULTS_DIR / "dataset_quality_report.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return md_path


def main() -> int:
    frame, path = load_dataset()
    report = inspect_frame(frame, path)
    written = write_report(report)
    print(json.dumps({"rows": report["n_rows"], "cols": report["n_columns"], "energy_column": report["energy_column"], "report": str(written)}, indent=2))
    if report["energy_column"] is None:
        print(report["why_training_stopped"])
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
