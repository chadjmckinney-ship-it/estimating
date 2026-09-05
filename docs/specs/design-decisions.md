# Design decisions — settled, with reasons

Things that have been decided and should not be re-proposed without new
information. Each records what was rejected and why, because the reasons are
usually less obvious than the decisions.

---

## Price reconciliation against the workbook is FINISHED

**Decided:** 2026-09-01, by Chad. **Status:** settled. **Read this before
opening a variance table.**

Chad, ending a long price reconciliation: *"thats in the workbook.. we are
moving away from anyway..."*

He is right, and the session that produced this note got it wrong for about an
hour — driving him to edit spreadsheet cells in a tool he is replacing.

**The prices are done.** Every price disagreement between the app and the LBJ
workbook was chased to ground on 2026-09-01, and every one of them traced to the
same thing: a cell on a tab whose `Pricing` lookup had been typed over with a
constant. Eight such cells were found. The diagnostic value of that exercise is
**spent** — it told us which of the *app's* prices were stale, they were fixed
(sql/043, sql/044), and the app's catalog is now the single source.

So, going forward:

- **A price gap against the sheet is not a finding.** The sheet is deliberately
  behind. Do not report it, do not "fix" it, and above all do not change an app
  price to match one.
- **The workbook is still the reference for RULES and QUANTITIES** — how a
  takeoff derives, which lines exist, what drives them, what a formula actually
  computes. That is what 07-COLUMNS needed from it, and what every later
  assembly will need.
- The variance tables in `docs/specs/workbook-reference.md` and the `*-spec.md`
  files are **dated snapshots**, not live checks. They record what was true when
  the rules were verified. Do not re-run them expecting agreement.

The general form: **a reconciliation has a shelf life.** It is worth doing once,
against a real bid, to prove the rules. Repeating it forever turns the thing you
are replacing into the thing you are validated by.

---

## The workbook is a starting point, not the target

**Decided:** 2026-09-01, by Chad. **Status:** settled.

Chad: *"I like having a workbook so we can start off of then fix the actual
issues I have.. and we can see what the real cost should be.. not what I force
the WB to try and cover."*

The app is not trying to reproduce the spreadsheet. It is trying to compute what
the work actually costs. The workbook is the best available starting reference —
a real bid, priced by someone who knows the trade — and it is also full of things
that are there because a spreadsheet made him put them there.

So **a variance is information, not a failure**, and it sorts into three piles
that look identical from the outside and mean opposite things:

**1. The app is wrong.** A real defect. Fix the app.
> TIE STEEL silently billing $0 while the crew tied eleven tons, because an
> allowance sized to cancel the workbook's padding ate the whole job once the
> padding was removed (sql/032).

**2. The workbook is wrong.** A formula bug that has been quietly costing money.
Change nothing in the app; record it.
> `SUM(K11:K42)` swallowing the perimeter TOTAL cell and buying 24 boxes of nails
> instead of 13. `SUM(W10:X41)*3` adding a section-*number* column to a length
> column. Poly tape filed under cost code 40011 "Patch/Grout" for years. The
> paving sheet's five `=T*R` cells whose neighbours read `=T*R*(1+tax)`.
> 07-COLUMNS' chamfer summing four *type* heights and never multiplying by
> quantity — 240 LF on a 68-column job, wrong by 18×.

**3. The workbook was forced.** The sheet says what it says because Chad had to
make it say that, working around a limit the app does not have. **Here the app
should be deliberately different, and reproducing the sheet would be the bug.**
> ~44,000 lb of phantom beam steel, because GB types were capped and folding the
> support allowance into §1 and §2 was the only way to carry it. The brick ledge
> entered as a separate 6×32 grade beam because there was no way to express a
> thickening. A tie-steel allowance sized precisely to cancel padding that should
> never have been there.

The failure mode is treating a pile-3 finding as pile 1 and "fixing" the app to
match. That is how a workaround gets promoted into a rule, and it imports the
limitation that caused it. **Before calling a variance an error, open the detail
and ask why the sheet says that.** "Forming accessories −$4,383, the untested
corner" survived several write-ups on the strength of a cost-code label; the
label was wrong and the forming package had been right the whole time.

Note the pile-2 findings are **worth recording and not worth acting on** — see
the entry above. They were how the app's own stale prices got found; that is all
they were ever for.

---

## No reusable beam-section library

**Decided:** 2026-08-30, by Chad. **Status:** settled.

Beam types (`estimate_beam_types`) are scoped to a single estimate, so a standard
12×32 section is entered fresh on every job. The obvious efficiency win is a
company-level library to copy from. **This was proposed and rejected.**

Chad's reason: *"I dont want a reusable beam sections. that way they have to make
sure they enter it."*

The friction is the point. A section entered once and carried forward is exactly
how the LBJ workbook's §1 and §2 kept a support-steel allowance written as
2-#5-with-stirrups across job after job — ~44,000 lb of rebar that was never going
in the ground, because nobody re-derived the schedule from the drawings. A
library would make that failure mode cheaper to repeat and harder to notice.

