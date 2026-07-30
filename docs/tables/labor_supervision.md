# Labor & supervision (mono slab)

Excel **04-PT Slab on Grade** → **LABOR: SLAB** and **SUPERVISION MONO SLAB**.

## Storage

| Table | Purpose |
|-------|---------|
| `estimate_labor_lines` | One row per item (enabled, rate, qty, ext $) |
| `estimate_labor_summary` | Drivers + labor / supervision / total / $/SF |
| `system_settings` `labor_*` | Company default rates |

## API

| Method | Path |
|--------|------|
| GET | `/api/estimates/{id}/labor` (auto-saves if empty) |
| POST | `/api/estimates/{id}/labor/refresh` |
| PATCH | `/api/estimates/{id}/labor/lines/{code}` body `{ enabled, rate, qty, mark_manual }` |

## UI

Estimate detail → header **Labor & supervision** or card below Forming.

## Slab labor lines

| Code | Label | Qty | Default rate |
|------|-------|-----|-------------:|
| forming | FORMING | total SF | $0.45 /SF |
| grading | GRADING / CABLES | total SF | $0.70 /SF |
| place_finish | PLACE AND FINISH | total SF | $0.55 /SF |
| wreck | WRECK AND CLEAN UP | total SF | $0.20 /SF |
| drops | DROPS | drops_ff | $8 /FF |
| labor_add | LABOR ADD | manual $ | 0 |
| excavation | EXCAVATION ADD | CY (manual) | $12 /CY |
| hold_downs | HOLD DOWNS / FTGS | EA (manual) | $100 /EA |
| tie_steel | TIE STEEL | rebar_lb/2000 | $450 /TON |
| extra_hours | EXTRA HOURS | manual $ | 0 |

Enabled (Y) = include in total. Toggle in UI.

## Supervision

| Code | Qty | Default rate |
|------|-----|-------------:|
| superintendent | SF/16000 weeks × 7 days | $425 /day |
| foreman | 0 until set (often = super days) | $250 /day |
| expense | super days | $100 /day |
| pm | super days | $200 /day |

## Migration

`sql/018_estimate_labor.sql`
