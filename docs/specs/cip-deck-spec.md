# CIP elevated deck — specification

**Status:** 2026-09-04. **Reconciled, decided and BUILT.** Every formula below
was read out of the sheet and its numbers reproduced before a line of code was
written; the five open questions at the end were put to Chad and answered; the
assembly ships as `sql/052`, `services/cip_deck.py`, a grid screen and 33
tests. The answers, the golden number and everything found on the way are in
**"Answered, 2026-09-04"** at the bottom.

**Source:** `08-CIP EL. DECK` in
`C:\Users\Chad\Estimate_Projects\workbooks\Downloads\Trammel Crow - LBJ Estimate.xlsm`.
The most filled-in of the unbuilt tabs (~1,099 cells).

**Sheet totals — and they reconcile from their own parts, exactly:**

| | |
|---|---:|
| Deck area | **32,100 SF** (level 2 = 10,447 · level 3 = 21,653) |
| Cost | **$952,052.02** |
| Sale (cost + 18%) | **$1,123,421.39** |
| Cost / SF | $29.6589 |
| Concrete | 1,459.8519 CY, all 5000-ASH |
| Steel | 61,715.46 lb (30.8577 tons) |
| PT | 32,100 SF, 36,915 lb of cable |

Summing the sheet's own nineteen cost columns (`BJ50:CC50`) gives
**$952,052.0214** against the stated $952,052.0215 — a tenth of a cent of
float. The model is understood, not guessed at.

---

## Why this one is different

The five built assemblies are all ground-bearing. This is the first that hangs
in the air, and that shows up in four places nothing else has:

1. **Labor can be subcontracted, line by line.** Column C on each labor row is
   `Y`/`N`, and it routes that line's money to one of two buckets:

   ```
   K{r} = IF(C{r}="N", rate × driver, 0)     our crew
   N{r} = IF(C{r}="y", driver × rate, 0)     the sub
   ```

   On LBJ **all ten lines are subbed** — $251,654.73 — and the own-crew column
   is zero throughout. There is a whole `SUB LABOR SHEET` tab fed by hidden
   per-level columns (`CP:CT` — name, drops, rebar weight, PT weight, SF).

2. **Shoring and reshoring**, which only exist because there is nothing
   underneath. Form rental shoring $1.25/SF × 1.1, a reshoring material line,
   and reshoring labor at $0.35/SF.

3. **A crane.** $3,200/day × 27 billable days = **$136,728** with fuel and tax
   — 14% of the section on one line, and by far the largest single equipment
   figure anywhere in the app.

4. **Post-tension priced by the square foot, with a quote slot already in the
   sheet:**

   ```
   N80 = IF(I80 = 0, SF × $1.45, I80) × tax
   ```

   `I80` is a supplier quote that replaces the computed figure — which is
   exactly what `section_quotes` does (sql/039). The PT quote lands there
   rather than in a new column.

---

## The takeoff

### Deck levels — rows 8–49

| Column | | LBJ level 2 |
|---|---|---|
| A | CIP EL. DECK TYPE | "level 2" |
| C | SQUARE FOOTAGE | 10,447 |
| E | THICK INCH | 14 |
| F | CABLE y/n | y |
| G | MIX DESIGN # | 8 (5000-ASH) |
| H | PERM. EDGE LF | 628 |
| I / J | TOP REINFORCING size / space | #4 @ 10" |
| K / L | BOTTOM REINFORCING size / space | — |
| M | SQ FT WIRE MESH | — |
| N/O · P/Q · R/S | up to three grade-beam TYPES and their LN FT | type 1 × 30 LF, type 2 × 45 LF |

The sheet gives every level **two rows** and sums concrete and steel across the
pair (`U10 = (C10×E10/324 + C11×E11/324) × …`). Row 11 holds only `A11='l'` on
this job. See question 1.

### Grade beams on the deck — rows 52–62