Cost accepted: the honest beam model takes more data entry than folding an
allowance into two padded sections. That is the trade, made knowingly.

**If revisited**, the thing to preserve is the forced read of the drawing — e.g. a
template that pre-fills dimensions but leaves the bar schedule blank would keep the
safeguard while saving the typing. A straight copy of a full section would not.

---

## Recalc does not touch completed work

**Decided:** 2026-08-30, by Chad. **Status:** settled.

Bulk repricing — a catalog price change or a company-default change — skips
estimates whose status is `final` or `archived` (`FROZEN_STATUSES` in
`services/recalc.py`). A job bid last spring keeps the numbers it was bid with.

Chad: *"I dont want it to recalculate on estimates I am not currently working on so
an older project that we have already completed doesnt change the cost later.
should be a button for updating."*

Direct edits to an estimate still recalculate it, and its own Recalculate button
overrides the freeze. Only the sweep across every estimate respects it. The sweep
reports what it skipped rather than staying silent.

---

## Tax is a visible line, not baked into prices

**Decided:** 2026-08-30. **Status:** settled.

The workbook multiplies each material cost code by 1.0825 inside the cell, so its
material lines are tax-inclusive and the tax is invisible. The app keeps the
catalog **pre-tax** and stores tax as its own column (`mono_slabs.calc_tax`).

Chad: *"concrete and rebar price do not include tax. all materials price is pre
tax."*

Consequence: a material list reads as a real material list, tax is one auditable
number, and exemption is a project fact (`projects.tax_exempt` — ROW paving is
always exempt at 8.25%).

**Extended 2026-08-31 (sql/036):** a takeoff line can now say it is *not* taxed,
via `estimate_forming_lines.taxable`. Exactly one line uses it — concrete
haul-off, which is hauling, not a purchase.

---

## Support steel is an allowance, and is never tied, wasted, or padded into beams

**Decided:** 2026-08-30, by Chad. **Status:** settled.

`support_rebar_lb_per_sf` (0.1 lb/SF) stands for the #3 bar that holds cables and
mat up while the crew works. Three rules follow, and they are consistent:

- It is **not** in the tie-steel driver — placing it *is* the tying, so billing it
  again charges one pass twice (sql/032).
- It gets **no waste** — wasting an allowance is slop on slop.
- It does **not** belong inside beam schedules — that was the workbook's
  workaround, and it is what made 13,755 LF of PT grade beam look reinforced.

**Extended 2026-08-31:** and it does not belong on paving at all. A paving mat
sits on chairs, which are already a line of their own. Left at the company
default it would have added 27,270 lb of #3 nobody buys.
`assembly_rates('paving', 'support_rebar_lb_per_sf') = 0`.

**Extended 2026-09-01:** nor on columns. A column cage is tied by hand, every
pound of it — the same call piers and walls made.

---

## A line set belongs to the assembly, and an absent line is absent

**Decided:** 2026-08-31. **Status:** settled. Supersedes a phase-2 call.

Forming, labor and equipment each dispatch on `section.kind`. Paving does not
get the mono-slab line set with some rates zeroed; it gets the lines 10-PAVING
has, and only those.

Phase 2 did the opposite, deliberately: the GRADING / CABLES line stayed on a
paving section at $0.00, on the reasoning that *a rate that reads zero on screen
can be questioned; a line that is not there cannot.* That was right while paving
was borrowing the slab's lines and only its rates differed.

It stopped being right once the set itself came from the sheet. What a paving
section shows now — FORMING, PLACE AND FINISH, WRECK, REBAR, CURB — **is** the
sheet, and a $0 GRADING row sitting in it reads as work that exists and has not
been priced, which invites the opposite error.

The division that follows:

- **`assembly_rates` holds rates and rules** — 6% concrete waste, 100% of curb
  formed, SF/25,000 supervision, a $15/day vault. **Not prices** — see below.
- **The line set holds structure.** Which lines exist, what drives their
  quantities, and the divisors inside those formulas — nails per 1,500 LF of curb
  instead of 500, cure at 350 SF/gal instead of 300.

A section that changes kind drops the lines the new set does not have, manual
overrides included.

---

## The screen is part of the assembly, and a driver the schema does not name never reaches it

**Decided:** 2026-09-01. **Status:** settled. Learned building the columns page.

`FormingDrivers` and `LaborDrivers` are Pydantic response models that list their
fields explicitly. A service can compute `column_count`, `form_sf` and
`chamfer_lf`, hand them back in the drivers dict, and have the schema drop all
three on the way out. The browser then renders `num(undefined)` as `—`.

**There is no error anywhere in that chain.** 200 OK on every request, nothing
in the console, and a stat card that should read 7,716 SF reads a dash. Walls had
carried the same hole unnoticed since sql/040: its forming header fell through to
the mono-slab branch and read "Perim 0 LF · drops 0 LF · SF 0".

A third variant, same class: `load_stored_labor` rebuilds its driver dict **by
hand** from the summary table, which carries the columns a mono slab needs and
nothing else. So even with the schema fixed, every read after the first lost the
geometry again.

