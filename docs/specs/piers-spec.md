# Piers — specification, and what got built

**Status:** built and tested, 2026-08-31. `sql/037_piers.sql` needs applying —
`run.cmd` warns about it.

**Source:** `01-Piers` in the LBJ workbook, every formula re-derived against its
own numbers.

**Target:** 106 piers, 2,348 LF, **$295,601.21** cost / **$348,809.43** sale at
18%, taxable at 8.25%. The app reads **$297,204.52**, +0.54%, accounted for
below.

---

## The finding that mattered most: piers do not fit `mono_slabs`

Paving fitted because a paving area **is** a pour. A pier is not: its unit is
EA and it has no square footage at all.

That is not a modelling nicety. `refresh_pour_costs` spreads every shared
cost — forming, labor, equipment — across a section's rows **weighted by SF**,
and `allocate_amount` falls back to "the last row takes the remainder" when
every weight is zero:

```python
if total_w <= 0:
    out = [_ZERO] * n
    out[-1] = amount        # everything lands on the last row
```

A piers section run on the SF basis would have put the **entire** $58,000 of
takeoff cost on whichever group sorted last, and reported a per-pier cost that
was nonsense for the other five. No error. Nothing wrong on screen.

So costing now has an **allocation basis per assembly**:

```python
def allocation_basis(kind):
    return "EA" if kind in PIER_KINDS else "SF"
```

and works on a uniform `_Unit` — a pour on a slab, a group on a piers section —
carrying a weight, a CY figure, a taxable and an untaxed direct cost, and where
to write the answer. That is the piece that makes assemblies four and five
cheap instead of another special case.

The test that guards it: two of LBJ's six groups are the same pier in different
quantities — 12 and 4 shafts, both 24" × 21'. Priced per pier they must come
out identical, and three times the piers must cost three times as much.

## A near-miss worth keeping

The tie formula on the sheet reads as a units error: it multiplies a hoop
circumference in **inches** by a depth in **feet** divided by a spacing in
**inches**. There was $115,301 of "missing" pier steel written down before it
was checked. The two twelves cancel exactly:

```
sheet:  (M/16)² × 10.68 × ((F−3) × π) × J / N
honest: lb/ft × (F−3)×π/12 ft hoop × J×12/N ties     identical, to the digit
```

Verified on the 46-pier group: 4,296.936 lb either way. It is written the
honest way in `services/piers.py` with a comment saying why it agrees with a
sheet that appears to be wrong, and there is a test — otherwise someone
"corrects" it in a year and adds 106,743 lb of steel that is not there.

## The cage — what changed, and what deliberately did not

Settled with Chad: **1.5" cover, cages cut to length and field tied,
confinement bands.**

```
vertical = n × lb/ft × depth                      cut to length: no lap
ties     = [ band_count + (depth − band_count×band_sp/12) × 12 / spacing ]
           × lb/ft × (π × (dia − 3) + hook) / 12
dowels   = n × lb/ft × length                     the projection into the cap
```

Two things the sheet does not do, both asked for:

| | lb | $ |
|---|---|---|
| 12" hook or lap on every tie hoop | +1,165 | +1,259 |
| 3 #3 confinement ties at 3" at the top | +763 | +824 |
| real π and ASTM bar weights | +107 | — |
| **total** | **+2,035** | **+2,110** |

The band is **a count at a spacing**, not a band length — that is how the
drawing says it ("3 #3 stirrups at 3 inches top") and so it is what the model
takes. Its own depth comes off the run below so the top nine inches are not
counted twice.

Three things deliberately unchanged: verticals run the full hole depth (no lap
because they are cut to length, no bottom cover unless the assembly asks), the
projection up into the cap stays the **dowels** column, which is what it always
was, and `waste_rebar` here means genuine waste — drops and mis-cuts. On a slab
mat the same column carries the **lap**. Same field, two meanings, decided by
the assembly. Do not unify them.

## Drilling is a rate table, not a quote

The sheet's $58,032 "PIER QUOTE" is computed in a hidden block from **$/LF by
diameter**:

