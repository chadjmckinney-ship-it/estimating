# Importing an estimate workbook (2026-09-10)

**Source:** the Lakeside Townhomes workbook, `Lakeside Townhomes - Estimate -
26-051 - 2026-09-09_14.xlsm` (GMP 08.13.2026 set, rev 14, Greystar, Flower
Mound TX), on the office's newer template — headers a row lower than the
LBJ tab's, a building-type QTY column on the slab tabs, hand-pour and
finish columns on paving and sidewalks. **Chad, 2026-09-10:** "while we
wait, lets import this estimate" — and, on the proposal, "full import,
build it".

## What was built

* **`backend/app/services/workbook_import.py`** — the reader and the
  apply. Tabs are found by name (a mono slab, a paving, the sidewalks, the
  grade beams, the footings, a slab on grade, the miscellaneous; piers,
  walls, panels, columns, decks are named as having no reader yet) and
  their columns by **header text**, not by letter. Under each grid it reads
  the tab's money: the mixes and their prices, the steel, mesh, PT and sand
  prices, the waste factors, the cartons' Y/N, the labor block (rate, unit,
  quantity, sub flag, cost), the supervision block (days at a day rate),
  the equipment block (days at a day rate), the contract services (rate,
  quantity, cost, and the "Pump Paving? N" switch), the PRICE row's sale
  and COST + markup, and the tax flag. The costs are read under the block's
  own "LABOR" and "SUB LABOR" headers, which the tabs merge across two cells
  and place differently tab to tab.
* **`backend/import_workbook.py`** — the command: `--dry-run` prints what
  would be written; `--replace` rebuilds an estimate of the same name;
  `--project` and `--estimate` name them.
* **The apply, through the app's own services.** The project (found by
  name or created, with the job number, the GC, the address, the bid date
  and the tax flag), the estimate (which pulls the master price list), the
  job's price sheet at the workbook's numbers — the mixes (a mix the
  catalog has no price for gets a row of its own), the rebar by kind
  (PT slabs, grade beams, paving), the PT cable, the sand, the Pricing
  tab's lumber by name, the four day rates, the pump — then one section per
  tab at the tab's waste factors and COST + markup with its labor subbed as
  the tab says, the takeoff rows (a pour at its building count, the beam
  schedule as beam types, each pour's beam, exposed-beam and drop feet as
  usages; a beam run; a spot footing at its count; a misc item matched to
  the library by name or added as a round base or a pad), the three line
  sets built the way opening the section builds them, the tab's labor and
  contract rates as **section rates** (only where the section reads such a
  key and the units agree), the supervision and machine **days typed** onto
  their lines, a count the app cannot derive (ADA ramps) typed, a service
  the tab charges nothing for and a machine or labor line the tab does not
  carry **switched off** and listed, the cartons off where the tab says N,
  and the job rolled up.
* **The per-row add $/SF** (2026-09-10, `docs/specs/labor-add-per-sf.md`): the slab tabs' `LABOR ADD` column, the
  paving tab's `Paving Add $$/SF` and the sidewalks tab's `Cost Adder` are read onto the row, and a row carrying one
  keeps the section's LABOR ADD line on whatever the tab's labor block says.
* **What stays the app's.** Every derived quantity — square feet, pump
  yards, saw-cut and joint feet, tons of steel, the lumber, the drops'
  feet, the excavation — is left to the app's rule. Nothing is pinned but
  days and typed counts, so the estimate keeps following its takeoff.
* **The tie-out.** Each section's app sale against the tab's SALE cell,
  the quantities beside them, and per section what was rated, typed and
  switched off and every tab line that found no home.

## The Lakeside tie-out (test database, 2026-09-10)

