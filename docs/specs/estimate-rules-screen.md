# Rules for this job — the middle rung gets a screen

**Status:** 2026-09-04, built and shipped. 19 tests; suite 628 green.
**No migration** — `estimate_rules` shipped with sql/055. This is the box.

Chad: **"estimate rules."**

---

## What was missing

The table and its resolution have been correct since sql/055. Setting one still
took SQL, which made it the one rung nobody could reach:

```
section_rates      this section                <- has a card
  estimate_rules   THIS JOB                    <- had nothing
    assembly_rates what a paving section does  <- still has nothing
      system_settings  what S&S does           <- has a card
        code default
```

## Why rules are not on the price sheet

The card leads with this, because getting it backwards is the expensive
mistake:

* a **PRICE** is frozen on this job's sheet at the pull, so a company change
  leaves a live bid alone;
* a **RULE** is read **live**, so a correction to how the work is *computed*
  reaches the jobs it was made for.

Freezing a rule breaks the second half. So a job that needs its own waste
factor, its own supervision pacing or its own divisor needs somewhere that is
not the sheet — and that is what this is.

A monetary key `PUT` here **400s with somewhere to go**. `_rate_numeric` never
consults `estimate_rules` for a price, so a row written there would sit in the
table looking like a decision and change nothing at all. A box that accepts a
number and silently ignores it is worse than no box.

## The three calls (Chad, 2026-09-04)

**1. It lives on the estimate page**, not the price sheet. The per-job *price*
overrides sql/048 shipped sat about 200 material rows down that page and went
unfound for weeks. That is the whole argument.

**2. It lists only what this job's sections read.** Same mechanism as the
section card — each section's takeoff is run inside `recording_rates()` and the
union is the list, so it cannot drift from the line sets. A deck + piers job
shows 33 of the 55 rules. Adding a section adds its rules automatically.

**3. Where a section answers a rule itself, the row says so.** This is the
substance of the change.

## The four that are also section fields

`waste_concrete`, `waste_sand`, `waste_rebar` and `form_percent` are **columns
on `estimate_sections`**, read by `calc._waste` *before* the ladder runs at all.
So a job rule for those reaches only the sections that left the column blank.

The row wears a `per-section field` badge and a count — *"1 section sets its
own"* — with the section, its number and where that number came from in the
tooltip. The column beats even a `section_rates` row, so that is what gets
named.

Typing a job waste and watching a section not move is exactly the moment a
screen has to explain itself. A job rule that quietly does nothing on half the
sections is the class of bug this app keeps finding in the workbook.

## Two things worth keeping

* **`assembly_rates` is per KIND.** On a deck + piers job the same key can have
  two different assembly answers, so they are reported per kind rather than
  flattened to one number that would be wrong for one of the two sections. A
  row where they disagree does not print either one as *the* fallback — it
  falls through to what the company says.
* **`read_by` is a positive signal, not a complete one.** Only forming, labor
  and equipment replay without storing; the **geometry pass does not**. So
  `waste_concrete` comes back with an empty `read_by` on a deck that plainly
  reads it. It is still listed (the assembly names it), and the screen
  deliberately never says *"nothing reads this"* — a false "not used" beside the
  one rule an estimator most wants to set per job would cost the whole card its
  credibility.

## Details carried over from sql/055

* **An emptied box is "stop overriding", not zero.** Clearing DELETES the row —
  there is no unset state, because a row means somebody decided.
* **Every write reprices the whole job.** A rule is read live, which is exactly
  why it cannot wait for a later recalc: every stored `calc_*` column was
  computed under the old rule, so until something rewrites them the job shows
  one number while the rule says another. sql/053 shipped a company key that
  rewrote nothing and reported success — the same failure, one layer up.
* **Reading writes nothing.** A job nobody has touched prices exactly as it did
  before the screen existed.

## Verified live

A deck + piers job (LBJ deck + piers fixture, one section rate and one section
column already set):

* card shows **33 in play**, grouped in the served order — Supervision, Waste &
  allowances, Equipment, Contract services, Forming quantities, Vapor barrier,
  Pier geometry
* `waste_concrete` carries the `per-section field` badge and *"1 section sets
  its own"* (0.07 on the deck)
* `reshoring_multiplier` carries *"1 section overrides this"* (1.4, per Sam)
* setting `lumber_2x4_per_lf` moved the job **$1,242,911 → $1,255,495**, the row
  jumped to the top table, and the section table above it re-rendered

## Still to build

* **`assembly_rates` has no screen** — now the only layer editable purely by
  migration.
* Recording the **geometry pass** would make `read_by` complete. It stores, so
  it cannot simply be replayed; it would need a rolled-back savepoint.
