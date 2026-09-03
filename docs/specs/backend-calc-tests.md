# Implementation Spec — Backend Calc Tests

**Status:** proposed, not implemented. No source touched.
**Author:** Autumn, 2026-08-04
**Backlog item:** `docs/todo.md` → Testing → "Backend calc tests" (flagged as the highest-value gap)
**Related:** `docs/mono.md` · vault [[Estimating App]] · vault [[Estimate Job Playbook]]

---

## 1. Why this exists

Three staleness bugs shipped in a single session on 2026-07-30:

1. Estimate waste edits left pours and takeoffs silently stale.
2. `system_settings` changes did not rewrite stored results.
3. Beam edits did not refresh forming / labor / equipment.

All three shared one shape: **a stored number stayed behind after its input moved.**
None of them raised an error. Each produced a page of plausible figures that were
wrong, which is the failure mode that actually loses money on a bid.

The app's whole reason for existing is that Excel formulas are fragile and silent.
Replacing them with locked SQL functions only helps if something proves the locks
hold. That proof is this test suite.

**The one rule the suite exists to enforce:** no quantity in this system is allowed
to be wrong quietly. Either it is right, or the suite fails loudly.

### Estimating principles this suite encodes

These come from banked field lessons, not from software convention. Each becomes an
executable assertion later in the spec.

| Principle | Source | Test consequence |
|---|---|---|
| **No number beats a bad number.** A missing input yields zero or NULL, never a silently interpolated guess. | Trinity River (six undimensioned pads left unpriced); Colleyville (civil hatch dead end) | §5.3 — missing-input tests assert `0`, and assert it is *visible*, not absorbed |
| **Cushion is deliberate — measure honestly, then decide what rides on top.** | Playbook 7h | §5.2 — waste applied exactly once, at exactly one place; raw and carried both recoverable |
| **Every automated quantity gets divided by a known length or unit count before it is carried.** An area alone has no error signal. | Playbook 7g (47% paving miss) | §5.4 — dimensional cross-check tests that re-derive thickness / height / spacing from the output |
| **A constant term outside its gate is phantom quantity.** | Playbook 7i (Footings Term5 `+4 ft` false-fire) | §5.5 — every additive constant must vanish when its gate is off |
| **Never leave pours on a stale beam size after resizing the type library.** | Playbook §2, banked Excel lesson | §6.3 — edit a type, assert every pour using it moves |
| **Trace every bid quantity to a source.** | Playbook §2 | §7 — golden estimate reconciles to the Excel workbook line by line |

---

## 2. Scope

**In scope**

- The nine locked SQL functions (`sql/001`, `014`/`015`, `021`, `023`).
- `app/services/calc.py` — pour and beam refresh, rollups, breakdowns.
- `app/services/recalc.py` — propagation scope and ordering.
- `app/services/forming.py`, `labor.py`, `estimate_equipment.py` — takeoff drivers and lines.
- The API-level propagation paths: `PATCH /api/estimates/{id}`, `PATCH /api/system-settings/{key}`, `POST /api/estimates/{id}/recalc`, `POST /api/system-settings/recalc-all`, and the beam-type editing endpoints.

**Out of scope**

- Frontend (already covered by `npm run verify`).
- CRUD-shape tests for routers that do no arithmetic (estimators, projects, mix designs, materials, equipment catalogs).
- Auth (does not exist yet).

**Non-goal:** coverage percentage. The target is *every path where a number can go
stale or be silently defaulted*, not every line.

---

## 3. Test database

**Hard rule: tests never touch `estimating`.** The live DB holds the LBJ and Crunch
bids and lives on one laptop with no backups. This mirrors the standing rule that
Playwright smoke tests stay read-only against live bids — the Python suite gets its
own database instead, so it is free to write.

### 3.1 Provisioning

Database name `estimating_test`, created and torn down by the fixture, built by
applying the numbered migrations **in order** against an empty database.

