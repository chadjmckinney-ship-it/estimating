# The estimate price sheet — specification

**Status:** 2026-09-02. **Complete — stages 0, 1, 2 and 4 all shipped and
verified live.** LBJ recalculated through a 209-row sheet at $2,759,140.62,
every section to the cent. Stage 3 was folded into stage 2 (one reader,
`_rate_numeric`). Every price the app uses now comes from the job's own sheet.

**Decision taken:** an estimate holds **its own prices, and you can edit them
for that job**. Not a read-only snapshot, not an as-of date on the catalog.
Freezing comes free — an estimate that reads its own sheet cannot drift when
the catalog moves, because it is no longer reading the catalog.

---

## Why

Two equipment day rates were edited in the catalog at 09:35 on 2026-08-31. The
LBJ mono slab moved **−$4,984.91**, the whole 248-test suite passed, and it took
a morning to establish that nothing was broken. `docs/specs/price-restore-checklist.md`
records it, and its open item was this feature:

> **No audit on catalog edits.** A price change silently reprices every draft
> estimate and leaves no record of who, when, or from what.

That is the safety argument. The working argument is bigger: **a job's prices are
not the company's prices.** The plant gives a break on a big continuous pour. A
site with no laydown carries a haul premium. Chad's only options were to change
the catalog (moving every other open bid) or to absorb it. Neither is what he
actually wants, which is to say *"on this job, concrete is $168."*

The freeze is the side effect. The price sheet is the feature.

Chad's own framing, 2026-09-02:

> *"I like having a master list of rough mix prices that we get from suppliers
> that we update as we get them, then as we start an estimate, it pulls those
> numbers and we can update when a supplier gives us a quote."*

---

## The shape

```
master list  ──pull──▶  estimate price sheet  ──▶  every section on the estimate
(the catalog)                  │
    ▲                     edit per job
    └── drift is DETECTED, never applied
```

One estimate, one sheet. Every price the job uses appears on it by name, with
what the master list said when it was pulled and what this job actually uses.

### A consequence worth stating on its own

**The sheet stores resolved prices, not pointers.** Every name search and every
default-material pointer is resolved *at pull time* and recorded by name.

