# Walls & Footings — specification, and what got built

**Status:** built and tested, 2026-08-31. `sql/040_walls.sql` needs applying.

**Source:** `06-Walls & Footings` in the LBJ workbook. Every formula was read
and reproduced **before any app code was written** — a standalone check
confirmed all 16 rows to the digit, and only then was the migration written.

**Target:** 652 LF of retaining wall on a continuous 70" × 12" footing,
3,452.55 form feet, **$200,477.16 cost / $230,548.73 sale** at 15%.
The app reads **$200,752.39**, **+0.14%**, accounted for below.

---

## The takeoff shape: one row is a wall AND its footing

That pairing is the sheet's and it is right. You do not take off a retaining
wall without the footing under it, the two share a length, and the footing's
width drives the trench the wall sits in. Splitting them into two tables would
mean keeping two rows in step by hand for no gain.

It is the **third takeoff shape**, after the pour (`mono_slabs`, shared with
paving) and the group (`pier_groups`). Its unit is **form feet**, which makes a
third allocation basis:

```python
if kind in PIER_KINDS:  return "EA"
if kind in WALL_KINDS:  return "FF"
return "SF"
```

Same reasoning as piers: `allocate_amount` falls back to "last row takes the
remainder" when every weight is zero, so a walls section run on the SF basis
would have put the whole forming, labor and equipment package on whichever run
sorted last, silently.

## Three things that look wrong and are not

**Footing steel is added twice.** The sheet computes `E*(N/P)` and `(E/P)*N` —
algebraically identical expressions, side by side, reading exactly like a
copy-paste duplicate. They are the two directions of a footing mat:

| | count | each | total LF |
|---|---|---|---|
| longitudinal | N/P bars | E ft | E×N/P |
| transverse | E×12/P bars | N/12 ft | E×N/P |

Both real, both needed, equal by construction. Same trap as the pier tie
formula, same verdict. "Fixing the duplicate" would take ~8,000 lb of steel out
of LBJ.

**Form feet is HALF the contact area.** The sheet computes both faces of the
wall and then halves the result, so "form feet" here means one face. That is
worth $2.83/FF against $5.66/FF on the same job — every rate in the assembly is
priced against the convention, so it is stated in the column comment rather
than assumed.

**The pilaster steel term carries a bare `+4`.** With no pilasters the product
collapses and the +4 survives, so every row with horizontal steel picks up four
bars' worth — 12.5 lb on the biggest row, ~200 lb across the job. Reproduced
because the sheet does it, pinned by a test because it looks like a stray
keystroke.

## One thing that IS wrong: the excavation divisor

The sheet divides by **3088**. Every other inches × inches × feet → CY
conversion in the workbook — including the footing concrete two columns to the
right — divides by **3888** (12 × 12 × 27). 3088 has no dimensional meaning.

**Chad's call: compute it honestly and name the difference.** 141 CY against
181, worth **$480** of excavation labor at $12/CY. `sheet_mode=True` reproduces
the bid exactly, because a bid that went out is a record and should stay
checkable; there is a test for that too.

**Confirmed by Chad, 2026-09-05, with the workbook open: a typo. 3888 stays.**
What the workbooks showed: the cell is `ROUND(N×O/3088×E, 0)` under "Labor
Sheet / Excavation" — footing width × thickness × length, the neat footing
volume. Every other inch × inch × feet → CY on the same sheet divides by 3888
(286 cells, including the footing concrete built from the same three inputs).
The backfill cell beside it ends in `/27*1.3`: when the template wants a
factor, it writes one. 3088 sits in the New Current template on all five
walls-type sheets (03, 06, 06-Footings, both garage sheets), 26 rows each, the
same fill on every one; LBJ inherited it. The older template (Updated Estimate
Worksheet) has no 3088 anywhere — its excavation was an allocated labor line,
not a per-row CY, so there was no cell to mistype until the rework created
one. Only excavation labor keys on the number; the excavator is per day and
walls carry no haul-off. The workbook's DD column is Chad's to correct.

## Two mixes on one section — a first

The wall takes its mix **per row** (every LBJ row is mix 5, 4000 PSI at $145).
The footing takes **one mix for the whole section** (the sheet's R8 = 3, 3500
PSI at $140). Cheaper concrete in the ground, better concrete in the wall — an
ordinary decision no other assembly has needed.

So `estimate_sections.footing_mix_design_id`, exactly where the sheet keeps it.
NULL falls back to the row's wall mix rather than to nothing: a footing priced
at zero is a hole, and a costlier fallback is a visible error where a free one
is not.

## The line sets

**Labor** — four rates on form feet, one on footing plan area:

```
FOOTINGS         $8.00 /SF of footing    3,803.33 SF   30,426.67
FORMING          $3.50 /FF               3,452.55 FF   12,083.92
PLACE AND FINISH $3.50 /FF                             12,083.92
WRECK & CLEAN    $1.00 /FF                              3,452.55
RUB AND PATCH    $0.25 /FF                                863.14
TIE STEEL      $450.00 /TON              16.864 tons    7,588.89
FRENCH DRAINS   $10.00 /LF                 652 LF       6,520.00
EXCAVATE        $12.00 /CY                 141 CY       1,692.00
BACKFILL         $8.00 /CY                 979 CY       7,832.00
```

The footing is priced per **square foot of footing**, not per form foot — it is
a flat pour in a trench and its labor has nothing to do with the wall above.
**RUB AND PATCH** has no slab equivalent: it is what you do to a wall face when
the forms come off.

