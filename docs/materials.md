# Materials Catalog

Browseable copy of the `materials` table in the **estimating** database.

| | |
|--|--|
| **Source workbook** | `workbooks/Downloads/New Current Worksheet.xlsm` → **Pricing** (cols P–R) |
| **Also** | Earlier seed from Updated Estimate Worksheet (Whitecap); superseded by `007` |
| **Seed / sync** | `sql/002_materials.sql` then `sql/007_materials_from_new_current.sql` |
| **Active rows** | 72 (+ 3 inactive) |
| **Last synced** | 2026-07-29 |
| **Diff notes** | [materials_vs_new_current.md](./materials_vs_new_current.md) |

Names and spellings match the Excel sheet (including POLSTERS, ROCK DELEVERED, RW Medows).

```bash
# Live data
psql -d estimating -c "SELECT category, name, unit, unit_cost FROM materials ORDER BY sort_order;"
```

Related: [tables/materials.md](./tables/materials.md) (schema) · [notes.md](./notes.md) · [todo.md](./todo.md) · [mono.md](./mono.md)

---

## Units

| Unit | Meaning |
|------|---------|
| LF | Linear foot |
| SF | Square foot |
| LB | Pound |
| EA | Each |
| CY | Cubic yard |
| CF | Cubic foot |
| SHEET | Sheet |
| BOX | Box |
| BAG | Bag |
| BUNDLE | Bundle |
| ROLL | Roll |
| DRUM | Drum |

`unit_note` holds pack size or size detail when the unit alone is not enough (e.g. `50/BOX`, `2" x 4 x 8`).

---

## Summary by category

