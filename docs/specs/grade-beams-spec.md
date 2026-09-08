# Grade beams and continuous footings — 02-Gd Beams, one engine, two kinds (2026-09-07)

**Source:** `02-Gd Beams` and `02-Cont Footings` on the Pearl Landing Podium
estimate (`workbooks/Pearl_Landing/Podium Estimate.xlsm`). On the LBJ workbook
the beams tab is an empty template, so both Podium tabs are the goldens.

**Chad, 2026-09-07:** "most spread footings have a weld plate.. so I think we
need a section for spread footings and one for continuous footings.. we can do
cont footings when we do grade beams" — and on the unit: "we use LF for both
of those."

## What the tab is

The **separately poured** beam: formed on both faces and poured before the
slab, which the vault has held apart from the monolithic beam on the mono
slab since 2026-08-02 ("the two methods do not share a cost model"). One row
per beam type:

| | Podium beams | Podium footings |
|---|---:|---:|
| Section | 24" × 30", three #6 top and bottom, #3 stirrups at 12" | the same |
| Length | 1,248 LF | 184 LF |
| Face feet (one face, I63) | 3,120 | 460 |
| Steel | 17,019.84 lb | 2,509.34 lb |
| Concrete | 240.36 CY | 35.44 CY |
| Cost / sale | $112,207.97 / $134,649.56 | $17,047.88 / $20,457.46 |

Steel (W10): top and bottom bars run the length; mid bars are typed per side
and doubled; stirrups are a hoop of 2(W + H) inches every spacing with no
hooks; L bars one every spacing along the beam, each of a typed length;
pilaster steel is 3% of the pilaster's volume at 0.2836 lb/in³. Concrete
(X10): L × W/12 × H/12 / 27 plus the pilasters' volume rounded up to whole CY
per row. The trench (FT, FV) is as deep as the beam is tall and as wide as it
is tall, plus the beam itself for excavation.

The cost stack is the walls tab's: forming, place and finish, wreck, and rub
and patch per face foot of one face; pilasters per face foot of pilaster; tie
steel per ton; excavation and backfill per CY; the lumber block off face feet
× "% of forming" (T48), stakes and chamfer off length, wall ties off contact
feet, camlocks off face feet; the supervision block; the equipment ladder off
the superintendent's days; the pump and haul-off per CY of concrete.

`02-Cont Footings` is the same tab with four cells typed differently: carton
forms and the durrock retainer switched on (F58, F59), wall ties and camlocks
zeroed (T62, T71).

## What was built (`sql/073`)

* **Two kinds on one engine.** `grade_beams` (which existed, unbuilt) and
  `cont_footings`, both in `BEAM_KINDS` everywhere the engine branches;
  `CONT_KINDS` where a footing differs — its label, its headings, and its
  defaults: wall ties and camlocks start off.
* **`beam_runs`**, the sixth takeoff shape: label, mix, L, W, H, top, bottom
  and mid bars (count and size), stirrups (size, spacing), L bars (size,
  spacing, length), pilasters (count, length, width). `services/beams.py`
  computes face and contact feet, pilaster face feet, CY, steel, excavation
  and backfill per the tab; `sheet_mode` swaps the tab's bar constants in.
* **The three line sets** in `forming.py`, `labor.py` and
  `estimate_equipment.py`, costing in `costing.py` (weight = face feet, unit
  = LF), material lines, the recalc dispatch, the rebar quote, the section
  delete guard, and the `/api/beam-runs` router with a bulk save.
* **Rates** for both kinds seeded from the workbook (the LBJ template where
  it types one, the Podium job where the template is blank), and put on every
  existing job's price sheet. Three new prices — `labor_pilasters_ff`,
  `carton_forms_lf`, `durrock_retainer_lf` — and two rules —
  `pilaster_steel_pct`, `carton_forms_waste`.
* **Lines the tab carries and zeroes by formula** — keyway, water stop, the
  slab dowels, form rental — exist and start **off**; a decision taken on a
  section survives a refresh (the forming store now honors a line's own
  default). Carton forms and the retainer are switch lines priced by rate,
  on by default the way the template types Y.
* **The grid, the stat cards, the headings and the rentals card** on the
  section page; the Activity page names beam-run edits.
* **Sold per LF** with the sheet's own $/face-foot beside it.

## Where the app deliberately differs from the tab

| | Tab | App | Beams | Footings |
|---|---|---|---:|---:|
| Tax on concrete and steel | none — the EXEMPT cell U39 holds "200", not Y or N | taxed on a taxable job | +$4,283.55 | +$631.54 |
| Accessories | typed $0.02/lb | the catalog's $0.04 (sql/044), taxed | +$368.37 | +$54.31 |
| Concrete haul-off | taxed with the lumber | a service, untaxed (sql/036) | −$16.57 | −$2.47 |
| Carton forms, durrock retainer | LF × rate, no tax | materials, taxed | — | +$154.46 |
| Miscellaneous equipment | flat days × rate | fuel and tax, as everywhere | +$61.16 | +$4.08 |
| Bar weight | (size/16)² × 10.680159; stirrups at 3.145 × 0.2836 | the catalog's lb/ft | −$2.28 | −$0.33 |
| Camlocks | $0.859375 (V71 reads the 2x4 price) | the same, at the catalog's four decimals | +$0.05 | — |
| Stirrup spacing 0 | zeroes every pound of steel on the row | no stirrups, the bars remain | — | — |

Goldens: **$116,902.23** and **$17,889.47**, held in
`tests/grade_beams_fixture.py`; `tests/test_grade_beams.py` holds each row of
the table above.

## Left alone

The monolithic beams on the mono slab; post-tension on this tab (row 54, 0 on
both jobs); the template leftovers whose cells read junk references or blank
prices (anchor bolts, patch, slab chairs, slab cure, form release, poly,
insulation, the special-material rows, PPE, bolsters); the walls-engine
continuous footing under the garage walls (`06-Garage Footings`), which is a
walls section with the wall left blank and already works.
