# Mobilization (sql/053)

**Status:** 2026-09-04, built and shipped. 14 tests; suite 563 green.

Chad, while settling the CIP deck's crane rate: **"we need to add a price for
mobilization."**

---

## The workbook has never priced it

Every tab of the LBJ estimate was searched for `mobil`, `demob`, `delivery`
and `haul in`. **Eight hits, and all eight are noise** — six are the word
"Mobile" beside a supplier's phone number on the Pricing tab, and two are a
box-delivery line on the PT slab sheets.

So this is not a formula being reproduced. It is a real cost that every bid in
the system has been leaving out, and on a section renting a **$3,200/day
crane** that is not a rounding error. It surfaced only because settling the
crane's price made somebody ask how the crane gets there.

Every decision below is Chad's rather than the workbook's.

## What it is

| | |
|---|---|
| **Where** | One line per SECTION — the contract-services block on *every* assembly, beside FREIGHT and OUT OF TOWN EXPENSE |
| **Shape** | `rate` = one ROUND TRIP, there and home. `days_qty` = **how many moves** |
| **Uplifts** | Neither taxed nor fuelled. It is a haul — work done, not a thing bought |
| **Default** | Zero moves at an unset rate. It moves no existing bid by a cent |

A job that mobilizes twice for two phases says `2`, rather than somebody
doubling a number in their head.

**Per-machine is still reachable** if a job ever needs it — a
`mobilization_cost` column on the equipment catalog, and this line sums the
machines instead of being typed. Nothing built here forecloses it.

**Why one line and not six.** The line is built once, above the six assembly
branches in `_calc_estimate_equipment`, and appended to each. "Every assembly
mobilizes" is the whole point, and six copies of a line is how one of them
quietly stops having it.

## Why the migration carries no number

sql/044: prices live in the catalog and on the estimate's price sheet, never
in a migration. A mobilization figure committed in SQL would be a second home
for a price, and the second home is the one nobody updates.

So sql/053 creates the **key** and leaves the **value** as `jsonb null`. That
is deliberate and it does three things at once:

* the key exists, so it can be edited and so it lands on a price sheet the
  moment it has a number;
* `#>> '{}'` on a jsonb null is SQL NULL, so `_setting_numeric` falls through
  to the caller's default and `_rate_optional` returns `None` — **unpriced,
  not free** (design decision 5, *"a zero rate is a statement"*);
* sql/049's settings backfill has a numeric guard, so the null is skipped
  rather than copied onto every estimate's sheet as a zero.

`test_price_sheet.py`'s master-list proof grew the same guard, which is now
also the proof that a null key is skipped rather than pulled as zero.

## The warning

> **mobilization — not entered** (this section rents equipment and carries
> nothing for getting it there)

It fires **only where there is something to move** — a section billing rental
days with $0 of mobilization. A section with no machines on it says nothing,
because a warning that fires on every section is one people learn to scroll
past. Same call the quote drift band was made on.

A **warning, not a refusal.** Chad, on validation: *"Skip it."* A job really
can have no mobilization — equipment already on site from the last phase. It
should just never be a **silent** zero.

Every existing section in the app will carry this the moment sql/053 is
applied, which is correct: none of those bids has mobilization in it.

## How to price it

Two places, and the section line wins:

1. **On the section.** Type the rate and the number of moves on the
   MOBILIZATION line and press Save. It marks the line manual, so a refresh
   does not wipe it.
2. **Company-wide.** `system_settings.mobilization_ls` seeds the rate on every
   new section. **Settings -> Company settings** (sql/054) edits it; that
   screen was built the same day, because shipping a key with no way to set it
   is how this one was found.

   The company figure seeds the RATE, not the count. A section still shows $0
   until somebody says how many moves the job needs -- which is right: nothing
   should bill a mobilization the estimator has not decided on.

It is a MONETARY key, so once it has a number it is pulled onto each
estimate's price sheet and frozen there like every other rate: the company can
move on without moving a job that is already out.

## What it turned up

Building the settings screen for it caught a bug in this very change:
`mobilization_ls` is neither `labor_*` nor `equip_*`, so
`recalc.settings_scope` classified it as *"a key that feeds no stored
calculation"* -- a company rate change that rewrote nothing, with a save
message confidently saying so. `_EQUIPMENT_KEYS` now names it, and
`test_company_settings` guards it.

## Still to build

* Optional: **per-machine mobilization** on the equipment catalog, if a job
  ever turns out to need it broken down that way. Nothing here forecloses it.
