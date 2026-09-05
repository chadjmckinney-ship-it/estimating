# LBJ workbook reconciliation (2026-08-30)

> ## ⚠ Reference moved — read `docs/specs/workbook-reference.md` first (2026-09-01)
>
> This document was written against
> `Estimate_Projects\workbooks\Downloads\Trammel Crow - LBJ Estimate.xlsm`.
> **The live reference is now `C:\Users\Chad\Estimate_Project\Trammel Crow - LBJ
> Estimate.xlsm`** — a different, actively-edited copy. `docs/specs/workbook-reference.md`
> has the current per-sheet figures, the cells to read, and where each variance
> stands.
>
> Two corrections to an earlier, over-stated warning:
>
> * The **slab** figures below are **still current**. `04-PT Slab on Grade` reads
>   $703,265.37 in the live copy, exactly as recorded here, and both slab-relevant
>   mixes are still at bid prices. This reconciliation stands as written.
> * The piers figure recorded here, **$295,601.21, is cell T40** — the per-group
>   row path. The sheet's own `TOTAL COST` is **T42**, and the two do not agree.
>   See the reference doc; quote T42.
>
> Live sections read *above* their fixtures where the catalog has moved:
> `4000-AIR-ASH` is $155/CY against the bid's $145, `3500-AIR-ASH` $150 against
> $140. `3000-AIR-ASH` is untouched at $134, which is why the slab still
> reproduces to the penny and piers and walls do not. Catalog drift, not rules —
> see `docs/specs/price-restore-checklist.md`.
>
> The golden numbers live in fixtures now, each stating its own prices:
> `tests/mono_slab_fixture.py` ($671,712.66), `tests/walls_fixture.py`
> ($200,752.39), `tests/piers_fixture.py` ($297,204.52). **Those are the
> reference that fails when a rule changes. The workbook is a starting point** —
> see the first entry in `docs/specs/design-decisions.md`.

Golden-number check of the app against a real bid, then the fixes it exposed.
**Complete** — every dollar of the remaining variance is named.

**Source of truth (as of 2026-08-30):** `workbooks/Downloads/Trammel Crow - LBJ
Estimate.xlsm`, sheet `04-PT Slab on Grade`. **Compared to:** estimate
`152b3611` (5550 LBJ Multifamily, OHT Partners).

## Final result

| | Workbook | App | Variance |
|---|---|---|---|
| Cost | $703,265.37 | **$671,712.74** | **−$31,552.63 (−4.49%)** |
| Sale (both ×1.15) | $808,755.18 | $772,469.65 | −$36,285.53 |
| Cost / SF | $11.2122 | $10.7092 | |

Prices matched to the bid: mix $134/CY, rebar $0.60/lb, skid steer $225/day, poly
**Yellow Guard 14×210 at $340/roll**, accessories $0.04/lb, tape **2.5 rolls per
barrier roll**, markup ×1.1500.

| Item | Impact | Why |
|---|---|---|
| Rebar | **−$28,653** | the sheet carried ~44,000 lb of steel that was never going in the ground |
| Tie steel | −$5,687 | billed on that padded tonnage; the app bills what is actually tied |
| Poly | +$1,799 | same product, same price — the app applies 10% lap waste, the sheet applies none to this one product |
| Tape | −$924 | same 2.5 ratio; the app buys more rolls (waste) at Yellow Guard Tape's $23.65 vs the sheet's unnamed $33 |
| Brick ledge labor | +$830 | 830 LF @ $1.00; the sheet had no such line |
| Misc rental uplift | +$577 | the sheet applies neither tax nor the 50% fuel factor to Miscellaneous |
| Sand | +$524 | the app's 5% sand waste; the sheet has none |
| Forming package | −$17 | agrees to $16 on $29,600 |
| Concrete, PT, pumping, supervision | ~$0 | exact |

Exact to the cent or near it: concrete 2,205.1955 CY / $295,496.20, PT cables
$57,713.00, pumping $35,283.13, supervision within $0.07, all five original labor
rates.

Started at −$28,191 with the cause misdiagnosed; went to +1.28% once the vapor
barrier and tape were right; landed at −4.5% once the rebar was told the truth.

## Rebar — the big one

**The workbook was carrying about 44,000 lb of rebar that does not exist.**

| | Workbook | App |
|---|---|---|
| Beam steel | 65,771 lb | 15,382 lb |
| Slab mat | 291 lb | 291 lb |
| Support steel | folded into the beams | 6,272 lb |
| **Total** | **66,062 lb** | **21,945 lb** |

