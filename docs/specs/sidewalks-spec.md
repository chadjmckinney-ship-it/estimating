# Sidewalks — the SIDEWALKS tab, the kind's own line sets (2026-09-08)

**Source:** the `SIDEWALKS` tab of the older template family, as Chad
populated it on 2026-09-08 in
`workbooks/Downloads/Updated_Estimate_Worksheet_from_Estimate_Project.xlsm`.
Three walk types, 40,075 SF: $394,411.82 cost, $485,126.54 sale at 20 percent
margin and the Summary's 3 percent contingency, $12.11/SF.

**Chad, 2026-09-08:** asked whether sidewalks were done, then "do you want
me to populate the sidewalk tab so you have numbers to go off of?" — and on
the mix, "I know the mixes dont line up but you can use the 3000 psi w/ air
and ash".

## Where the kind stood

`sidewalk` was a kind on the paving engine since `sql/035`, on five rates
marked "Assumed as paving until 11-Sidewalks is read". The numbered family's
`11-Sidewalks` tab is empty on every workbook in the folder; the older
family's `SIDEWALKS` tab is the one with a cost model, and it is not the
paving tab.

## What the tab is

One row per walk type: SF, thickness, sand, mix, thickened-edge LF, three
finish flags (stamped, integral color, acid etch or sandblast), traffic
control, stair treads as LF × rise × run, a bar mat, a mesh gauge.

| | Paving | Sidewalks |
|---|---|---|
| Lumber runs off | curb LF | square feet: 2x4 at SF ÷ 4, stakes at SF ÷ 400, nails at SF ÷ 6,000 |
| Joints | 60 ft construction, 15 ft control | 15 ft expansion, 5 ft control; 1x4 redwood, tack strip and 1/2" dowels at 18" on the expansion joints |
| Labor $/SF | 0.30 / 0.55 / 0.15, curb per LF, rebar per lb | 1.75 / 1.00 / 0.25, thick edge $10/LF, stair treads $2/LF, ADA ramps $400 each |
| Supervision | SF ÷ 25,000 a week | concrete: CY ÷ 10 × 1.5 + 5 days, expense follows, no foreman, no PM |
| Equipment ladder | bobcat, light tower, vault | bobcat and miscellaneous; backhoe, trencher, light tower, barricades typed |
| Finishes | stamping typed | stamped $3.50/SF, integral color $100/CY, acid etch $2/SF, from the flags |
| Thick edge | 1.5 ft wide | 1.8 ft wide, with two #3 along it |
| Steel | mat with waste | mat with waste, plus the edge bars outside it |

## What was built (`sql/076`)

* **`SIDEWALK_KINDS`** with its own labor, forming and equipment line sets
  beside paving's. The kind stays a paving-family area on `mono_slabs`.
* **Six columns on the area row:** the three finishes and the stair treads.
  Stair concrete is LF × rise × (run + 12) ÷ 3888, wasted like the pour;
  the edge bars are LF × count × lb/ft, outside the mat's waste.
* **Supervision from concrete**, the superintendent's formula on the line.
* **Joint spacings and the thickened edge's width as rules per kind**, so
  paving keeps 60/15 and 1.5 ft while a walk reads 15/5 and 1.8 ft.
* **Rates** from the tab, replacing the guesses; every job's price sheet
  carries them. Five new prices — thick edge, stair tread and ADA ramp
  labor, integral color, acid etch — and ten new rules.
* **The grid** with the finishes as checks, stairs as three fields, and the
  stat cards for finishes, edge and stairs, joints.

## Where the app deliberately differs from the tab

| | Tab | App | Amount |
|---|---|---|---:|
| Accessories | typed $0.02/lb, untaxed | the catalog's $0.04 (sql/044), taxed | +$515.26 |
| Miscellaneous equipment | flat days × rate | fuel and tax, as everywhere | +$655.31 |
| Tack strip, tie wire, cure, dowels | untaxed (W × U) | purchased materials, taxed | +$402.83 |
| Bar weight | (3/16)² × 10.6870159 | the catalog's 0.376 lb/ft | +$11.77 |
| Stakes and cure | full precision | three places | +$0.17 |
| Contingency | the Summary's 3% | the section's own 3% | — |

Golden: **$395,997.18**, held in `tests/sidewalks_fixture.py`;
`tests/test_sidewalks.py` holds each row above and the sale at cost × 1.23.

## Left alone

The tab's ADA bricks, chairs, siding, ply, keyway, chamfer and the 2x6 to
2x10 sit at zero, typed when a job has them. Panels (12) and miscellaneous
(13) are the sections still unbuilt.
