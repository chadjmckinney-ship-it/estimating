# Todo / Feature Backlog

Working list for the estimating system.  
Design: [mono.md](./mono.md) · DB notes: [notes.md](./notes.md)

**Last updated:** 2026-07-28

Status legend: `[ ]` todo · `[~]` in progress · `[x]` done · `[-]` deferred

---

## Done

- [x] Project workspace `~/Estimate_Projects` + Excel workbook copies
- [x] Postgres DB `estimating` on laptop
- [x] Core schema: projects, estimates, mono_slabs, grade_beams
- [x] Bar weights #3–#11 + locked CY/rebar/PT SQL functions
- [x] Supplier bid table + variance view
- [x] eTakeoff import audit table (shell)
- [x] Materials catalog from Pricing tab (58 items)
- [x] Design notes from web Grok (`docs/mono.md`)
- [x] DB notes + this todo
- [x] Expand `estimators` (role, phone, title, notes) + seed Chad as admin
- [x] FastAPI CRUD for estimators (`backend/`)
- [x] Expand `projects` from Notion bid list + `project_estimators`
- [x] Seed estimators Edward, Sam, Henry (from Notion)
- [x] FastAPI CRUD for projects
- [x] Expand mix_designs from Pricing/CONCRETE BIDS + suppliers/prices + API
- [x] Mix matrix: SC / ASH / Air-ASH for all PSI + 3000 integral color
- [x] Compare/sync materials vs New Current Worksheet Pricing
- [x] Equipment table + API (Pricing EQUIPMENT RENTAL)
- [x] Web UI shell (dashboard, projects, estimates create, catalogs)
- [x] Estimates API CRUD
- [x] Materials list API
- [x] Mono slab entry API + calcs + UI on estimate
- [x] Grade beams per mono pour (5+ types, rebar rollup)
- [x] Per-pour SOG support rebar / PT lb/SF rate overrides
- [x] PT cable LF: slab spacing + cables per GB type
- [x] Grade beam concrete CY added into each pour total
- [x] Per-pour beam kinds: grade_beam / exposed (EXP GB) / drop (Excel 04)
- [x] Poly/Stego SF: pour SF + beam wrap ((W+2H)/12)×L + waste_poly
- [x] Forming materials takeoff (Excel lumber/access from pour drivers)
- [x] Labor & supervision takeoff (Excel 04 rates, stored lines, editable)
- [x] Equipment takeoff (days ladder, rental tiers, pumping CY)

---

## Decisions to lock (before more schema)

- [ ] Confirm **waste factors** (concrete, sand, rebar) — defaults in `system_settings`
- [ ] Confirm **PT quantity** rule (currently 1.0 lb/SF) vs Pricing $/SF
- [ ] Confirm **slab support rebar** 1.0 lb/SF
- [~] Confirm **stirrup** weight method — hook allowance locked at 1.0 ft (`sql/023`).
      Still open: concrete cover deduction (bar is measured out-to-out today, runs
      16–39% heavy) and the missing end stirrup / unrounded count.
- [ ] Confirm **L-bar** weight method
- [ ] Full **mix design** list (w/ ash, sidewalk mixes, etc.) from Pricing / bids
- [ ] **Cost code** mapping from existing spreadsheet
- [ ] **Roles**: Admin vs Estimator vs Viewer (mono.md)
- [ ] Same assembly for non-PT mono slab vs separate (DB currently uses `post_tension` flag)

---

## Database / schema next

- [ ] Seed a **sample project** (e.g. Pearl Landing garden-style pour) for end-to-end calcs
- [ ] Wire mesh: optional **gage** link from `mono_slabs` → `materials` (not just boolean)
- [ ] Expand `mix_designs` (or new table) for **supplier mix bid grid**
- [ ] **Equipment** rental rates table (from Pricing)
- [ ] **Metro / joint / sawcutting** unit prices (from Pricing)
- [ ] **Job-level price overrides** (estimate-specific unit costs vs company defaults)
- [ ] `calc_l_bar_lb` (or fold into grade-beam total)
- [x] Service function to **refresh all `calc_*`** — `app/services/recalc.py`, exposed as
      `POST /api/estimates/{id}/recalc` (+ UI button) and `POST /api/system-settings/recalc-all`
- [ ] `cost_codes` table + link to materials / line items
- [ ] Roles / permissions tables (or defer until auth exists)
- [ ] Numbered migration discipline (`003_….sql`) + optional Alembic later
- [ ] Automated `pg_dump` backups under `Estimate_Projects/backups/`

---

## Product features (app)

### Import

- [ ] eTakeoff **CSV import** UI/API + column mapping
- [ ] Map Measurement List rows → mono slab / grade beam fields
- [ ] Re-import / update behavior (version or replace)

### Mono Slab estimating

- [x] Create/edit project + estimate
- [x] Enter main slab quantities
- [x] Enter grade beam bar schedules (per mono pour; 5+ types)
- [x] Live calculated CY, sand, support rebar, PT, grade-beam rebar, totals
- [x] Multi-pour / multi-location under one estimate

### Supplier comparison

- [ ] Enter supplier quotes (rebar weight/price, PT qty/price)
- [ ] Variance report (calc vs quote, lb and %)
- [ ] Multiple suppliers per estimate

### Catalogs / admin

- [ ] Materials browser + edit unit costs (Admin)
- [ ] Effective-dated rate history
- [ ] Mix design admin
- [~] System settings **API** done (`GET/PATCH /api/system-settings`; a PATCH rewrites
      affected estimates automatically). UI page still to build.

### Auth & multi-user

- [x] Estimators table + API (no passwords yet)
- [ ] Login / session
- [ ] Admin can edit rates & assemblies; Estimator cannot break formulas
- [ ] Audit who changed what
- [ ] Seed remaining estimator people (names TBD)

---

## Platform

- [ ] Choose and scaffold **backend** (FastAPI preferred)
- [ ] Choose and scaffold **frontend** (Flutter Web preferred)
- [ ] API for CRUD + calc endpoints
- [ ] Deploy path to **office Fedora** + Postgres
- [ ] HTTPS / LAN access for estimators

---

## Later assemblies (after Mono Slab is solid)

- [ ] Paving
- [ ] Sidewalks / hardscape
- [ ] Piers
- [ ] Grade beams / continuous footings standalone (`02-Gd Beams` sheet)
- [x] Exposed GBs + drops on mono pour (with grade beams)
- [ ] Walls & footings
- [ ] Elevated / CIP deck / slab on deck
- [ ] Panels / columns
- [ ] Generic `assemblies` engine if needed

---

## Nice to have

- [ ] Export estimate to PDF / Excel summary
- [ ] Proposal sheet generation
- [ ] Concrete yardage rollup by mix design
- [ ] Timeline / checklist (from workbook tabs)
- [ ] Sync materials from Whitecap / supplier files

---

## Immediate next (suggested order)

1. Mono slab UI + API on an estimate (quantities → calc_*)
2. Grade beams UI + rebar rollup
3. Optional: import open bids from Notion → `projects`
4. Lock waste + PT + stirrup decisions
5. Flutter Web later if you outgrow the static SPA