```
sql/001_schema.sql
sql/002_materials.sql
...
sql/015_forming_materials.sql      <-- explicit ordering, see below
sql/015_poly_sides_only.sql
sql/016_estimate_forming_lines.sql
...
sql/025_estimate_beam_types.sql
```

Two files share the `015_` prefix. The suite carries an **explicit ordered list** in
`tests/backend/migrations.py` rather than globbing, because `015_poly_sides_only.sql`
redefines `calc_poly_beam_sf` from `014` and must land after `015_forming_materials.sql`
for the DB to match production. Sorting by filename happens to give the right order
today; relying on that is how it breaks the day someone adds `015a_`.

### 3.2 What this buys beyond testing

Applying 001–025 from scratch on every test run is also the **deploy rehearsal** for
the office Fedora box — an open backlog item. If the migration chain will not build a
working database, the suite goes red before anyone drives to the office to find out.
Migration `022` is destructive (drops `mono_slabs.drops_ff`); a from-scratch build
proves the chain is still coherent with it in place.

It does **not** solve the missing applied-migrations ledger. It reduces the cost of
that gap: the canonical definition of "a correct database" becomes the ordered list
the tests use.

### 3.3 Fixtures

| Fixture | Scope | Behavior |
|---|---|---|
| `test_engine` | session | Create `estimating_test`, apply the ordered migration list, yield engine, drop DB at teardown |
| `db` | function | Open a connection, begin an outer transaction, bind a `Session` to it, yield, **roll back** — no test sees another's writes |
| `client` | function | `TestClient` with `get_db` dependency-overridden to the `db` session |
| `settings_reset` | function | Restore `system_settings` to seeded values (guards suites that PATCH defaults) |

The service layer calls `db.commit()` internally (`recalc_estimate`, `refresh_and_store_*`).
The fixture must therefore use SQLAlchemy's **join-an-external-transaction** pattern
with a `SAVEPOINT` restart hook, so a service-level commit lands inside the outer
transaction and still rolls back at teardown. Without this, tests will leak state into
each other and the suite will fail intermittently — which is worse than no suite.

### 3.4 Tooling

New file `backend/requirements-dev.txt`:

```
pytest>=8.0
pytest-cov>=5.0
httpx>=0.27          # FastAPI TestClient dependency
```

The venv at `.venv/` currently has no pytest. Run as
`.venv/bin/python -m pytest tests/backend`.

Add to `package.json` scripts for one-command verification:

```json
"test:backend": "cd backend && ../.venv/bin/python -m pytest ../tests/backend -q",
"verify": "npm run check && npm run lint && npm run test:backend && npm run test:e2e"
```

### 3.5 Layout

```
tests/
  e2e/smoke.spec.js              (existing, unchanged)
  backend/
    conftest.py                  fixtures above
    migrations.py                ordered migration list + applier
    factories.py                 make_estimate / make_pour / make_beam_type / make_usage
    goldens.py                   verified expected values, one place (§4)
    test_sql_functions.py        §5
    test_pour_calcs.py           §6.1–6.2
    test_beam_calcs.py           §6.3
    test_propagation.py          §6.4  <-- the three shipped bugs
    test_forming.py              §6.5
    test_labor.py                §6.6
    test_equipment.py            §6.7
    test_settings_scope.py       §6.8  <-- drift guard
    test_golden_estimate.py      §7
```

---

## 4. Golden values

All expected numbers live in `tests/backend/goldens.py`, each with a comment giving
its derivation. **Every value below was verified against the live functions on
2026-08-04**, not hand-computed and trusted.

Reference pour: **10,000 SF, 4" slab, 4" sand, PT, `waste_concrete` = `waste_sand` = 0.05,
`waste_rebar` = 0, mat #4 @ 18" o.c.e.w., support 0.1 lb/SF, `pt_lb_per_sf` 1.0, PT @ 48" o.c.**

