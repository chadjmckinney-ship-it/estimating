# The reference workbook — fully reconciled, 2026-09-01

**Use this file when comparing the app to the bid:**

    C:\Users\Chad\Estimate_Projects\workbooks\Downloads\Trammel Crow - LBJ Estimate.xlsm

**Not** `C:\Users\Chad\Estimate_Project\Trammel Crow - LBJ Estimate.xlsm` (no "s").
Both exist, both were edited on 2026-09-01, and they diverged — at one point the
second was 13 hours newer by clock and older by content. Chad works in the
`Estimate_Projects\workbooks\Downloads\` copy.

---

## Every section reconciled, every dollar named

| Section | Cell | Workbook | App | Δ | What the difference is |
|---|---|---:|---:|---:|---|
| 01-Piers | T42 | $292,301.97 | $293,575.71 | **+$1,273.74** | tie hooks + confinement band steel (+2,034.97 lb), tie labor on it, lumber at today's prices, real π — less the $1,500 Chad added to the sheet |
| 04-PT Slab on Grade | V45 | $706,113.87 | $674,561.18 | **−$31,552.69** | ~44,000 lb of phantom beam steel in the sheet |
| 06-Walls & Footings | S40 | $207,686.56 | $207,961.84 | **+$275.28** | sand taxed (+633.60), excavation ÷3888 not 3088 (−479.88), misc fuel/tax (+122.33), pump on exact CY, ASTM weight, precision |
| 10-PAVING | T39 | $1,401,697.71 | $1,404,380.20 | **+$2,682.49** | missing tax on cure/siding/dowels (2,605.33), ASTM bar weight (73.93), precision (3.23) |
| **Job** | | **$2,607,800.11** | **$2,580,478.93** | **−$27,321.18** | |

Live sale **$3,018,489.47**. The estimate header agrees with the sum of its
sections to the cent (the `refresh_estimate_totals` flush fix — see
`claude/rollup-flush-and-quote-units.md`).

**No difference is a defect in the app.** Each is either the sheet forgetting
tax, a formula bug in the sheet, or a rule the app deliberately does differently
— the three-piles framing in `claude/design-decisions.md`.

---

## What made this possible: the sheet had been unhooked from `Pricing` in six places

`Pricing` is the workbook's single price source — row 2 names ten mixes, row 4
holds the supplier price, row 3 takes `=MIN(F4:F9)`, and every tab looks up
`Pricing!F$3`…`O$3` by mix number. Materials and equipment live in columns A–E
and P–U of the same sheet.

Six cells had their lookup **typed over with a constant**, so a price change
reached some totals and not others. All six are now restored:

| Cell | Was | Now | Cost of the override |
|---|---|---|---|
| `01-Piers!G51` | `155` | `=IF(B51=1,Pricing!F$3,…)` | the two piers roll-ups disagreed by **$6,848.97** — T42/E42 read $358,661 while T40/AB39 read $350,579 |
| `01-Piers!G53` | `0.75` | `=Pricing!D22` → **0.60** | pier steel priced 25% over what it costs: **$11,648.21** on the sheet, $11,978.64 in the app |
| `06-Walls!F85` | `275` | `=Pricing!D35` → 325 | skid steer $50/day light |
| `04-PT Slab!G99` | `225` | `=Pricing!D35` → 325 | skid steer $100/day light on 18 days |
| `10-PAVING!T90` | `1.9` | `=Pricing!Q50` → 4.995 | dowels at a 2002 bare-bar figure — **$14,069.87** |
| `10-PAVING!F54` | `0.55` | `=Pricing!D24` → 0.60 | paving steel $0.05/lb light |

### Two lessons worth keeping

**A variance that looks too good deserves the same suspicion as a bad one.** An
earlier reading of piers reported **+$179.92** and looked excellent. It was two
errors cancelling: the app's skid steer was $100/day light on 9 days, and the
sheet carried Chad's +$1,500. Fixing the catalog moved piers to its true
variance.

**The app faithfully reproduced a keystroke.** `assembly_rates('piers',
'rebar_cost_per_lb') = 0.75` was seeded in sql/037 straight from `01-Piers!G53`,
believing it was a real pier premium. It was a typed-over lookup. **sql/043**
deletes the row and `resolve_rebar` now reaches the catalog item named for this
exact use — REBAR PIERS / PT slabs, the same bar a PT slab buys — so the price
tracks the catalog the way paving tracks REBAR PAVING. Copying a number out of a
sheet imports whatever is wrong with it.

---

## Prices settled on 2026-09-01

`Pricing` row 4 now matches the app's catalog:

| Col | Mix | Was | Now |
|---|---|---:|---:|
| F | 1 · 3,000 Ash+Air | 134 | 134 |
| G | 2 · 3,000 no Air | 145 | 145 |
| H | 3 · 3,500 Ash+Air | 140 | **150** |
| I | 4 · 3,500 no Air | 140 | **150** |
| J | 5 · 4,000 Ash+Air | 145 | **155** |
| K | 6 · 4,000 no Air | 145 | **155** |
| L | 7 · 4,500 Ash+Air | 158 | **160** |
| M | 8 · 5,000 no Air | 170 | **175** |
| N | 9 · Integral Color | 240 | **250** |
| O | 10 · Sidewalks | 121 | **134** |

Steel and equipment: `D22` REBAR PIERS/PT slabs **0.60** · `D23` REBAR GRADE BEAM
**0.65** · `D24` REBAR PAVING **0.60** · `D33` MINI EXCAVATOR **475** ·
`D35` SKID STEER **325** · `Q50` 3/4" × 24" smooth dowels **4.995**.

**App catalog changed:** SKID STEER $225 → **$325** (equipment id 4), on Chad's
call that `Pricing` is current. That moved the live estimate **+$5,222.25** and
took the mono slab off the $671,712.66 in the reconciliation doc. The golden
*test* is unaffected — `mono_slab_fixture.py` states $225 itself.

---

## Live LBJ state

| Section | Margin | Cost | Sale |
|---|---|---:|---:|
| Piers | 18% | $293,575.71 | $346,419.34 |
| Mono slab on grade | 15% | $674,561.18 | $775,745.36 |
| 10-Paving | 18% | $1,404,380.20 | $1,657,168.64 |
| 06-Walls & Footings | 15% | $207,961.84 | $239,156.13 |
| **Estimate** | | **$2,580,478.93** | **$3,018,489.47** |

---

## Sheets with no golden number

Every other tab reads 0.00: `02-Gd Beams`, `05-Slabs`, `03-Walls & Footings`,
`06-Footings`, `06-Garage Walls & Footings`, `06-Garage Footings`,
**`07-COLUMNS`**, `08-CIP EL. DECK`, `09-SLAB ON DECK`, `11-Sidewalks`,
`12-PANELS`, `13-Miscellaneous`, `14-Contingency`.

**07-COLUMNS will be the first assembly built with no reconciliation to check
against.** It needs a takeoff from Chad. Its rate block is populated
(`F67`–`F71` carry mixes 1, 2, 8, 9, 10 via the normal lookup), so the sheet is
ready — it just has no quantities.

---

## Docs superseded by this exercise

* **`piers-spec.md`** quotes the old $0.75 steel rate throughout — "+1,652 steel
  … at $0.75", "$297,204.52 against $295,601.21, +0.54%". After sql/043 those
  read **+$1,322 at $0.60**, **$285,225.89 against $283,953.00, +0.45%** in the
  fixture, and **+$1,273.74** live. Not yet rewritten.
* **`paving-spec.md`** explained the app's $4.995 dowel as "the dowel assembly,
  with cap and basket". **Invented** to make a variance feel resolved.
  `Pricing!P50/Q50` carries "3/4" x 24" smooth dowels" at exactly $4.995 — a bare
  dowel, straight from Chad's own price list. Corrected in place.
* The same doc's "+2,605 sales tax the sheet's cure and siding cells forgot" was
  called inconsistent with its own detail table (which summed to $732). **The
  $2,605 was right** — the label omitted dowels, at $1,873.35 the largest of the
  three.
* An earlier banner on `lbj-workbook-reconciliation.md` said the bid state was
  unrecoverable. Too strong; corrected there.

The pattern in all four: **reasoning from notes instead of opening the file.**
Open the workbook.