| Section | Tab sale | App sale | Gap |
|---|---:|---:|---:|
| Mono Slab on Grade Garden Style | 2,387,292 | 2,463,003 | +3.2% |
| Mono Slab on Grade Building 1 | 181,417 | 184,429 | +1.7% |
| Private Paving | 2,163,343 | 2,174,590 | +0.5% |
| Footings | 46,060 | 43,065 | −6.5% |
| Gd Beams | 257,840 | 281,282 | +9.1% |
| SLAB ON GRADE | 16,949 | 15,827 | −6.6% |
| SIDEWALKS | 685,162 | 663,290 | −3.2% |
| Miscellaneous | 61,675 | 61,675 | 0.0% |
| **Total** | **5,799,737** | **5,887,161** | **+1.5%** |

The workbook's own Summary tab is broken in this template (its total reads
0 and its misc line carries one item), so the tabs' SALE cells are the
target. The named differences:

* **Garden style, +$76K.** The app prices drop labor at the Drops column's
  8,098 FF (367 FF × 5 T1s and so on); the tab's labor line uses 4,172 FF
  from a column driven by the exposed-beam cells, which are empty. That is
  the tab disagreeing with itself; the app follows the Drops column. A
  light tower the tab carries for 120 days ($3,703) has no line in the
  mono-slab set. The app's mini excavator is switched off (the tab has
  none).
* **Gd Beams, +$23K.** The app excavates the trench (852 CY) where the tab
  excavates the concrete volume (374 CY); the app's lumber for a
  separately poured beam is fuller than the tab's; a compactor ($1,899)
  has no line in the beams set. Cartons and the retainer are off, as the
  tab says.
* **Footings, −$3K.** Place & finish, wreck and rub & patch have no lines
  in the spot-footing set (the app's footing labor is one line per SF); a
  compactor ($950) has no line.
* **Slab on grade, −$1K.** The tab's grade/poly per LF and thickened-edge
  labor have no lines in the slabs set.
* **Sidewalks, −$22K.** The app's lumber and sand for a walk are lighter
  than the tab's; the supervision (152.5 days), the 33 ADA ramps and the
  labor rates are the tab's.
* **Miscellaneous.** The sale is typed and ties; the AC condenser pads
  (not in the library) were added as a slab, 9 SF × 4".

## What it deliberately does not do

* It does not read the piers, walls, panels, columns, deck or slab-on-deck
  tabs. Lakeside has none priced; the reader for each is a later job.
* It does not price the catalog. A mix the catalog has no price for gets a
  price-sheet row at the workbook's number, and the note says so.
* It does not pin derived quantities to the tab's. Where the two rules
  differ the tie-out says so, and the section keeps following its rows.

## Tests

`backend/tests/test_workbook_import.py` builds a workbook in the Lakeside
layout and pins: the reader (the header-keyed columns, the placeholder row
skipped, the building counts, the beam schedule and usages, the material
block with its waste and the cartons' N, the labor/supervision/equipment/
contract blocks with their merged costs, the "Pump Paving? N" switch, the
PRICE row, the tax flag, the misc tab's site mix and per-unit labor); the
mix-name reading; the apply (the project and estimate, the price sheet
with a row made for an unpriced mix, the sections' waste and markup, the
pours at their counts with their beams and the drop, the rates on the
section, the days pinned, the machine the tab has not switched off, the
pump the tab said no to off, the spot footing at its count, the misc
library item at the tab's dimensions and the pad added, every section
priced, the roll-up and the tie-out); and the replace/refuse rule.

## Running it on the box

```bash
scp "<the workbook>.xlsm" chad@192.168.0.145:~/estimating/imports/
ssh chad@192.168.0.145 'cd ~/estimating/app && .venv/bin/python backend/import_workbook.py ~/estimating/imports/<file>.xlsm --dry-run'
ssh chad@192.168.0.145 'cd ~/estimating/app && .venv/bin/python backend/import_workbook.py ~/estimating/imports/<file>.xlsm'
```

The estimate id is printed last; the tie-out above it. Deleting the
estimate in the app (an admin) removes everything the import wrote except
the project.
