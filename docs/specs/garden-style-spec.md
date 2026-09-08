# Garden style — a quantity on the pour (2026-09-08)

**Source:** the `Mono Slab on Grade Garden Style` tab of the estimate
workbook. **Chad, 2026-09-08:** "garden-style multiplier on the mono slab?"
and, on the proposal, "yes, build it".

## What the tab is

The 04 tab with a QTY column. One row per **building type**, taken off once —
square footage, thickness, cable, mix, sand, permanent edge, reinforcing,
mesh, the grade beams and drops by type and length — and priced once, then
multiplied by the number of buildings of that type: `AH = AF × G`, with the
hidden `QTY SLABS` and `TOTAL SQ FT` columns carrying the count and the area
into the Summary. University Hills is five type rows covering eight buildings.

The app had one shape for a pour and no multiplier, so a garden-style job was
eight rows that had to agree, edited eight times.

## What was built (`sql/079`)

* **`mono_slabs.qty`**, integer, default 1, never negative. The pour form
  carries it beside the description; the pour table shows it and, on a row
  at more than one, what the row's SF adds up to. The paving and sidewalk
  grids have no column for it and their saves leave it alone.
* **The row's stored figures are the row's totals.** `refresh_mono_slab_calcs`
  computes and quantizes every per-building figure exactly as it always
  has — slab, edge, stair and beam concrete, sand, the mat, the support
  steel, the cables, the beam rollups, the poly — and multiplies the stored
  columns by qty once, at the end. So a row at qty 8 carries to the last
  decimal what eight rows would sum to, and a section of qty-1 rows is
  untouched.
* **Every sum over the raw takeoff columns carries it too.** The section
  totals, the forming, labor and equipment drivers, the supervision
  fallback, the costing weights, the $/SF prices (PT cable, mesh), the
  material list, the PT quote driver, the beam-kind breakdown the pour table
  hovers show, and the beam lengths under the pour — drops, ledges — through
  the join. `costing.pour_sf` is the one place that knows a row's area is
  SF × qty.
* **Blank reads as one.** A cleared box on the form must not zero a pour that
  was priced a moment ago. **Zero** keeps the row on the list and out of
  every total.

## The contract

`tests/test_garden_style.py`: the LBJ fixture's Pour 01 with a mat, 48" cable
spacing and its five beam usages (two PT grade beams, a reinforced one, a
brick ledge and a drop), as **one row at qty 8** against **eight rows at
qty 1**. Every section quantity identical; the forming, labor and equipment
lines identical; the material list identical; the money within the cents
that rounding eight rows to the cent can move. A row at qty 0 beside a row
at qty 1 equals the second row alone. The endpoints: a posted qty reads back
and the totals carry it, a pour without one is 1, `null` is 1, a negative is
a 422, and a grid save that does not send it does not change it.

The mono slab, paving and sidewalk goldens are the qty-1 case and did not
move.

## Left alone

The tab's `BLD #` column is a label and lives in the description. The typed
`AF` price per building is the app's cost at the section's markup, as on
the 04 tab. Contingency is not a section.
