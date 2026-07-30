# Forming materials (mono slab)

Estimate-level lumber / access takeoff for Excel **04 → LUMBER AND ACCESS** (ACC #02).

## Where it is stored

| Object | Purpose |
|--------|---------|
| **`estimate_forming_lines`** | One row per material line (qty, unit, $, formula, material_id) |
| **`estimate_forming_summary`** | Drivers used on last refresh (perim, drops, SF, form%, total $) |
| **`estimates.form_percent`** | Per-estimate **% of forms** (NULL → system default) |
| **`system_settings.form_percent`** | Company default 0.50 |
| **`system_settings.form_waste`** | Optional waste on extended cost |

### What form% multiplies

| Uses form% | Does **not** use form% |
|------------|------------------------|
| 2×4, 2×6, 2×10 | Bracing, nails, anchors |
| Forming ply | Slab chairs, tie wire, cure |
| Masonite / siding | Keyway, chamfer, redwood, form release |
| (Stakes follow 2×10 qty, so they move with form% indirectly) | |

Not stored on pours. Recalc writes the estimate tables via **Refresh from pours**.

| | |
|--|--|
| **API** | `GET /api/estimates/{id}/forming-materials` (auto-saves if empty) |
| | `POST /api/estimates/{id}/forming-materials/refresh` |
| **UI** | Estimate detail → header **Forming materials** (scrolls) or card at bottom |
| **Settings** | `form_percent` (default **0.50**), `form_waste` |
| **Migration** | `sql/016_estimate_forming_lines.sql` |

## Drivers (from mono pours)

| Driver | Source |
|--------|--------|
| `total_sf` | Σ `mono_slabs.square_footage` |
| `perimeter_lf` | Σ `mono_slabs.perimeter_edge_lf` |
| `drops_ff` | Σ `grade_beams.length_lf` WHERE `kind='drop'` |
| `mesh_sf` | Σ SF of pours with `wire_mesh` |
| `total_rebar_lb` | Σ pour rebar (accessories) |
| `form_percent` | system setting (Excel W65; LBJ used 50%) |

## Qty rules (locked)

| Material | Qty |
|----------|-----|
| 2 X 6 X 16' | `perimeter × form%` |
| 2 X 4 X 16' | `(2x6_LF × 3 + drops_ff) × form%` |
| 2 x 4 BRACING | `3 × drops_ff` (Excel also summed drop *type* codes — we use FF only) |
| 2 X 10 X 16' | `perimeter × form% × 2` |
| Siding (16' lengths) | `ceil(perimeter × 0.03 / 16)` |
| 3/4" forming ply | `drops_ff / 32 × form% × 1.1` |
| 2x2x30 stakes | `round(2x10_LF / 25)` bundles |
| 16p / 8p / 20p nails | `ceil(perimeter × 1.25 / 500)` boxes each |
| Anchor bolts | `perimeter / 150` boxes |
| Keyway / chamfer / 1x6 / 1x8 RW | **manual** (0) |
| Slab chairs | `ceil(SF / 15000)` bags |
| Tie wire | `SF / 15000` rolls |
| Accessories | `rebar_lb + mesh_sf × 0.75` lb |
| Slab cure | `ceil(SF / 300 / 55)` drums |
| Form release | **manual** (0 for typical SOG) |

Catalog unit costs applied when name matches `materials`.

## LBJ check (form% = 0.50, perim 4890, drops 865, SF 62723)

| Item | Excel | App target |
|------|------:|----------:|
| 2x6 | 2445 LF | 2445 |
| 2x4 | 4100 LF | 4100 |
| 2x10 | 4890 LF | 4890 |
| ply | ~14.87 sht | 14.867 |
| stakes | 196 bndl | 196 |
| 16p | 13 box | 13 |
| bracing | 3027 LF | 2595 (FF-only; Excel + type codes) |

## Migration

`sql/015_forming_materials.sql`

## Later

- Carton forms GB / slab (Y/N + LF/SF)
- Override form% per estimate
- Manual qty overrides on lines
- Box forms (8.5" / 12")
- Exp/drop extra forming beyond SOG edge package
