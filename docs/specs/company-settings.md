# Company settings (sql/054)

**Status:** 2026-09-04, built and shipped. 12 tests; suite 575 green.

Chad: **"yes, build the company settings section."**

It exists because sql/053 shipped `mobilization_ls` with no way to set it. The
only settings UI in the app was the vapor-tape picker, and half a dozen figures
that decide what every bid costs — the sales tax rate, the fuel-and-maintenance
uplift, the four supervision day rates — were reachable only through the
database.

`Settings → Company settings` in the sidebar. Thirty-five figures, grouped, with
the money first.

---

## The one thing it has to teach

Two kinds of setting live in the same table, and they behave in **opposite**
ways:

| | |
|---|---|
| **price** | Frozen on each estimate's price sheet when that estimate pulls. Editing it here sets what **new** work is priced at and **leaves existing jobs alone** — a bid that has gone out keeps the numbers it was bid with. An open job picks it up when you pull its sheet, and shows it as drift until you do. |
| **rule** | Read live. Editing it **rewrites every open estimate now**, because a correction to *how the work is computed* has to reach the jobs it was wrong on. |

Getting them the wrong way round is how somebody raises a rate, sees the job
not move, and raises it again. So every row wears a badge, the header explains
both, and the save toast says which one just happened — *"rewrote 3 open
estimates"* or *"no stored estimate changed."*

The two tests at the bottom of `test_company_settings.py` are that pair, and
they are the point of the whole file:

* `test_changing_a_PRICE_does_not_move_a_sheeted_estimate` — if it ever fails,
  every archived bid in the system just moved.
* `test_changing_a_RULE_rewrites_the_open_estimates` — if it ever fails, a
  correction stopped reaching the jobs it was made for.

## The taxonomy is served, not re-derived

`is_price`, `label`, `unit`, `group`, `group_order`, `is_set`, `scope` and
`unclassified` all come off the row. Same reasoning as `quote_kinds` on a
section: **a second copy in JavaScript of the split that decides the money is a
copy that will disagree.**

`scope` is `services/recalc.settings_scope` — so the screen can say *what a
change rewrites* before the click rather than after it. `unclassified` marks a
key in neither `MONETARY_KEYS` nor `RULE_KEYS`; `test_price_sheet_rates`
already fails the day one appears, and the screen shows the row with a banner
rather than hiding it.

## Unset is a real state

`mobilization_ls` ships as `jsonb null` and the screen draws it dim, with a
*"not set"* placeholder, never as `0`. A company with no mobilization figure is
a different thing from one that mobilizes for free.

`PATCH` now accepts `null`, which **clears a price back to unset**. Leaving
that out is how a guessed number becomes permanent — you could set a price once
and never take it back. Only prices get a Clear button; blanking a rule would
leave the code default in charge with nothing on screen saying so, which is the
opposite of what this screen is for.

## The groups, in order

Money first, because that is what anyone opens this page for.

1. **Tax & uplifts** — the two ratios that turn quantities into money. They do
   not compound: `× (1 + tax + fuel)`, as the workbook applies them.
2. **Supervision** — day rates (prices) plus the pacing that decides how many
   days (rules).
3. **Mobilization**
4. **Waste & allowances** — rules, all of them.
5. **Labor rates** — the company figure; every assembly can override it.
6. **Equipment** — day rates for machines with no catalog row of their own.
7. **Forming quantities** — divisors and coverages. Read these as quantities,
   never money: `nails_16p_per_sf` is SF per box.
8. **Vapor barrier** · 9. **Quotes**

Ordering is served (`group_order`) because it is a judgement, and alphabetical
is not it — the page used to open on "Vapor barrier", which is nobody's first
question.

## What building it caught

**`mobilization_ls` rewrote nothing.** It is neither `labor_*` nor `equip_*`,
so `settings_scope`'s prefix rules classified it as *"a key that feeds no
stored calculation"* — a company rate change that reached nothing, with a save
message confidently saying so. `_EQUIPMENT_KEYS` now names it.

**Three settings had no description**, which on a screen full of numbers means
no way to know whether touching one is safe. sql/054 is documentation only:
the two quote-band ratios (easy to misread as money — they are multiples of the
catalog) and `labor_tie_steel_ton`, which described itself as a slab rate when
every assembly reads it.

## Still to build

* **Assembly rates have no screen.** `assembly_rates` is the layer between the
  company figure and the section — 90-odd rows now, and the reason paving forms
  at $0.30/SF against the slab sheet's $0.45. It is edited only by migration.
  This screen is the shape that one should take.
* A **recalculate-all confirmation.** The button sweeps every open estimate
  and currently just does it.
