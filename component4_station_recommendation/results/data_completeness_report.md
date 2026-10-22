# Station inventory: data completeness

Source: Open Charge Map public location pages, country Sri Lanka, retrieved 2026-10-22. Creative Commons Attribution 4.0 International (CC BY 4.0), © Open Charge Map contributors.

- Listings in the snapshot: 68 (1 duplicate: ST063)
- Stations in the inventory: **67** (original CSV: 4)
- Listed as operational: 66
- Within 20 km of Colombo Fort: 18
- With DC fast charging: 37

| Field | Original CSV | Same 4 stations, rebuilt | Full inventory |
| --- | ---: | ---: | ---: |
| Connector types | 4/4 | 4/4 | 67/67 |
| Per-connector count, kW and AC/DC | 0/4 | 4/4 | 67/67 |
| Maximum listed power | 4/4 | 4/4 | 67/67 |
| Number of charging points | 0/4 | 4/4 | 67/67 |
| Usable LKR/kWh tariff (for your plug type) | 1/4 | 4/4 | 48/67 |
| Usage / access type | 0/4 | 4/4 | 67/67 |
| Contact phone | 0/4 | 4/4 | 62/67 |
| Opening hours | 0/4 | 1/4 | 2/67 |
| Live availability | 0/4 | 0/4 | 0/67 |
| Current queue length | 0/4 | 0/4 | 0/67 |
| Current waiting time | 0/4 | 0/4 | 0/67 |

## Corrections to the original rows

- ST001 `max_power_kw_listed`: `30` → `24`. The original value came from the '30kW DCFC' comment text. The listing's equipment record gives the connector power.
- ST002 `max_power_kw_listed`: `30` → `24`. The original value came from the '30kW DCFC' comment text. The listing's equipment record gives the connector power.
- ST003 `max_power_kw_listed`: `30` → `18`. The original value came from the '30kW DCFC' comment text. The listing's equipment record gives the connector power.
- ST003 `tariff_lkr_per_kwh_listed`: `120` → `120 DC`. Rebuilt from the per-level rates in the current listing comments (L3 = DC, L2 = AC).
- ST004 `tariff_lkr_per_kwh_listed`: `80 listed; verify current tariff` → `70 AC`. Rebuilt from the per-level rates in the current listing comments (L3 = DC, L2 = AC).

## Still unknown

Live availability, queue length and waiting time are not published by Open Charge Map. They stay blank and are never set to zero.
