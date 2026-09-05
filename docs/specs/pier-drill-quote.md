# The drilling quote (sql/038)

**Status:** built and tested, 2026-08-31. `sql/038_pier_drill_quote.sql` needs
applying.

## What was wrong

`sql/037` created `estimate_sections.pier_drill_quote` with a column comment
promising it *"REPLACES the figure computed from pier_drill_rates, exactly as
the sheet's J54 does."*

Nothing ever read it. Not the model, not the schema, not costing, not the UI —
the string `pier_drill_quote` appeared in exactly one file, the migration that
created it. A number typed into that column changed nothing and warned nobody.

That is the worst line on the job to have a fake override on. Drilling is
**$58,032 of LBJ's $211,441 direct cost — 27%** — and in the field it is a hard
number from the drilling sub. The rate table is the placeholder until the quote
arrives, not the other way round.

## The design decision: how a quote is spread

A lump sum cannot just replace the section total. Piers allocate on an **EA**
basis and every group carries its own `calc_cost_per_unit`, so dropping the
whole lump on the section leaves every per-pier figure below it wrong.

The first implementation apportioned by **LF**, which looks obviously right and
is not. A test caught it: the rate table charges **$8/LF for a 24" shaft and
$30/LF for a 42"**. Spreading a lump evenly per foot prices small piers at
nearly three times their real cost and large ones at a discount — the same
distortion the EA-basis fix was written to prevent, reintroduced one layer down.

So the quote is apportioned by the **shape of the rate table**: each group's
`rate × LF` as a fraction of the table's total.

> The quote sets the level. The table sets the relative weights.

A driller's lump is priced off a mix of diameters, and the table is the best
model of that mix we have. `drill_quote_basis` reports which basis ran —
`rate_shape`, or `lf` as the fallback when a diameter has no row to describe the
shape. `allocate_amount` gives the last group the remainder, so six shares of an
awkward number still sum to the quote to the cent.

A quote also **rescues a diameter the table has never heard of**. Without one, a
38" shaft prices at nothing and flags `no rate`; with one, the hole is covered
and `groups_without_drill_rate` correctly reads 0.

## Staleness — the only way this field can hurt you

A quote is priced against a takeoff, and takeoffs move. `pier_drill_quote_lf`
stamps the drilled LF at the moment the quote is written, **and recalc never
touches it**. If recalc re-stamped, the baseline would chase the takeoff and the
warning could never fire — and a warning that cannot trigger is worse than no
warning, because the screen looks reassuring.

Add 8 piers after the driller quoted and the lump does not grow. That is
correct — a quote is a quote — which is exactly why the banner has to carry the
weight:

> **This quote is out of date.** It was priced against 2,348 LF and the takeoff
> is now 2,540 LF (+192 LF). The lump sum has not moved — go back to the
> driller, or clear it and let the rate table price the holes.

An **unstamped** quote (typed into the database, or carried over from before
sql/038) reads as stale. Having no baseline is not evidence of being current.

Two smaller rules, both about not being clever:

- **Zero is a cleared field, not free drilling.** Nobody drills 2,348 LF for
  nothing, so a 0 falls back to the table rather than pricing the largest line
  on the job at zero.
- **The rate-table comparison is withheld** when any diameter is missing a row.
  A partial total shown next to a full quote invites subtracting one from the
  other and calling the difference a saving.

## What got built

| | |
|---|---|
| `sql/038_pier_drill_quote.sql` | `pier_drill_quote_lf`, `pier_drill_quote_note` |
| `services/piers.py` | `drill_quote`, `apply_drill_quote`, `drill_quote_basis`, `rate_table_drill_cost`; the spread runs in `refresh_section_pier_calcs` because apportioning needs every group's feet at once |
| `routers/estimate_sections.py` | stamps the baseline on write only, re-spreads and re-costs on change |
| `routers/pier_groups.py` | create / update / delete now re-run the **section**, not one group — under a quote, touching one group moves everyone's share |
| the UI | a quote card with the note field, the rate-table comparison, the effective $/LF, and the stale banner |

`backend/tests/test_pier_drill_quote.py`, 18 tests. **217 in the suite, all
passing.**

## Left for later

- **Casing and rock** are still bid-form unit rates, not cost. A quote that
  excludes them is a common shape and the note field is currently the only place
  that fact lives.
- **Per-diameter quotes.** Chad confirmed a driller quotes one lump, so that is
  what was built. If a quote ever arrives as `$/LF by size`, it overrides the
  table rows for one section rather than becoming a second lump.
