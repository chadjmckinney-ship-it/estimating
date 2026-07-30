# Todo / Feature Backlog

Working list for the estimating system.  
Design: [mono.md](./mono.md) · DB notes: [notes.md](./notes.md)

**Last updated:** 2026-07-30

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

---

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
      exist**, and nothing records which migrations have been applied to a database
- [ ] Automated `pg_dump` backups under `Estimate_Projects/backups/` — the repo
      backs up code only; the database exists on this laptop alone

---

## Testing

- [x] Frontend: `npm run verify` — `node --check`, oxlint, Playwright smoke tests
      (read-only against the live DB; fail on any console error)
- [ ] **Backend calc tests** — the locked helpers and the takeoff services have no
      tests at all. Three staleness bugs shipped in one session (estimate waste,
      `system_settings`, beam edits) that an "edit X, assert Y follows" test would
      have caught. Highest-value gap in the project.
- [ ] Fixture/seed database so tests do not run against live bids
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
3. **Backend calc tests** before more features — see Testing.
4. **Fix the 10 placeholder drop sections** (12×12 guesses from `sql/022`).
5. **Auth**, then tighten CORS — currently anyone on the LAN can edit, and any
   website can drive the API.
6. `pg_dump` backups — the database lives on this laptop only.
7. Supplier bid comparison (tables exist, no UI/API yet).
