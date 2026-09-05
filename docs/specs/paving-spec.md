# Paving — specification, golden numbers, and what got built

**Status:** built and tested, 2026-08-31 (phase 3). `sql/036_paving.sql` needs
applying before the app will start clean — `run` warns about it.

**Source:** `10-PAVING` in the LBJ workbook (live reference:
`C:\Users\Chad\Estimate_Project\Trammel Crow - LBJ Estimate.xlsm` — see
`claude/workbook-reference.md`), a filled paving section Chad copied in from
another project on 2026-08-30 so the app has real numbers to build against.
Every formula below was read from the sheet and re-derived to the cent.

---

## ⚠ Correction, 2026-09-01: the dowel "assembly" explanation was wrong

An earlier version of this doc justified the app's $4.995 dowel price by saying
the catalog item is "the **dowel assembly**, with cap and basket" against the
sheet's "bare bar" at $1.90. **That was an inference invented to make a $15,231
variance feel resolved, and the catalog does not support it.**

| id | Name | Price |
|---|---|---:|
| 58 | `1/2" SMOOTH DOWELS **& CAP**` | $1.00 |
| 53 | `DOWEL SPACING / 3/4" **& CAP**` | $3.50 |
| 61 | `1/2" x 24" smooth dowels` | $1.995 |
| 63 | `5/8" x 24" smooth dowels` | $3.12 |
| **64** | `3/4" x 24" smooth dowels` | **$4.995** ← what paving resolves to |

Catalog items that include a cap **say so in the name**. Item 64 does not, and
1.995 → 3.12 → 4.995 is a clean diameter ladder for plain bar. Item 64 is a
**bare dowel**.

Chad confirmed on 2026-09-01 that paving joints take **bare dowels, not
assemblies** — so the app is buying the right thing, and the only open question
is whether $4.995 is a current price. **Awaiting a real invoice figure.** At
4,546 pieces, every $1 moves this section $4,546.

The lesson is the one in `claude/design-decisions.md`: a variance is not
resolved by an explanation that sounds plausible. It is resolved by looking.

---

## Both price questions are answered — and both prices are current

An earlier draft raised two open questions about prices and quoted **REBAR
PAVING at $0.50**. That $0.50 was from the **sql/002 test seed**, not Chad's live
catalog. Confirmed against the running database:

| Line | Sheet types | Live catalog | Verdict |
|---|---|---|---|
| Concrete, Mix 3 | $140/CY | **$150** | catalog current |
| Paving steel, REBAR PAVING | $0.55/lb | **$0.60** | catalog current |
| 3/4" smooth dowels | $1.90 ea | **$4.995** | **unconfirmed — see above** |

The sheet was bid at older prices; the app prices at today's. Against the **live**
catalog the section reads **$1,404,380.20** — **+$77,196.73** over the sheet's
$1,327,183.47 — and quantities agree exactly (272,703 SF, 4,832.4125 CY,
150,386.615 lb, 4,546 joint LF). It is entirely prices:

| Line | Sheet | App | Qty | Δ (incl. 8.25% tax) |
|---|---:|---:|---|---:|
| Concrete Mix 3 | $140 | $150 | 4,832.4125 CY | **+$52,310.87** |
| Paving steel | $0.55 | $0.60 | 150,386.615 lb | **+$8,139.68** |
| 3/4" smooth dowels | $1.90 | $4.995 | 4,546 PCS | **+$15,230.63** |
| Cure — sheet forgets tax | | taxed | $8,512.50 | +$702.28 |
| Siding — same cell bug | | taxed | $360.00 | +$29.70 |
| | | | | **$76,413.16** |

Residual **~$784** (0.06%): ASTM bar weight (the app uses 0.376 lb/ft where the
sheet computes 0.3757154 from `(size/16)² × 10.6870159`), four-decimal price
storage, and a remainder not yet named.

**Two of these are workbook edits, not app changes:**

* `Pricing!H4` 140 → 150 (Mix 3)
* `10-PAVING!F54` 0.55 → 0.60 — the paving steel rate, typed on the tab rather
  than pulled from `Pricing`

