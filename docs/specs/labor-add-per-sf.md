# The add $/SF on every pour-shaped row (2026-09-10)

**Source:** the LBJ workbook. The slab tab (`04-PT Slab on Grade`, and
`05-Slabs` the same) carries `LABOR ADD /SF` in column C on every pour
row; CP is `C × D` (the rate times the square feet) and the LABOR ADD line
under the grid is `SUM(CP)`. The paving tab carries `Paving Add $$/SF`
(column F, BA = `C × F`); the sidewalks tab carries `Cost Adder` (column
H, BG = `H × C`). **Chad, 2026-09-10:** "on the LBJ workbook, there is a
column for most items of a cost added per sf" — and, on the proposal,
"build it".

## What the app had

A paving area has carried the box since `sql/036` — `paving_add_per_sf`
on the row, summed as square feet × rate onto the paving set's LABOR
ADJUSTMENT line at $1 a lump. A mono slab or rebar slab pour had no box;
its LABOR ADD line was a typed lump at $0. A walk had neither.

## What was built

* **The pour form** (mono slab, rebar slab, slab on deck) has an **Add
  $/SF** box; the **walk grid** has an Add $/SF column. Both write the
  same field the paving grid writes.
* **The slab set's LABOR ADD line** rides the rows: Σ square feet × the
  building count × that pour's add $/SF, at $1 a lump, the tab's `SUM(CP)`.
  A section with no add reads $0 with a note saying how to carry one. A
  typed total still pins the line, as before.
* **The walk set** gains a LABOR ADJUSTMENT line on the same rule, the
  paving set's line by another name.
* **The importer** reads `LABOR ADD` (with its `/SF` subheader), `COST
  ADDER` and `PAVING ADD` columns onto the row on the slab, slab-on-grade
  and sidewalk tabs.
* No migration: the column exists on every mono-slab row already, and the
  name stays `paving_add_per_sf` in the schema so nothing that reads it
  moves. Every screen calls it Add $/SF.

On the Summary the line files where LABOR ADD always has: 000046 Labor
Burden subbed, 000027 in house.

## Tests

`backend/tests/test_labor_add_per_sf.py`: the line rides the pours (three
buildings of 10,000 SF at $0.50 is 15,000), a pour without one adds
nothing, the section's cost moves by exactly the add, the API takes it on
a pour and the line follows and a blank takes it off, a typed total still
pins, and a walk's cost adder is a LABOR ADJUSTMENT. The workbook-import
test carries a LABOR ADD column; the screen-contract tests carry the box.
