# Todo / Feature Backlog

Working list for the estimating system.  
Design: [mono.md](./mono.md) · DB notes: [notes.md](./notes.md)

**Last updated:** 2026-08-30

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
- [x] Poly/Stego SF: pour SF + beam wrap ((2×H)/12)×L (two sides only) + waste_poly
- [x] Forming materials takeoff (Excel lumber/access from pour drivers)
- [x] Labor & supervision takeoff (Excel 04 rates, stored lines, editable)
- [x] Equipment takeoff (days ladder, rental tiers, pumping CY)
- [x] Git repo + private GitHub remote (`chadjmckinney-ship-it/estimating`)
- [x] Estimate waste bounds + DB check constraints (`sql/020`)
- [x] Estimate edits recalculate pours and takeoffs (was silently stale)
- [x] Slab bar mat from size + spacing, each way (`sql/021`); `waste_rebar`
      finally used, as the lap allowance
- [x] Support rebar re-based to 0.1 lb/SF = chairs/dowels only
- [x] Drops retired from `mono_slabs`; entered as `kind='drop'` beams (`sql/022`)
- [x] Beam edits refresh forming/labor/equipment (was silently stale)
- [x] `system_settings` API + recalc; non-manual rates now track defaults
- [x] Stirrup hook allowance 1.0 ft (`sql/023`)
- [x] Frontend tooling: `node --check`, oxlint, Playwright smoke tests
- [x] Grade beams as a per-estimate type library + per-pour lengths (`sql/025`)
- [x] Beam schedule section on the estimate page (define/edit types, usage rollups)
- [x] Backend test harness + calc/staleness tests (`cd backend && pytest`)
- [x] Editable catalogs (materials, equipment, mix designs + supplier price grid)
- [x] Bulk recalcs skip `final` / `archived` estimates

---

## Live data problems

- [ ] **Concrete is priced at $0/CY on every estimate.** All 16 mix designs have
      `unit_cost` NULL *and* zero rows in `mix_prices`, so `_mix_unit_cost()`
      returns 0 and `costing._direct_cost` adds nothing for concrete. On
      `04-PT Slab on Grade` that is 2,161.75 CY costing nothing inside a
      $370,854.93 total — at ~$150/CY the estimate is roughly $324k light. The
      three suppliers (Argos, Martin Marietta, SRM) exist with no quotes against
      them. Fix from the Mix designs page: enter a unit cost per mix, or the
      per-supplier quotes, then Reprice open estimates.
- [ ] Enter `pt_spacing_in` on the LBJ PT pours so cable LF stops reading 0
      (see the PT decision below)

## Decisions to lock (before more schema)

- [ ] Confirm **waste factors** (concrete, sand, rebar) — defaults in `system_settings`
- [ ] Confirm **PT quantity** rule (currently 1.0 lb/SF) vs Pricing $/SF —
      **live gap**: LBJ's 16 PT pours have no `pt_spacing_in`, so cable LF is 0
      and the estimate rides entirely on the flat lb/SF rate
- [x] ~~Confirm slab support rebar 1.0 lb/SF~~ — superseded: mat is priced from
      size + spacing, support is 0.1 lb/SF for chairs/dowels only
- [~] Confirm **stirrup** weight method — hook allowance locked at 1.0 ft (`sql/023`).
      Still open: concrete cover deduction (bar is measured out-to-out today, runs
      16–39% heavy) and the missing end stirrup / unrounded count.
- [ ] Confirm **L-bar** weight method — today they price as plain long bars;
      `l_bars_spacing_in` is captured but unused
- [ ] Full **mix design** list (w/ ash, sidewalk mixes, etc.) from Pricing / bids
- [ ] **Cost code** mapping from existing spreadsheet
- [ ] **Roles**: Admin vs Estimator vs Viewer (mono.md)
- [ ] Same assembly for non-PT mono slab vs separate (DB currently uses `post_tension` flag)

---

## Database / schema next

- [ ] Seed a **sample project** (e.g. Pearl Landing garden-style pour) for end-to-end calcs
- [ ] Wire mesh: optional **gage** link from `mono_slabs` → `materials` (not just boolean)
- [ ] Expand `mix_designs` (or new table) for **supplier mix bid grid**
- [ ] **Metro / joint / sawcutting** unit prices (from Pricing)
- [ ] **Job-level price overrides** (estimate-specific unit costs vs company defaults)
- [ ] `calc_l_bar_lb` (or fold into grade-beam total)
- [ ] Stirrup formula: concrete cover deduction + missing end stirrup —
      currently 16–39% heavy on stirrup steel (`sql/023` header has the numbers)
- [ ] Fix the 10 drop beams left on placeholder 12×12 dimensions:
      `SELECT * FROM grade_beams WHERE label LIKE 'Drop (migrated%';`