Both applied, the sheet reads ~$1,379,494 and the gap falls to ~$24,886 — which
is then the dowel question plus the sheet's two missing-tax cells.

---

## The golden target, against the sql/002 test seed

The numbers below are the app run on the **test seed**, which is what
`test_paving.py` asserts against — the seed reproduces the sheet's own prices, so
a difference here is a difference in the *rules* rather than in the price list.

| | Sheet | App (test seed) | Δ |
|---|---|---|---|
| **Total cost** | **$1,327,183.47** | **$1,335,789.97** | **+$8,606.50** (+0.65%) |
| Sale (18% markup) | $1,566,076.49 | $1,576,232.16 | +$10,155.67 |
| Cost / SF | $4.8668 | $4.8983 | |
| Tax | 8.25% — **not exempt** | same | |

Every cent of the difference, named:

| Δ | Cause | Verdict |
|---|---|---|
| **+15,943.22** | 3/4" smooth dowels at $4.995 against the sheet's typed $1.90 | **unconfirmed — see the correction above** |
| **−8,133.51** | steel at the seed's $0.50/lb against the sheet's typed $0.55 (live catalog is $0.60) | seed artifact |
| +702.28 | cure taxed. The sheet's cure cell reads `=T*R` where its neighbours read `=T*R*(1+tax)` | app right |
| +29.70 | siding taxed, same cell bug | app right |
| +64.07 | #3 bar weighed at the ASTM 0.376 lb/ft the whole app uses; the sheet computes 0.3757154. 113.8 lb, and the accessories line rides the same tonnage | app right |
| +0.77 | catalog prices stored to four decimals where the Pricing sheet carries six (2x6 at 1.4453 against 1.4453125) | |
| −0.03 | rounding: superintendent days stored to four decimals (76.3568 against 76.35684), tie wire rolls likewise, per-pour cents on concrete and sand | |

Two more cells have the same missing-tax bug and do not move this job: **concrete
haul-off**, which really is a service and stays untaxed in the app too, and
**form release**, whose quantity is zero.

Asserted line by line in `backend/tests/test_paving.py`, which rebuilds the sheet
out of the app's own parts against the **real seeded catalog** — not an invented
one, because running on invented prices would only have proved the arithmetic.

---

## The takeoff

Three areas:

| Type | SF | Thick | Curb LF | Mix | Sand | Steel |
|---|---|---|---|---|---|---|
| Light Duty parking | 187,752 | 5" | 6,566 | 3 | 2" | #3 @ 18" |
| Firelane | 82,399 | 6" | 2,882 | 3 | 2" | #3 @ 18" |
| Heavy Duty | 2,552 | 6" | 89 | 3 | 2" | #3 @ 18" |
| **Total** | **272,703** | | **9,537** | | | |

Derived: **4,832.41 CY** concrete (4,738.81 slab + **93.60 curb**),
**1,784.35 CY** sand, **150,387 lb** steel.

**That this section is taxable is worth noting.** It is the direct evidence for
the decision not to default `tax_exempt` from the section kind — this is paving,
inside a job, paying full sales tax. Only ROW paving is exempt.

## Per-area quantities

Read straight off the sheet's row formulas (row 10 shown):

```
sand CY      = SF × sand_in / 324 × (1 + waste_sand)          waste_sand = 0.06
steel lb     = SF × 24/spacing_in × (size/16)² × 10.6870159
                                          × (1 + waste_rebar) waste_rebar = 0.10
concrete CY  = ( SF × thick_in / 324
               + curb_LF / 108                ← 0.25 CF per LF of curb
               + thick_edge_LF × 1.5 × 0.18 / 27 )
                                          × (1 + waste_conc)  waste_conc = 0.06
```

`24/spacing` is the sheet's `(N/12+N/12)/(N/12 × N/12)` written plainly — mat bar
each way, which is the same formula `calc_slab_mat_rebar_lf` already used. The
app keeps its own ASTM bar weights rather than the sheet's `(size/16)²` form.

Curb and thickened edge are stored separately as `calc_edge_concrete_cy`, so
`calc_slab_concrete_cy` still means the flat plane on every assembly.

