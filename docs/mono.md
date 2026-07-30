# Mono Slab Estimating Module – Design Notes

**Last updated:** 2026-07-28  
**Status:** Core calculation rules and fields locked for v1 (PT SOG)

---

## Project Goal

Build a web-based estimating system (starting with Mono Slab) that:

- Replaces fragile Excel formulas with locked calculation logic
- Supports multiple estimators (4+ people)
- Imports quantities from eTakeoff (CSV)
- Calculates rebar & PT quantities, then allows comparison against supplier bids
- Runs on the office Fedora server with PostgreSQL

The long-term goal is to reduce key-person risk while preserving the 20-year depth of the existing spreadsheet logic.

---

## Tech Direction

| Layer              | Choice                          | Notes                                      |
|--------------------|---------------------------------|--------------------------------------------|
| Server             | Fedora (office server)          | Full control, self-hosted                  |
| Database           | PostgreSQL                      | Familiar relational model                  |
| Backend            | TBD (Python/FastAPI preferred)  |                                            |
| Frontend           | TBD (Flutter Web preferred)     | Existing Flutter experience                |
| Import             | eTakeoff Measurement List → CSV | Map measurements to assemblies             |
| Auth / Permissions | Simple roles                    | Admin (rates/assemblies) vs Estimator      |

---

## Mono Slab – Quantity Inputs

### Main Slab

| Field                    | Type     | Notes / Example                          | Required |
|--------------------------|----------|------------------------------------------|----------|
| Description / Location   | text     | "Garden Style", "Bld 1 Pour 3"           | Yes      |
| Square Footage           | decimal  | 9525                                     | Yes      |
| Thickness (inches)       | decimal  | 4                                        | Yes      |
| Post Tension             | boolean  | true / false                             | Yes      |
| Mix Design               | lookup   | 3000 PSI w/ Ash, 3500, 4000, etc.        | Yes      |
| Sand Thickness (inches)  | decimal  | 2                                        | No       |
| Perimeter Edge (LF)      | decimal  | 500                                      | No       |
| Wire Mesh                | boolean  |                                          | No       |
| Drops (FF)               | decimal  | Total linear feet of drops               | No       |
| Notes                    | text     |                                          | No       |

### Grade Beams / Exposed GBs / Drops (per pour)

Excel **04** pour columns **GRADE BEAMS**, **EXP GB**, and **Drops** share one bar-schedule shape. Stored as `grade_beams` with `kind`:

| `kind` | Excel | Notes |
|--------|-------|--------|
| `grade_beam` | GRADE BEAMS | Optional PT cables |
| `exposed` | EXP GB | No PT |
| `drop` | Drops | No PT; pour-level `drops_ff` remains a simple LF total if used |