| Quantity | Formula | Expected |
|---|---|---|
| `calc_concrete_cy(10000, 4, 0.05)` | SF × thk / 12 / 27 × 1.05 | **129.6296** |
| `calc_sand_cy(10000, 4, 0.05)` | same with sand thickness | **129.6296** |
| `calc_slab_mat_rebar_lf(10000, 18)` | 2 × SF × 12 / spacing | **13333.333** |
| `calc_slab_mat_rebar_lb(10000, 4, 18, 0)` | LF × 0.668 lb/ft × 1.00 | **8906.666** |
| `calc_support_rebar_lb(10000, 0.1)` | SF × rate | **1000.000** |
| `calc_pt_cable_lb(10000, true, 1.0)` | SF × rate when PT | **10000.000** |
| PT slab LF | SF × 12 / 48 | **2500.000** |

Reference beam: **12" × 24" × 100 LF, 3-#5 top, #3 stirrups @ 12", `waste_concrete` 0.05.**

| Quantity | Formula | Expected |
|---|---|---|
| `calc_long_bar_lb(3, 5, 100)` | 3 × 100 × 1.043 | **312.900** |
| `calc_stirrup_lb(12, 24, 100, 3, 12)` | (100×12/12) × (2×(12+24)/12 + 1.0) × 0.376 | **263.200** |
| `calc_poly_beam_sf(12, 24, 100)` | (2 × 24 / 12) × 100 | **400.000** |
| beam CY | (12×24×100)/(144×27) × 1.05 | **7.7778** |

Derived (10,000 SF pour with that one beam):

| Rollup | Expected |
|---|---|
| pour concrete CY | 129.6296 + 7.7778 = **137.4074** |
| pour total rebar lb | 8906.666 + 1000.000 + 576.100 = **10482.766** |
| pour poly SF | (10000 + 400) × 1.10 = **11440.000** |
| super days | 10000 / 16000 × 7 = **4.375** |
| equip days | ladder(4.375) = **7** |
| billable units (7 days, tiers) | d < 8 → **3.0** |