**Confirmed by Chad: GB 1 and GB 2 have no actual rebar besides support.** They are
13,755 LF of PT grade beam — the tendons draped through them do the reinforcing,
and the only loose steel is the #3 that holds cables and mat up while the crew
works.

Why the sheet said otherwise: sections §1 (12×32) and §2 (10×30) were written as
2-#5 top with #3 stirrups @ 24", and **that schedule was the support allowance, not
real steel.** Chad: *"I usually carry extra rebar in the beams for the #3 rebar that
gets used to support cables and rebar."* It was entered that way because the
workbook capped how many GB types existed, so folding the allowance into a section
made the takeoff quicker. The app carries the same allowance as an explicit
**6,272 lb support-steel line** (0.1 lb/SF).

Real beam steel is only the 2,596 LF that genuinely has bars: GB 3 (901 LF), brick
ledge (830 LF), Drop 9 (865 LF).

**The trade Chad named: more accurate, more work.** Entering beams honestly means
more types than folding an allowance into two of them. The app has no cap on beam
types — per estimate or per pour — so the constraint that caused the shortcut is
gone, but the data entry is real, and it is **accepted rather than optimised away**:
a reusable section library was proposed and rejected, because a section carried
forward is exactly how the padding survived job after job. See
`docs/specs/design-decisions.md`.

Two smaller structural differences, both deliberate:

- **The sheet's 10% on beam steel is not waste** — `× (1 + K$70)` is baked into
  every section's lb/LF at P49:P59, invisible in the schedule. The app now applies
  `waste_rebar` to beam steel the same way, stored on the beam row like concrete
  CY, and leaves support steel unwasted (wasting an allowance is slop on slop).
- **Stirrup hooks** — the sheet's stirrup term is bare perimeter `2×(W+H)` with no
  hook allowance. The app adds 1.0 ft per stirrup (sql/023): +13.6% on the stirrup
  portion of any beam that has stirrups.

## Tie steel (sql/032)

The TIE STEEL line used to be driven by every pound of rebar on the pour, less an
allowance of 0.35 lb/SF. Both halves were workbook artifacts: the sheet's tonnage
was inflated by the padding above, and the allowance was sized to cancel that
inflation. Once the padding left the beams the allowance ate the whole job —
21,953 lb carried against 21,945 lb of steel — and the line **silently billed $0
while the crew still tied eleven tons.**

Now: **beam bars + slab mat, support steel excluded.** Placing that #3 is the
tying, so billing it again charges one pass twice. LBJ bills 7.8363 tons =
$3,134.52. The allowance survives as a setting but defaults to 0. The line reports
its own driver on screen — *"Beam + slab steel 15,673 lb of 21,945 lb — support
steel excluded"*.

Uncheck the line when a sub's price includes tying; the enable checkbox on each
labor row already does that.

## Forming — the "untested corner" was a mis-filed line

It read as −$4,383 until the workbook's detail block (columns R–Z, rows 64–110) was
opened. **Cost code 40011 "Patch/Grout" is not patch or grout — it is poly tape.**
Row 95: `V95 = V88 × 2.5`, barrier rolls × 2.5 at $33/roll = $4,033.39. Filed under
the wrong code for years.

Move it where it belongs and the forming package agrees to **−$15.81 pre-tax on
$29,600**. What remains are four real differences, all of them the app being right:

| | Workbook | App | |
|---|---|---|---|
| 8p nails | 24 boxes | 13 | `SUM(K11:K42)` slipped down a row and swallowed **K42, the perimeter TOTAL cell** |
| 20p nails | 24 boxes | 13 | `SUM(K12:K47)` — same bug, two rows |
| 2x4 bracing | 1,009 LF | 865 | `SUM(W10:X41)*3` adds a section-**number** column to the length column: 144 + 865 |
| Siding | 10 sheets | 5 | the only form material the sheet does not scale by form% |

16p uses the correct range (`K10:K41`) and buys 13, which is what makes the other
two visibly wrong: three nail lines off one perimeter should not disagree. About
$1,500 of nails per job this size.

`tests/test_forming.py` pins all of it — 14 tests, each citing the workbook cell.

## Poly and tape detail (workbook rows 87–95)

The sheet's barrier menu is a Y/N column over four products; the selected row is
**10 Mil Yellow Guard 14' × 210' at $340/roll** — `V88 = DC$47/2940`, where DC47 is
the **pre-waste** area of 143,735.33 SF.

Catalog now matches at $340. The remaining +$1,799 is lap waste: the app applies
10% uniformly, the sheet applies none *to this product only* — its other three
options divide by effective coverages that quietly embed lap loss (2,000 → 1,900,
1,960 → 1,760, 3,187.5 → 2,360). Yellow Guard is the only row at full nominal
coverage, which looks like an oversight.