| Field              | Type               | Notes                          |
|--------------------|--------------------|--------------------------------|
| Kind               | enum               | grade_beam / exposed / drop    |
| Label              | text               | e.g. GB1, Perimeter, EXP 1     |
| Width (in)         | decimal            |                                |
| Height (in)        | decimal            |                                |
| Length (LF)        | decimal            |                                |
| Top Bars           | # + size           | e.g. 2 - #5                    |
| Bottom Bars        | # + size           |                                |
| Mid Bars           | # + size           | optional                       |
| Stirrups           | size + spacing     | e.g. #3 @ 18"                  |
| L-Bars             | # + size + spacing | optional                       |
| PT cables (#)      | integer            | grade_beam only                |
| Notes              | text               |                                |

---

## Calculation Rules (PT Slab on Grade)

| Item                        | Rule                                                                 | Unit      |
|----------------------------|----------------------------------------------------------------------|-----------|
| Concrete CY                | (SF × Thickness_in / 12 / 27) × (1 + waste factor)                  | CY        |
| Slab Mat Rebar             | (2 × SF × 12 / spacing_in) LF each way × lb/ft(size) × (1 + waste_rebar) | lbs   |
| Slab Support Rebar         | SF × **0.1** lb/SF — chairs / dowels / misc only                    | lbs       |
| PT Cable Quantity          | SF × **1.0** lb/SF                                                  | lbs       |
| Grade Beam / Exp / Drop Rebar | Same bar schedule for all three kinds; sum into pour             | lbs       |
| Grade Beam / Exp / Drop CY | Same (W×H×L)/(144×27)×(1+waste); sum into pour concrete             | CY        |
| **Total Rebar**            | Slab Mat + Slab Support + (GB + Exp + Drop) rebar                   | lbs / tons|
| Exp / Drop forming & labor | Additional to GBs (cost sheet later); materials already on pour     | $         |
| Sand CY                    | (SF × Sand_Thickness_in / 12 / 27) × (1 + waste)                    | CY        |
| Poly / Stego SF            | Pour SF + Σ((2×H″)/12 × L) for beams (sides only, Excel); × (1 + waste_poly) | SF        |

### Standard Bar Weights (lb/ft)

| Bar Size | Weight (lb/ft) |
|----------|----------------|
| #3       | 0.376          |
| #4       | 0.668          |
| #5       | 1.043          |
| #6       | 1.502          |
| #7       | 2.044          |
| #8       | 2.670          |
| #9       | 3.400          |
| #10      | 4.303          |
| #11      | 5.313          |

**Grade Beam rebar weight calculation:**

```
Weight = (Number of bars × Length_ft × Weight_per_ft)
       + stirrup weight (based on spacing + perimeter of stirrup)
       + any L-bars
```

System calculates theoretical quantities. Estimator then enters supplier quoted quantities/prices for variance checking.

---

## Supplier Bid Comparison Fields

| Field                     | Type     | Notes                              |
|---------------------------|----------|------------------------------------|
| Supplier                  | text     | Rebar supplier / PT supplier       |
| Quoted Rebar Weight       | lbs/tons |                                    |
| Quoted Rebar Price        | $        |                                    |
| Quoted PT Quantity        |          |                                    |
| Quoted PT Price           | $        |                                    |
| Variance (calculated)     |          | System calculated vs quoted        |
| Notes                     | text     |                                    |

---

## High-Level Data Model (First Version)

- `projects` – job header info
- `cost_codes` – mirrors existing budget codes
- `rate_tables` – material, labor, equipment rates (with effective dates)
- `assemblies` – e.g. “Mono Slab”
- `assembly_fields` – defines required quantity inputs per assembly
- `project_assemblies` – one row per pour/location on a bid
- `project_assembly_quantities` – entered or imported values
- `project_assembly_results` – calculated CY, rebar, costs, etc.
- `etakeoff_imports` – raw CSV import records + mapping status
- `users` + simple roles (Admin / Estimator / Viewer)

---

## Open / Next Decisions

- Concrete, rebar, and sand **waste factors** (defaults)
- Full list of mix designs and master rate tables
- Exact cost-code mapping from existing spreadsheet
- Permission model details
- Whether to support non-PT mono slabs in the same assembly or as a separate one
- Stirrup weight calculation details (perimeter method, hooks, etc.)

---

## Notes from Discussion

- Current master Excel template is copied for each new bid. Updating the master propagates to new jobs only.
- Goal is to protect calculation logic so other estimators cannot accidentally break formulas.
- eTakeoff remains the takeoff tool; this system focuses on the estimating/calculation layer.
- Start narrow: Mono Slab / Garden Style first, then expand to paving, sidewalks, elevated, etc.

---

---

## Related docs (this repo)

| File | Purpose |
|------|---------|
| [notes.md](./notes.md) | PostgreSQL schema, migrations, conventions |
| [tables/](./tables/) | One page per DB table |
| [materials.md](./materials.md) | Full materials catalog browse |
| [todo.md](./todo.md) | Feature backlog and open decisions |
| [REQUIREMENTS.md](./REQUIREMENTS.md) | Short requirements baseline |

Physical schema today is Mono-Slab-specific (`mono_slabs`, `grade_beams`, …) rather than the generic `assemblies` model above — see notes.md.

---

*This file is the working source of truth for the Mono Slab module design. Update it as decisions are locked.*
