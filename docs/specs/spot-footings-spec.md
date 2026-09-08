# Spot footings — 06-Footings, on the walls engine (2026-09-07)

**Source:** `06-Footings` on the Pearl Landing Podium estimate
(`workbooks/Pearl_Landing/Podium Estimate.xlsm`), $187,680.06. On the LBJ
workbook both footings tabs are empty copies of the walls tab, so there was
nothing there to reconcile against.

**Chad, 2026-09-07:** "most spread footings have a weld plate.. so I think we
need a section for spread footings and one for continuous footings.. we can do
cont footings when we do grade beams.. for spot footings, the wall calc works
if we do l w and h with a count.. t&b mats"

## What the tab is

The walls tab with the wall columns left blank. Four rows on the Podium job:

| Type | Count | Each | Wide | Thick | Mats |
|---|---:|---:|---:|---:|---|
| 5 | 6 | 10 ft | 144" | 24" | #6 @ 6", two mats |
| 6 | 17 | 8.5 ft | 102" | 24" | #6 @ 10", two mats |
| 7 | 47 | 6.5 ft | 78" | 24" | #6 @ 10", two mats |
| 8 | 16 | 3 ft | 36" | 24" | #6 @ 10", two mats |

The length is typed as the count times the size (`E10 = B10 * 10`), the
footing block (N:R) does the rest, and the cost stack is the walls tab's:
concrete and steel by the same formulas, FOOTINGS labor at $15/SF of footer,
tie steel per ton, excavation per CY, the lumber block (2x10, stakes, chamfer,
water stop, turnbuckles, haul-off, accessories), the supervision block, the
equipment ladder off the superintendent's days, the pump per CY.

Built as a walls section with the wall blank, the app matched every one of
those line for line before anything was written — the scratch run on
2026-09-07 reproduced 446.4 LF of 2x10, 18 bundles of stakes, 1,116 LF of
chamfer and 558 LF of water stop to the foot. What it lacked was a row shaped
like a footing.

## What was built (`sql/072`)

* **A kind, `spot_footings`, in `WALL_KINDS`** everywhere the engine branches
  — calc, forming, labor, equipment, costing, material costs, quotes, section
  rates — and in `SPOT_KINDS` where a footing differs from a wall.
* **Three columns on `wall_runs`:** `footing_count`, `footing_each_ft`,
  `weld_plate`. `refresh_wall_run_calcs` sets `length_ft = count x each`
  when the second is given; a wall run leaves it blank.
* **The grid** is one line per type — type, qty, L ft, W", H", mix, bottom
  mat, top mat, weld plate, backfill — with SF, CY, steel and cost per
  footing derived. The section is sold per footing (`unit` EA,
  `calc_quantity` = the count); `footing_sale_per_sf` is the sheet's Z column.
* **The labor set drops the wall-only lines** (forming, place & finish,
  wreck, rub & patch, the french drain); the lumber block stays, unchecked
  where a line does not apply.
* **WELD PLATE** is a catalog material with no price until Chad names one:
  one per footing that carries one, on the material list, reported as
  unpriced rather than free.
* **Rates** for the new kind are the walls tab's, copied by the migration;
  the job sheets carry them at those values.

## Where the app deliberately differs from the sheet

| | Sheet | App | Why |
|---|---:|---:|---|
| Excavation | 380 CY (`N x O / 3088 x E`) | 302 CY | the walls typo Chad left at 3888, 2026-09-05: −$936.00 of labor |
| Pump | 320 CY (`ROUND(W36)`) | 320.1985 CY | the pour, not a rounded pour: +$1.98 |
| Miscellaneous equipment | flat days × rate | an ordinary rental | fuel and tax, as on walls: +$122.33 |
| Sky track, vault | 14 days off the ladder (`D83 = D84`) | typed 14 days | off until typed on the walls set; typed, no difference |
| Bar weight | `(6/16)^2 x 10.680159` | catalog 1.502 lb/ft | +$1.74 of bar, +$0.53 of tie labor, ten cents of accessories |
| Lumber block | $3,719.48 | $3,719.51 | 2x10 at $1.0938 not $1.09375, haul-off loads to three places |
| Weld plates | none | 86, unpriced | the point of the unpriced rule |

The sheet's $187,680.06 less those is the app's number, held as `GOLDEN_COST`
in the fixture.

`tests/spot_footings_fixture.py` states the prices and the golden number;
`tests/test_spot_footings.py` holds each of the above.

## Width in feet (2026-09-08)

**Chad:** "on spot footings, you have lf x w" x h", can we change it to width
in feet?" — a spread footing is called out in feet. The grid's width column
is now **W ft**, typed in decimal feet (4.5 is 4'-6"); the box shows the
stored inches ÷ 12 and the save multiplies back, to a thousandth of an inch
(`frontend/assets/js/units.js`, tested in `frontend/tests/units.test.mjs`).
The row still stores and sends `ftg_width_in`, so the walls engine, the API,
the wall grid's own Width" box and the sheet's N column all keep their
inches. Length stays L ft and thickness H". A footing on file at 120" reads
back as 10.

## Not built here

Continuous footings (`02-Cont Footings`, `06-Garage Footings` — 1,189 LF and
$449,050.89 on the Podium job) wait for grade beams, as Chad said.
