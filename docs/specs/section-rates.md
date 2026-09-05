# Rates per section (sql/055)

**Status:** 2026-09-04, built and shipped. 21 tests; suite 596 green.

Chad:

> "can we pull the settings section into each estimate so they can be edited
> for just that estimate… lets say a place and finish sub says for a project,
> he can do it for less because of the size of the pours.."

and, asked where the override belongs: **"I think making rates changes per
section is what I would like the best"**, with the per-estimate layer kept
underneath.

---

## Half of it already existed

A **price** has been editable per job since sql/048. The Prices screen on every
estimate carries the assembly rate groups — *"Paving — where it differs from
the company rate"* — with **Place & finish labor** an editable row in it,
marked `edited`, frozen against pulls, reaching that job and no other.

That had never been found, which is a finding in itself: those groups sit about
200 material rows down the page.

## What was genuinely missing

1. **The sheet is per ESTIMATE.** A job with two paving sections could not say
   the sub is cheaper on the big pours and not the little ones — editing the
   paving rate moved both. And the size of the pours is a property of the
   **section**, which is exactly the sentence Chad wrote.

2. **Rules had no per-job override at all.** Waste, form %, supervision pacing
   and every divisor are read live. Four (`waste_concrete`, `waste_sand`,
   `waste_rebar`, `form_percent`) are columns on `estimate_sections`; the other
   twenty-odd had nowhere to be said differently.

## The ladder now

```
section_rates          this section, price or rule    <- beats everything
  price sheet          a PRICE, frozen at this job's pull
  estimate_rules       a RULE, this job, read live
    assembly_rates     what this assembly does
      system_settings  what the company does
        code default   the last resort
```

Two tables because they answer different questions. `section_rates` is *"on
this bit of work the number is X"* and wins outright. `estimate_rules` is *"on
this job we're wasting 8% concrete"* — a job fact, so it sits where the price
sheet sits.

**Rules are deliberately not on the price sheet.** The sheet *freezes* what it
holds, and a rule that froze would stop a correction reaching the jobs it was
made for. That distinction is the spine of the pricing design and this change
had to preserve it.

The four existing section columns still win over everything, checked first, so
no stored number moved.

## How it reaches 113 call sites

`_rate_numeric` is read from 113 places. Threading a `section_id` through them
would be 113 chances to forget one — and a forgotten one does not fail, it
silently reads the company's number for a section that overrode it, forever.

So the section travels in a **context**, `for_section()`, set at the same
twelve gates `priced_as` already uses. Same argument, same evidence: it is
written down in `price_book.py` as the reason the price book is a context and
not a parameter, and it applied again unchanged.

Two piers functions deliberately get no section context — they read the
drilling table rather than `_rate_numeric`, and claiming a section would be a
lie about what the pass is doing.

## What the card is actually for

The editing is two lines. The card's real job is **saying where each number
came from** — every row reports the whole ladder, so *"$0.42 here where the
company says $0.55"* reads as a decision rather than a typo. A rate you cannot
trace is a rate you cannot defend three months later, and this app has spent
its whole life finding numbers nobody could explain.

Collapsed to the overrides by default: a deck section reads 59 rates, and a
card that opens on all of them is one nobody scrolls past.

**The list is not hand-written.** A list of "keys a paving section reads" would
drift from the line sets the day somebody adds a line. Instead the takeoff is
run inside `recording_rates()` and the keys it actually asked for are the keys
shown — dimmed if the assembly names a rate this section does not currently
read.

## Details worth keeping

* **An emptied box is "stop overriding", not zero.** A zero rate is a statement
  somebody makes on purpose; a blank is not one. Clearing DELETES the row —
  there is no unset state in `section_rates`, because a row means somebody
  decided.
* **Every write recalculates the whole section**, for the reason the columns
  router paid $436,826.42 to learn: a rate feeds the takeoffs, the takeoffs
  feed the cost, and a per-row refresh leaves the rest stale.
* **Both tables ship empty**, which is the proof the change moved nothing —
  596 tests, every golden number unchanged.
* `Decimal("NaN")` is `_equip_price`'s sentinel for "no code default". It
  reached the new recording context and 500'd the screen on a JSON serialiser;
  it now records as `None`, which is what it means.

## Labor per section, material per job

Chad, stating the policy after the first build:

> "I want all the rates editable per section, each section should be separate
> from the others for labor... forming labor for slabs, paving, CIP decks, etc
> is based on that section. **materials should be standard across the
> estimate.** concrete and materials are quoted per job so should be edited
> that way."

Most of that needed no code. Mixes and materials are catalog rows on the price
sheet, resolved by `ref_id` — they never come through `_rate_numeric`, so
concrete and lumber have always been job-level and could never be set on a
section.

The gap was the handful of things that ARE rate keys and were being offered
per section when they should not be.

### The line took two passes to find