**Supervision is typed**, as on piers — a wall job's duration comes from pour
sequence and cure, not area, so `labor_super_sf_per_week` is 0. 10 super days,
5 foreman, **5 expense**. Note the expense line does *not* ride the
superintendent's days here: the sheet types 5 against 10, because the super is
on site through pour and cure while the crew eating the per-diem is not.

**Equipment** rides the same ladder off typed days — 10 → 14 rental days → tier
→ 6 billable. **No trencher and no bobcat**: a wall crew digs its footing trench
with the mini excavator, which is what the sheet bills. Sky track and vault are
present at zero, because the sheet *has* those rows and types a zero into them —
different from a line the sheet does not have at all, which is simply absent.

**Forming** is 40% of form area against the slab's 50%, and carries two lines no
other assembly has — **wall ties** and **pipe bracing**, which are what holds a
formed wall together and plumb. The **french drain appears twice** on purpose:
you buy the pipe (forming) and you install it (labor), and the sheet carries
both at 652 LF.

## Every cent of the difference

$200,752.39 against $200,477.16 — **+$275.23, +0.14%**:

| Δ | |
|---|---|
| **+633.60** | **sand taxed.** The sheet's sand cell reads `IF(Q29="N",1+T29,1)` and Q29/T29 are empty, so it applies no tax to $7,680 of sand while taxing every other material. Same class of cell bug as the paving cure and siding lines — the app is right |
| **−479.88** | excavation at the honest 3888 divisor — 141 CY against 181 |
| **+122.33** | fuel and tax on MISCELLANEOUS equipment; the sheet exempts that one line from both uplifts. Same quirk the mono slab reconciliation found |
| **−1.39** | pumping on 284.8607 CY where the sheet rounds to 285 |
| **+0.45** | ASTM bar weights against the sheet's `(size/16)² × 10.680159` — half a pound across 33,728 |
| **+0.12** | four-decimal catalog prices against the Pricing sheet's six |

Matched exactly: 652 LF, **3,452.55 form feet**, 3,803.33 footing SF, 284.86 CY
split 135.54 wall / 149.32 footing, 384 CY sand, 979 CY backfill, all nine labor
rates, supervision $6,000, and the whole lumber package.

## What got built

| | |
|---|---|
| `sql/040_walls.sql` | `wall_runs`, `estimate_sections.footing_mix_design_id`, 31 walls rows in `assembly_rates` |
| `services/walls.py` | form feet, footing SF, three concrete pours, four steel terms, sand, excavation, backfill — with `sheet_mode` to reproduce the bid |
| `costing.py` | `_wall_units` and the FF allocation basis; two mixes on one section |
| line sets | walls forming, labor and equipment, dispatched on kind as paving and piers are |
| `routers/wall_runs.py` | CRUD, totals, and a bulk grid save with `extra="forbid"` |
| the grid | a wall-run column spec on the generic grid built for paving and piers |

`backend/tests/test_walls.py` (22) + `test_walls_api.py` (1). **300 in the
suite, all passing.** The tests were checked against a deliberately broken
build: halving the footing steel fails five of them by name.

## 2026-09-05 — the footing's mats can differ (`sql/059`)

Chad, looking at the wall grid freshly split into a wall line and a footing
line: "there are times with footings when the top and bottom mat are
different."

The footing had carried **one bar set and a mat count** — `ftg_spacing_in`,
`ftg_size`, `ftg_mats` — which is the sheet's shape and is right for LBJ, where
all sixteen rows are #5 @ 12" top and bottom, and wrong for a footing with
#5 @ 12" on the bottom and #4 @ 18" on top. Now each mat is its own bar set:

| column | meaning |
|---|---|
| `ftg_bot_spacing_in`, `ftg_bot_size` | the bottom mat — bar spacing (both directions) and bar size |
| `ftg_top_spacing_in`, `ftg_top_size` | the top mat — blank on a one-mat footing |

A mat with no spacing or no size contributes nothing (the deck's rule for its
top and bottom bars). Per mat the steel is unchanged — both directions,
`E*N/P` each, the "added twice" defended above — and the footing's steel is the
**sum of its mats**, so two identical mats come to exactly what "2 mats" came
to and the reconciled 33,727.83 lb stands.

Backfill on the live database: the sixteen LBJ rows (`ftg_mats = 2`) got a top
mat copied from the bottom; one test row with `ftg_mats = 0` had its bottom
cleared, since a count of zero contributed nothing. `ftg_mats` is gone. The
migration refuses to run if any row ever carries more than two mats.

On the grid the footing line puts its **bottom mat under the wall's horizontal
bars and its top mat under the vertical** (`bot sp"`, `bot #`, `top sp"`,
`top #`). `services/walls.py` `footing_mat_lb` + `footing_rebar_lb`;
`backend/tests/test_footing_mats.py`.

## Left for later

- **Pilasters are untested.** Every LBJ row leaves those columns empty, so the
  pilaster concrete, the ROUNDUP inside it and the steel term have never run
  against a real number. Same caveat as the pier bell.
- **Two skid steer rates.** This sheet types $275/day where 04-PT Slab uses
  $225 — one catalog, two sheets bid at different times. The fixtures each
  state their own, but the live catalog can only hold one.
- **Waterproofing** is a line at zero here ($5.25/SF of wall face). It will
  matter on a below-grade job.
- **`03-Walls & Footings`** is also filled, at $251,511 — a second walls
  section not in the LBJ contract total. Worth checking what it is before
  assuming this section is the only one.