Three rules:

1. **An assembly is not done when its tests pass — it is done when its page is
   right.** The API and the screen for columns were written the same week, which
   is the only reason this was caught at all.
2. **Adding a driver means touching three places**: the service that computes it,
   the response schema that names it, and — for labor — the stored-path dict that
   reassembles it.
3. **The field names the page reads are a contract, so test them.**
   `tests/test_columns_ui_contract.py` is a deliberately dumb list of keys
   asserted against the four payloads the section page fetches. It checks nothing
   about whether the numbers are right; `test_columns.py` does that. It exists so
   that renaming a driver breaks a test instead of blanking a card.

---

## A price comes from the catalog. Nothing else stores one.

**Decided:** 2026-08-31, **hardened 2026-09-01**. **Status:** settled.

Resolution order, in `costing.resolve_rebar`, `forming._assembly_unit_cost` and
`estimate_equipment._equip_rate`:

1. **A catalog item chosen for the assembly** — paving steel resolves to REBAR
   PAVING and pier steel to REBAR PIERS / PT slabs, both of which the catalog
   already carries under those names.
2. **The catalog item the mono-slab path already used.**
3. **An `assembly_rates` row**, only where no catalog item could carry it — a
   vault day rate, a miscellaneous allowance, an out-of-town per-diem.
4. **The price the workbook types**, only when nothing answers to the line at
   all — and the line then says `price_source: "sheet"` so it reads as a number
   to check rather than a number to trust.

Every resolved item is reported by name. That comes from the Yellow Guard
(sql/030): a price found by name search is a price nobody can see.

### Why the order changed on 2026-09-01

It used to put `assembly_rates` **first**, and sql/035–040 seeded seventeen
prices into that table straight out of workbook cells. Two consequences, both
real:

* `assembly_rates('piers','rebar_cost_per_lb') = 0.75` came from `01-Piers!G53` —
  a cell whose own `Pricing` lookup had been typed over. The app billed pier
  steel 25% high for weeks, faithfully reproducing a keystroke (sql/043).
* Four rows were **dead on arrival** — `chamfer_lf_cost` and friends, keyed so
  that no lookup would ever find them, sitting in the table looking
  authoritative. Six more exactly duplicated a catalog item. Two more were stale
  copies that moved real money (sql/044).

Chad, on why a doc quoting `$0.75` is a problem: *"its a bad place to store
pricing as it changes monthly so in a year.. it can be way off."* The same
applies to a migration file, and to a Python literal.

**The test: if the catalog could carry it, the catalog must.** Prices do not go
in migrations, in `assembly_rates`, in code defaults, or in documentation.

**Extended:** `GET /api/sections/{id}/material-costs` reports every purchase on
a section with its quantity, rate, resolved catalog item and dollars, and the
stat cards show the money next to the pounds. It exists because Chad could not
see how much was in rebar and typed into the quote box to find out — putting a
$0.65 *lump* on 21,945 lb of steel and understating the slab by $14,252.58
behind a green "quoted · current" badge. **A quantity with no price beside it is
a number nobody can question.**

---

## Paving areas live in `mono_slabs`

**Decided:** 2026-08-31. **Status:** settled.

A paving area has SF, a thickness, sand under it, a mix and a bar mat, computed
the same way a building-slab pour computes them. It is a pour. Giving it a table
of its own would have meant a second copy of the allocation, the costing, the
section rollup and the recalc plumbing, kept in step by hand.

`sql/036` adds the six drivers it does have that a slab does not — curb LF,
thick-edge LF, demo LF, slip form, traffic control, paving add $/SF — plus mesh
gauge and `calc_edge_concrete_cy`. A building slab leaves them NULL.

The cost is that `mono_slabs` is now wider than "mono slab" suggests. Accepted:
the alternative was duplicating the machinery that the whole sections
restructuring existed to unify.

---

## A grid save writes rows, then recalculates once — and never deletes silently

**Decided:** 2026-08-31. **Status:** settled.

Paving is entered as a table: 16 columns across up to 25 areas. Every takeoff on
the section keys off the section totals, so a save per field would re-run
forming, labor and equipment on every keystroke. `PUT /api/mono-slabs/bulk`
writes the rows and calls `recalc_section` once.

Rows the grid did not send are **left alone** unless `delete_missing` is set. The
grid scrolls, a filter can hide a row, a request can be truncated — and none of
those should cost an area. A save that quietly deletes work the user could not
see is a worse failure than a row that has to be deleted twice.

A blank cell saves as NULL, not 0. A column the estimator has not measured is not
a zero, and storing it as one would put a $0 curb on an area that is simply not
done yet.

**Four takeoff shapes now share this machinery**, and the grid is driven by a
column spec rather than written four times: the **pour** (`mono_slabs`, shared by
slabs and paving), the **group** (`pier_groups` — identical shafts, measured in
EA), the **run** (`wall_runs` — a wall and the footing under it, measured in form
feet), and the **type + count** (`column_types` — a schedule entry and how many,
allocated by form contact SF).
