# Columns — specification, and the live section

**Status:** 2026-09-01, amended 2026-09-02. **Built, tested, on screen, and
entered on the LBJ job.** Every formula was reproduced against the sheet's own
numbers before a line of code was written; the four decisions below are all
implemented, all with a test.

**Source:** `07-COLUMNS` in
`C:\Users\Chad\Estimate_Projects\workbooks\Downloads\Trammel Crow - LBJ Estimate.xlsm`,
filled in by Chad on 2026-09-01. Until then the tab was empty and columns was
going to be the first assembly with no golden number.

**Sheet:** 68 columns, **$160,746.20** cost, **$2,789.42/column** at 18%,
taxable at 8.25%. The sheet's own total reconciles to that from its parts
exactly — materials $56,167.51 + labor $43,913.83 + supervision $13,175 +
PM $3,400 + equipment $19,257.53 + contract $2,600 + forming materials
$22,232.33.

**Live section** — estimate `152b3611`, section `e9f8ca1c`, created 2026-09-01:

| | |
|---|---:|
| Cost | **$173,327.42** |
| Sale (18%) | $204,526.35 |
| Cost / column | $2,548.93 |
| Sale / column | $3,007.74 |
| Cost / form SF | $22.46 |
| Tax | $7,529.47 |

**+$12,581.22 against the sheet, +7.83%, every dollar named** — see the
reconciliation at the end.