Bar weights are seeded reference data (#3 = 0.376 … #11 = 5.313); a test asserts all
nine rows exist and match, because every steel number in the app multiplies through them.

---

## 5. Layer 1 — locked SQL functions (`test_sql_functions.py`)

Pure arithmetic against the database, no ORM. Table-driven with `pytest.mark.parametrize`.

### 5.1 Happy path

Each of the nine functions gets its golden value from §4, plus two or three
additional points across its range.

### 5.2 Waste is applied exactly once

For each waste-bearing function, assert the ratio between the wasted and unwasted
result equals `1 + waste` to full precision:

```
calc_concrete_cy(sf, thk, 0.05) / calc_concrete_cy(sf, thk, 0) == 1.05
```

Then at the rollup level (§6.2), assert the same ratio holds for the *pour total*.
This is the test that catches waste compounding — a factor applied in the beam
function and again in the rollup reads as a plausible 10.25% instead of 5%.

Related, and stronger: **recalc must be idempotent.** Running
`POST /api/estimates/{id}/recalc` twice must produce byte-identical `calc_*` values.
Any accumulating factor dies here.

This is the software form of playbook 7h: the cushion Chad places is deliberate and
must be exactly the cushion he set. A waste factor that quietly compounds is not
negotiating room, it is a wrong bid.

### 5.3 Missing input yields zero, never a guess

| Input | Expected |
|---|---|
| `spacing_in` NULL or ≤ 0 → `calc_slab_mat_rebar_lf` | 0 |
| `bar_size` NULL → `calc_slab_mat_rebar_lb` | 0 |
| `stirrup_size` NULL, spacing set → `calc_stirrup_lb` | 0 |
| `spacing_in` NULL, size set → `calc_stirrup_lb` | 0 |
| `bar_count` NULL → `calc_long_bar_lb` | 0 |
| `post_tension` false → `calc_pt_cable_lb` | 0 |
| `sand_thickness_in` NULL → `calc_sand_cy` | **NULL**, not 0 |
| `sf` ≤ 0 → mat functions | 0 |

The sand case is deliberately different and must stay that way: NULL means "no sand
on this pour", 0 would mean "sand priced at zero". Assert the distinction explicitly.

Negative and zero inputs get their own cases. `sql/020` bounds waste 0–1 at the DB
level after a `-1` PATCH once 500'd the whole estimates list; a test asserts the
constraint rejects `-0.01` and `1.01` on all three waste columns and on `form_percent`.

### 5.4 Dimensional cross-checks

Playbook 7g, in code. Rather than only comparing against a hardcoded expected value,
**re-derive the input from the output** and assert it comes back:

| Check | Assertion |
|---|---|
| Thickness recovery | `calc_concrete_cy(sf, t, w) / sf × 324 / (1+w) == t` for t in 4, 5, 6, 8 |
| Beam height recovery | `calc_poly_beam_sf(w, h, L) / L / 2 × 12 == h` |
| Mat spacing recovery | `calc_slab_mat_rebar_lf(sf, s) / sf / 2 × 12 == s` |
| Stirrup count recovery | `calc_stirrup_lb(...) / lb_per_ft / bar_ft × spacing / 12 == L` |

A hardcoded expected value confirms one point. A recovery identity confirms the whole
formula shape, and fails when someone swaps a `/ 12` for a `× 12` in a way that happens
to still look reasonable at the test's one data point.

### 5.5 Gated constants must vanish

The Footings `Term5` bug (playbook 7i) was a `+4 ft` constant that evaluated whenever
Top Mat spacing was non-zero, regardless of whether any pilaster existed. The app has
the same shape in `calc_stirrup_lb`: a `+1.0 ft` hook allowance inside the same
expression as the perimeter.

Assertions:

- `calc_stirrup_lb` with `stirrup_size` NULL returns exactly 0 — the `+1.0` cannot leak.
- `calc_stirrup_lb` with `length_lf = 0` returns exactly 0.
- Setting `l_bars_spacing_in` on a beam type changes **nothing** in any output.

That last one is a **known-gap lock**. `l_bars_spacing_in` is captured but unused —
L-bars price as plain long bars today. The test asserts the current behavior so that
the day someone wires spacing in, the suite fails and forces the decision to be made
deliberately rather than discovered in a bid. Mark it `@pytest.mark.provisional`.

### 5.6 Provisional numbers, marked as such

Two locked values are known to be wrong and deliberately unfixed:

- **Stirrups run 16–39% heavy** — no concrete cover deduction, end stirrup omitted,
  count unrounded (`sql/023` header carries the numbers).
- **PT quantity** rides a flat 1.0 lb/SF pending confirmation against the Pricing sheet.

Tests lock **current** behavior under `@pytest.mark.provisional`, and
`goldens.py` carries a header block listing every provisional value with a pointer to
the open decision in `docs/todo.md`. When a decision lands, the failing test list *is*
the change checklist. Nothing about a red provisional test should read as a surprise.

---

## 6. Layer 2 — services and propagation

This is the layer that would have caught all three shipped bugs. Every test has the
same shape: **change one input, assert the derived value follows.**

### 6.1 Pour calcs (`test_pour_calcs.py`)

- Build the §4 reference pour, refresh, assert every `calc_*` column against goldens.
- Per-pour overrides beat system defaults: set `support_rebar_lb_per_sf` = 0.25 on the pour, assert the pour uses it and a sibling pour without an override still uses 0.1.
- Estimate-level waste beats system default; NULL falls through to `system_settings`.
- No mat priced (`slab_bar_size` NULL) → `calc_slab_bar_lf` and `_lb` both 0, and `calc_total_rebar_lb` still equals support + beams. The mat's absence must not be absorbed into another line.
- Non-PT pour → `calc_pt_cable_lb`, `calc_pt_slab_lf`, `calc_pt_gb_lf`, `calc_pt_cable_lf` all 0, even when the beam type carries `pt_cables_count`.
- **The LBJ case:** PT pour with `pt_spacing_in` NULL → `calc_pt_slab_lf` = 0 while `calc_pt_cable_lb` is non-zero. Assert both. This is live on 16 LBJ pours today; the test makes the shape permanent and documented rather than a surprise found mid-bid.

### 6.2 Rollups

- `calc_concrete_cy` = `calc_slab_concrete_cy` + `calc_gb_concrete_cy`, exactly.
- `calc_total_rebar_lb` = mat + support + all beam kinds.
- `calc_poly_sf` = (pour SF + Σ beam wrap) × (1 + `waste_poly`).
- Per-kind breakdown: `grade_beam` + `exposed` + `drop` sums equal the pour totals, for both `_beam_breakdown` and `beam_kind_breakdown()`.
- `estimate_mono_totals()` equals the sum over pours for all 16 aggregate columns.
- **Waste ratio at the rollup**, per §5.2.
- **Idempotency**: recalc twice, assert identical.

### 6.3 Beam types (`test_beam_calcs.py`)

Post-`sql/025` the schedule lives once per estimate and pours reference it. The banked
Excel lesson — *never leave pours on a stale size after resizing the library* — is
directly testable here and is one of the strongest tests in the suite.

- One type used by three pours: edit width 12 → 14, assert **all three** pours' `calc_concrete_cy`, `calc_rebar_lb` and `calc_poly_sf` move, and the estimate total moves by the sum.
- Kind is on the type, not the usage: flipping a type `grade_beam` → `drop` moves the LF and CY out of the GB bucket and into the drop bucket, moves `drops_ff` in the forming and labor drivers, and zeroes that type's PT cable LF.
- Two pours using the same type at different lengths scale linearly.
- `GradeBeam` proxy properties read through to the type for all sixteen proxied fields (a `getattr` typo here silently zeroes a bar row, because `_apply_beam_rebar_and_cy` skips falsy counts).
- Exposed and drop kinds carry no PT cable LF even when the pour is PT.

### 6.4 Propagation (`test_propagation.py`) — the three shipped bugs

One test class per bug, each named for what shipped.

**A. Estimate waste edit → pours and takeoffs refresh**
`PATCH /api/estimates/{id}` with `waste_concrete` 0.05 → 0.10; assert every pour's
`calc_concrete_cy` moved, the forming `accessories` line moved (it rides total rebar),
labor tie steel moved, and equipment pumping CY moved.
Assert the reverse too: a `notes`-only PATCH triggers no recalc and leaves
`refreshed_at` untouched.

**B. `system_settings` change → stored results rewritten**
`PATCH /api/system-settings/waste_concrete` → assert affected estimates rewritten and
`RecalcReport` names them. Then the psql path: `UPDATE system_settings` directly,
assert stored values are now stale (documenting the known limitation), then
`POST /api/system-settings/recalc-all` and assert they converge.

**C. Beam edit → forming / labor / equipment refresh**
Edit a beam type's dimensions and separately a usage's `length_lf`; assert the forming
summary, labor summary and equipment summary all move. Drop-kind length changes must
move `drops_ff` in both the forming and labor drivers, which since `sql/022` reads from
`grade_beam_details`, not from a pour column.

**D. Ordering and creation discipline**
- `recalc_estimate` runs pours → forming → labor → equipment. Equipment reads the superintendent days labor produces, so assert equipment days reflect the *new* labor days in a single pass — not the previous run's.
- A recalc on an estimate with **no stored takeoffs** must not conjure them. Assert `EstimateFormingSummary` etc. remain absent and the report shows `forming: false`.
- Lines marked `is_manual` survive recalc with their qty and rate intact; non-manual lines track the current default. Both directions asserted, since a manual line that silently reverts is a priced decision quietly undone.

### 6.5 Forming (`test_forming.py`)

- Every formula in the module docstring gets a case at the reference pour: 2x6, 2x4, 2x4 bracing, 2x10, siding, ply, stakes, nails ×3, anchors, chairs, tie wire, accessories, cure.
- `form_percent`: estimate override beats system default; scaling it 0.50 → 1.00 doubles exactly the five form-lumber lines (2x6, 2x4, 2x10, siding, ply) and leaves bracing, nails, anchors, chairs, tie wire, accessories and cure unchanged. The split between what form% scales and what it does not is an Excel rule that is easy to break and invisible when broken.
- `ceil` vs `round` boundaries: siding and nails use `ceil`, stakes use `round`. Assert at values straddling each boundary.
- Zero drops → ply 0 and bracing 0.
- Manual line preservation: mark keyway manual with a qty, refresh, assert qty survives and `ext_cost` picks up a changed unit cost.
- Material lookup is best-effort `ILIKE`; assert a missing catalog row yields `unit_cost` NULL and `ext_cost` NULL rather than a zero that reads as free.

### 6.6 Labor (`test_labor.py`)

- Four `/SF` lines at the reference pour against goldens.
- Tie steel = `calc_total_rebar_lb` / 2000 × rate, wired to the pour's *current* rebar.
- Supervision: weeks = SF / 16000, days = weeks × 7 = **4.375**; expense and PM ride the same days; foreman defaults to qty 0.
- Foreman's carry-forward quirk: a qty set without `is_manual` survives refresh (`labor.py:361`). Lock it, because it is the one place a non-manual qty is deliberately sticky.
- Disabled line → `ext_cost` exactly `0.00` while qty and rate remain visible.
- `cost_per_sf` = total / SF; NULL when SF is 0 (no division by zero on an empty estimate).
- A non-manual rate tracks `system_settings`: PATCH `labor_forming_sf`, assert the line's rate moves. A user-edited rate arriving with `mark_manual=True` does not.

### 6.7 Equipment (`test_equipment.py`)

The two ladders are step functions transcribed from Excel and are exactly where an
off-by-one hides. Parametrize the boundaries.

**Days ladder** (`equip_days_from_super`) at 0, 3, 3.01, 4.375, 5, 5.01, 10, 10.01, 15,
15.01, 20, 20.01, 27, 40, 40.01, 60, 80, 100, 120, 140. The docstring's worked example —
27 days → 60 — is a required case. Note for the record: the band structure leaves
`3 < d ≤ 5` at a flat 7 with no additive band; the test locks that as current behavior
rather than assuming it is a bug. Flag for Chad against the Excel sheet.

**Rental tiers** (`rental_billable_units`) at 0, 1, 3, 3.99, 4, 7, 7.99, 8, 20, 20.99,
21, 29, 29.99, 30, 60. Verified: 7 days → 3.0; 8 days → 3.4286; 21 days → 9.0; 30 days → 9.0.

- `equip_use_rental_tiers` false → units = days, no tiering.
- Pumping = `calc_concrete_cy` × $/CY, and moves when a waste factor moves. **Open question for Chad:** pumping currently rides concrete *including* waste. Test locks current behavior; flagging it rather than changing it.
- Skytrack is off by default with 0 days; enabling it and setting days survives refresh (`estimate_equipment.py:404`).
- Fallback path: with no labor summary stored, super days come from SF / 16000 × 7 and must equal the labor module's figure for the same pour. Two code paths, one number — assert they agree.

### 6.8 Settings scope drift guard (`test_settings_scope.py`)

Bug B shipped because a setting existed that nothing recalculated. The guard against
the *next* one:

```
for key in every row of system_settings:
    scope = settings_scope([key])
    assert any(scope.values()) or key in KNOWN_INERT_KEYS
```

`KNOWN_INERT_KEYS` starts empty. All 25 live keys map today (verified 2026-08-04:
`waste_*`, `support_rebar_lb_per_sf`, `pt_lb_per_sf` → pours; `form_percent`,
`form_waste` → forming; `labor_*` → labor + equipment; `equip_*` → equipment). Adding a
setting without wiring it turns the suite red and the author must either wire it or
declare it inert on purpose.

Plus the mapping itself: a pour key sets all four flags (pour quantities feed forming,
labor and equipment); a forming key sets only forming; a `labor_` key sets labor and
equipment (equipment days ride superintendent duration); an `equip_` key sets only
equipment; an unknown key sets nothing.

---

## 7. Layer 3 — golden estimate (`test_golden_estimate.py`)

One complete estimate, built by fixture, reconciled end to end against the Excel
workbook. This is the app's version of the playbook's pre-submit audit — the check
that the whole cascade agrees, not just each cell.

**Shape:** a small wrap-style building — 3 pours, 2 grade beam types plus 1 drop type,
PT with spacing set, sand, mesh on one pour, perimeter LF on all three. Small enough
to compute by hand in the workbook, broad enough that every code path participates.

**Reference:** built once in `Updated Estimate Worksheet.xlsm` (reference copies under
`workbooks/`), with the sheet, cell and value for each expected figure recorded beside
the assertion. Trace every bid quantity to a source — including in tests.

**Asserted:** total concrete CY (slab and beams split), sand CY, slab mat LF and lb,
support lb, all beam steel by kind, PT cable LF and lb, poly SF, every forming line
qty, labor cost by group and per SF, equipment days and cost.

**Tolerance:** exact to the stored column precision on quantities. Where the app and
Excel genuinely differ, the test asserts the app value and the comment records the Excel
value and *why* they differ — e.g. stirrups, which run heavy by a known and deliberate
margin. A documented difference is fine; an undocumented one fails.

**Rebuild rule:** the golden is not regenerated from app output. If it drifts, either
the app changed on purpose (update the golden, note it in `docs/todo.md` and the vault
note) or the app broke. Regenerating goldens from the code under test proves only that
the code equals itself.

---

## 8. Build order

Each phase leaves the suite green and useful on its own.

| Phase | Content | Why here |
|---|---|---|
| **1** | `conftest.py`, `migrations.py`, `factories.py`, `goldens.py`, `test_sql_functions.py` | Harness plus the locked arithmetic. Also proves the migration chain builds — the deploy rehearsal. |
| **2** | `test_pour_calcs.py`, `test_beam_calcs.py` | Pour and beam correctness, including the LBJ PT gap and the stale-beam-size lesson. |
| **3** | `test_propagation.py`, `test_settings_scope.py` | The three shipped bugs and the drift guard. **Highest value per line in the whole spec.** |
| **4** | `test_forming.py`, `test_labor.py`, `test_equipment.py` | Takeoff formulas and the two step ladders. |
| **5** | `test_golden_estimate.py` | Needs an Excel reconciliation pass; do it when the open calc decisions are locked, so the golden is not built on numbers about to change. |

Phases 1–3 are the ones that pay for themselves. If time runs out, stopping after 3
still covers every bug that has actually shipped.

---

## 9. Open questions for Chad

Answers change assertions, not structure. Phases 1–4 can proceed with current behavior
locked and marked provisional.

1. **Phase 5 timing.** The golden estimate is best built after the open calc decisions land (waste factors, PT rule, stirrup cover, L-bar method), or it gets rebuilt immediately. Build it now against current behavior, or wait?
2. **Equipment days band `3 < d ≤ 5`.** The ladder gives a flat 7 with no additive band there. Correct against the Excel sheet, or a transcription gap?
3. **Pumping on wasted concrete.** Pumping rides `calc_concrete_cy`, which includes the concrete waste factor. Intended (you pump what you order) or should it ride raw volume?
4. **Golden estimate source workbook.** Which file is authoritative for the reconciliation — the Bid Project Template's `Updated Estimate Worksheet.xlsm`, or a specific shipped job?

---

## 10. Definition of done

- [ ] `npm run verify` runs backend tests alongside the frontend checks; both green.
- [ ] The suite never connects to `estimating`. A test asserts the configured URL is not the live database.
- [ ] Every one of the three shipped staleness bugs has a test that fails when its fix is reverted. **Verified by actually reverting each fix on a scratch branch, not assumed.**
- [ ] Every provisional value is marked and listed in `goldens.py` with a pointer to its open decision.
- [ ] `docs/todo.md` Testing section updated; vault [[Estimating App]] "Known bugs / lessons banked" updated to record that the bugs are now covered.
