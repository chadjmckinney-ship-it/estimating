# Estimate equipment (mono slab)

Excel **04 EQUIPMENT** — day-rate fleet + contract services (pumping, haul off).

## Storage

| Table | Purpose |
|-------|---------|
| `estimate_equipment_lines` | Per-item days/qty, rate, billable units, ext $ |
| `estimate_equipment_summary` | Super days, ladder days, totals |
| `equipment` | Company rate catalog (Pricing EQUIPMENT RENTAL) |

## Days ladder (from super days)

Additive Excel bands on superintendent days, e.g. **27 days → 7 + 53 = 60** equip days.

## Rental tiers (billable units)

| Calendar days | Billable |
|---------------|----------|
| 1–3 | days |
| 4–7 | 3 |
| 8–20 | (days/7)×3 |
| 21–29 | 9 |
| 30+ | (days/30)×9 |

Cost = billable × day rate (no sheet markup in v1).

## Default lines

**Fleet:** SkyTrack (off), Mini excavator, Trencher, Skid steer, Vault, Misc  
**Contract:** Concrete pumping (pour CY), Haul off (manual), Engineering (off)

## API

| Method | Path |
|--------|------|
| GET | `/api/estimates/{id}/equipment` |
| POST | `/api/estimates/{id}/equipment/refresh` |
| PATCH | `/api/estimates/{id}/equipment/lines/{code}` |

## Migration

`sql/019_estimate_equipment.sql`
