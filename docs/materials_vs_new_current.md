# Materials vs New Current Worksheet

**Source file:** `workbooks/Downloads/New Current Worksheet.xlsm`  
**Sheet:** Pricing (lumber list cols **P–R**; steel/mesh/PT left column)  
**Synced:** `sql/007_materials_from_new_current.sql` (2026-07-29)

Copied from `~/Estimate_Project/New Current Worksheet.xlsm`.

---

## Layout difference

| Old seed (Updated Estimate Worksheet) | New Current Worksheet |
|---------------------------------------|------------------------|
| Lumber in cols **M–O** (Whitecap 5/12/2025) | Lumber in cols **P–R** (“84 lumber Price update 9-1-21”) |
| Mix grid simpler | Mix 1–10 across F–O (SRM prices) |
| Fewer vapor options | Expanded Stego / Yellow Guard / Raven / Perminator |

Unit cost used from Pricing **column Q** (includes sheet multiplier where present).

---

## Summary of sync

| Action | Count (approx) |
|--------|----------------:|
| Price updates on existing items | ~35 |
| Renames | 3 (REBAR PIERS, POLY, WIRE MESH 8→5 GAGE) |
| New active materials | ~17 |
| Soft-deactivated (old, not on sheet) | 3 |

**Active materials now:** 72 · **Inactive:** 3

---

## Notable price changes (DB was → New Current)

| Item | Was | Now |
|------|----:|----:|
| 2 X 4 / LF | 0.56 | **0.86** |
| 2 X 6 / LF | 0.66 | **1.45** |
| Forming ply / sheet | 50 | **74.75** |
| Nails / box | 42 | **68.20** |
| Tie wire / roll | 4 | **37.80** |
| PT cables / SF | 0.65 | **1.05** |
| Rebar grade beam / LB | 0.70 | **0.55** |
| Rebar paving / LB | 0.65 | **0.50** |
| Rock / CY | 40 | **45** |
| Slab cure / drum | 540 | **567.50** |

---

## Added from New Current

- Anchor bolts ½″×8″ Galv, ½″×10″ Galv  
- Smooth dowels ½×24, ½×30, ⅝×24, ¾×24  
- Stego 10/15 mil, Yellow Guard 10/15 mil, tapes  
- Perminator 15 mil, Raven 10 mil, R.W. Meadows roll  
- POLY 10 mil 20×100 Black (replaces “POLY 10 mill”)

## Soft-deactivated (not on new Pricing)

- STEGO WRAP 10 mil. 20 x 150  
- RW Medows 15 mil VAPOR MAT  
- Generic ANCHOR BOLTS (BOX)

---

## Unchanged / note

- ACCESSORIES $0.04/LB, FORM RELEASE, BOND BREAKER, WALL TIES, many structural items  
- Sand still $25/CY  
- Wire mesh **5 GAGE** replaced former **8 GAGE** row (workbook has 10 / 6 / 5, not 8)

---

## Not imported (still on Pricing, separate tables later)

- Equipment rental day rates  
- Metro / sawcutting / joint prices  
- Concrete mix bid grid (Mix 1–10) — handled by `mix_designs` / `mix_prices`  
- Redi-mix supplier contact block  

---

## Verify

```bash
psql -d estimating -c "SELECT name, unit, unit_cost FROM materials WHERE is_active ORDER BY sort_order;"
```