| Category | Count | What it is |
|----------|------:|------------|
| [lumber](#lumber) | 18 | Form lumber, ply, stakes, nails, keyway/chamfer |
| [structural_accessories](#structural-accessories) | 12 | Chairs, pier hardware, inserts, tie wire |
| [site_accessories](#site-accessories) | 6 | Paving chairs, snap ties, poly |
| [chemical](#chemical) | 3 | Cure, form release, bond breaker |
| [vapor_barrier](#vapor-barrier) | 5 | Poly / Stego / vapor mat rolls |
| [foam](#foam) | 2 | Foam fill void (two units) |
| [form_accessories](#form-accessories) | 1 | Misc accessories by weight |
| [aggregate](#aggregate) | 2 | Sand, rock delivered |
| [steel](#steel) | 5 | Rebar rates, dowels |
| [mesh](#mesh) | 3 | Wire mesh by gage |
| [pt](#pt) | 1 | Post-tension cables ($/SF in Pricing) |

---

## Lumber

Whitecap unit costs (Pricing cols M–O).

| ID | Name | Unit | Unit cost | Note |
|---:|------|------|----------:|------|
| 1 | 2 X 4  X 16' | LF | 0.5625 | |
| 2 | 2 X 6 X 16' | LF | 0.6563 | |
| 3 | 2 X 8 X 16' | LF | 1.0000 | |
| 4 | 2 X 10 X 16' | LF | 1.2500 | |
| 5 | 3/4 " FORMING PLY | SHEET | 50.0000 | |
| 6 | MASONITE SIDING | SHEET | 19.0000 | |
| 7 | 1 X 1 TACT STRIP | LF | 0.1500 | |
| 8 | 1 X 4 RED WOOD | LF | 1.0000 | |
| 9 | 1 X 6 RED WOOD | LF | 1.2500 | |
| 10 | 1 X 8 RED WOOD | LF | 0.9000 | |
| 12 | 2 x 2 x 30 Stakes | BUNDLE | 18.0000 | |
| 13 | 16p NAILS DUPLEX | BOX | 42.0000 | |
| 14 | 8p DUPLEX | BOX | 42.0000 | |
| 15 | 6p NAILS | BOX | 42.0000 | |
| 16 | KEYWAY | LF | 0.7800 | |
| 17 | CHAMFER | LF | 0.1600 | |
| 18 | WALL TIES | BOX | 45.0000 | 50/BOX |
| 19 | 1 X 2 X 18" STAKES | BUNDLE | 8.0000 | |

---

## Form accessories

| ID | Name | Unit | Unit cost | Note |
|---:|------|------|----------:|------|
| 11 | ACCESSORIES | LB | 0.0400 | Misc accessories by weight |

---

## Structural accessories

| ID | Name | Unit | Unit cost | Note |
|---:|------|------|----------:|------|
| 20 | METAL CHAIRS 2.5" | BAG | 45.0000 | BAG/500 |
| 21 | LIFT INSERT | EA | 12.0000 | |
| 22 | CAMLOCKS | EA | 0.2500 | |
| 23 | TURNBUCKLES | EA | 0.7500 | |
| 24 | PATCH MATERIAL | BAG | 15.0000 | |
| 25 | PIER SLEDS | EA | 1.7000 | |
| 26 | PIER BOOTS | EA | 2.7000 | |
| 27 | SLAB CHAIRS | BAG | 27.0000 | |
| 28 | POLSTERS | LF | 1.2500 | Workbook spelling (bolsters?) |
| 29 | BRACE INSERTS | EA | 8.0000 | |
| 30 | ANCHOR BOLTS | BOX | 25.5000 | |
| 31 | TIE WIRE | ROLL | 4.0000 | |

---

## Site accessories

| ID | Name | Unit | Unit cost | Note |
|---:|------|------|----------:|------|
| 32 | 2-1/4 PAVING CHAIRS | BAG | 20.0000 | |
| 33 | 3-1/4 PAVING CHAIRS | BAG | 35.0000 | |
| 34 | ANCHOR BOLTS 8"x1/2" (50/BX) | BOX | 20.0000 | 50/BX |
| 35 | SPEED DOWEL INSERT w/ BASE | EA | 1.0000 | |
| 36 | SNAP TIES | BOX | 40.0000 | |
| 37 | POLY 10 mill | ROLL | 100.0000 | |

---

## Chemical

| ID | Name | Unit | Unit cost | Note |
|---:|------|------|----------:|------|
| 38 | SLAB CURE | DRUM | 540.0000 | |
| 39 | FORM RELEASE | DRUM | 542.0000 | |
| 40 | BOND BREAKER | DRUM | 635.0000 | |

---

## Vapor barrier

| ID | Name | Unit | Unit cost | Note |
|---:|------|------|----------:|------|
| 41 | 6 mil 20 x 100 | ROLL | 60.0000 | |
| 42 | 6 mil 32 x 100 | ROLL | 80.0000 | |
| 43 | 10 mil 20 x 100 | ROLL | 120.0000 | |
| 44 | STEGO WRAP 10 mil. 20 x 150 | ROLL | 400.0000 | |
| 45 | RW Medows 15 mil VAPOR MAT | ROLL | 355.0000 | Workbook spelling |

---

## Foam

Same material name, two sell units in the workbook.

| ID | Name | Unit | Unit cost | Note |
|---:|------|------|----------:|------|
| 46 | FOAM FILL VOID | EA | 22.7600 | 2" x 4 x 8 |
| 47 | FOAM FILL VOID | CF | 1.6500 | |

---

## Aggregate

Pricing left-column unit rates (not Whitecap lumber list).

| ID | Name | Unit | Unit cost | Note |
|---:|------|------|----------:|------|
| 48 | SAND DELIVERED PER CY | CY | 25.0000 | Renamed 2026-09-05 (`sql/060`): the Excel label said per ton, the unit was /YD, and Chad settled it — sand is per CY |
| 49 | ROCK DELEVERED PER TON | CY | 40.0000 | Workbook spelling |

---

## Steel

| ID | Name | Unit | Unit cost | Note |
|---:|------|------|----------:|------|
| 50 | REBAR PIERS | LB | 0.7000 | |
| 51 | REBAR GRADE BEAM | LB | 0.7000 | |
| 52 | REBAR PAVING | LB | 0.6500 | |
| 53 | DOWEL SPACING / 3/4" & CAP | EA | 2.0000 | |
| 58 | 1/2" SMOOTH DOWELS & CAP | EA | 1.7500 | |

---

## Mesh

| ID | Name | Unit | Unit cost | Note |
|---:|------|------|----------:|------|
| 54 | WIRE MESH 10 GAGE | SF | 0.4000 | 10 GAGE |
| 55 | WIRE MESH 8 GAGE | SF | 0.4000 | 8 GAGE |
| 56 | WIRE MESH 6 GAGE | SF | 0.4000 | 6 GAGE |

---

## PT

| ID | Name | Unit | Unit cost | Note |
|---:|------|------|----------:|------|
| 57 | POST TENSION CABLES | SF | 0.6500 | **Unit price** ($/SF). Quantity rule in mono.md is still SF × 1.0 **lb**/SF — different purpose. |

---

## Full flat list (all 58)

| ID | Category | Name | Unit | Cost | Note | Supplier | As of |
|---:|----------|------|------|-----:|------|----------|-------|
| 1 | lumber | 2 X 4  X 16' | LF | 0.5625 | | Whitecap | 2025-05-12 |
| 2 | lumber | 2 X 6 X 16' | LF | 0.6563 | | Whitecap | 2025-05-12 |
| 3 | lumber | 2 X 8 X 16' | LF | 1.0000 | | Whitecap | 2025-05-12 |
| 4 | lumber | 2 X 10 X 16' | LF | 1.2500 | | Whitecap | 2025-05-12 |
| 5 | lumber | 3/4 " FORMING PLY | SHEET | 50.0000 | | Whitecap | 2025-05-12 |
| 6 | lumber | MASONITE SIDING | SHEET | 19.0000 | | Whitecap | 2025-05-12 |
| 7 | lumber | 1 X 1 TACT STRIP | LF | 0.1500 | | Whitecap | 2025-05-12 |
| 8 | lumber | 1 X 4 RED WOOD | LF | 1.0000 | | Whitecap | 2025-05-12 |
| 9 | lumber | 1 X 6 RED WOOD | LF | 1.2500 | | Whitecap | 2025-05-12 |
| 10 | lumber | 1 X 8 RED WOOD | LF | 0.9000 | | Whitecap | 2025-05-12 |
| 11 | form_accessories | ACCESSORIES | LB | 0.0400 | | Whitecap | 2025-05-12 |
| 12 | lumber | 2 x 2 x 30 Stakes | BUNDLE | 18.0000 | | Whitecap | 2025-05-12 |
| 13 | lumber | 16p NAILS DUPLEX | BOX | 42.0000 | | Whitecap | 2025-05-12 |
| 14 | lumber | 8p DUPLEX | BOX | 42.0000 | | Whitecap | 2025-05-12 |
| 15 | lumber | 6p NAILS | BOX | 42.0000 | | Whitecap | 2025-05-12 |
| 16 | lumber | KEYWAY | LF | 0.7800 | | Whitecap | 2025-05-12 |
| 17 | lumber | CHAMFER | LF | 0.1600 | | Whitecap | 2025-05-12 |
| 18 | lumber | WALL TIES | BOX | 45.0000 | 50/BOX | Whitecap | 2025-05-12 |
| 19 | lumber | 1 X 2 X 18" STAKES | BUNDLE | 8.0000 | | Whitecap | 2025-05-12 |
| 20 | structural_accessories | METAL CHAIRS 2.5" | BAG | 45.0000 | BAG/500 | Whitecap | 2025-05-12 |
| 21 | structural_accessories | LIFT INSERT | EA | 12.0000 | | Whitecap | 2025-05-12 |
| 22 | structural_accessories | CAMLOCKS | EA | 0.2500 | | Whitecap | 2025-05-12 |
| 23 | structural_accessories | TURNBUCKLES | EA | 0.7500 | | Whitecap | 2025-05-12 |
| 24 | structural_accessories | PATCH MATERIAL | BAG | 15.0000 | | Whitecap | 2025-05-12 |
| 25 | structural_accessories | PIER SLEDS | EA | 1.7000 | | Whitecap | 2025-05-12 |
| 26 | structural_accessories | PIER BOOTS | EA | 2.7000 | | Whitecap | 2025-05-12 |
| 27 | structural_accessories | SLAB CHAIRS | BAG | 27.0000 | | Whitecap | 2025-05-12 |
| 28 | structural_accessories | POLSTERS | LF | 1.2500 | | Whitecap | 2025-05-12 |
| 29 | structural_accessories | BRACE INSERTS | EA | 8.0000 | | Whitecap | 2025-05-12 |
| 30 | structural_accessories | ANCHOR BOLTS | BOX | 25.5000 | | Whitecap | 2025-05-12 |
| 31 | structural_accessories | TIE WIRE | ROLL | 4.0000 | | Whitecap | 2025-05-12 |
| 32 | site_accessories | 2-1/4 PAVING CHAIRS | BAG | 20.0000 | | Whitecap | 2025-05-12 |
| 33 | site_accessories | 3-1/4 PAVING CHAIRS | BAG | 35.0000 | | Whitecap | 2025-05-12 |
| 34 | site_accessories | ANCHOR BOLTS 8"x1/2" (50/BX) | BOX | 20.0000 | 50/BX | Whitecap | 2025-05-12 |
| 35 | site_accessories | SPEED DOWEL INSERT w/ BASE | EA | 1.0000 | | Whitecap | 2025-05-12 |
| 36 | site_accessories | SNAP TIES | BOX | 40.0000 | | Whitecap | 2025-05-12 |
| 37 | site_accessories | POLY 10 mill | ROLL | 100.0000 | | Whitecap | 2025-05-12 |
| 38 | chemical | SLAB CURE | DRUM | 540.0000 | | Whitecap | 2025-05-12 |
| 39 | chemical | FORM RELEASE | DRUM | 542.0000 | | Whitecap | 2025-05-12 |
| 40 | chemical | BOND BREAKER | DRUM | 635.0000 | | Whitecap | 2025-05-12 |
| 41 | vapor_barrier | 6 mil 20 x 100 | ROLL | 60.0000 | | Whitecap | 2025-05-12 |
| 42 | vapor_barrier | 6 mil 32 x 100 | ROLL | 80.0000 | | Whitecap | 2025-05-12 |
| 43 | vapor_barrier | 10 mil 20 x 100 | ROLL | 120.0000 | | Whitecap | 2025-05-12 |
| 44 | vapor_barrier | STEGO WRAP 10 mil. 20 x 150 | ROLL | 400.0000 | | Whitecap | 2025-05-12 |
| 45 | vapor_barrier | RW Medows 15 mil VAPOR MAT | ROLL | 355.0000 | | Whitecap | 2025-05-12 |
| 46 | foam | FOAM FILL VOID | EA | 22.7600 | 2" x 4 x 8 | Whitecap | 2025-05-12 |
| 47 | foam | FOAM FILL VOID | CF | 1.6500 | | Whitecap | 2025-05-12 |
| 48 | aggregate | SAND DELIVERED PER CY | CY | 25.0000 | renamed from PER TON, `sql/060` | | 2025-05-12 |
| 49 | aggregate | ROCK DELEVERED PER TON | CY | 40.0000 | | | 2025-05-12 |
| 50 | steel | REBAR PIERS | LB | 0.7000 | | | 2025-05-12 |
| 51 | steel | REBAR GRADE BEAM | LB | 0.7000 | | | 2025-05-12 |
| 52 | steel | REBAR PAVING | LB | 0.6500 | | | 2025-05-12 |
| 53 | steel | DOWEL SPACING / 3/4" & CAP | EA | 2.0000 | | | 2025-05-12 |
| 54 | mesh | WIRE MESH 10 GAGE | SF | 0.4000 | 10 GAGE | | 2025-05-12 |
| 55 | mesh | WIRE MESH 8 GAGE | SF | 0.4000 | 8 GAGE | | 2025-05-12 |
| 56 | mesh | WIRE MESH 6 GAGE | SF | 0.4000 | 6 GAGE | | 2025-05-12 |
| 57 | pt | POST TENSION CABLES | SF | 0.6500 | | | 2025-05-12 |
| 58 | steel | 1/2" SMOOTH DOWELS & CAP | EA | 1.7500 | | | 2025-05-12 |

---

## Not in this catalog yet

Still on the Pricing tab, not imported:

- Equipment rental day rates (backhoe, bobcat, crane, etc.)
- Metro / sawcutting / joint / expansion unit prices
- Concrete supplier mix bid grid (company, contact, mix $/CY columns)

See [todo.md](./todo.md) for those tables.

---

## Regenerating this file

When unit costs change in the DB, re-export or ask the CLI to refresh this doc from:

```sql
SELECT id, category, name, unit, unit_cost, unit_note, supplier_ref, price_as_of
FROM materials
ORDER BY sort_order;
```