## Rates — where paving differs from the slab sheet

| | 04-Slab | 10-Paving | Where it lives |
|---|---|---|---|
| Forming labor | $0.45/SF | **$0.30/SF** | `assembly_rates` (sql/035) |
| Place & finish | $0.65/SF | **$0.55/SF** | `assembly_rates` |
| Wreck & clean | $0.10/SF | **$0.15/SF** | `assembly_rates` |
| Grading / cables | $0.65/SF | **no such line** | line set |
| Steel | catalog REBAR GRADE BEAM | **catalog REBAR PAVING** | catalog |
| Accessories | $0.04/lb (catalog) | **$0.02/lb** | `assembly_rates` |
| Support steel | 0.1 lb/SF | **none** | `assembly_rates` |
| Vapor barrier | yes | **none** | `assembly_rates` |
| Waste C/S/R | company | **0.06 / 0.06 / 0.10** | `assembly_rates` |
| Form % | 50% of perimeter | **100% of curb** | `assembly_rates` |
| Supervision | SF / 16,000 per week | **SF / 25,000** | `assembly_rates` |
| Project manager | days × $200 | **no days** | line set |
| Cure coverage | SF / 300 / 55 | **SF / 350 / 55** | line set |
| 16p nails | perimeter × 1.25 / 500 | **curb LF × 1.25 / 1500** | line set |
| 8p nails | perimeter × 1.25 / 500 | **curb LF × 1.25 / 3000** | line set |
| Vault | $25/day | **$15/day** | `assembly_rates` |

**Rates live in `assembly_rates`; structure lives in the line set.** A row in
`assembly_rates` says "this assembly buys or produces at a different number". A
line the sheet does not have — grading, drops, tie steel — is simply not in the
paving line set, rather than present at $0.

## Forming — driven by CURB LF, not perimeter

The single biggest structural difference, and the reason forming, labor and
equipment now each dispatch on the section's kind. Every lumber line reads
`SUM(I10:I34)` — the **curb** column — where the slab sheet reads perimeter:

```
2x4 / 2x6 / 2x10  = curb_LF × form%              9,537
siding            = ROUNDUP(curb_LF × 0.03 / 16)    18   ← no form% on this one
stakes            = ROUND(2x10 / 25)               381
16p               = ROUNDUP(curb_LF × 1.25 / 1500)   8
8p, 6p            = ROUNDUP(curb_LF × 1.25 / 3000)   4
1x6 redwood       = joint LF in areas ≤ 8" thick 4,546
1x8 redwood       = joint LF in areas > 8" thick     0
1x1 tack strip    = 1x6 + 1x8                    4,546
3/4" dowels       = construction joint LF        4,546
chairs            = ROUNDUP(SF / 15000)             19
tie wire          = SF / 15000                 18.1802
accessories       = steel lb @ $0.02        150,386.6
cure              = ROUNDUP(SF / 350 / 55)          15
```

Two things the app does that the sheet does not:

- **Siding is not scaled by form%.** The sheet's own cell has no form% in it. The
  first build had one, and it agreed only because this sheet forms 100%.
- **The redwood splits on thickness.** The sheet computes the split in hidden
  columns AT and AU and then hard-codes the 1x8 to zero, which is right while
  every area is thin and wrong the first time a job pours a 10" pad.

## Joints — and where the sealant LF comes from

```
construction joints = ROUNDUP(SF / 60)                    4,546 LF @ $1.60
control joints      = ROUNDUP(SF / 15 × 2 − construction) 31,815 LF @ $0.65
soft cut            = control joints                      31,815 LF @ $0.45
```

Control joints at 15 ft **both ways**, less the construction joints already cut.
Together these are cost code Saw Cutting/Sealing, **$42,270.10 — matched exactly**
— and they also drive the redwood, the tack strips and the smooth dowels. Six
lines run off these two numbers, so they are computed once, in
`app/services/paving.py`.

## Supervision and equipment

```
super weeks = SF / 25,000            10.9081
super days  = weeks × 7              76.3568
superintendent = days × $425      $32,451.64
expense        = days × $100       $7,635.68     (no foreman, no PM on this job)
```