The first cut said *"a material is a material however it is priced"* and put PT
cable on the job. Chad:

> "PT cables are section level, per sf on slabs is different the decks. also
> have done one a project that is townhomes and apartments and they had
> different pt spacing."

He is right, and the better rule is not about materials at all. **What decides
the level is what the price is PER:**

* **Per unit of the WORK** — $/SF of slab, $/SF of deck — varies with what is
  being built, so it is a **section** rate however material-shaped it looks. PT
  at $1.45/SF is not the same purchase on a slab as on a deck. And
  `pt_lb_per_sf`, the cable weight, was already a section-level rule for the
  same reason — which is what lets one estimate carry townhomes and apartments
  at different spacings.
* **Per unit of the MATERIAL** — $/CY of sand, $/lb of steel — is the
  supplier's number for the job, and it does not care which section the truck
  backs up to.

`ESTIMATE_LEVEL_KEYS` is what survives that test:

| Job-level | Why |
|---|---|
| `stud_rails_lb` · `rock_cy` · `sand_unit_cost` | priced per unit of the material itself |
| `sales_tax_pct` · `equip_fuel_maint_pct` | job facts, not section facts |
| `default_vapor_barrier_material_id` · `default_vapor_tape_material_id` | *which* material, so it follows the material |
| `quote_warn_low_ratio` · `quote_warn_high_ratio` · `equip_use_rental_tiers` | company conventions |

Everything else is section-level — labor, equipment day rates, subbed services,
waste factors, divisors, and the four $/SF-of-work materials (PT cable,
plywood forming, carton forms, reshoring). A deck section reads 59 rates; 56
are settable there and 3 are not.

**Refused loudly, and shown anyway.** The PUT 400s with somewhere to go
("*PT cable is set for the whole job… set it on the estimate's price sheet*"),
and the card still LISTS the six read-only with a `job` badge. Hiding them
would leave the card looking like the whole story when it is not.

## 2026-09-05 — rates are always per section

Chad, verifying the model: "supervision, equipment, materials are all project
specific pricing.. labor changes with each section" — then "labor needs to be
per section" — then, on the design: **"Rates are always per section. go."**

Until today a section that had not spoken inherited its kind's rates from the
job's sheet, the assembly and the company, and followed them forever: editing
the walls forming rate on the job sheet moved every walls section on the job.
The override existed; the ownership did not.

Now:

* **A new section is seeded.** `POST /estimates/{id}/sections` calls
  `services/section_rates.seed`, which writes every section-level PRICE the
  section reads onto `section_rates` at the value it resolves to that moment
  (the job sheet if the estimate has one, else the assembly, else the
  company, else the code default), with a note saying when and from which
  rung. From then on the rate is the section's: nothing that happens to those
  tables afterwards moves it, and two sections of one kind on one job share
  nothing. *Clear* hands a rate back to the ladder, and it follows the ladder
  again from then on.
* **Existing sections were seeded** by `backend/seed_section_rates.py` at
  what they resolved to on 2026-09-05, so no number moved on the way in.
  Idempotent; safe to run twice.
* **Supervision day rates moved to the job.** `labor_super_day_rate`,
  `labor_foreman_day_rate`, `labor_pm_day_rate`, `labor_expense_day_rate` are
  in `ESTIMATE_LEVEL_KEYS` now, on Chad's "supervision ... project specific
  pricing" — set on the price sheet, shown read-only on the card. The DAYS
  per section stay per section (rules).
* **Mobilization and the equipment day rates moved to the job as well**, an
  hour later — Chad, after seeing the first seeding take them per section:
  "mobilization and the equipment day rates are per job." `mobilization_ls`
  and every `equip_*_day_rate` key are in `ESTIMATE_LEVEL_KEYS`; `sql/064`
  took their seeded rows back out (25 on the live database, each at the value
  the section already resolved to, so nothing moved). The DAYS a section
  needs stay its own. `out_of_town_day_rate` was left section-level — it is
  neither, and nobody has said.
* **Rules are never seeded.** Waste, divisors, how the work is computed are
  read live by design (a rule change still reaches a priced estimate); they
  stay section-level and settable, just not frozen.
* The read and the ladder moved from the router into
  `services/section_rates.py`, because the seeding needs the same truth the
  screen shows.

`tests/test_rates_are_per_section.py`: a new section owns every price it
reads at the ladder's value; supervision rates and rules are not its to own;
a later assembly change does not move it while a section made after the
change starts at the new number; two sections of one kind share nothing;
Clear hands back; the backfill seeds a fixture-built section without moving
its cost and does nothing the second time.

## Still to build

* **`estimate_rules` has no screen.** The table and the resolution are done and
  tested; setting one still takes SQL. The natural home is the estimate page,
  beside the price sheet link — a "Rules for this job" card in the same shape
  as the section card.
* **`assembly_rates` has no screen either** — still the only layer editable
  purely by migration.
