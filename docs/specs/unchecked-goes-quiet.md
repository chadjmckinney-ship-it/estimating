# An unchecked line stops asking (sql/056)

**Status:** 2026-09-04, built and shipped. 13 tests; suite 609 green.

Chad:

> "there is one thing that is good and bad.. you have it set to that when
> something shows an error if nothing is entered, I like that so I can check
> it.. but that message should go away after I uncheck it as not used"

---

## Why this one mattered more than it looks

The unpriced list is the most valuable thing this app produces. It is the
answer to *"what on this bid has no price behind it"*, and it has already
caught **$436,826.42** of silent zeroes across the six assemblies.

Its value depends entirely on being **answerable**. A warning that stays lit
after you have dealt with it teaches people to scroll past the list — and once
somebody is scrolling past the list, they are scrolling past the real ones too.
So an unanswerable warning does not cost you that one line; it costs you the
whole mechanism.

Two of them were unanswerable.

## 1. Mobilization fired *because* the box was unchecked

My bug, one day old, in sql/053:

```python
if renting and (mobil is None or not mobil.enabled or _d(mobil.ext_cost) <= 0):
```

`not mobil.enabled` is exactly backwards. The single gesture that means
"considered, not needed" was the single gesture that could not clear the
warning — and on the one case sql/053 had *explicitly written down* as a real
zero: *"equipment already on site from the last phase is a real zero."*

Now:

```python
if renting and (mobil is None or (mobil.enabled and _d(mobil.ext_cost) <= 0)):
```

No line at all, or a line that is **on** and carrying nothing → warns, because
nobody has looked. A line switched **off** → somebody looked.

## 2. Forming lines had no box at all

`estimate_labor_lines` and `estimate_equipment_lines` have carried `enabled`
since the beginning, with a checkbox on each card. `estimate_forming_lines`
never did.

So `RESHORING — forming` — a real **32,100 SF** quantity whose rate does not
exist anywhere in the system — sat on every deck section with nothing to click.
The estimator's only honest options were to invent a price or to live with the
warning forever.

**sql/056** adds the column, `TRUE` for every existing row. Off means what it
means everywhere else in the app:

* keeps its **quantity, formula and unit price** — off is not delete, because
  the section should still show what was *decided*, not just what was bought
  (and the next refresh would put a deleted line straight back)
* extends at **$0.00**, and the section cost drops by that plus its tax
* drops off the unpriced list, and loses its `unpriced` badge
* **survives a refresh** — a refresh rewrites quantities, it must not undo a
  decision. Same rule labor and equipment already follow
  (`enabled = prev.enabled if prev is not None`), read off the rows *before*
  the delete, since the delete is what takes the flag with it.

`PATCH /api/sections/{id}/forming-materials/lines/{code}` — the first per-line
write endpoint forming has ever had. It deliberately does **not** refresh:
rewriting the line set would re-derive quantities the estimator may have
edited, and a checkbox should not move a number it was not pointed at. The
section cost *is* rebuilt, because the total just changed.

## 3. Superintendent days, same reading

Unchecking that line now silences *"superintendent days — not typed"*, and it
is safe for a specific reason worth writing down: on all three typed assemblies
(piers, walls, decks) the **rental ladder derives from super days**. Zero days
means every machine is already at zero, so the warning has nothing left to
protect. Switching the line off is somebody saying that is intended.

## The rule, in one sentence

**A line nobody has looked at warns; a line somebody switched off does not.**

Two corollaries the tests pin down:

* a line that is **on and empty still warns** — that is the case the list
  exists for, and the half of Chad's report that was already right
* **rechecking puts the question back.** Silence is a property of the switch,
  not a latch — otherwise unchecking once would blind the section forever.

And one guard: unchecking mobilization must not take the *rest* of the list
with it. That would be a far more expensive bug than the one being fixed.

## Incidental: the forming table now fits

The new `Use` column would have pushed Qty / Unit / Unit $ / Ext $ / Formula
off the right edge of the card. RESHORING's note now wraps instead of running —
which turns out to have been costing that card its five right-hand columns
already, before this change touched it.

## Verified on LBJ

Deck section, 08-CIP EL. DECK:

* before — banner reads *"Two things on this section are costed at nothing"*:
  `RESHORING — forming` and `mobilization — not entered`
* uncheck RESHORING → line goes muted with a `not used` badge, keeps 32,100 SF,
  `$0 — unpriced` becomes a plain `$0`, banner drops to one item
* uncheck MOBILIZATION → banner gone entirely
* cost unchanged at **$956,185.45** throughout (reshoring was contributing $0
  by definition, which is the whole reason it was flagged)

## Still open

* `estimate_rules` has no screen — setting a job-level rule still takes SQL.
* `assembly_rates` has no screen either.
* The reshoring **rate** still does not exist anywhere. Unchecking it is now a
  legitimate answer, but it is not the same answer as pricing it — the labor
  for that same work bills $11,235 on LBJ.
