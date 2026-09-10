# The estimate Summary — the workbook's Summary tab (2026-09-09)

**Source:** the `Summary` tab of the LBJ workbook (`Trammel Crow - LBJ
Estimate.xlsm`), its JOB COST SUMMARY (rows 9–63) and its COST CODES (rows
72–131), and each section tab's own cost-code column (the PT slab tab's
E120:E177), which is where the tab says which line goes under which code.
**Chad, 2026-09-09:** "there is something missing that the office uses
from the estimates.. a summary like that is in the excel spreadsheet..
pulls all the materials form each section, supervision, everything thats
in a project.. a total of each the a breakdown per section.." — and, on the
proposal, "build it".

## What the tab is

Two tables. The **JOB COST SUMMARY**: a row per section with its quantity,
its sale, and fifteen money columns — FORMS & ACCESSORIES, GRADE MATERIAL,
POLY / SEALING, PT CABLES, REBAR, REBAR ACCESSORIES, CONCRETE, SEAL / WTR
PRF / CURE, OTHER SUBS, SUB LABOR, LABOR, SUPV, PM, EQUIP, OUT OF TOWN — a
`$ /SF` line under each section, the TOTALS, each column's share of the
price, then TOTAL MATERIAL (the eight material columns), TOTAL LABOR (the
in-house column), TOTAL SUB LABOR (sub labor and the other subs), TOTAL
OTHER (out of town, equipment, supervision, PM), Margin Contingency, and
ESTIMATED PROFIT as the contract price less all of it. A LABOR INSURANCE
line notes 2.5% of sub labor, labor and supervision without deducting it.

The **COST CODES**: the chart from 000001 General Requirements to 000091
Margin Contingency (Material 1–15, Supervision 20–22, In-house labor 23–28,
Contract services 30–39, Sub labor 40–49 with 000040 a subtotal, Equipment
60–68 with 000060 a subtotal, Travel 70, Miscellaneous 71–73, Not Used 90,
Margin Contingency 91), a Summary column and a column per section. Each
tab's own column files its lines: the whole lumber block under Lumber, the
sand under Sand, rebar and mesh under Reinforcement Material, the chairs,
tie wire and accessories under Reinforcement Accessories, the cables under
PT Cables, the mixes under Concrete, cure under Cure/Sealers, the
superintendent and foreman under Supervision, the expense under Supervision
Expense, the PM under Project Management, the in-house lines under 23–27
(grading → 23, place & finish → 24, drops → 25, wreck → 26), the subbed
lines under 41–49 (forming → 41, grading → 42, place & finish → 43, drops →
44, wreck → 45, labor add → 46, tie steel → 47, PT install → 48, extra
hours → 49), the pump under Pumping, haul off under Haul off, saw cutting
under Saw Cutting/Sealing, each rental under its machine with the rentals'
uplift under Fuel, out of town under 70, engineering under 73, and the
tab's Margin Contingency line under 000091. The tab checks itself: E118 is
the sum of the codes less the section's total cost, and reads zero.

Two things the tab does that the app does differently, on purpose:

* **Tax.** The tab multiplies every purchase and rental by `(1 + tax +
  fuel)`, so its material figures are tax-inclusive. The app keeps sales
  tax per row (`calc_tax`) and fuel & maintenance per row
  (`calc_equip_fuel`). The summary shows the purchases at what they cost,
  a SALES TAX column of its own after the fifteen, and files the fuel under
  000066 Fuel the way the tab files the rentals' uplift.
* **Margin Contingency.** The tab's 000091 is the contingency dollars only
  — its G110 is the section's cost times Summary!P60, the contingency rate
  — and ESTIMATED PROFIT is what is left: the margin. A section here sells
  at cost × (1 + margin + contingency), so 000091 is the contingency's
  share of the markup, (sale − cost) × c ÷ (m + c): cost × c on every
  section but a miscellaneous one, whose sale is typed and whose markup is
  whatever falls out (the misc tab's W column makes the same division).

## What was built (`sql/088`)

* **`cost_codes`** — the chart, 58 codes, each with its category, the
  job-cost column it feeds (`summary_column`, NULL for the two subtotals,
  Not Used and 000091), and its order.
* **`cost_code_lines`** — where each line the app prices is filed, by
  `(line_kind, line_code)`: a `purchase` the material-costs reader reports
  (concrete, wall_concrete, footing_concrete, rebar, mesh, pt, sand, poly,
  tape, weld_plates, drilling, and `rounding`, that reader's per-row
  cents, filed with the concrete), a forming `material` line by its code,
  a `labor` line by its code with an `inhouse_code` where the chart has one
  (grading, layout, backfill, excavation → 000023; place & finish, rub &
  patch → 000024; drops → 000025; wreck, cleanup → 000026; labor add →
  000027; tie steel, rebar, stud rails, cable placement → 000023), an
  `equipment` line by its code, a `misc` item's typed allowance (forms →
  Lumber, labor → 000041 or 000024 in house, supervision → 000020,
  equipment → 000064 Skid Steer, where the tab puts it), and the `uplift`
  `fuel` → 000066. Every code the three services write today is seeded;
  the matrix test builds all thirteen shapes and fails on the first line
  with no home.