That kills the Yellow Guard class of bug (sql/030 — *"a price found by name
search is a price nobody can see"*) for any priced estimate, structurally. The
sheet **is** the list of what every lookup landed on. `_find_material(db, "6p")`
resolving to "16p NAILS DUPLEX" would have been visible on this screen the day
it was written, instead of surviving five assemblies until 2026-09-02.

---

## Schema

```sql
CREATE TABLE estimate_prices (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  estimate_id    uuid NOT NULL REFERENCES estimates(id) ON DELETE CASCADE,

  -- what kind of price this is, which decides how it is looked up
  kind           text NOT NULL CHECK (kind IN
                   ('mix','material','equipment','setting','assembly_rate','drill_rate')),
  scope          text,          -- assembly kind for assembly_rate rows; NULL = global
  ref_id         integer,       -- mix_designs / materials / equipment id, for joins
  ref_key        text,          -- settings key, rate key, drill diameter

  -- captured at pull, so the screen reads without joining anything
  label          text NOT NULL, -- "5000-ASH", "Superintendent", "REBAR GRADE BEAM"
  unit           text,          -- CY, LB, DAY, TON, SF, LF, RATIO
  category       text,          -- grouping on the screen (added in 048)

  catalog_value  numeric(14,4), -- what the master list said WHEN PULLED
  value          numeric(14,4) NOT NULL,  -- what this job uses
  is_edited      boolean NOT NULL DEFAULT false,
  note           text,          -- "SRM quoted 9/1, 400 CY continuous"

  pulled_at      timestamptz NOT NULL DEFAULT now(),
  created_at     timestamptz NOT NULL DEFAULT now(),
  updated_at     timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX estimate_prices_uidx ON estimate_prices
  (estimate_id, kind, coalesce(scope,''), coalesce(ref_key, ref_id::text));
```

`catalog_value` is not decoration. It is what makes **"3 master prices have
changed since you pulled this"** computable, which is the $4,984.91 incident
turned into a list instead of a morning.

`is_edited` is stored rather than derived from `value <> catalog_value`, because
deliberately setting a price back to the master number is still a decision and
a re-pull must not quietly discard it.

`value` is `NOT NULL` and a pull **never writes a zero from an unpriced master**
— see decision 5. (A zero *rate* is different — see stage 2.)

### What is on the sheet, by kind

| kind | source | keyed by | since | LBJ rows |
|---|---|---|---|---:|
| `mix` | `mix_designs.unit_cost` | `ref_id` | 048 | 16 |
| `material` | `materials.unit_cost` | `ref_id` | 048 | 78 |
| `equipment` | `equipment.unit_cost` ($0 = unpriced) | `ref_id` | 049 | 16 |
| `setting` | `system_settings`, MONETARY_KEYS only | `ref_key` | 049 | 17 |
| `assembly_rate` | `assembly_rates`, MONETARY_KEYS only | `scope` = kind, `ref_key` | 049 | 74 |
| `drill_rate` | `pier_drill_rates.drill_per_lf` | `ref_key` = diameter | 050 | 8 |
| | | | | **209** |

---

## Resolution order

```
1.  section quote            a sub's price for this package, on this section
2.  ESTIMATE PRICE SHEET     this job's price          ← new
3.  assembly_rates(kind)     this assembly's rate
4.  system_settings          the company default
5.  code default
```

The sheet slots in above the master list and below a quote. A quote is more
specific — a fabricator's number for *that section's* steel beats the job's
$/lb — and it already carries staleness and the catalog comparison.

`quotes.compare_to_catalog` compares against the **sheet** price once a sheet
exists, not the raw master (`catalog_cost_for_quote` runs inside `priced_as`).
"What would we have charged" means "at this job's prices." Same for piers'
`drill_rate_cost` since 050.

### Once a sheet exists, it is the only source

Stage 1 tightened the spec's original "fall back to the master list when the
sheet has no row". With a sheet present, an item **absent from the sheet is
unpriced** — flagged on the section, listed as `new` by the drift check, and
added by the next pull. Falling back to today's catalog for a job pulled last
spring would be exactly the silent drift the sheet exists to stop. An estimate
with **no** sheet rows (none should exist after the backfills) behaves as the
app did before: straight from the catalog.

For a **rate** the sheet keeps both levels `_rate_numeric` reads — the
assembly's own row (`scope`) and the company row — and resolves them in that
order. A monetary key absent from the sheet lands on the **code default**,
which is exactly where the tables land when neither has the key; the drift
check lists it as `new` until the next pull.

---

## What is a price, and what is a rule

This is the part that will break things if it is got wrong, because
`assembly_rates` and `system_settings` hold both, in the same tables, with
names that do not distinguish them.

### The traps — these look monetary and are NOT

| Row | Value | What it actually is |
|---|---:|---|
| `nails_16p_per_sf` | 1800 | SF **per box** — a divisor |
| `nails_8p_per_sf` | 3000 | SF per box |
| `lumber_2x4_per_sf` | 1.0 | LF of 2x4 per SF |
| `lumber_ply_per_sf` | 0.0625 | sheets per SF |
| `support_rebar_lb_per_sf` | 0.1 | lb allowance |
| `labor_tie_steel_free_lb_per_sf` | 0 | lb carried free |
| `chairs_sf_per_bag` | 12000 | SF per bag |
| `form_release_sf_per_gal` | 300 | SF per gallon |

**A sweep of `key LIKE '%_sf'` would freeze all eight and break every quantity
in the app.** So the split is enumerated by hand, in both directions —
`price_book.MONETARY_KEYS` (57 keys, with label and unit) and
`price_book.RULE_KEYS` — and mirrored once in `sql/049`.
`test_price_sheet_rates.py` fails the day a key appears in either table that
is on neither list, and the day the SQL copy differs from the Python one.
Adding a key means deciding what it is.

### Not pulled (rules)

Waste factors, `form_percent`, `form_waste`, `form_rental_percent`, spacings
and covers, the swell factors, `labor_super_sf_per_week` /
`labor_super_days_per_week` / `columns_per_super_week`, every `*_per_sf` /
`*_per_ff` divisor, `equip_use_rental_tiers`, `vapor_barrier_enabled`, the two
vapor pointers, `vapor_tape_rolls_per_barrier_roll`, and the `quote_warn_*` band.

A rule change SHOULD reach an old estimate when you recalculate it — that is a
correction to how the work is computed, not a change to what things cost.
Pinned by `test_a_rule_change_still_reaches_a_priced_estimate` (waste, and
`form_percent`).

### The three judgment calls

**`sales_tax_pct` — PULLED** (049). A statutory rate, not a purchase price, but
it was $36,556.64 on the LBJ slab and it is part of what was bid. The tri-state
exemption (section → project → setting) is a *rule* and stays live —
`test_the_tax_rate_is_pulled_but_the_exemption_stays_live`.

**`equip_fuel_maint_pct` — PULLED** (049). Freeze the day rates and not this,
and a frozen estimate still drifts. **Open:** it is 50% on the live settings
and nobody has ever questioned that figure.

**`default_vapor_barrier_material_id` / `default_vapor_tape_material_id` —
RESOLVE AND PULL THE RESULT.** The resolved material is priced off the sheet
(`resolve_vapor_*` run inside `priced_as`); the *pointer* itself is a rule and
is read live, deliberately — freezing it would mean an old estimate keeps
pointing at a discontinued roll after the default changes. Recording the
resolved name as its own sheet row was considered and dropped for the same
reason. Audit #8 made the fallback safe and made it announce itself instead.

### A zero rate is a statement

`concrete_pump_cy = 0` on paving and `labor_curb_lf = 0` on sidewalk are
deliberate: that assembly does not pump, has no curb labor. Both tables carry
such zeros; the pull copies them and the sheet accepts one typed. A **mix,
material, machine or drill rate** at $0 is still refused (decision 5) —
`set_price` decides by `kind`, and the API returns 400 for the latter.

---

## Threading it through the code — as built

The spec proposed passing a `PriceBook` down every call chain. **Built
differently, on purpose:** `price_book.py` holds the book in a **contextvar**
(`priced_as(db, estimate_id)`), set once at each entry point that prices a
section:

`refresh_pour_costs`, `cost_units`, `catalog_cost_for_quote`,
`calc_forming_materials`, `calc_labor_materials`, `calc_estimate_equipment`,
`section_material_costs`, `tax_rate_for`, `resolve_vapor_*`,
`refresh_pier_group_calcs`, `apply_drill_quote`, `rate_table_drill_cost`,
`drill_quote_basis`.

Inside, every `_find_material` / `_find_equip` / `_mix_unit_cost` /
`piers.drill_rate` reads `require_book()`, and `calc._rate_numeric` does too —
**for monetary keys only**; a rule key passes straight through to the tables.
Reasons, from the module docstring: ~100 call sites would each have needed a
threaded parameter, several through functions that have already dropped
`section`; the contextvar is re-entrant (an inner `priced_as` for the same
estimate reuses the outer book) and is exactly one thing to get right per
entry point instead of one per lookup.

### The coverage guard

`require_book(what)` outside any `priced_as`:

- `ESTIMATING_STRICT_PRICES=1` (set by `tests/conftest.py`): **raises
  `NoPriceBook`**. A costing path nobody threaded is a red test.
- production: logs a warning and prices from the catalog, as the app did
  before 048.

`catalog_only()` is the explicit way to say "the master list is what I mean"
(catalog screens, name-resolution tests).

The guard caught real sites in every stage: `cost_units` via the quotes
router, `resolve_vapor_*`, `tax_rate_for` called bare from tests (now
self-gating), and several test helpers.

---

## Pull, edit, and drift — as built

**On create:** `POST /estimates` pulls the master list before it commits. There
is never an unpriced estimate.

**Editing:** `PATCH /estimates/{id}/prices/{price_id}` with `value` and/or
`note`, or `reset: true`. Negative → 422; zero → 400 unless the row is a rate.
A write recalcs the whole estimate (`recalc_estimate`) and commits; the roll-up
rides along. Reset puts the master price back, clears `is_edited` **and the
note**. Typing the master number by hand still marks the row edited.

**Pull** (`POST /estimates/{id}/prices/pull`, `?dry_run=true` for the preview):

| result | meaning | applied? |
|---|---|---|
| `new` | on the master list, not on the sheet | added at master price |
| `changed` | on the sheet, unedited, master moved | follows the master |
| `conflicts` | on the sheet, **edited**, master moved | **yours kept**; `catalog_value` refreshed so the screen shows was / now / yours |
| `unpriced` | master has no price | reported, never copied as $0 |
| `retired` | on the sheet, gone from the master | kept, reported |

`drift` = changed + conflicts; the estimate page counts `drift + new` as
"moved". Entries carry `kind`, `scope`, `ref_id`, `ref_key`, `label`, `unit`.

**Screen** (`#prices/{estimate_id}`): grouped — concrete, the material
categories A–Z, equipment, drilling, labour & company rates, then each
assembly's own rates ("Paving — where it differs from the company rate").
Columns Item (with the key in mono for rates) · Unit · Master list (at pull) ·
This job (inline edit, Enter/blur saves, Esc reverts) · Note · Reset. Ratios
display as percentages. Badges: `edited`, `master $x` on rows the master has
moved under, `retired`. "Pull master list…" opens the dry-run diff with an
Apply button. The estimate page carries a **Prices** stat card and a drift
banner; the section's unpriced banner links to the sheet.

---

## What happened to the LBJ job, and every existing estimate

Each backfill inserts a sheet row for every estimate × master item, at the
master's own number, `pulled_at = now()`. NULL (and $0 equipment / drilling)
skipped. Proven in `test_a_sheeted_section_costs_exactly_what_a_catalog_section_did`
(same fixture with and without a sheet, both at `GOLDEN_COST["total_cost"]`),
and **live on 2026-09-02**, three times — after 048 (94 rows), after 049 (201
rows) and after 050 (209 rows). Every one returned Piers 293,575.71 / Mono slab
674,561.18 / 10-Paving 1,407,636.06 / 06-Walls 210,040.25 / 07-Columns
173,327.42 — **$2,759,140.62 in, $2,759,140.62 out**, with drift 0 and no
unpriced master items.

(07-Columns moves −$19.49 on its next recalc, from audit #7 — SLAB CHAIRS at
$27 where it had been buying METAL CHAIRS at $45. That is a correction, not
sheet drift.)

`estimates.status` freezing (`final`, `archived`) stays as it is.

---

## Fixtures and tests — as built

Every fixture's `build()` prices the catalog, **pulls a sheet**, then builds —
so all five golden files run through the book at their original numbers.

Tests that had NULLed the catalog to mean "unpriced" broke once sheets shielded
jobs from the catalog (which is the feature working) and now delete the sheet
row instead (`test_stage0_groundwork._unprice`, `test_quote_comparison`).
Name-resolution tests use `catalog_only()`; helpers that cost a section use
`priced_as`.

- `tests/test_price_sheet.py` (16) — stage 1: pull reproduces the master list
  exactly; sheeted vs unsheeted identical at the golden total; never writes a
  zero; edited price reaches this job only; master change does not move a
  priced estimate, is reported as drift; re-pull follows unedited rows, never
  overwrites edited; reset; item added after the pull is unpriced until the
  next pull; rule change still reaches; guard strict/quiet; create pulls;
  edit/pull/dry-run/reset over HTTP; quote comparison reads the sheet.
- `tests/test_price_sheet_rates.py` (14) — stage 2: every key in both tables
  is classified; SQL list == Python registry; the eight divisors are rules;
  edited super day rate reaches this job only; assembly override beats the
  company row and edits independently; master rate change reported not
  applied; zero rate allowed, zero machine refused; tax pulled, exemption
  live; machine prices off the sheet, catalog ×3 does not reach it; $0
  machine unpriced; `form_percent` still reaches; guard covers rates and
  ignores rules; API carries the new kinds.
- `tests/test_price_sheet_drilling.py` (9) — stage 4: pull carries every
  priced diameter; golden drilling total; a driller's break reaches one job
  only; table change reported not applied; the quote comparison is at the
  job's rates; a diameter off the sheet is unpriced, never interpolated; $0
  table rate unpriced; guard covers drilling.

Suite: **502 green**.

Notes for future fixtures: the test catalog ships every mix unpriced; a
fixture prices only its own mix, so a test needing a second priced mix says so
(`_price_mix`). Equipment names `SkyTrack` and `SKY LIFT` both match `%SKY%`.
Typing supervision moves the equipment ladder on the NEXT refresh (audit #5),
so a piers/walls fixture settles once with `recalc_section` before any
before/after comparison.

---

## Build order — all shipped

| Stage | Covers | Share of a slab section | Status |
|---|---|---:|---|
| 0 | groundwork — drop `mix_prices`, no more $0 concrete, delete the sidewalk row, promote the 4 literals | — | **shipped, verified live** |
| 1 | mixes + materials, sheet + screen + pull/diff, **and the coverage guard** | ~59% | **shipped, verified live** |
| 2 | equipment + every monetary setting **and assembly rate** (stage 3 folded in — one reader, `_rate_numeric`) | ~+41% | **shipped, verified live** |
| 4 | `pier_drill_rates` by diameter | piers only, ~20% of piers | **shipped, verified live** |

---

## Decisions — taken 2026-09-02

Chad answered all five. Recorded verbatim where his words carry the reasoning.

### 1. `mix_prices` — DROPPED (stage 0). The master list is `mix_designs.unit_cost`.

> *"I like having a master list of rough mix prices that we get from suppliers
> that we update as we get them, then as we start an estimate, it pulls those
> numbers and we can update when a supplier gives us a quote."*

One master price per mix, kept current as supplier numbers come in; the
estimate pulls it and overrides when a job-specific quote lands. Not a
per-supplier dated history. `supplier_bids` dropped with it; `concrete_suppliers`
kept as reference data. The master list is edited at `/api/mix-designs`.

### 2. Per estimate. A rebid is a new estimate.

> *"per estimate. if we rebid again, its a new estimate."*

A new estimate pulls the master list as it stands that day. `estimates.version`
stays a label.

### 3. No copying a sheet between jobs.

Every estimate starts from the master list. A price carried forward from
another job is a price nobody re-checked.

### 4. `sidewalk.accessories_unit_cost = 0.02` — DELETED (stage 0).

> *"think that was again someone edited a formula in the workbook and wasnt
> caught till we used the excel workbook to build this"*

### 5. Concrete must never start at $0.

> *"I dont like concrete prices starting @ $0.. pulling prices from the master
> table that gets updated monthly is a safer option."*

A mix, material, equipment or drill row with no master price is UNPRICED, not
free — flagged on the line and the section (stage 0). The pull refuses to copy
a NULL (stage 1), a $0 machine (stage 2) or a $0 drill rate (stage 4). The seed
stays priceless; a fresh install prices its master list before its first
estimate, and the app now says so instead of bidding concrete at $0.

### 6. CONCRETE HAUL OFF — $250 per load, every assembly.

Chad, 2026-09-02: *"set haul off as $250 per load."* The piers and walls
sheets computed loads at $250 and the paving sheet typed $500 on its manual
line; sql/047 promoted a single catalog row at $250 and this settles it there.
Nothing changed to apply it — the row, and LBJ's sheet, were already $250.

Distinct from the per-CY **Haul off** contract service (piers $4/CY, columns
$6/CY), which is spoil rather than concrete. Both are now on the price sheet
under similar names; piers carries both at once.

---

## Stage 0 — shipped (sql/047)

| # | Change |
|---|---|
| a | `DROP TABLE mix_prices; DROP TABLE supplier_bids;` (+ `supplier_bid_variance`) |
| b | sidewalk `accessories_unit_cost` row deleted |
| c | CONCRETE HAUL OFF $250/LOAD, TEXTURE COMB $200/EA, DOWEL BASKETS $5.25/LF, PIPE BRACING $15/EA promoted to catalog rows; `forming.py` literals removed |
| d | NULL price = unpriced: `costing._z`, `section_unpriced()` → `estimate_sections.calc_unpriced`; `material_costs` `unpriced`; banners on section and estimate pages |
| e | `_equip_price()` (rate, source) → `estimate_equipment_lines.price_source`; the 12 ternaries route through it |
| f | `tests/test_stage0_groundwork.py` (28) |

## Stage 1 — shipped (sql/048)

`sql/048_estimate_prices.sql`, `models/estimate_price.py`,
`services/price_book.py`, `schemas/estimate_price.py`,
`routers/estimate_prices.py`, gates in `costing.py` / `forming.py` /
`material_costs.py`, pull in `routers/estimates.create_estimate`, the Prices
screen in `app.js` (+ `api.js`, `app.css`), fixtures + `test_price_sheet.py`.

## Stage 2 — shipped (sql/049)

`sql/049_price_sheet_rates.sql` (temp `monetary_keys` table generated from the
registry, three backfills), `price_book.py` (MONETARY_KEYS / RULE_KEYS,
`equipment` + `rates` on the book, `_master_list` for five kinds, general
`_key`), `calc._rate_numeric` (book-aware for monetary keys),
`costing._money_setting` + self-gating `tax_rate_for`, gates in `labor.py` /
`estimate_equipment.py`, `_find_equip` priced off the sheet, schema `value ≥ 0`,
sheet groups in `app.js`, `test_price_sheet_rates.py`.

Known non-issue: rate-driven equipment lines (storage, misc) store
`price_source` NULL — they were never `_priced()` lines; their rates are on the
sheet as `assembly_rate` rows and reach them through `_rate_numeric`.
`rock_cy` is on the sheet but read by no service (audit P3, dead row).

## Stage 4 — shipped (sql/050)

`sql/050_price_sheet_drilling.sql` (one row per diameter, `ref_key` = the
diameter normalised — "24" for 24.00), `price_book.drill_key` / `drill` map /
`drill_rate()`, `piers.drill_rate` reads the book, gates on
`refresh_pier_group_calcs`, `apply_drill_quote`, `rate_table_drill_cost` and
`drill_quote_basis`, the drilling group on the sheet screen,
`test_price_sheet_drilling.py`.

`casing_per_lf` and `deduct_per_lf` stay in `pier_drill_rates` as reference
data — no service reads them.
