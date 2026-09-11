# eTakeoff bid codes: the coded template (2026-09-10)

**Source:** Chad, 2026-09-10, on the eTakeoff importer: "we can build a
bidcode file that I can import and them assign to each item... then there is
no way to screw it up... I wonder if you can read my template file with all
the prebuilt items" — and, on the plan, "yes". The template is
`Rev Template 2026-09-10.itt` (OneDrive root), the whole Quantity Worksheet
tree of eTakeoff Dimension saved from its top node with "Save Tree Branch as
Template…": 18 breakdowns that mirror the workbook tabs, 891 items, 691 with
a trace, 11 extensions. (A July file of the same name was a branch saved
earlier: 872 items, without the CIP deck's levels 2 to 5 or the metal deck's
areas 2 to 4, and with garage beam and pier sizes and a WALLS group that have
since been removed.)

## The idea

Every project Chad starts is copied from this template. If every measurable
item in the template carries the bid code the app expects, every Quantity
Worksheet item in every future project carries it too, the worksheet drags
out with it, and the importer (`docs/specs/etakeoff-import.md`, next) keys
on it with nothing to guess. The codes are the ones already in his projects —
`MonoSlabBld1Pour01`, `MonoSlabIntGBBld1Pour01`, `Footings-F01`, `WallSec01`,
`PavingHeavyDuty` — with the gaps filled in the same style.

## What was built

* **`backend/app/services/etakeoff_template.py`** — reads the `.itt`
  (a `Name{ … }` / `Name("value")` text, one field per line, CRLF), decides a
  code for every measurable item, and writes the file back with **only the
  `BidCode` values changed**: every other byte is the office's. `recode()`,
  `bid_code_rows()`, `review()`, `expected_layer()`.
