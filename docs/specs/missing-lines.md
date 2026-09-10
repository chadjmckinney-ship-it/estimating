# The lines the Lakeside tie-out found missing (2026-09-10)

**Source:** the Lakeside Townhomes import's tie-out (`workbook-import-spec.md`)
listed a light tower the slab set had no line for, a compactor the beam
and footing sets had no line for, and place & finish, wreck and rub & patch
the spot-footing set had no lines for. **Chad, 2026-09-10:** "add the
missing line sets, light tower, compactor, place and finish".

## What the two templates do

* The **LBJ slab tabs** run a sky track, a mini excavator, a trencher, a
  skid steer, a vault and a miscellaneous line; no light tower. The
  **Lakeside slab tab** runs bobcats, a trencher, a **light tower** ($65 a
  day, E = the bobcat's days), a vault and miscellaneous, all at the
  ladder's days.
* The **LBJ beam and footing tabs** run a sky track, a mini excavator, a
  skid steer, a light tower, a vault and miscellaneous; no compactor. The
  **Lakeside beam and footing tabs** run a backhoe, a bobcat, a
  **compactor** (`Pricing!D42` = $200 a day, E = the backhoe's days), a
  light tower and miscellaneous.
* The **06-Footings tab** on LBJ carries FOOTINGS per SF of plan area
  (H66 = BG36) and then FORMING, PLACE AND FINISH, WRECK AND CLEAN UP and
  RUB AND PATCH at 3.50 / 3.50 / 1.00 / 0.25 off `H67 = BF36` — the
  **wall's** face feet, which are zero on a footing. That is why `sql/072`
  left those four rates off the kind.
* The **Lakeside Footings tab** is the same block with the per-SF row
  unlabelled and reading `AZ37` (the wall's footer SF, zero here), and the
  four face-foot rows priced at 4 / 4 / 1 (subbed) and 0.5 (in-house) off
  `I65 = AY37`. Its takeoff columns define that number:
  `AX = (LENGTH FT × INCHES THICK / 12 × 2 + pilasters) × QTY` is
  **CONTACT FT** and `AY = AX / 2` is **FACE FT** — the footing's length
  times its thickness times its count, one face, the wall rule with the
  footing's thickness for its height. Lakeside: 13 × 8.5 × 20″ + 5 × 5.5 ×
  14″ + 8 × 14″ + 6 × 4 × 14″ = 253.58 face feet.

## What was built (`sql/089`)

Three additions, every line **off by default**, so no priced job moves
until somebody switches one on — the same convention as the sky track on
a slab:

* **LIGHT TOWER on the slab sets** (mono slab, rebar slab, slab on deck):
  after the skid steer, at the rental ladder's days, priced off the
  catalog's TOWER LIGHT row the way the beam, wall and pier sets already
  price theirs.
* **COMPACTOR on the beam and wall/footing sets:** between the skid steer
  and the light tower, at the ladder's days, priced off the catalog's
  COMPACTOR row ($200 a day, the same figure Lakeside's Pricing tab
  carries).
* **FORMING, PLACE AND FINISH, WRECK AND CLEAN UP, RUB AND PATCH on a spot
  footing:** per face foot, beside the per-SF FOOTINGS line, at the footing's
  **length × thickness × count** — the newer tab's FACE FT, summed over the
  section's runs as `length_ft × ftg_thick_in / 12`. The rates are the walls
  tab's four (3.50 / 3.50 / 1.00 / 0.25), copied onto `spot_footings` the
  way `sql/072` copied the rest of the kind, and onto every existing
  estimate's price sheet. A job priced the Lakeside way types 4 / 4 / 1 /
  0.5 over them, and the importer does exactly that.
* **The importer** switches a line on when the tab carries days or a cost
  for it, so Lakeside re-imported picks up its light tower, its compactors
  and its four face-foot rows at their rates, and switches off the per-SF
  FOOTINGS line the tab does not carry.

No screen change: a line the set carries shows on the Equipment and Labor
tabs with its switch, as every line does.

**Worth knowing:** the tab's face feet count ONE face of the footing — a
square footing's forms touch four. The app reproduces the tab's rule
because the office's rates are per that number; if the office ever wants
all four faces, that is a rule change with the rates to follow it.

## Lakeside, re-imported (test database, 2026-09-10)

| Section | Tab sale | App sale, before | App sale, after |
|---|---:|---:|---:|
| Mono Slab on Grade Garden Style | 2,387,292 | 2,463,003 (+3.2%) | 2,467,447 (+3.4%) |
| Mono Slab on Grade Building 1 | 181,417 | 184,429 (+1.7%) | 185,540 (+2.3%) |
| Footings | 46,060 | 43,065 (−6.5%) | 41,093 (−10.8%) |
| Gd Beams | 257,840 | 281,282 (+9.1%) | 283,561 (+10.0%) |
| **Total** | **5,799,737** | **5,887,161 (+1.5%)** | **5,893,023 (+1.6%)** |

The slabs and the beams moved by exactly the light tower and the
compactors the tabs carry (typed at the tab's days and rates). The
footings' four labor rows now tie to the dollar — forming 1,014.33, place
& finish 1,014.33, wreck 253.58, rub & patch 126.79 on 253.58 face feet —
and the per-SF FOOTINGS line is off as the tab leaves it blank; the
section reads lower than before because that line had been carrying the
tab's FORMING rate on 1,250 SF of plan area. What remains is not these
lines: the tab's lumber-and-accessories block (`R52:X90`, $3,624) is not
read and the app's forming package prices $918, and the tab excavates
1.3 × the concrete where the app digs its trench rule
(`workbook-import-spec.md`).

## Tests

`backend/tests/test_missing_lines.py`: the light tower is there, off, at
the trencher's days, off the catalog, between the skid steer and the vault,
and the LBJ golden is untouched; switched on it prices its days and a
refresh keeps the switch; the compactor is there and off on both sets, off
the catalog at $200, between the skid steer and the light tower; the spot
footing's four lines are there and off at its face feet and the walls
rates with the sheet's golden untouched, place & finish switched on prices
the face feet, and the rates sit on the estimate's sheet.
`test_spot_footings.py` and the importer test carry the change (the test
footings tab's FORMING comes on at $4 × 184.17 face feet; its FOOTINGS
line goes off).

## On the box

```bash
cd ~/estimating/app && git pull -q
.venv/bin/python backend/apply_sql.py sql/089_missing_lines.sql
systemctl --user restart estimating && curl -sk https://127.0.0.1:8001/health
```
