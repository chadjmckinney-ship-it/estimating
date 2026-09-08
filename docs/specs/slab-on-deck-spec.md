# Slab on deck — 09-SLAB ON DECK on the mono-slab engine (2026-09-08)

**Source:** the `09-SLAB ON DECK` tab of the LBJ template
(`workbooks/Downloads/Trammel Crow - LBJ Estimate.xlsm`). **No job in the
workbooks folder has priced a slab on deck** — all eighteen workbooks were
scanned, and every 09 tab is the empty template — so there is no bid to
reconcile to. The build follows the template's own cells, and the fixture
exercises them on a takeoff of its own.

**Chad, 2026-09-08:** "ok, lets do slab on deck".

## What the tab is

The `05-Slabs` variant of the mono-slab tab — a rebar slab: the mat, no
support steel, tie steel with a free allowance, a typed superintendent, a
live concrete haul-off — with what a slab on metal deck changes typed in:

| | 05 slabs | 09 slab on deck |
|---|---|---|
| Forming labor | $0.25/SF | $0.05/SF — edge forms only |
| Second labor line | GRADING $0.50/SF | SLAB PREP $0.10/SF |
| Tie steel | $350/ton, first 0.35 lb/SF carried | $350/ton, first 0.45 lb/SF carried |
| Bar | grade-beam bar (Pricing!D23) | PT-slab bar (Pricing!D22) |
| Pump | $10/CY | $20/CY — it is upstairs |
| Form % | 1 | 0.5 |
| Joints | sawn by formula, SF × 2 ÷ 20 | rates typed, no formula — a typed LF |
| Contract line at row 103 | ENGINEERING $0.20/SF | DEMO $1.75/LF |
| Equipment ladder | mini excavator; trencher and skid steer parked | trencher; excavator and skid steer blank |
| Haul-off | $250/load | $500/load |
| Slab cure | $567.50/drum | $225/drum |

Sand is a pour field left blank; the barrier rows carry a 15-mil wrap with a
rolls formula and no switch.

## What was built (`sql/075`)

* **`slab_on_deck` in `DECK_SLAB_KINDS`**, and in `RB_SLAB_KINDS` beside
  `slabs`, so it takes the rebar-slab variant of the engine — the typed
  superintendent, the sawn-joint lines, the tack strips, the haul-off line,
  the 2x10 once around — with a deck's differences on top. No new table.
* **The bar** resolves to the PT-slab item (the tab's G70).
* **The second labor line** is labelled SLAB PREP.
* **The equipment set** parks the excavator and the skid steer, keeps the
  trencher on the ladder, carries DEMO at $/LF where the ground tabs carry
  ENGINEERING, and makes the two joint lines typed rather than computed.
* **Haul-off** looks for a catalog item named for the deck first (any name
  with HAUL OFF and DECK in it), so the tab's $500 a load can be priced
  without touching the ground price; it falls back to CONCRETE HAUL OFF.
* **Rates** seeded from the template and put on every job's price sheet;
  the labor and equipment cards say `09-SLAB ON DECK`.

## The fixture

One 12,000 SF level, 4" thick, #4 at 12" each way, 440 LF of edge, mix 2,
no sand, a 15-mil Yellow Guard, ten superintendent days. Each line is
checked against the template's formula worked by hand; the total,
**$70,873.46**, is held as a regression golden and asserted to be the sum of
its parts. The app's deliberate departures are the same as on every tab:
accessories at the catalog's $0.04, haul-off untaxed, the miscellaneous
uplift, catalog bar weight, and the barrier's lap as poly waste rather than a
1,760 SF roll.

## To settle with a job

The template's cure and haul-off prices differ from the ground tabs'; the
catalog holds one price for each. When a slab on deck is bid, price the
deck's cure and haul-off as catalog items of their own if they really do
cost what the template says.
