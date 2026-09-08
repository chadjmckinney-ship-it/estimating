# Miscellaneous — the 13-Miscellaneous tab, a priced library of site items (2026-09-08)

**Source:** the `13-Miscellaneous` tab of the LBJ workbook and its template.
Nothing on any workbook in the folder is typed into it, so the golden is an
exercise on the library. **Chad, 2026-09-08:** "ok, lets do miscellaneous"
and, on the proposal, "Yes, make those and then a way to add similar.. so have
the 4 sections with the ones shown as defaults, minus the quantities.. then a
button for each section to add another row".

## Where the kind stood

`miscellaneous` was a kind in name only: on the section list since `sql/033`,
unit LS, no table, no line sets, no rates.

## What the tab is

Not a takeoff. A priced library of 22 named site items in four blocks of rows,
each row a typed **unit sale** (H), a typed **labor cost per unit** (J), a sub
flag, and a shape the concrete and steel come from. Every other piece of a
row's cost is a formula particular to that item. The margin is the result:
`1 − cost ÷ sale`, per row (Z) and for the section. The Summary reads the
tab's sale as the sum of the rows' sales and its cost as the sum of the rows'
costs.

| Family | Rows | Concrete | Steel | Forms, supervision, equipment |
|---|---|---|---|---|
| Round base | dia" × depth' | π r² × depth ÷ 27, rounded up per row | dia × depth × 0.95 lb | 10% of sale + $37.50, 20–25% of labor, $8–139 each |
| Block | LF × W" × H" | L×W×H ÷ 3888 × 1.15, plus a floor (L ÷ 4)² ÷ 27, each rounded up | 145 or 55 lb/CY, rounded | 10–20% of sale (+ $4.25 a face SF on a pit), 10–30% of labor, $3–250 each |
| Slab | SF × thick" | SF × thk ÷ 324 | 132.32 lb/CY | 10% of sale or 50–70% of the concrete, 5–15% of labor, equipment as the steel or the supervision |
| Box | L" × W" × D" | L×W×D ÷ 46656 × 1.2 | 66.6 lb/CY, or a ratio of the concrete dollars | $5–25 each, 10–100% of labor, $30 a unit with a $300 minimum |

The slab and box families tax their concrete, steel and forms inline; the
round bases and the blocks forgot to. Three rows price no concrete at all: the
bike rack is an install, the elevator waterproofing a service, the radon pit a
sump.

## What was built (`sql/078`)

* **The eighth takeoff shape:** `misc_items` — a priced item. Code,
  description, unit, quantity, unit sale, labor per unit, sub flag, a shape
  with up to three dimensions, a mix, and the rest of the cost as typed
  allowances: concrete waste; steel per CY, per inch-foot of a round base, or
  per unit; forms as a share of the sale, dollars a unit, dollars a face SF
  and a share of the concrete; supervision as a share of labor; equipment as
  dollars a unit, a share of labor and a minimum. Every knob visible on the
  row instead of buried in 26 formulas.
* **The library** (`misc_item_library`): the tab's 22 named items with their
  dimensions, sale prices, labor and factors. A new miscellaneous section is
  seeded with all of them at no quantity, in four family grids; each grid's
  add button puts the tab's own blank row on it (1305 for the round bases,
  1324–1326 for the boxes).
* **The sale is the typed sale.** The section's sale is the sum of the rows'
  sales, the first shape whose sale is not the cost at the section's markup;
  the cost at that markup shows beside it for comparison, and the margin
  shows as the answer.
* **Concrete and steel** from the shape, priced from the catalog and taxed:
  the steel is the tab's D22 and D24, the piers bar and the paving bar, both
  $0.60. Forms are taxed as the purchase they are; labor, supervision and
  equipment are not, as the tab types them.
* **No forming, labor or equipment line set, no supervision ladder, no rates:**
  every item carries its own, and the three cards stay off the page.

## The exercise, and where the app deliberately differs

The library at these quantities: 10 light pole bases, 20 bollard bases, 4
bike racks, 6 pipe bollards, an elevator pit and its waterproofing, a monument
base, 20 LF of building transformer pad, 2 three-phase pads, 40 LF of gate
track, 4 trellis and 2 gate column footings, a fire pit footing, 40 LF of site
wall footing, 100 LF of landscape curb, a call box footing, a prep counter, a
grill footing, 2 radon pits, 6 stair treads, 12 LF of blockouts, 4 ADA ramps.
Sale $88,340.00, typed. Priced at the LBJ Pricing sheet's mix 1 ($134) and
bar ($0.60), 8.25% tax.

| | Tab | App | Amount |
|---|---|---|---:|
| Round bases | yards rounded up per row, π as 3.145, concrete, steel and forms untaxed | decimal yards, π, every purchase taxed | +$297.13 |
| Blocks | both yard terms and the steel rounded per row, forms rounded up, concrete, steel and forms untaxed | decimal yards, every purchase taxed; the gate track's 10 lb per unit | +$859.31 |
| Slabs | forms as a share of the sale untaxed | taxed | +$23.92 |
| Boxes | forms per unit untaxed; the ADA ramp's steel as a ratio of the concrete dollars | taxed; 211.7 lb/CY | +$4.15 |
| Elevator waterproofing | $2,000 a pit filed under forms | filed under labor, the same $2,200 with its supervision | — |

Golden: **$78,982.63** against the tab's $77,798.11 (+1.52 percent), a margin
of 10.6 percent on the typed sale; held in `tests/misc_fixture.py`, which also
carries the tab row by row (`tab_row`) so `tests/test_misc.py` can check every
item's six pieces against the tab's structure and name the whole gap.

## Left alone

The tab's cost-code columns (130000 + item × 100), its labor sheet split
(75% set-up, 25% clean-up) and its budget names are not carried. Contingency
(14) is not a section.