Tape: **2.5 rolls per barrier roll** in both. The app prices Yellow Guard Tape at
its catalog $23.65 rather than the sheet's unnamed $33, and buys rolls off the
wasted area (134.4 vs 122.2), netting −$924.

## How the workbook stores cost

Its 13 cost codes sum exactly to the sheet total. **Material codes are tax
inclusive** (Concrete $319,874.69 = 2,205.19586 CY × $134 × 1.0825); labor,
supervision and pumping are not. Equipment is odder still: rows 164–168 divide by
`(1 + tax + fuel)` to back out a base, and the **Fuel** line is the whole 0.5825
uplift, tax included. The app keeps tax as its own visible number
(`mono_slabs.calc_tax`) with a pre-tax catalog.

The item detail behind the cost codes lives in columns **R–Z, rows 64–110**:
R = cost code, S = item name, U/V = qty, W/X = unit + price, Z = extended
(tax-inclusive). That block carries the formula, not just the number, and is the
fastest way to settle any material question.

## What was built (sql/027–032)

1. **Sales tax, 8.25%** — `projects.tax_exempt` per project (ROW paving always
   exempt), stored as `mono_slabs.calc_tax`. Taxed: materials and rental days.
   Not taxed: labor, supervision, pumping. Worth **+$37,778** on this job.
2. **Fuel & maintenance, 50% on rentals** (`equip_fuel_maint_pct`). **+$12,058**.
   Fuel and tax both ride the pre-uplift base — they do not compound.
3. **Brick ledge as its own beam kind** (sql/028–029).
4. **Vapor barrier named on the estimate** (sql/030) instead of matched by name.
5. **Seam tape** (sql/031).
6. **Tie steel on tied steel** (sql/032).
7. **`waste_rebar` applies to beam steel**, not just the slab mat.
8. **`apply_sql.py`** — cross-platform migration runner with a `schema_migrations`
   table. Closes the migration-discipline backlog item.

Test suite: **145 passing** at the time of writing — `test_forming.py`,
`test_vapor_barrier.py`, `test_brick_ledge.py`, `test_pour_calcs.py`,
`test_tax_and_uplifts.py`, `test_staleness.py`, `test_recalc_freeze.py`,
`test_calc_functions.py`, `test_costing.py`. (322 as of 2026-09-01.)

## Vapor barrier and seam tape

The old rule searched for a name containing "10 mil" and "20", which found a black
20×100 roll filed under `site_accessories` at half the bid price. Yellow Guard
could not have won that search at any price — no "20" in its name. Both barrier and
tape are now **named on the estimate**, falling back to a company default (Stego
Wrap / Stego Tape).

Tape prices off the **barrier's roll count**, not slab SF:
`rolls × vapor_tape_rolls_per_barrier_roll × $/roll`. A barrier quoted in $/SF has
no roll count and carries no tape. Partial rolls are not rounded up, matching how
the poly itself prices. Chad's ratio is **2.5** — the sheet's figure; the extra
covers rolls walking off the jobsite.

Two recalc paths, deliberately different:

- Naming a product **on an estimate** reprices inside the PATCH (`_COSTING_FIELDS`
  in `routers/estimates.py`): a price changed, not a quantity.
- Changing a **company default** (`default_vapor_barrier_material_id`,
  `default_vapor_tape_material_id`, `vapor_tape_rolls_per_barrier_roll`) is in
  `_COSTING_KEYS` in `services/recalc.py`, so the recalc-all sweep rewrites every
  open estimate that named nothing.

## Brick ledge

