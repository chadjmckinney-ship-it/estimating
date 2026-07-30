# `grade_beams`

Per-**mono slab pour** beam schedules for Excel **04 Mono / PT SOG**:

| `kind` | Excel column | Notes |
|--------|--------------|--------|
| `grade_beam` | GRADE BEAMS | Default; optional PT cables |
| `exposed` | EXP GB | Same bar schedule; no PT |
| `drop` | Drops | Same bar schedule; no PT |

Not the separate workbook sheet `02-Gd Beams` (standalone assembly — later).

| | |
|--|--|
| **Parent** | `mono_slabs` |
| **API** | `GET /api/grade-beams?mono_slab_id=&kind=` · `PUT /api/mono-slabs/{id}/grade-beams` body `{ kind, beams }` |
| **UI** | Estimate → pour → **GBs** / **Exp** / **Drops** |

## Design rules

- Job/pour-specific schedules (no global GB catalog yet). Excel’s type catalog at sheet bottom is modeled as rows here with lengths filled per pour.
- UI shows **at least 5** type rows per kind; **+ Add type** for more. No hard DB max.
- Blank rows (no W/H/L) skipped on save.
- **Replace is kind-scoped**: saving Exp does not wipe GBs or Drops.
- **Materials:** rebar + concrete CY for **all kinds** roll into the pour
  (`calc_grade_beam_rebar_lb`, `calc_gb_concrete_cy`, `calc_concrete_cy`, `calc_total_rebar_lb`).
  API `beam_breakdown` shows GB / Exp / Drop pieces; stored totals are the sum.
- **Forming & labor** for Exp and Drops are *additional* to GBs (Excel labor lines) — not in material CY/lb yet.
- PT LF only from `kind = grade_beam` with `pt_cables_count`.

## Columns

`kind`, label, width_in, height_in, length_lf, top/bottom/mid bars, stirrups, L-bars, `pt_cables_count` (GB only), `calc_rebar_lb`, `calc_pt_cable_lf`, `calc_concrete_cy`, `calc_poly_sf` (wrap SF for vapor barrier).

## Calcs

- Long bars: `calc_long_bar_lb(count, size, length_lf)`
- Stirrups: `calc_stirrup_lb` (provisional perimeter + hooks)
- L-bars: simplified as long bars for now
- Concrete: `(W″ × H″ × L_ft) / (144 × 27) × (1 + waste)`

## Migration

- `sql/013_grade_beam_kinds.sql` — adds `kind`, drops obsolete estimate-level `exposed_grade_beams`