> **These figures predate the 2026-09-02 SLAB CHAIRS fix** (audit #7) and move
> **−$19.49** on the section's next recalculate: $173,327.42 → **$173,307.93**,
> and the job $2,759,140.62 → $2,759,121.13. The chairs line was buying METAL
> CHAIRS at $45 where it is labelled SLAB CHAIRS at $27.

The job moved from $2,585,813.20 to **$2,759,140.62** cost, **$3,229,247.88**
sale, and the estimate rollup equals the sum of its five sections exactly.

---

## The takeoff

| Type | Qty | Height | L × W | Verticals | Ties | Dowels | Steel lb | CY | Face SF |
|---|---:|---:|---|---|---|---|---:|---:|---:|
| C1 | 38 | 12' | 18×24 | 8-#8 | #4 @ 6" | 8-#8 × 5' | 18,911.8 | 53 | 2,736 |
| C2 | 23 | 24' | 18×24 | 8-#8 | #4 @ 6" | 8-#8 × 5' | 20,185.3 | 64 | 3,312 |
| C3 | 1 | 12' | 18×24 | 8-#8 | #4 @ 6" | 8-#8 × 5' | 497.7 | 2 | 72 |
| C4 | 6 | 12' | 18×30 | 10-#10 | #4 @ 6" | 10-#10 × 5' | 5,231.2 | 11 | 540 |
| | **68** | | | | | | **44,825.9** | **130** | **6,660** |

All mix **5000-ASH** (catalog id 15). Three vertical bar sets are supported per
type; only set 1 is used here.

What the app reads for the same takeoff: **7,716 form SF**, **128.2666 CY**,
**47,417.079 lb** (vert 27,373.896 + ties 11,339.433 + dowels 8,703.750),
**4,368 LF** chamfer, **17** superintendent days.

## Geometry, as the sheet computes it

```
steel lb  = [ height × n₁ × (size₁/16)² × 10.680159                    vertical set 1
            + ( height × n₂ × (size₂/16)² × 10.680159                  set 2
              + n₃ × (size₃/16)² × 10.680159 × height                  set 3
              + (tie_size/16)² × 3.145 × 0.2836
                × ((L×2 + W×2) × height × 12 / spacing)                ties
              ) × (1 + waste)
            ] × qty
          + qty × (dowel_size/16)² × 10.703064 × dowel_lf × dowel_n × (1 + waste)

concrete  = ROUNDUP( height × L/12 × W/324 × qty × (1 + 4%) , 0 )      per TYPE
face SF   = height × W × L / 36 / 2 × qty                              ← see below
```

The tie constant works out: `(4/16)² × 3.145 × 0.2836 = 0.0558 lb/in`, against
#4 ASTM at 0.668 lb/ft ÷ 12 = 0.0557. The sheet is computing lb per **inch** of
tie and its quantity term is in inches.

Reproduced in Python to 4 decimals on every row — 44,825.9163 lb, matching
`T54`. The model is therefore understood, not guessed at.

**Concrete divisor:** the sheet writes `F × G/12 × H / 324`, which is
`L × W × height / 3888` with one of the twelves moved. Building it as `/324`
put 1,539 CY on the section — 12× high — before the first test caught it.

---

## Four differences from the sheet, three of them decided

### 1. Rebar waste skips the main vertical bars — FIXED (Chad, 2026-09-01)

The bracket in `T10` closes after vertical set 1, so the `× (1 + 10%)` lands on
sets 2 and 3, the ties and the dowels — but not on the biggest bar in the cage.
It reads as a misplaced parenthesis rather than a decision.

**+2,479 lb, +$1,611 at $0.65/lb** (plus tie-steel labor on the same tonnage).

### 2. Form area uses the cross-section, not the perimeter — FIXED (Chad)

`AZ` computes `height × (L × W / 36) / 2`. For an 18×24 column that is **72 SF**
where wrapping it is `(18+24)×2/12 × 12 = 84 SF`. It is not a consistent factor
either — 18×30 lands at 93.8% of the honest figure where 18×24 lands at 85.7%,
because area and perimeter do not scale together.

**The sheet already holds the right number.** Column X, "Build up", is
`(L×2 + W×2)/12 × height × qty` and totals **7,716 SF** — exactly the perimeter
figure. It drives the BUILD-UP labor line and nothing else. Forming, place and
finish, wreck, rub and patch, and the entire equipment/supervision/contract
allocation all ride `AZ` instead.

**6,660 → 7,716 SF, +15.9%.** This is the expensive one: it moves four labor
lines, the 2x4 / plywood / nail quantities, and the basis every shared cost is
spread by.

`services/columns.py` keeps the sheet's expression as `sheet_form_sf()` and the
fixture can build in `sheet_mode=True`, so the difference stays demonstrable
rather than asserted.

### 3. Chamfer forgets the quantity — FIXED

`S81 = SUM(F10:F53) * 4` sums the **height** column across the four column
*types* and never multiplies by qty. 240 LF on a 68-column job; the honest
figure is `Σ(height × qty) × 4` = **4,368 LF**. Same class as the paving
`SUM(W10:X41)*3` bug — a range that sums the wrong thing.

**+4,128 LF, +$1,032 at $0.25/LF.** Small money, wrong by 18×.

### 4. Concrete rounds up to a whole yard per type — NOT REPRODUCED

`ROUNDUP(…, 0)` turns 52.6933 CY into 53. Sensible when ordering trucks, not
when costing, and the app keeps decimals everywhere else.

**128.2666 CY against 130, −$303.**

---

## Rates and line sets

**Materials** — both resolved from the catalog and reported by name:

| | | Live |
|---|---|---|
| Concrete | mix per type, 4% waste | 5000-ASH, $175.00/CY → $22,446.66 |
| Steel | REBAR GRADE BEAM, 10% waste on **every** bar | $0.6500/lb → $30,821.10 |

**Labor** — all per SF of form contact area except tie steel

| Line | Driver |
|---|---|
| BUILD-UP | perimeter × height (already honest on the sheet) |
| FORMING | form SF |
| PLACE AND FINISH | form SF |
| WRECK AND CLEAN UP | form SF |
| RUB AND PATCH | form SF |
| TIE STEEL | per ton — every pound, no support-steel exclusion, as on piers |

Live labor + supervision: **$65,823.82**.

**Supervision — driven by COLUMN COUNT, not area.** A third duration model:

```
weeks = columns / 20          68 / 20 = 3.4
days  = weeks × 5             = 17          ← five-day weeks, not seven
```

The slab derives days from SF/16,000 × 7; paving from SF/25,000 × 7; piers and
walls type them. Columns is the first assembly to derive them from a **count**,
and the first to use a 5-day week.

**Quantized once**, in `services/columns.super_days`. Rounding the weeks and
then multiplying is a double round — the mistake that cost the mono slab eight
cents.

**Consequence worth knowing:** changing the quantity on ONE type moves the
superintendent, the foreman, the expense allowance, the PM and the entire rental
ladder for every other type on the section. Every write path re-runs the whole
section for that reason.

**Equipment** — 17 super days → 30 rental days → 9 billable (the same tier rule
paving uses). Sky track, hoisting (the mini excavator line), skid steer, storage
and miscellaneous, all from the catalog; fuel & maintenance 50%. Live:
**$12,285.00**, which is 9 × $1,365 exactly.

**Contract services** — pump allowance per CY. Cure, saw cutting and
out-of-town carry rates but no quantity on this job.

**OFF SITE HAUL OFF is present but OFF by default** (2026-09-02). Chad:

> *"I think columns having hauloff is an artifact from building the workbook..
> there shouldnt be hauloff.. and if there is, thats on us for a mistake or a
> CO.. but we will need it for pilasters."*

A column is formed off a footing somebody else dug, so there is no spoil. The
line exists because the 07 sheet has the row — which is how a workbook column
becomes a feature. It is **disabled rather than deleted** because a pilaster is
a columns section (below) and a pilaster does dig. The rate still shows, so
turning it on is one click. `tests/test_audit_small_fixes.py` pins the default,
the billing path when it is switched on, and that piers and walls keep theirs
enabled.

**Forming materials** — a hidden column on the sheet worth $22,232.33, 14% of the
section. Live: **$25,713.54**.

```
2x4 x 16'        form SF × form%              3,858 LF @ $0.8594
3/4" ply         form SF / 32 × 2 × form%     241.125 sheets @ $74.75   ← the big one
stakes           ROUNDUP(columns / 2 / 25)    2 bundles @ $24
16p nails        ROUNDUP(form SF / 1800)      5 boxes @ $68.20
8p nails         ROUNDUP(form SF / 3000)      3 boxes @ $68.20
6p nails         = 8p                         3 boxes @ $68.20
chamfer          Σ(height × qty) × 4          4,368 LF @ $0.25          ← see finding 3
accessories      steel lb                     47,417 lb @ $0.04         ← see below
form release     ROUNDUP(form SF/300/55)      1 drum @ $542
slab chairs      ROUNDUP(form SF / 12000)     1 bag @ $27               ← was $45, audit #7
```

`form% = 0.5`, on the 2x4 and the plywood only.

**Allocation basis: FORM CONTACT SF.** Every shared cost spreads by it, and the
per-column cost is the section total ÷ qty. So columns allocate the way walls
allocate by form feet, not the way slabs allocate by area. Note the difference
from walls: a column is **wrapped** — all four faces — where a wall is formed on
the face you can reach, which is why the $/SF rates here look small beside the
wall sheet's $/FF.

---

## What was built

1. `sql/045_columns.sql` — the `column_types` table (qty, mix, height, L, W,
   three vertical sets, tie size/spacing, dowel size/count/length) and 27
   `assembly_rates` rows. **No prices** — see `claude/design-decisions.md`.
   (The `assembly_rates` column is `note`, not `notes`.)
2. `services/columns.py` — the geometry above, with the four decisions applied.
3. `costing.py` — `_column_units`, `allocation_basis` returning SF, and
   `resolve_rebar` reaching the grade-beam bar.
4. Forming / labor / equipment line sets dispatched on the new kind, including
   the count-driven, five-day-week supervision.
5. `models/column_type.py`, `schemas/column_type.py`, `routers/column_types.py`
   — CRUD plus `PUT /bulk` and `/totals`, mirroring `wall_runs`.
6. `tests/columns_fixture.py` + `test_columns.py` — 14 tests, stating their own
   prices.
7. **The screen** (`frontend/assets/js/app.js`): `COLUMN_KINDS`, nine stat
   cards, a 22-column grid spec, and columns branches on the forming, labor and
   equipment card headers. `tests/test_columns_ui_contract.py` guards the field
   names it reads; `frontend/check.mjs` guards the parse. See
   `claude/frontend-parse-and-drivers.md` — building the screen surfaced three
   silent failures, none of which produced an error anywhere.

**Still open: a second columns section called "Pilasters."** Chad, 2026-08-31:

> *"I dont use the pilaster section because it doesnt let me add enough info
> and I just use column sheet for it since it is basically a short column… so
> when we create columns we can just make 2 and call the second section
> pilasters."*

That is why `sql/041` dropped the pilaster fields from `wall_runs`. Nothing
needs building — create a second section of kind `columns` and name it. **The
one thing a pilaster section differs on is haul-off:** tick OFF SITE HAUL OFF
on and give it the spoil CY, because unlike a column a pilaster digs. That is
the whole reason the line is disabled rather than removed.

---

## Reconciliation: +$12,581.22 (+7.83%) against the sheet

| | Impact | |
|---|---:|---|
| Form area 6,660 → 7,716 SF | the large one | four labor lines, lumber, nails, and the whole allocation |
| Vertical bar waste | +2,479 lb steel | plus tie labor on it |
| Chamfer quantity | +$1,032 | 240 → 4,368 LF |
| Accessories $0.02 → $0.04 | **+$1,026.58** | see below |
| Concrete decimals | −$303 | 130 → 128.2666 CY |

(Since 2026-09-02, less **$19.49** for SLAB CHAIRS at its own price — see the
note under the live figures.)

**The accessories line is the only item not in the pre-build prediction, and it
is the catalog doing its job.** `07-COLUMNS!U99` types **$0.02/lb**; the catalog
carries ACCESSORIES at **$0.04**, which `sql/044` established as the current
price after finding the same $0.02 typed over `Pricing!Q14` on the paving sheet.
47,417.079 lb × $0.02 = $948.34, × 1.0825 tax = **$1,026.58** — exactly the gap
between the live section and `tests/columns_fixture.py`, which states the
sheet's $0.02.

Per `claude/design-decisions.md`, **that is not a finding.** The sheet is
deliberately behind; the catalog is the single source. The fixture states $0.02
so the test still fails when a *rule* changes, and the live section reads the
current price.

Residual beyond those five: **nothing**. The materials reconcile to the cent
($22,446.66 + $30,821.10 = $53,267.76 direct).

## One bug the live entry found

The forming card's 6p nails line was labelled **"16p NAILS DUPLEX"**.

`_find_material(db, "6p")` matches on `name ILIKE '%6p%'`, and "1**6p** NAILS
DUPLEX" contains it — sorting first on id, ahead of the real "6p NAILS".
**Every assembly in the app calls it with "6p"** — slab, paving, piers, walls,
columns, five line sets — so all five had been buying 16p nails on their 6p
line.

It cost nothing, because all three nail boxes are $68.20, and that is precisely
what kept it invisible: the extension was right and the material name beside it
was not. The day 6p and 16p prices diverge, five line sets quietly buy the wrong
nail.

Fixed by **ranking** rather than filtering — a name containing the fragment at a
word boundary wins, substring behaviour stays as the fallback — so nothing that
resolved before stops resolving. `tests/test_forming.py` pins both halves.

This is the Yellow Guard rule (sql/030) paying off again: *a price found by name
search is a price nobody can see*, so every resolved item is reported by name.
That report is the only reason this was ever visible.

**The same class caught it again on 2026-09-02:** the SLAB CHAIRS line was
asking for `"CHAIRS"` and getting METAL CHAIRS 2.5" at $45 where the row it is
named after is $27. Boundary ranking does not fix that one — all four `%CHAIRS%`
rows rank equally and sort order decides — so the fix was to ask for the full
name, as the mono slab always did (audit #7).