The perimeter GB is thickened 6" for the brick ledge, and the ledge itself is a
**6" × 10" formed void** at the top of the (18"-wide) beam. In Excel it was entered
as a separate 6×32 grade beam — the easiest available workaround, which over-counted
poly and rebar. Some jobs have a ledge with **no widening at all**, which that model
could not express.

Priced as the thickening it is: concrete, rebar and poly behave like a beam, full
depth; the ~12.8 CY of void concrete is accepted as small. The kind adds a 2×6 at
ledge LF × form%, ply over `form_face_in` (the 10" void depth), and its own
`BRICK LEDGE` labor line at $1.00/LF. **0 × 0** expresses a ledge that is only formed.

Entered on LBJ as 6×32, 10" face, 830 LF across 14 pours — one entry that closed the
whole concrete gap (43.45 CY) and made poly area exact.

**The "six missing sections" finding was wrong** — the schedule is a library of ten
sections, and pours assign them to slots. Only five are used here. One was missing,
not six.

## Bugs found along the way

**In the app** (all fixed):

- **`GET /api/system-settings` had never worked.** `.format()` on SQL containing
  `#>> '{}'` raises IndexError before it reaches the database.
- **Number inputs rejected whole inches.** Stirrup spacing and slab bar spacing
  both had `min="0.1" step="0.5"`, so the browser accepted only 0.1, 0.6 … 23.6,
  24.1 — 24" and 18" o.c. were invalid, and the rejected field left 0.1 behind.
  Both are now `step="any"`; every other number input was swept.
- **Read models are built field by field.** Adding a column to the model and schema
  is not enough; `_to_read` in `projects.py`, `mono_slabs.py` and `estimates.py`
  each need it too.
- **Vapor defaults were missing from `_COSTING_KEYS`**, so changing one reported
  "nothing needed rewriting" and left stale numbers on screen.

**In the workbook** (all live in the sheet, all cost real money):

- 8p and 20p nails: ranges include the perimeter TOTAL cell — 24 boxes instead of
  13, roughly $1,500 pre-tax.
- 2x4 bracing: a section-number column summed into a length column.
- Poly tape filed under the Patch/Grout cost code.
- Yellow Guard poly the only barrier option with no lap allowance.
- Beam steel padded with a support allowance that reads as design steel.
- **`01-Piers` has two totals that disagree** — T40/AB39 (row path) against
  T42/E42 (cost codes), $6,848.97 apart, because a manually-changed concrete
  price reached one and not the other. Found 2026-09-01.

## Open

1. **Restore today's prices** — deliberately deferred while the calc engine is
   being built, so LBJ stays a golden-number fixture. Values, risks and the apply
   steps are in `docs/specs/price-restore-checklist.md`. **Partly overtaken by
   events:** `4000-AIR-ASH` and `3500-AIR-ASH` have already moved to $155 / $150,
   which is why live piers and walls read above their fixtures.
2. The published artifact **"LBJ Bid Reconciliation"** is stale — it predates the
   rebar work. This doc is the current record.
3. **Paving is +$77,196.73 (+5.8%) against the live sheet and not reconciled at
   that figure.** ~$48,324 is the paving mix at $150 against the bid's $140,
   untaxed. The remaining ~$28,900 has not been walked through. Not in this
   contract, so not urgent.

**Not open — decided against:** a reusable beam-section library
(`docs/specs/design-decisions.md`).

## Process notes

Five rounds were lost to a stale uvicorn process serving old code while the files on
disk were current. Windows allowed a second bind on 8001, so restarts reported
success while the original process kept answering. **Check what the server is
actually serving before reading any number from it** — the OpenAPI schema, or a
string you know changed in the last edit. A reboot cleared it.

Correct invocation, from the repo root:
`.\.venv-win\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --port 8001`
(`backend.app.main` fails — `main.py` imports `app.config`, so `backend/` is the
import root.)

The app's own API is the fastest way to reconcile: `/api/mono-slabs` and
`/api/estimates/{id}/labor|equipment|forming-materials` give every stored line, and
a residual that is **constant per unit of some driver** names the wrong price
immediately — a flat $0.02041 per poly SF was exactly ($370 − $310) / 2,940, which
found a Stego/Yellow Guard mix-up in one step.

Since 2026-09-01 there is a faster route still for material questions:
`GET /api/sections/{id}/material-costs` returns every purchase on a section with
its quantity, its rate, the catalog item it resolved to and its dollars. It is what
found the $0.65 rebar lump within minutes of going live.

**Open the workbook rather than reasoning from this document.** On 2026-09-01 a
piers variance was reported as +$8,528.89 by comparing the app against the figures
recorded here; reading the actual sheet put it at **+$179.92**. These numbers are a
record of one day, and the sheet moves.

**Read the hidden multipliers before calling a variance an error.** Tax inside the
material cost codes, the support-bar allowance inside every beam section's lb/LF, a
tie-steel allowance sized to cancel that same padding. None is visible in the
sheet's own presentation.

**Open the detail before naming a gap.** "Forming accessories −$4,383, the untested
corner" survived several write-ups on the strength of a cost-code label. The label
was wrong: it was tape. The forming package had been correct all along.

**A line that reads $0 must say why.** Tie steel silently zeroed twice — once from
the allowance, once from a beam edit — and both times the total still looked
plausible. Every derived line now carries its driver in `notes`.

**Ask what a workaround was working around.** The padded sections and the brick
ledge entered as a separate beam were both shaped by limits in the sheet — a cap on
GB types, no way to express a ledge. Reproducing the workaround would have imported
the limit with it.
