# `mono_slabs`

Main **Mono Slab / PT SOG** quantity inputs for one pour or location on an estimate. Stored `calc_*` columns hold last computed results (refresh via app/functions).

Design field list: [../mono.md](../mono.md)

| | |
|--|--|
| **Type** | Table |
| **Created in** | `sql/001_schema.sql` |
| **API** | `/api/mono-slabs` |
| **UI** | Estimate detail → Mono slab pours |
| **Calcs** | Auto on create/update via SQL helpers + `system_settings` / estimate waste |

---

## Columns — inputs

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| `id` | uuid | NO | `gen_random_uuid()` | PK |
| `estimate_id` | uuid | NO | | FK → `estimates` |
| `description` | text | YES | | e.g. Garden Style, Bld 1 Pour 3 |
| `location` | text | YES | | |
| `square_footage` | numeric(14,3) | NO | | SF |
| `thickness_in` | numeric(8,3) | NO | | Inches; must be > 0 |
| `post_tension` | boolean | NO | `false` | If true, PT qty calculated |
| `mix_design_id` | integer | YES | | FK → `mix_designs` |
| `sand_thickness_in` | numeric(8,3) | YES | | Inches |
| `perimeter_edge_lf` | numeric(14,3) | YES | | Linear feet |
| `wire_mesh` | boolean | NO | `false` | Gage not linked yet |
| `drops_ff` | numeric(14,3) | YES | | Total LF of drops |
| `support_rebar_lb_per_sf` | numeric(8,4) | YES | | SOG support rebar override; NULL = system default |
| `pt_lb_per_sf` | numeric(8,4) | YES | | PT cable lb/SF override; NULL = system default |
| `notes` | text | YES | | |
| `sort_order` | integer | NO | `0` | Display order |
| `created_at` | timestamptz | NO | `now()` | |
| `updated_at` | timestamptz | NO | `now()` | |

## Columns — calculated (stored)

| Column | Type | Unit | Rule (from mono.md) |
|--------|------|------|---------------------|
| `calc_concrete_cy` | numeric(14,4) | CY | `(SF × thk/12/27) × (1+waste)` |
| `calc_sand_cy` | numeric(14,4) | CY | sand thickness same pattern |
| `calc_support_rebar_lb` | numeric(14,3) | lb | SF × 1.0 (default) |
| `calc_pt_cable_lb` | numeric(14,3) | lb | SF × 1.0 if PT else 0 |
| `calc_grade_beam_rebar_lb` | numeric(14,3) | lb | Sum of child grade beams |
| `calc_total_rebar_lb` | numeric(14,3) | lb | Support + grade beam |

### Constraints

- PK: `id`
- FK: `estimate_id` → `estimates(id)` ON DELETE CASCADE
- FK: `mix_design_id` → `mix_designs(id)` ON DELETE SET NULL
- CHECK: SF ≥ 0; thickness > 0; optional lengths ≥ 0
- Index: `mono_slabs_estimate_id_idx`

---

## Relationships

| Direction | Table | Notes |
|-----------|-------|-------|
| → | `estimates` | Parent estimate |
| → | `mix_designs` | Optional mix |
| ← | `grade_beams` | CASCADE |

### SQL helpers

```sql
SELECT calc_concrete_cy(9525, 4, 0.05);
SELECT calc_support_rebar_lb(9525, 1.0);
SELECT calc_pt_cable_lb(9525, true, 1.0);
SELECT calc_sand_cy(9525, 2, 0.05);
```

---

## Example

```sql
INSERT INTO mono_slabs (
  estimate_id, description, square_footage, thickness_in,
  post_tension, mix_design_id, sand_thickness_in, wire_mesh
) VALUES (
  (SELECT id FROM estimates LIMIT 1),
  'Garden Style',
  9525, 4, true,
  (SELECT id FROM mix_designs WHERE code = '3000'),
  2, false
)
RETURNING *;

-- Fill calcs (example; waste from estimate or settings)
UPDATE mono_slabs ms SET
  calc_concrete_cy = calc_concrete_cy(ms.square_footage, ms.thickness_in, 0.05),
  calc_sand_cy = calc_sand_cy(ms.square_footage, ms.sand_thickness_in, 0.05),
  calc_support_rebar_lb = calc_support_rebar_lb(ms.square_footage, 1.0),
  calc_pt_cable_lb = calc_pt_cable_lb(ms.square_footage, ms.post_tension, 1.0),
  updated_at = now()
WHERE ms.id = :slab_id;
```

---

## Notes / TODO

- mono.md marks Description, PT, Mix as required; DB only requires SF + thickness.
- Wire mesh is boolean only — no gage → `materials` link.
- No automatic refresh of `calc_*` on insert/update (trigger or app later).
