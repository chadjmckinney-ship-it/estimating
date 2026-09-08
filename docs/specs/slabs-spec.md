# Slabs — 05-Slabs on the mono-slab engine (2026-09-07)

**Source:** `05-Slabs` on the Pearl Landing Podium estimate
(`workbooks/Pearl_Landing/Podium Estimate.xlsm`): 56,522 SF, $349,626.42
cost, $419,551.70 sale, $7.42/SF. The LBJ workbook's tab is an empty
template; its typed rates are the assembly's defaults.

**Chad, 2026-09-07:** "ok, lets do slabs".

## What the tab is

The `04` mono-slab tab, cell for cell, used for a **conventional (rebar)
slab on grade**. The pour row is the same — SF, thickness, sand, perimeter,
a mat as a bar size at a spacing, a mix — and so are the lumber block, the
vapor barrier, the supervision block and the equipment ladder. What the tab
types differently is what makes it a kind of its own:

| | 04 mono slab | 05 slabs |
|---|---|---|
| Steel | PT-slab bar (Pricing!D22) | grade-beam bar (Pricing!D23) |
| Tie steel | $450/ton | $350/ton, the first 0.35 lb/SF carried (U10) |
| Support steel | 0.1 lb/SF allowance | none — P10 is the mat and its waste |
| Sand | with waste | without (K73 blank) |
| Labor $/SF | 0.45 / 0.70 / 0.55 / 0.20 | 0.25 / 0.50 / 0.50 / 0.20 |
| Joints | none | sawn at 20 ft both ways, $0.55/LF; sealant a switch at n |
| 2x10 | twice around the perimeter | once |
| Form % | 0.7 | 1 |
| Pump, haul-off | $16, $12.50 | $10, $12 |
| Superintendent | SF ÷ 16,000 × 7 | typed (E91 is a cell) |
| Concrete haul-off | blank cell | CY ÷ 300 loads, live (V97) |
| Trencher, skid steer | on the ladder | 0 days, blank |

## What was built (`sql/074`)

* **`slabs` in `RB_SLAB_KINDS`** on the mono-slab engine. No new table: the
  pours are `mono_slabs` rows, the kind was already in `SECTION_KINDS` and
  the kind check.
* **A typed superintendent.** The labor drivers read the stored line, the
  way walls and beams do; the equipment ladder rides it.
* **The equipment set** parks the trencher and the skid steer, and adds
  SAW CUTTING (SF × 2 ÷ spacing × $/LF) with SAW JOINT SEALANT beside it,
  off until switched on. One new rule, `saw_joint_spacing_ft`.
* **The lumber block** runs the 2x10 once around, carries TACK STRIPS with
  the redwood, and hauls the concrete spoil by the tab's live formula.
* **Rates** seeded from the template and put on every job's price sheet.
* **The labor and equipment cards** say `05-SLABS`.

## Where the app deliberately differs from the tab

| | Tab | App | Amount |
|---|---|---|---:|
| Accessories | typed $0.02/lb | the catalog's $0.04 (sql/044), taxed | +$1,013.01 |
| Miscellaneous equipment | flat days × rate | fuel and tax, as everywhere | +$288.34 |
| Bar weight | (3/16)² × 10.6870159 | the catalog's 0.376 lb/ft | +$24.90 steel, +$6.18 tie labor |
| Concrete haul-off | taxed with the lumber | a service, untaxed (sql/036) | −$68.42 |
| Lumber, concrete, barrier | — | four-decimal prices, per-line cents | +$0.10 |

Golden: **$350,890.51**, held in `tests/slabs_fixture.py`;
`tests/test_slabs.py` holds each row above.

## Left alone

The template leftovers with junk references or blank prices (cover sheets,
carton forms under the slab as a switch at n, form release, keyway and
chamfer at zero). Slab on deck (`09`), panels (`12`) and miscellaneous (`13`)
are the sections still unbuilt.