* **`backend/etakeoff_template.py`** — the command. Writes three files beside
  the template (or into `--out-dir`): `<name> - coded.itt`,
  `<name> - bid codes.csv` (code, description; no header row, the two
  columns Dimension's Standard Bid Code List pastes), `<name> - code
  review.md` (what was kept, added and changed; what to look at; the layers
  and descriptions to straighten).
* **`backend/tests/fixtures/etakeoff/Rev Template 2026-09-10.itt`** — the
  template as the test fixture; `.gitattributes` keeps `.itt` bytes as they
  are.

## What is measurable

An item gets a code when a measurement can land on it: not a breakdown
header, not a hand-typed number (`N`), not a formula without a trace (the
`Perimeter` and `TOTAL PER & INT GB` rows), not an item with neither a type
nor a trace. Formula items that carry a trace — `Heavy Duty/Firelane`,
`Light Duty` — are measured and coded. Groups such as `COLUMNS` and `PIERS`
are not.

## The codes

| Breakdown | Code | Example |
|---|---|---|
| `05 MonoSlab Wrap Bld N` | `MonoSlab` + role + `BldN` + `PourNN` (`PourLO` for the leave-outs) | `MonoSlabIntRBBld2Pour03`, `MonoSlabBld1PourLO` |
| `05 Mono Slab Garden Style` | `MonoSlab` + role + `TypeNN`, or `Type` + the name for a named type | `MonoSlabDropType04`, `MonoSlabBrickType02`, `MonoSlabTypeClubhouse` |
| depth-coded drops and exposed beams | `MonoSlab` + depth + `Drop`/`EXP` + scope | `MonoSlab06DropBld2Pour01`, `MonoSlab24EXPBld2Pour01` |
| keyways | `MonoSlabKeywayBldN`, `MonoSlabKeywayGarden` | |
| `06 Footings`, `09 Garage Footings` | `Footings-FNN`, `GarageFooting-FNN` | |
| `06 Walls`, `09 Garage Walls` | `WallSecNN`, `GarageWallSecNN` | |
| `01 PIERS`, `02 COL` | `PierPNN`, `Column` + type | `PierP01`, `ColumnTypeA` |
| `03 SLAB ON METAL DECK`, `04 CIP DECK` | `Deck…`, `CIPDeck…` | `DeckArea04`, `CIPDeckLevel03GB02` |
| `07 PAVING`, `07 ROW PAVING` | `Paving…`, `ROWPaving…` | `PavingFirelane`, `PavingTurnLaneMedian`, `ROWPavingApproachCurb` |
| `08 SIDEWALK`, `08 Courtyard Hardscape` | `Sidewalk…`, `Courtyard…` | `SidewalkADARampsCity`, `CourtyardBroom` |
| `09 GARAGE SOG` | `GarageSOGCol…`, `GarageSOGGB…`, `GarageSOGPier…`, `GarageSOGPierCap…` | `GarageSOGColC01`, `GarageSOGGBS01`, `GarageSOGPierP07` |
| `MISC` | `Misc…` | `MiscLightPoleBases`, `MiscArea` |

The roles on a mono slab, in Chad's words (2026-09-10): `IntGB` interior
grade beam, `IntRB` interior rebar beam, `TKND` thickened beam, `Drop` drop
beam, `EXP` exposed grade beam, `Stem` stem wall, `Brick` brickledge.

A code is letters, digits and hyphens. A label becomes a code fragment by
running its words together, keeping `ADA`, `GB`, `CMU` and the like, and
padding a bare single digit (`Wall 1` → `Wall01`, `C1` → `C01`, `GB2` →
`GB02`, `18 x 36` → `18x36`). Codes must be unique; a second item on the
same code is marked `-DUP2` and named in the review, because two items on
one code is a template defect, not something to paper over.

## What the template held, and what changed

891 items; 725 coded — 340 kept as they were, 135 added, 250 changed; 166
not measurable. Every changed code has one of these reasons, and the test
pins the count of each:

* **146** items under `05 MonoSlab Wrap Bld 2` were coded for building 1
  (`MonoSlabIntRBBld1Pour05` under Building 2's Pour 05).
* **36** duplicates, marked `-DUP2`: the whole of `06 Garage Walls`
  duplicates `09 Garage Walls` (09 is the maintained one and keeps the clean
  codes), Building 2 has both a `Bld 02 Pour 01` and a `Bld 02 Pour 1`,
  Building 1 has two leave-out items, and the garage piers list `P1`/`P2`
  beside `P01`/`P02`.
* **22** garage piers carried a bare `P01`…`P22`, which the piers tab's own
  `P1`…`P4` would collide with; they are `GarageSOGPierP01`… now.
* **14** items under `Bld Type 01` and `Bld Type 02`, which were re-created
  as copies of `Bld Type 03` and still carried its `Type03` codes.
* **13** items under two named building types, `Clubhouse` and `Trash
  Enclosure`, which came into the template from a job carrying the old
  `Type01` and `Type02`. They are `MonoSlabTypeClubhouse` and
  `MonoSlabTypeTrashEnclosure` now.
* **12** children were coded for the neighbouring pour (Pour 02's `INT RB`
  as `…Pour01`, Pour 03's as `…Pour04`).
* **7** Building 1 leave-out items were coded as Pour 18; they are `PourLO`.

The review also names, for a person to fix in Dimension: four traces that
point at a numbered sibling (`F16 Footings` on the F15 trace, `P15` on P14,
`P22` on P21, Building 2's `Pour 1` on Building 1's trace); two typeless
leftovers under Clubhouse; four breakdown headers carrying a trace.

## Layers and descriptions

Chad, 2026-09-10: "there is a lot I need to straighten up in it.. like the
layers... some items have bad descriptions". The review's **Layers to
straighten** table lists every item whose default layer is not the one its
family uses — pours on `04 Slab`, the beam roles on `04 GradeBeams`, stem
walls and brickledges on `04 Walls`, footings on `04 Footings`, walls on
`04 Walls`, piers on `01 piers`, columns on `03 Columns`, paving on
`03 Paving`, walks on `10 SIDEWALK` — 229 rows on this export, 210 of them
the Wrap buildings' beam and wall items sitting on `Sidewalks`. Decks and
MISC have no convention and are not judged. The **Descriptions** table lists
the 152 items that carry one, so the stale ones are in one place.

## How Chad uses it

1. Read `Rev Template 2026-09-10 - code review.md`; straighten what he wants
   straightened in Dimension (the coded file deletes and renames nothing).
2. Paste `Rev Template 2026-09-10 - bid codes.csv` into Dimension's Standard
   Bid Code List, so any item he adds later picks from the same set.
3. Import `Rev Template 2026-09-10 - coded.itt` as the item-tree template on
   a scratch project first; when it opens as his template did, with the codes
   on the items, make it the template. After any clean-up, save the tree from
   the top again and re-run the command: it takes seconds.
4. Drag the Quantity Worksheet of that scratch project out as values, with
   Breakdown Code, Description, Bid Code, Quantity and unit showing: that is
   the sample the importer is built against.

## Tests

`backend/tests/test_etakeoff_template.py`: the fixture reads as the tree
Chad keeps (18 breakdowns, 891 items, 691 traced, 590 coded); the output
differs only in BidCode values and keeps its CRLF, and reads back item for
item; every measurable item is coded once and the counts are pinned; the
families in use are kept, depth-coded beams included; the gaps are filled in
the same style and a named type keeps the family; every changed code has a
named reason with its count; the slips are fixed and named; the layers and
descriptions to straighten are listed; the code list is two columns without
a header; a small synthetic template round-trips its bytes, escapes and
CRLF; a duplicate code is flagged.
