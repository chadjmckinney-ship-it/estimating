# Price restore — the hold is lifted

**Status changed 2026-08-31.** The catalog no longer has to hold LBJ bid prices.

The hold existed so estimate `152b3611` could work as a golden-number fixture:
while the calc engine was being built, a change in its total should mean a
formula changed, not a price. That protection was **a document and an
intention**, and it failed — see below.

It is now `backend/tests/mono_slab_fixture.py` +
`backend/tests/test_mono_slab_golden.py`, **29 tests**, which state the bid
prices themselves and reproduce **$671,712.66 / $772,469.56** from them. The
catalog is free.

---

## What the hold was protecting against, and how it failed

Two equipment day rates were edited in the catalog at **09:35 on 2026-08-31**
(both rows' `updated_at`). The Mono slab section moved **−$4,984.91** and the
entire 248-test suite passed. It took a morning to establish that nothing was
broken.

| | Bid | Drifted to | Effect (18 days, ×1.5825 for fuel + tax) |
|---|---|---|---|
| MINI EXCAVATOR (id 2) | $475.00 /day | $250.00 | −$6,409.13 |
| SKID STEER (id 4) | $225.00 /day | $275.00 | +$1,424.25 |
| | | | **−$4,984.88** |

Three cents of per-pour rounding from the observed −$4,984.91. **Never a code
regression.** Both rates were restored the same afternoon so the live estimate
matches the workbook again — but that is now a convenience, not a dependency.

The new test was verified against exactly this failure: setting the mini
excavator back to $250 in the fixture fails five tests by name, including
`test_the_two_rates_that_drifted` and `test_equipment_rentals_and_services_are_separate`.
A failure now says *which block moved*, not just that a total is wrong.

## The 8 cents

The fixture reads **$671,712.66** where `docs/specs/lbj-workbook-reconciliation.md`
says $671,712.74. The difference is a fix, not drift.

Supervision days used to quantize weeks to four decimals and *then* multiply by
seven — a double round. Phase 3 changed it to carry raw weeks and quantize once:

```
62,723 SF / 16,000 = 3.92019 weeks
old:  round(3.9202, 4) x 7 = 27.4414 days
new:  round(3.92019 x 7)   = 27.4413 days
```

One ten-thousandth of a day across three lines that all ride super days:
superintendent @ $425 −$0.05, expense @ $100 −$0.01, PM @ $200 −$0.02.
**$671,712.74 − $0.08 = $671,712.66.** Read the reconciliation doc's headline
as $671,712.66 from phase 3 onward.

## What the fixture pins

Quantities (14 of them, one assertion each so a failure names the field),
then money by block:

| Block | |
|---|---|
| Direct materials | $393,605.54 |
| Forming | $29,615.36 |
| Labor | $126,922.07 |
| Supervision | $19,894.94 |
| Equipment rental | $19,890.00 |
| Equipment contract (pumping) | $35,283.13 |
| Fuel & maintenance | $9,944.98 |
| Sales tax | $36,556.64 |
| **Total** | **$671,712.66** |

Plus the rules worth stating out loud: tie steel bills tied steel only
(21,944.977 lb less 6,272.300 support = 7.8363 tons), rentals carry fuel and
tax where pumping carries neither, GB 1 and GB 2 carry no bar, and the blocks
sum to the total with nothing counted twice.

## Prices now free to restore

Held in the fixture, so the catalog can carry whatever is current:

| What | Bid (in the fixture) | Believed current | Where |
|---|---|---|---|
| Mix 3 — 3000 PSI Air + ASH | $134.00 /CY | $145.00 | `/api/mix-designs/3` |
| Rebar — PIERS / PT slabs (id 50) | $0.6000 /lb | $0.65 | `/api/materials/50` |
| SKID STEER (id 4) | $225.00 /day | $275.00 *(seen 8/31)* | `/api/equipment/4` |
| MINI EXCAVATOR (id 2) | $475.00 /day | $250.00 *(seen 8/31)* | `/api/equipment/2` |
| `labor_grading_sf` | 0.65 | 0.70 | system setting |
| `labor_place_finish_sf` | 0.65 | 0.55 | system setting |
| `labor_wreck_sf` | 0.10 | 0.20 | system setting |
| `labor_tie_steel_ton` | 400 | 450 | system setting |

**Confirm the "current" column against a live quote before applying** — those
figures were captured on 2026-08-30 and have not been re-verified. Note two move
*down*. The $250 / $275 equipment figures may well have been a deliberate
current-price update on 8/31; both rows cite `Pricing (New Current Worksheet)`.

Already confirmed current and left alone: poly Yellow Guard 14×210 at $340/roll,
ACCESSORIES at $0.04/lb, tape ratio 2.5, sand $25/CY, PT cables $0.85/SF,
trencher $325.

## How to apply

Each catalog edit is a PATCH; the settings are one each. Nothing reprices on its
own — **follow with a reprice-all sweep**, which rewrites every draft and
in-review estimate and leaves anything `final` or `archived` at its bid numbers
(`services/recalc.py`, `FROZEN_STATUSES`).

LBJ `152b3611` will move when you sweep, and that is now fine — the golden
number lives in the test, not on the screen. If you want the live estimate to
stay a readable record of what was bid, **mark it `final` first**; the freeze
will skip it.

## Still open

- **No audit on catalog edits.** A price change silently reprices every draft
  estimate and leaves no record of who, when, or from what. The only evidence
  available on 8/31 was two `updated_at` timestamps.
- **Piers and paving have fixtures but no live-estimate golden test** of the
  same kind. `piers_fixture.py` and `paving_fixture.py` already state their own
  prices, so they were never exposed to this — worth confirming rather than
  assuming.