| Dia | 16" | 18" | 24" | 30" | 36" | 42" | 48" | 54" |
|---|---|---|---|---|---|---|---|---|
| Drill $/LF | 10 | 8 | 8 | 24 | 30 | 30 | 35 | 36 |
| Casing $/LF | 6 | 24 | 30 | 35 | 45 | 60 | 80 | 100 |

564 LF of 24" × $8 + 1,104 of 36" × $30 + 680 of 42" × $30 = **$58,032**, to the
dollar. `J54` on the sheet overrides it when a real quote arrives, which is now
`estimate_sections.pier_drill_quote`.

It lives in `pier_drill_rates`, and a diameter with **no row prices at nothing
and says so** — on screen as a `no rate` badge, in the totals as
`groups_without_drill_rate`. Interpolating a drilling rate across 2,348 LF is a
five-figure error with nothing to notice. Casing is carried but does not reach
the cost: it is a unit rate for the bid form.

Drilling is also **never taxed** — it is work, not a purchase — which is why
`_Unit` splits direct cost into taxable and untaxed halves.

## Labor per pier, supervision typed

```
LAYOUT / PLACE & FINISH / CLEANUP   $50 each × 106  =  5,300 apiece
TIE STEEL          $450/ton × 36.89           = 16,598.56
```

Tie steel bills **every pound** — a pier cage has no support-steel allowance to
carve out, so the mono-slab exclusion does not apply.

**Supervision days are entered, not derived**, and this is the sharpest
line-set difference in the app so far. Every other assembly gets a duration
from area — SF/16,000 a week on the slab sheet, SF/25,000 on paving. Piers has
no area. The sheet types 15 super days and 10 foreman, so the app takes them
off the superintendent line, and **the equipment ladder rides whatever is
typed**: change the days and the rentals move with them. That last part was the
piece that would silently not have happened.

15 typed days → ladder → 21 rental days → tier → 9 billable.

## Every cent of the difference

$297,204.52 against $295,601.21 — **+$1,603.31, +0.54%**:

| Δ | |
|---|---|
| **+1,652** | steel: the tie hook and the confinement band, +2,034.97 lb at $0.75 |
| **+458** | tie labor on that same steel, $450/ton |
| **−547** | lumber: pier sleds $2.25 in the catalog against the $2.75 the sheet types, boots $3.00 against $3.25 — today's prices, below the 2002 bid — plus concrete haul-off no longer taxed, because hauling is a service |
| **+26** | equipment: the sheet exempts the vault and miscellaneous from fuel and tax and bills miscellaneous flat; both are ordinary rentals here |
| **+15** | real π instead of 3.1412, on concrete and pumping |

Matched exactly: 106 piers, 2,348 LF, drilling $58,032, layout/place/cleanup
$5,300 apiece, supervision $8,875, PM $2,000, surveying $2,650.

## What got built

| | |
|---|---|
| `sql/037_piers.sql` | `pier_groups`, `pier_drill_rates`, `pier_drill_quote` on the section, 28 piers rows in `assembly_rates` |
| `services/piers.py` | shaft and bell concrete, the cage, the drill lookup, section totals |
| `costing.py` | `_Unit`, `allocation_basis`, `cost_units` — and direct cost split taxable / untaxed |
| line sets | piers forming, labor and equipment, dispatched on kind as paving's are |
| `routers/pier_groups.py` | CRUD, `/drill-rates`, and a bulk grid save |
| the grid | rewritten as `gridCardHtml` / `wireGrid` driven by a **column spec**, so paving and piers are two column lists rather than two grids |
| `PAVING_KINDS` / `PIER_KINDS` | moved to `models/estimate_section.py` — four private copies of a frozenset is how they stop agreeing |

`backend/tests/test_piers.py`, 17 tests. **199 in the suite, all passing.**

## Left for later

- **Bells are untested.** Every LBJ pier is straight-shafted, so the bell term —
  a cone approximation over a height taken as the bell diameter in inches read
  as feet, which is the sheet's convention and not a standard — has never run
  against a real number. Check it, do not trust it, the first time a job has
  bells.
- **The ADD/DED/CASING per-foot columns** are unit rates for the bid form, not
  cost. Worth capturing when proposals get built.
- **Confinement defaults** are 3 at 3" from `assembly_rates`; if they turn out
  to vary by diameter, that becomes a small table like the drill rates.
