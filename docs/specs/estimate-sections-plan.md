# Estimate sections — restructuring plan

**Status:** phases 1, 2 and 3 complete. Phase 3 (paving) is built and tested;
`sql/036_paving.sql` still needs **applying** — `run` warns about it. Phase 4 is
next. Updated 2026-08-31.

## The problem

An estimate used to **be** a mono-slab worksheet. `mono_slabs`, the three line
tables and `estimate_beam_types` hung directly off `estimates`, and the estimate
page was the mono-slab page. Adding paving there would have meant paving pours
beside slab pours under one set of labor rates.

Chad: *"each tab in my workbook has different labor rates and should… we need an
estimate summary page per project then we add the sections under it."*

## What LBJ actually is

We reconciled `04-PT Slab on Grade`. That is **one of three** filled sections:

| Section | Qty | Unit | Sale |
|---|---|---|---|
| 01-PIERS | 106 | EA | $348,809.43 |
| 04-PT SLABS | 62,723 | SF | $808,755.18 |
| 06-WALLS | 3,452.55 | FF | $230,548.73 |
| **Contract price** | | | **$1,388,113.34** |

## Settled

| Question | Decision |
|---|---|
| Markup | **Per section**, default 20%. New sections inherit the estimate's figure; changing the job default does not reprice existing sections. |
| Tax exemption | A **project** fact with a **section** exception. `estimate_sections.tax_exempt` is tri-state: NULL inherits the project. |
| Never defaulted by kind | Plenty of paving is not ROW — and the filled 10-PAVING sheet is **taxable**, which is the evidence. |
| Job per-unit cost | Blank. Sections are EA, SF, FF and LS. |
| Rates | Per assembly kind, falling back to the company setting. A row in `assembly_rates` means "this assembly differs". |
| Line sets | Also per assembly kind. A line the sheet does not have is **absent**, not zero. See `claude/design-decisions.md`. |
| Reusable beam sections | **Rejected** — `claude/design-decisions.md`. |

## Phase 1a — `sql/033` ✅

`estimate_sections` created; every estimate given one `mono_slab` section
carrying its settings; `section_id` populated on the five child tables while
`estimate_id` stayed, so nothing broke on apply.

## Phase 1b — `sql/034` + services ✅

`section_id` became the only parent; `estimate_id` dropped; unique constraints
moved to `(section_id, code)`; the three `*_summary` caches re-keyed;
`grade_beam_details` and `supplier_bid_variance` rebuilt; the wastes, form% and
vapor columns dropped from `estimates`.

`recalc_section` prices one assembly; `recalc_estimate` runs every section then
`refresh_estimate_totals` adds them up. The estimate computes nothing of its own.

Verified with a forced recalc: $671,712.74 / $772,469.65, 62,723 SF @ $10.7092.

## Phase 1c — the UI ✅

`#estimate/{id}` is the job summary; `#section/{id}` is the assembly page and is
deep-linkable. Add Section modal defaults tax to "follow the project" and names
from the kind. On a section page, markup edits the section, Recalculate reprices
the section, Delete deletes the section.

**Lesson:** the first version used CSS classes that do not exist in the
stylesheet (`.stat-big`, `.stat-row`) and put `class="grid"` on a `<table>`,
where `.grid` is `display: grid` — so the page rendered as unstyled text with the
headers run together. `node --check` says a file parses, not that it renders.
**Screenshot after a UI change.**

## Phase 2 — `sql/035`, rates by assembly ✅

Resolution: `assembly_rates(kind, key)` → `system_settings` → code default.
Seeded for paving and sidewalk; **mono_slab deliberately has no rows.**

| | Paving | Mono slab |
|---|---|---|
| Forming | $0.30 | $0.45 |
| Place & finish | $0.55 | $0.65 |
| Wreck & clean | $0.15 | $0.10 |
| Grading | — | $0.65 |
| Supervision | SF/25,000 | SF/16,000 |

LBJ unchanged at $671,712.74.

**Lesson:** mono_slab was first seeded *from* the live settings, on the reasoning
that copying current values guaranteed nothing moved. It does — and it would also
have meant a company rate change never reached a slab section again, because the
copy taken at migration time would shadow it forever. Four tests caught it. A row
means "differs", not "is".

## Phase 3 — paving ✅ `sql/036`

Full spec, golden numbers, and every named variance: **`claude/paving-spec.md`**.

The app reads **$1,335,789.97** against the sheet's $1,327,183.47 — +0.65%, with
every cent accounted for. Four of the five causes are the sheet being wrong.
**Two are questions for Chad, both about a price**, and they are at the top of
the spec: the 3/4" smooth dowels ($4.995 catalog vs $1.90 typed, worth $15,943)
and paving steel ($0.50 catalog vs $0.55 typed, worth $8,134).

Matched to the cent: labor $272,703.00, saw cutting $42,270.10, equipment
$25,066.80, sand $48,289.05, joints 4,546 / 31,815 LF, the 120-day / 36-billed
equipment ladder.

What got built:

1. **Paving drivers on the pour** — curb LF, thick-edge LF, demo LF, slip form,
   traffic control, paving add $/SF, mesh gauge, plus `calc_edge_concrete_cy`.
   A paving area **is** a pour, so it lives in `mono_slabs` and the allocation,
   costing and rollup machinery works unchanged.
2. **A line set per assembly** in forming, labor and equipment, dispatched on
   `section.kind`. Forming runs off **curb LF, not perimeter** — these areas have
   no perimeter entered at all, so the old code would have formed for free.
   Joints, soft cut, demo and slip forming are contract services.
3. **A grid entry form** — 16 columns across up to 25 areas, one Save, backed by
   `PUT /api/mono-slabs/bulk`. A save per field would have re-run forming, labor
   and equipment on every keystroke.

Four smaller things fixed on the way, each its own defect:

- Superintendent days were computed by rounding *weeks* to four decimals and then
  multiplying by seven, which multiplied the rounding error by seven too.
- A contract service priced by the day was picking up equipment fuel &
  maintenance. Rentals are now told from services by group, not by unit string.
- Seven-figure totals were being clipped by their stat cards — $1,335,790 read as
  $1,335,79.
- The grid's Save button could be re-fired on a detached handler after the
  re-render and create the same areas twice. Latched.

## Phase 4 — job-level extras (next)

Bond, CCIP / labor insurance, the cost-code rollup across sections.

The bond row is already on the paving sheet at 3% and priced $0 there, so it has
a home; CCIP has none yet. The cost-code rollup is the bigger piece: every sheet
maps its lines to the same 1000xx codes, and the codes are **mislabelled on both
sheets read so far** — read the rate block, not the label.

## Tools

- `run` / `run.ps1` — starts the API with the right flags, **refuses to start if
  something already holds the port**, and warns about unapplied migrations.
- `backend/dbquery.py --check sections|orphans|totals|migrations` — read-only.
- `backend/debug_section.py [section_id]` — runs labor, forming and equipment
  directly so a traceback prints instead of hiding behind a 500.
- `backend/apply_sql.py --status` — what is actually applied.

## The running theme

Three times in one day, a mysterious failure was new code meeting an old
something:

| | Stale thing | Symptom |
|---|---|---|
| Morning | uvicorn serving old code | endpoint 500s that survived a "fix" |
| Evening | schema without sql/034 | three endpoints 500 |
| Night | browser cache | new page "not showing" |

**Check what is actually running before reading a line of code.**
`apply_sql.py --status` for the schema, the OpenAPI schema or a known-changed
string for the server, `Ctrl+Shift+R` for the browser.