- [x] Service function to **refresh all `calc_*`** — `app/services/recalc.py`, exposed as
      `POST /api/estimates/{id}/recalc` (+ UI button) and `POST /api/system-settings/recalc-all`
- [ ] `cost_codes` table + link to materials / line items
- [ ] Roles / permissions tables (or defer until auth exists)
- [ ] Numbered migration discipline + optional Alembic later — **two `015_` files
      exist**, and nothing records which migrations have been applied to a database.
      Every test run now rebuilds `estimating_test` by applying `001`–`026` in
      filename order, so the chain is at least known to work on an empty database
      (the two `015_` files are independent; forming-then-poly is the live order)
- [ ] Automated `pg_dump` backups under `Estimate_Projects/backups/` — the repo
      backs up code only; the database exists on this laptop alone

---

## Testing

- [x] Frontend: `npm run verify` — `node --check`, oxlint, Playwright smoke tests
      (read-only against the live DB; fail on any console error)
- [x] Fixture/seed database so tests do not run against live bids —
      `backend/tests/dbsetup.py` builds `estimating_test` from `sql/`, refuses any
      database not ending in `_test`, and every test rolls back (savepoints, so
      the services' own `commit()`s roll back too)
- [~] **Backend calc tests** — 64 tests, `cd backend && pytest`. Covered: the nine
      locked SQL helpers (golden numbers), `refresh_mono_slab_calcs` (CY, mat and
      support steel, poly, PT, beam rollups, per-pour and per-estimate
      overrides), and all three staleness bugs as regression tests — estimate
      waste, `system_settings` PATCH, beam edits — plus `is_manual` survival and
      `settings_scope`. **Still untested:** the forming and equipment line
      formulas (only that they refresh, not what they compute), the routers, and
      `costing.refresh_pour_costs`.
- [ ] Golden-number test: one full estimate checked against the Excel workbook

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

- [x] Materials browser + edit unit costs — add / edit / deactivate, search and
      category filter, show-inactive toggle (`POST` and `DELETE /api/materials`
      added; the UI never called the existing `PATCH`)
- [x] Mix design admin — add / edit / deactivate, plus the per-supplier $/CY grid
      (add / edit / remove quotes; `DELETE /api/mix-prices/{id}` added). The modal
      says which basis costing will use: the mix's own unit cost, else the
      cheapest quote, else $0
- [x] Equipment admin — add / edit / deactivate rental rates
- [x] **Catalog prices never auto-reprice.** A price edit stores and stops there;
      a "Reprice open estimates" button on each catalog page pushes it through.
      `final` and `archived` estimates are frozen and reported as skipped, so a
      completed job keeps the numbers it was bid with. Overrides:
      `recalc-all?include_frozen=true`, or an estimate's own Recalculate button
- [ ] Effective-dated rate history — `price_as_of` is captured per row but a price
      edit still overwrites the old value rather than versioning it
- [~] System settings **API** done (`GET/PATCH /api/system-settings`; a PATCH rewrites
      affected **open** estimates automatically — see the freeze above). UI page
      still to build.

### Auth & multi-user

- [x] Estimators table + API (no passwords yet)
- [ ] Login / session
- [ ] Admin can edit rates & assemblies; Estimator cannot break formulas
- [ ] Audit who changed what
- [ ] Seed remaining estimator people (names TBD)

---

## Platform

- [x] Backend scaffolded — FastAPI, 13 routers, 42 endpoints
- [x] Frontend scaffolded — static SPA, no build step (Flutter only if outgrown)
- [x] API for CRUD + calc endpoints
- [ ] Deploy path to **office Fedora** + Postgres — migrations `001`–`023` must be
      applied in order; `022` is destructive (drops `mono_slabs.drops_ff`)
- [ ] HTTPS / LAN access for estimators
- [ ] **CORS is `allow_origins=["*"]` with no auth** (`backend/app/main.py`) — any
      site visited while the server runs can drive the API. Tighten with auth.

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

1. **Lock the open calc decisions** — PT quantity rule, stirrup cover + end
   stirrup, waste factors, L-bar method. These change real numbers and everything
   downstream inherits them.
2. **Enter `pt_spacing_in`** on the LBJ PT pours so cable LF stops reading 0.
3. ~~Backend calc tests before more features~~ — harness and the high-value cases
   are in (`cd backend && pytest`). Extend to forming/equipment line formulas
   when those rules next change.
4. **Fix the 10 placeholder drop sections** (12×12 guesses from `sql/022`).
5. **Auth**, then tighten CORS — currently anyone on the LAN can edit, and any
   website can drive the API.
6. `pg_dump` backups — the database lives on this laptop only.
7. Supplier bid comparison (tables exist, no UI/API yet).