Equipment ran a **120-day ladder billing 36 days** (120 / 30 × 9 — the tier rule
generalises). Bob Cat $325, light tower $100, vault $15, all at 36 days = $15,840;
fuel and tax ride the same base at 0.5 + 0.0825, giving **$25,066.80 — matched
exactly**.

A fix went in alongside: a contract service priced by the day — out-of-town
expense, a crew day rate — no longer picks up fuel & maintenance. Costing tells
rentals from services by group, not by the unit string.

## Cost codes — and three more mis-filings

| Code | Label | $ | Actually |
|---|---|---|---|
| 100002 | Lumber | 55,243.88 | |
| 100003 | Sand Material | 48,289.05 | |
| 100005 | Reinforcement Material | 89,468.66 | |
| 100006 | Reinforcement Accessories | 13,190.03 | chairs + tie wire + accessories + **dowels** |
| 100008 | Concrete Material | 732,352.10 | |
| 100010 | Cure/Sealers | 8,512.50 | untaxed, unlike the slab sheet |
| 100020/21 | Supervision + Expense | 40,087.34 | |
| 100034 | Saw Cutting/Sealing | 42,270.10 | |
| 100040 | Total Sub Labor | 272,703.00 | **a subtotal of the three below — do not add** |
| 100041 | Labor Forming | 81,810.90 | forming |
| 100042 | Labor Grade, Poly, Reinf. | 149,986.65 | **actually place & finish** |
| 100044 | Labor Drops | 40,905.45 | **actually wreck & clean up** |
| 100060 | Total Equipment Rental | 25,066.80 | Bob Cat + light tower + vault + fuel |
| 100062/64/65 | Mini Ex / Skid Steer / General | 11,700 / 3,600 / 540 | **Bob Cat / light tower / vault** |

The eleven real codes sum to $1,327,183.46, one cent off the sheet's own total.

Two traps for whoever touches this next:

- **100040 is a subtotal.** $0.30 + $0.55 + $0.15 = $1.00/SF × 272,703 SF.
  Adding it to the three lines it summarises double-counts the entire labor
  package. The slab sheet does the same thing with 40040 "Forming Systems".
- **100042, 100044 and the equipment codes are mislabelled**, as 40011
  "Patch/Grout" was on the slab sheet when it turned out to be poly tape. Read
  the rate block, not the label.

## What got built

| | |
|---|---|
| `sql/036_paving.sql` | curb LF, thick-edge LF, demo LF, slip form, traffic control, paving add $/SF, mesh gauge and `calc_edge_concrete_cy` on `mono_slabs`; `taxable` on `estimate_forming_lines`; the paving and sidewalk rows in `assembly_rates` |
| `app/services/paving.py` | the joint layout, the curb/edge concrete and the cure coverage — computed once, used by three takeoffs |
| `forming.py`, `labor.py`, `estimate_equipment.py` | a line set per assembly, dispatched on kind; a section that changes kind drops the lines the new set does not have |
| `costing.py` | honours `taxable`; resolves the paving rebar item; reports which catalog item priced the steel |
| `pours.py` + `PUT /api/mono-slabs/bulk` | save a whole grid in one request and recalculate the section once |
| the section page | a 16-column grid for up to 25 areas, paving stats, and no vapor-barrier or beam-schedule cards |

A paving area **is** a pour — same SF, thickness, sand, mix and bar mat — so it
lives in `mono_slabs` rather than a table of its own, and the allocation, costing
and rollup machinery works unchanged.

## Acceptance

`backend/tests/test_paving.py`, 20 tests. 182 in the suite at the time of writing
(322 as of 2026-09-01), all passing.

**Imported into the live "testing" estimate on 2026-08-31** as section
`10-Paving`, three areas, reading $1,404,380.20 against the live catalog.

## Open

1. **The 3/4" dowel price is unconfirmed** — see the correction at the top.
   Awaiting a real invoice figure; $4,546 of section cost per $1.
2. The **~$784 residual** against the live sheet is not fully named.