A schedule, like the columns one: beam #, width in, height in, top bars
(#/size), bottom bars, mid bars, stirrups (size/spacing), "L" bars
(size/spacing/length ft). Three derived rates per beam type, which the levels
then multiply by their LN FT:

```
O   lb per LF   = top# × (size/16)² × 10.680159
                + bot# × (size/16)² × 10.680159
                + mid# × 2 × (size/16)² × 10.680159
                + stirrups:  (size/16)² × 3.145 × 0.2836 × (2W + 2L)″ × 12/spacing
                + L bars:    (size/16)² × 10.680159 × (12/spacing) × length ft
                  … all × (1 + waste_rebar)
Q   CY per LF   = (width/12 × height/324) × (1 + waste_concrete)
U   face ft/LF  = height / 12                          ← ONE face; question 2
```

LBJ: beam 1 = 18×24 with 4 top / 4 bottom, **56.6982 lb/LF**, 0.1156 CY/LF;
beam 2 = 24×24 with 5 top / 5 bottom, **63.4553 lb/LF**, 0.1541 CY/LF.

---

## Geometry, as the sheet computes it

```
slab CY     = Σ(SF × thickness_in / 324) × (1 + waste_concrete)  +  beam CY
beam CY     = Σ over the level's 3 beam slots:  LN FT × (CY per LF)

slab rebar  = for EACH mat (top, bottom), where s = spacing in inches:
                (2 / (s/12)) × SF × (size/16)² × 10.6870159 × (1 + waste_rebar)
beam rebar  = ROUNDUP(Σ LN FT × lb per LF) × 1.12       ← 12% on beams only

PT cable lb = SF × 1.15
PT SF       = SF where cable = "y"
GB form ff  = Σ LN FT × (height / 12)
```

`(2 / spacing_ft) × area` is LF of bar for a two-way mat — the standard rule.
The sheet writes it as `(s/12 + s/12) / (s/12 × s/12) × area`, which is the
same thing the long way round.

**Two constants for one thing.** The deck's slab mats use `10.6870159`; the
beam schedule on the same tab uses `10.680159`, the columns constant. A #4 bar
is 0.668 lb/ft, and `(4/16)² × 10.68 = 0.6675`, `× 10.687 = 0.6679`. Both are
approximations of the same ASTM weight and they disagree in the fourth decimal.
The app uses the catalog's `bar_lb_per_ft`, as columns and piers already do.

---

## Rates and line sets

### Materials

| Line | Driver | LBJ |
|---|---|---|
| Concrete | CY by mix × mix price × tax | $276,550.69 |
| Steel | total lb × $0.65 × tax | $43,424.54 |
| PT cables | SF × $1.45 × tax, **or a quote** | $50,384.96 |
| Stud rails | lb × $1.65 | $0 |
| Carton forms | SF × $0.85 | $0 |
| Plywood forming | SF × **0.5 coverage** × **$1.50** × tax | $26,061.19 |
| Reshoring | SF × rate × **1.1** | **$0 — the rate cell is blank** |
| Form rental shoring | SF × $1.25 × **1.1** × tax | $47,778.84 |

The `1.1` on the last two is **one cell, `J83`, read by both**. It is labelled
under reshoring and silently reused by form rental shoring — a shared
multiplier with two meanings, and the kind of thing that moves $4,300 when
somebody edits it for one of the two reasons it exists.

### Lumber and accessories — the familiar sidebar, $11,029.92

Same shape as every other assembly (`Q/S/U/W`, rows 73–118), driven off
`perm edge LF + GB form ff` = 1,924:

```
2x4 x 16'      1,924 LF @ $0.8594        2x6 x 16'   1,924 LF @ $1.4453
2x10 x 16'     384.8 LF @ $1.0938        3/4" ply    30.0625 sheets @ $74.75
stakes         7.5 bundles @ $24         16p nails   2 boxes @ $68.20
8p / 6p        1 box each @ $68.20       PAVECRETE   26.75 bags @ $15
SLAB CHAIRS    3 bags @ $27              ACCESSORIES 61,715 lb @ $0.02
SLAB CURE      2 drums @ $567.50
```

`ACCESSORIES` at **$0.02/lb** is the same typed-over cell sql/044 found on
paving and columns; the catalog says $0.04. And PAVECRETE is a real material
the catalog did not have — sql/052 adds it, at $15/bag, rather than reaching
for PATCH MATERIAL at $45 by name (which is exactly how the columns CHAIRS
line ended up buying METAL CHAIRS).

### Labor — all ten lines, all subbed on this job

| Line | Rate | Driver | LBJ |
|---|---|---|---|
| FORMING | $4.75 | SF | $152,475 |
| PLACE AND FINISH | $0.50 | SF | $16,050 |
| WRECK AND CLEAN | $0.45 | SF | $14,445 |
| RESHORING | $0.35 | SF | $11,235 |
| EDGE / SAFETY RAILS | $6.00 | 1,684 LF perm edge | $10,104 |
| GB FORMING | $6.00 | 240 FF | $1,440 |
| RUB & PATCH | $0.25 | SF | $8,025 |
| STUD RAILS | $500 | ton | $0 |
| CABLE PLACEMENT | $0.65 | 36,915 lb (SF × 1.15) | $23,994.75 |
| TIE STEEL | $450 | 30.8577 tons | $13,885.98 |
| | | | **$251,654.73** |

`G87 = $6.05/SF` looks like an input and is **derived** — the blended rate of
the first four lines over the deck area. It then drives the per-level
allocation. Not seeded.

### Supervision — TYPED, like piers and walls

60 days each for superintendent ($425), foreman ($250), expense ($100) and
PM ($200) = **$58,500**. Nothing derives them from area or count, so this
assembly inherits the untyped-supervision warning built for audit #5.

### Equipment — the ladder the app already has

`60 typed super days → 90 equipment days` by the additive band ladder, then
`→ 27 billable` by the rental tier. Both are `equip_days_from_super` and
`rental_billable_units` unchanged.

| | Days | Rate | LBJ |
|---|---:|---:|---:|
| 20 TON LIFT | 0 | $850 | $0 |
| CRANE & OPERATOR | 27 | $3,200 | **$136,728** |
| SKID STEER | 27 | $325 | $13,886.44 |
| LIGHT TOWER | 27 | $100 | $4,272.75 |
| SKY LIFT | 27 | $380 | $16,236.45 |
| MISCELLANEOUS | 27 | $35 | $945 |
| | | | **$172,068.64** |

Each carries `× (1 + tax + 50% fuel)` — **except MISCELLANEOUS**, whose
formula ends without the multiplier. That is the fifth time this quirk has
turned up (slab, piers, walls, columns, now deck): the sheet exempts one
line and the app treats it as an ordinary rental.

### Contract services

Engineering $1.05/SF, saw cutting $2.50/LF, **concrete pumping $10/CY =
$14,598.52**, freight $1,100/load, waterproofing $2.25/SF, out-of-town $225/day,
barricades $1.45/LF. Only pumping has a quantity on this job.

### Allocation basis: SQUARE FEET

Every shared cost spreads by deck area (`BU:BY` all divide by `C50`), and the
section's unit is SF. Same as the mono slab, unlike columns (form SF) or walls
(form feet).

---

## Bugs and traps found while reading

**1. `BD` is labelled TOTAL and used as MIX #10.** The mix-CY columns run
`AT`=mix 1 … `BC`=mix 10 by header, but the lookup in `K73:K77` reads
`IF(A=9, BC$50, IF(A=10, BD$50))` — off by one against the headers, and `BD`
itself is `SUM(AT:AY)`, only mixes 1–6. **A job on mix 9 or 10 picks up the
wrong column, and one of them is a partial sum of six other mixes.** Same
class as the paving `SUM(W10:X41)*3` bug. LBJ is on mix 8 and unexposed.

**2. Beam types 4–10 resolve to different rows in different columns.** Steel
maps type 4 to schedule row 56; form feet maps type 4 to row 60. And the
7–10 branches are nested INSIDE the `=6` branch in every one of them, so a
level on beam type 7 gets nothing at all.

**3. Cost codes mislabelled, again.** `80043 Labor Drops` is actually
reshoring + edge rails + GB forming; `80046 Labor Burden` is rub & patch;
`80061 SkyTrack` is the sky lift. The standing rule holds — **read the rate
block, not the label.**

**4. The reshoring material rate is blank**, so that line prices at $0 while
its labor prices at $11,235.

---

## Open questions — these change the takeoff, not a rate

1. **The paired rows.** Every level occupies two rows (10/11, 12/13 …) and
   concrete and steel sum across both. Row 11 is empty on LBJ. Is the second
   row a second pour area on the same level, a different thickness, or dead
   weight from the sheet it was copied from?

2. **Grade beam face feet = height / 12 — one face.** A 24" beam over 30 LF
   gives 60 FF, where forming both sides would be 120. Is a deck grade beam
   formed on one side only (the other being cast against the deck form), or
   is the sheet light here?

3. **Sub-vs-own labor.** The sheet decides it per line. Is that real — would
   you ever sub the forming and self-perform the tie steel — or is it in
   practice one switch for the whole section?

4. **Reshoring material at $0.** Blank rate, deliberate, or a price that
   never got typed?

5. **Stud rails.** Zero on this job, $1.65/lb and $500/ton of labor when used.
   Real line to keep, or furniture like the columns cure and saw cutting?

---

## Answered, 2026-09-04 — and built

All five went to Chad. Four came back as choices; the fifth never got asked
(the question tool caps at four) and was decided by the rule the app already
has.

| | Question | Answer |
|---|---|---|
| 1 | The paired rows | **"Dead weight from the source sheet."** One row per level. |
| 2 | Grade beam face feet | **"Both faces — the sheet is light."** `height/12 × 2`. |
| 3 | Sub vs own labor | **One switch per section.** Per-line stays possible later; the flag lives on the line, not just the section. |
| 4 | Reshoring material at $0 | Not asked. A blank rate is **unpriced**, not free (decision 5) — the section reports it, and the labor for the same work still bills $11,235. |
| 5 | Stud rails | **"Real — keep it."** A per-level `stud_rail_lb`, a material line at $1.65/lb and a labor line at $500/ton. |

Shipped as `sql/052_cip_deck.sql`, `services/cip_deck.py`,
`models/deck_level.py`, `schemas/deck_level.py`, `routers/deck_levels.py`, the
deck grid on the section page, and `tests/test_cip_deck.py` +
`tests/test_cip_deck_ui_contract.py` (33 tests; suite **549 green**).

### The biggest bug on the tab, and it is live

**`AM` reads the wrong column.** Beam slot 1 (`AL`) reads column O, lb per LF.
Slot 2 (`AM`) reads column **Q**, which is **CY per LF**. Slot 3 (`AN`) reads
column **S**, a header cell.

So LBJ's level 2 is charged **7 lb** for a 45 LF type-2 grade beam that weighs
**2,855.49**, and a third beam on any level is free.
`AO10 = (1701 + 7 + 0) × 1.12 = 1,912.96`, which is exactly what the sheet
holds. **+3,190.88 lb**, about **$2,247** of steel and **$719** of tie-steel
labor.

There are no slots in the app. A level holds as many beams as it holds.

### Two more, neither exposed on LBJ

* **`K83`, reshoring SF, is a hand-picked list of rows** —
  `C10+C12+C14+C16+C22+C24+C28`. It skips 18, 20, 26 and everything past 28,
  so a level entered on one of those is reshored for free.
* **`K95`, own-crew cable placement, reads row 100**, which is blank. The sub
  column is right; self-perform cable placement on the sheet and it charges
  $0 — **$23,994.75** on this job.

## The golden number

    952,052.02   the sheet
     + 2,247.26   steel the beam slots dropped
     +   718.59   tie-steel labor on that steel
     + 1,440.00   GB forming labor, both faces
     + 1,013.75   lumber on the doubled beam faces (+ tax on PAVECRETE)
     +   550.46   MISCELLANEOUS taxed and fuelled like the rental it is
     + 1,676.58   ACCESSORIES at the catalog $0.04, and tax on four lines
                  the sheet leaves untaxed
     - 3,513.21   bar at the PT-slab price ($0.60), not the grade-beam price
    -----------
    956,185.45   sale $1,128,298.83 at cost + 18%

Every line of that has its own test. Under `sheet_mode` the concrete
reconciles to the sheet **exactly** (1,459.8518 CY), and so do the slab mats
(56,603.78 lb) and both beam schedule rows (56.6982 and 63.4553 lb/LF) — which
is what makes the differences above arguable rather than guessed at.

## Three prices this section raises

* ~~**The crane.**~~ **Settled, 2026-09-04.** Chad: *"$3,200/day is again
  someone editing the tab instead of the price sheet, and is current daily
  price."* So the CATALOG is the thing that is wrong, not the tab — it carries
  CRANE AND OPERATOR at $2,400. Fix is one field on the Equipment screen. The
  fixture already states $3,200, so nothing in the tests moves; existing price
  sheets stay frozen and report it as drift until pulled.

  It also produced sql/053: settling the crane is what surfaced that **nothing
  in the workbook prices getting it to the job.** See `docs/specs/mobilization.md`.
* **The bar.** The `-$3,513.21` above. The sheet points `F78` at REBAR GRADE
  BEAM ($0.65); the app resolves the catalog row named for exactly this case,
  REBAR PIERS / PT slabs ($0.60), the way sql/043 already resolves a
  post-tensioned slab.
* **Reshoring material.** No rate anywhere. Unpriced until one is typed.

## One live bug found on another screen

`wallColumns`' Backfill column is declared `type: "checkbox"` where
`gridRowHtml` expects `type: "check"`. An unrecognised type falls through to
the TEXT branch, so **Backfill has rendered as a free-text box reading "true"
since sql/040** — it round-trips (Pydantic coerces the string) and lets you
type anything into it. Fixed in the same change as the deck's PT column, which
had the same typo before it shipped.

## Still open

* **13-Miscellaneous, 05-Slabs, 09-SLAB ON DECK, 12-PANELS, 14-Contingency.**
* Four sheets that may just be extra wall-kind sections: 03-Walls & Footings,
  06-Footings, 06-Garage Walls & Footings, 06-Garage Footings.
* The `SUB LABOR SHEET` tab itself — the level-by-level breakdown the sub is
  handed. The data is all stored now (`subcontracted` on every labor line, and
  the levels underneath it); nothing renders it yet.