* **The reader, `services/cost_summary.py`.** Nothing is priced. A
  section's lines are: the purchases from `material_costs`, a misc item's
  four allowances, the enabled lines of the three stored line sets at
  their `ext_cost` (what `costing._on_takeoff_lines` allocated), the fuel
  read back off the rows, and the tax. Each line takes its code from the
  table, and its column from the code — except field labor, which lands in
  LABOR or SUB LABOR by the section's `labor_subcontracted` whatever its
  code, since the chart has no in-house forming code and in-house forming
  is still in-house labor. A line the table does not know is UNASSIGNED:
  counted in a column of its own so the section still ties, and named. The
  section's columns add to its stored cost; the gap is `difference` — the
  per-row rounding, cents — and is shown, never smeared. A section whose
  line sets were never built says so (`missing_line_sets`); its cost is
  missing the same money, because costing reads the same stored rows.
* **`GET /api/estimates/{id}/summary`** — every section's money by column
  and by code, the per-unit figures, the totals, each column's share of
  the price, the lower block, the chart. **`GET
  /api/estimates/{id}/summary.xlsx`** — the tab, one sheet: the header,
  the job-cost table with a `$ / unit` line under each section, the
  TOTALS and the shares as formulas, the lower block as formulas, the cost
  codes with a Summary column (`=SUM` across the sections), the two
  subtotals as formulas over their block, then the tax, the total cost, the
  sale and the profit under it. Named `<Job> - Summary - <Job #> -
  <YYYY-MM-DD>.xlsx`, the proposal's pattern.
* **`GET /api/cost-codes`** — the chart and every line the summary can
  meet: the lines some section carries today, the purchases and allowances
  the readers report, and anything the table names, each with its code.
  **`PUT /api/cost-codes/lines/{kind}/{code}`** — a senior estimator files
  a line (a subtotal is refused; an in-house code only on a labor or misc
  line). The summary reads the table live, so every job follows; nothing
  is repriced.
* **The screen.** A **Summary** button on the estimate page beside
  Proposal, to a page of its own (`#summary/<estimate>`): the four cards
  (contract price, total cost, estimated profit, margin contingency), the
  job-cost table with a `$ / unit` line under each section and the shares
  under the totals, the lower block, the cost codes with a column per
  section (empty codes hidden until asked for), a banner naming any
  unassigned line and any section never opened, and Download .xlsx. Under
  **Settings → Cost codes**, every line with a select for where it is
  filed and, on a labor line, its in-house code; a filter box; Save per
  line for a senior estimator, read-only below.

## What it deliberately does not do

* It does not reprice anything, and it does not read a line set the
  section has not built — that would put money on the summary that is not
  in the section's cost.
* It has no bond line (the tab's E54, off by default) and no CCIP value.
* It does not spread a misc item's labor over the eight sub-labor codes
  the way the misc tab does (`=E80/8` each); the labor is one line, under
  000041 Labor Forming, or 000024 Place & Finish in house. Refile it from
  Settings if the office wants it elsewhere.

## Tests

`backend/tests/test_cost_summary.py`: the thirteen-shape matrix (every
line has a home, the columns and the codes add to the stored cost, profit +
contingency + cost = sale, the subtotals are their blocks); the slab's
columns against its purchases and its lines; the Y/N swap moving labor
between columns and code blocks without moving a dollar; the job adding
its sections and the lower block's identities, with 000091 checked on
every section including the misc one; a senior refiling a line and every
summary following, with the refusals (estimator, user, a code that is not
one, a subtotal, an in-house code on a machine, a misspelled body); an
unknown line counted as UNASSIGNED and named; a section never opened; the
.xlsx as the tab.
