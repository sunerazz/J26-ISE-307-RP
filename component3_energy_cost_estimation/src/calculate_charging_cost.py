"""Transparent charging-cost calculation. The tariff is always supplied by the caller.

Formula
-------
energy_charge = predicted_or_measured_energy_kwh × tariff_per_kwh
estimated_total = energy_charge + extra_fixed_fees

Units
-----
- Energy: kilowatt-hours (kWh). This is vehicle energy only when that is what
  the kWh value represents. This dataset does not measure charger-side energy.
- Tariff: currency units per kWh. No Sri Lankan or other official rate is hardcoded.
- Extra fees: same currency as the tariff. Use 0 when taxes or time charges
  are unknown. They are not inferred.

Negative energy is rejected. It is not clipped, because a negative kWh would
hide an invalid prediction inside a smaller bill.

Rounding: money is rounded to 2 decimal places for display. The unrounded
product is also returned.
"""

from __future__ import annotations

import math
from typing import Any


def estimate_charging_cost(
    energy_kwh: float,
    tariff_per_kwh: float,
    *,
    currency: str = "LKR",
    tariff_category: str | None = None,
    extra_fixed_fees: float = 0.0,
    energy_basis: str = "vehicle_energy_kwh",
) -> dict[str, Any]:
    """Estimate cost from energy and a caller-supplied tariff.

    Parameters
    ----------
    energy_kwh:
        Non-negative energy in kWh. Rejected when negative or non-finite.
    tariff_per_kwh:
        Price of one kWh in ``currency``. Must be non-negative. Not a default
        national tariff.
    tariff_category:
        Optional label such as a customer or station tariff class. Stored for
        the audit trail and not used to look up a hidden rate.
    extra_fixed_fees:
        Optional fixed amount in the same currency. Default 0.
    energy_basis:
        What the kWh figure represents. Use ``vehicle_energy_kwh`` or
        ``station_energy_drawn_kwh`` when that distinction is known.
    """
    energy = float(energy_kwh)
    tariff = float(tariff_per_kwh)
    fees = float(extra_fixed_fees)
    if not math.isfinite(energy) or energy < 0:
        raise ValueError(
            "energy_kwh must be a finite number greater than or equal to 0. "
            "Negative predictions are rejected rather than clipped."
        )
    if not math.isfinite(tariff) or tariff < 0:
        raise ValueError("tariff_per_kwh must be a finite number greater than or equal to 0.")
    if not math.isfinite(fees) or fees < 0:
        raise ValueError("extra_fixed_fees must be a finite number greater than or equal to 0.")
    if not currency or not str(currency).strip():
        raise ValueError("currency is required.")
    raw_energy_charge = energy * tariff
    raw_total = raw_energy_charge + fees
    return {
        "energy_kwh": energy,
        "energy_basis": energy_basis,
        "tariff_per_kwh": tariff,
        "tariff_category": tariff_category,
        "currency": str(currency),
        "energy_charge_unrounded": raw_energy_charge,
        "extra_fixed_fees": fees,
        "estimated_total_unrounded": raw_total,
        "energy_charge": round(raw_energy_charge, 2),
        "estimated_total": round(raw_total, 2),
        "formula": "estimated_total = energy_kwh * tariff_per_kwh + extra_fixed_fees",
        "assumptions": [
            "Tariff is supplied by the caller and is not an official current rate.",
            "One tariff does not automatically apply to every station or customer.",
            "No taxes or time-based charges are added unless extra_fixed_fees is set.",
            "Station energy drawn is not estimated from vehicle energy; pass the correct basis.",
        ],
    }


def main() -> None:
    example = estimate_charging_cost(10.0, 50.0, currency="LKR", tariff_category="example")
    print(example)


if __name__ == "__main__":
    main()
