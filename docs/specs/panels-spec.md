# Panels — the 12-PANELS tab, a panel type and its count (2026-09-08)

**Source:** the `12-PANELS` tab of the LBJ workbook, as Chad seeded it on
2026-09-08 in `workbooks/Downloads/Trammel Crow - LBJ Estimate.xlsm`.
Twelve panel types, three of each, all 7.25" on mix 5: 36 panels, 30,024 SF,
673.57 CY, 124,024 lb of steel. $411,101.45 cost, $485,099.71 sale at 18
percent, $13.69/SF. Only the twelve rows, the mix slot and the forty
superintendent days are typed on that tab; every rate is the template's.

**Chad, 2026-09-08:** "lets do panels, I can seed a couple of panels real
quick.. ok, its in the LBJ workbook" — and, on the proposal, "yes, but add
more opening fields.. right now we we have to figure total opening size if
more than 1 opening so it is actually short on rebar and lumber for the
openings.. 4 openings total per panel type".

## Where the kind stood

`panels` was a kind in name only: on the section list since `sql/033`, unit
SF, no takeoff table, no line sets, no rates. The tab had read 0.00 on every
workbook in the folder until Chad seeded it.

## What the tab is

One row per panel type: mix, length, thickness, top and bottom elevation, an
opening as L × W, a horizontal mat and a vertical mat each as a spacing, a
size and a count of mats, edge bars and corner bars each as a count and a
size. Hidden columns to the right roll the type up — CY by mix, steel, SF,
panels, perimeter, bottom LF, 2x6 and 2x8 by thickness — and spread every
shared cost back onto it by SF, so the tab can show a cost per panel.

| | Columns (07) | Panels (12) |
|---|---|---|
| Takeoff | a type and a count, measured in EA | a type and a count, measured in SF |
| Area | form contact, all four faces | L × H, **gross** — openings come off the concrete, not the area |
| Steel | verticals, ties, dowels | two mats at a spacing, edge bars, a set more per opening, corner bars |
| Labor $/SF | 2.50 / 1.25 / 0.50 / 0.25 on form SF | 0.35 / 0.65 / 0.25 / 0.85 on panel SF, tie steel $450/ton, backfill $8/CY |
| Supervision | 20 columns a week, five-day week | **typed** (D88); a foreman for every day (D89 = D88), no PM |
| Ladder | sky track, hoist, skid steer, storage | sky track, mini excavator, skid steer, compactor, misc; trencher parked |
| Lumber runs off | form SF | the formed perimeter × 40%, the bottom LF, the panel count, gross SF |
| Along the bottom | — | carton forms at $1/LF × 1.10, durrock both sides at $1.80, a backfill trench 6.5 × 2 ft |
| Contract | pump, cure, saw, haul-off | pump $20/CY, **engineering $90 per type**, waterproofing, saw, haul-off |

## What was built (`sql/077`)

* **The seventh takeoff shape:** `panel_types` — a panel type and its count.
  Stored per row: height, SF each, SF, opening SF and LF, perimeter LF,
  bottom LF, concrete CY, steel per panel and total. Sold per SF and
  allocated by SF; cost per panel on the totals and on the row.
* **Four opening slots per type** where the tab has one. Each opening comes
  off the concrete ((L × H − openings) × thickness ÷ 324), adds one more set
  of the panel's edge bars, and puts its perimeter on the formed edge the
  lumber and the chamfer run off.
* **The steel is the tab's column U** with catalog bar weights: L × H × 12 ÷
  spacing × mats × lb/ft for each mat, (n × L + n × H) × 2 × lb/ft for the
  edge bars, the same set again per opening, n × 4 ft × lb/ft for the corner
  bars, 5 percent waste on every bar. `sheet_mode` swaps the tab's constant
  back in for reconciliation.
* **Labor** per gross SF, tie steel per ton of every pound, the brick ledge
  per LF typed, backfill per CY of bottom LF × 6.5 × 2 ÷ 27. The tab marks
  every labor row as sub; the section's one switch shows on the page.
* **Supervision typed**, foreman and expense following the superintendent,
  and the equipment ladder riding those days.
* **Rates** from the tab on the assembly table and every job's price sheet:
  two new prices (panel engineering per type, the compactor's day rate at the
  job level) and nine new rules (the backfill trench, the 2x10 per bottom LF,
  stakes per 100 LF of 2x8, 8p as 0.6 of 16p, lifting and bracing inserts per
  panel, bond breaker coverage, the 2x6/2x8 split at 6", the corner bars'
  4 ft).
* **The grid** with the four openings, the two mats and the two bar sets;
  stat cards for panels, SF, concrete, steel, the formed edge, the bottom LF,
  cost and sale per SF and per panel; the cards say 12-PANELS.

## Where the app deliberately differs from the tab

| | Tab | App | Amount |
|---|---|---:|---:|
| Opening steel | `Q×D + Q×H×2×w` — a dropped bracket, `Q×D` as bare pounds | `(Q×D + Q×H)×2×w`, once per opening | +2,383.7 lb |
| Bar weight | (size/16)² × 10.7028 | the catalog's 0.668 and 1.043 lb/ft | −235.2 lb |
| The steel, net, with its tie labor and accessories | | | **+$2,088.13** |
| Opening lumber | none | 936 LF of blockout on the 2x4, the 2x8, the stakes and the chamfer | +$1,368.76 |
| 2x10 | D52, the sum of the type lengths (347 LF) | per bottom LF (1,041) | +$821.69 |
| Miscellaneous equipment | flat days × rate | fuel and tax, as everywhere | +$366.98 |
| Lumber prices | eight places | the catalog's four | +$0.14 |
| Bond breaker | 2.7295 drums | 2.729 | −$0.34 |
| Mini excavator, compactor | typed 425 and 125 | the catalog's 475 and 200; the fixture states the tab's | — |

Golden: **$415,746.83** against the tab's $411,101.45 (+1.13 percent), held
in `tests/panels_fixture.py`; `tests/test_panels.py` holds each row above,
the tab's steel reproduced to the pound in `sheet_mode`, and the four-opening
case.

## Left alone

The tab's ply, anchor bolts, keyway, wall ties, reveal, bracing,
turnbuckles, bolsters and smooth dowels sit at zero, typed when a job has
them. The reveal has no catalog item and prices as the tab types it until one
exists. Miscellaneous (13) is the section still unbuilt.
