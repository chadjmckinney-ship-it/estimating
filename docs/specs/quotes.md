# Quotes — the lump, the baseline, and the alarm

Updated 2026-09-02 after audit findings #4.

## What a quote is for

A quote replaces the app's computed price for one thing on one section with a
number a sub or fabricator actually gave. Two shapes, and the difference is the
whole design:

- **Unit-priced** — `$0.62/LB`, `$1,240/TON`, `$62/CWT`, `$/SF` for PT. It
  follows the takeoff by construction: change the steel and the money changes
  with it. **A unit price can never go stale.**
- **Lump (`LS`)** — one number for the whole package. It does *not* follow the
  takeoff, which is exactly why it needs a baseline.

The unit is stored rather than normalised on the way in, because a fabricator's
paper says $/cwt and an estimator checking this screen against that paper needs
to see the number they were quoted, not one we divided.

## The baseline, and why it exists

A lump is stamped with the takeoff it was priced against — `baseline_qty`, in
`baseline_unit` (lb of steel, LF drilled, SF of PT). `is_stale` compares that
stamp to the takeoff now:

```
stale = quote is a lump
        AND (no baseline recorded  OR  baseline != current takeoff)
```

An unstamped lump reads as **stale**, deliberately: having no baseline is not
evidence of being current.

**This is the app's only defence against a wrong quote.** On 2026-09-01 a rebar
quote was entered as `$0.65 LS` — sixty-five cents, lump, against 21,945 lb of
steel — and understated the mono slab by **$14,252.58**. Nothing rejected it,
nothing flagged its magnitude, and the section still read plausibly. It was
caught *only* because the badge went stale.

## The bug (#4, fixed 2026-09-02)

`section_driver_qty` dispatched on kind for piers and then treated **everything
else as a mono slab**:

```python
if kind in PIER_KINDS:   ...pier_groups...
rows = select(MonoSlab).where(...)      # ← everything else
```

Walls keep their takeoff in `wall_runs`; columns in `column_types`. Both summed
**zero**, against 33,728 lb and 47,417 lb of real steel.

Nothing looked wrong. The card's number was right and the spread across rows was
right — `costing._apply_lump_quotes` had been kind-dispatched correctly the
whole time. What was gone was the **check**: `is_stale` compared 0 to 0 and
returned False forever. Doubling a wall takeoff left the quote reading
"current". A `$1.00 LS` lump wiped $20,079.95 (walls) and $33,362.76 (columns)
of steel behind a green badge.

**The $0.65 LS bug with the alarm disconnected**, on the two assemblies added
after the alarm was built.

### The fix, and the shape of it

Two implementations of "what is this quote priced against" had drifted apart —
one for stamping the baseline, one for spreading the lump. The spread was right
because it went through `cost_units`, which every assembly must extend to work
at all. The baseline was its own copy, which a new assembly could silently miss.

Now there is **one definition**, `quotes.LUMP_DRIVERS`, keyed by quote kind and
taking a single takeoff row:

```python
LUMP_DRIVERS = {
    REBAR:    lambda row: row.calc_total_rebar_lb,
    PT:       lambda row: row.square_footage if row.post_tension else 0,
    DRILLING: lambda row: row.calc_total_lf,
}
```

`section_driver_qty` sums it over `cost_units(db, section)` — the same rows
costing spreads across. `_apply_lump_quotes` reads the same map instead of its
own lambdas. The docstring had always claimed the baseline and the spread could
not disagree; now that is true rather than aspirational.

`tests/test_quote_staleness.py` runs the contract as a **matrix** over all five
assemblies — stamped with the real takeoff, badge fires when the takeoff moves,
a derisory lump still gets a real baseline, a unit price carries none — plus a
structural test that fails if `_apply_lump_quotes` ever grows a private copy of
the drivers again. Verified by reverting the fix: exactly six failures, walls
and columns only.

## Rules that hold

- **PT spreads only onto post-tensioned pours.** Spread by plain SF a PT lump
  would charge PT to slabs that have none, which reads as a plausible per-SF
  number and is wrong on every row.
- **A row with no steel takes no share of a rebar lump** — not an equal share.
- **A lump whose every weight is zero is left alone**, not dumped on the last
  row. `allocate_amount`'s remainder rule is right for pennies and wrong for a
  whole quote.
- **A zero-amount quote is dropped**, not priced at nothing.
- **Drilling has a second check the others lack**: `rate_table_drill_cost`
  compares the quote against what the $/LF rate table would have charged, so a
  wildly-off drilling number is visible on its own terms.

## Still open

**Nothing checks a lump's MAGNITUDE against what it replaced.** `$1.00 LS` for
23 tons of steel is accepted, priced, and — now — correctly stamped and
correctly flagged the moment the takeoff moves. But on a takeoff that never
moves again, it stays green.

Drilling already has the comparison (`rate_table_drill_cost`). Extending that
shape to rebar and PT — *"this lump is 3% of what the catalog would have
charged; is that right?"* — is the obvious next defence, and it is the one that
would have caught the $0.65 on entry rather than on the next edit.

Chad declined a sanity guard on 2026-09-01 when it was offered as a hard
validation ("Skip it"). Worth re-offering as a **warning on the card** rather
than a refusal — the objection was to being blocked, not to being told.
