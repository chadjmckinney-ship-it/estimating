# The proposal — the estimate on the bid form (2026-09-08)

**Source:** the Sherry Pointe Apts 26-102 proposal of 2026-09-01 (`_02`) on
the NEW FORM of 2026-08-28, the blank `Proposal Template - NEW FORM.xlsx`,
and the vault's Proposal Section Library. **Chad, 2026-09-08:** "ok,
proposal? here is the latest proposal form we are using" — and, on the
proposal, "build it".

## What the form is

A header — submitted to, attention, email, date, job and number, location,
four drawings with their plan dates — then numbered lines under section
titles. Each line prints its number, description, quantity, unit and status
(INCLUDED or EXCLUDED); its unit price and extended sit in columns F and G
outside the print area, so the section totals and the lump sum print and the
rates behind them do not. Then the standing blocks — alternates, additional
equipment rates, additional labor rates, qualifications, exclusions — the
lump sum, six numbered terms, and the acceptance page. The money is live:
G is `=C*F`, a section total is `=SUM(G..)`, the lump sum adds the section
totals.

## What was built (`sql/080`)

* **One proposal per estimate.** The header (seeded from the project: the
  GC, the job and number, the location), a revision counter and a date. The
  file is named to the playbook's standard, `<Job Name> - Proposal - <Job #>
  - <YYYY-MM-DD>_<NN>.xlsx`; the revision is typed, never bumped by a
  download.
* **Seeded from the takeoff.** One proposal section per estimate section, in
  order, titled with the section's name. One line per costed row across the
  eight shapes — a pour, a pier group, a wall run, a column type, a deck
  level, a beam run, a panel type, a misc item — carrying the row's name, its
  quantity in the section's unit (a garden-style pour at all its buildings'
  SF), and its sale over its quantity to four places. A row at no quantity
  is not a line.
* **Every line remembers its row.** A refresh re-reads the quantity, unit
  and price onto every seeded line and keeps its description, status and
  notes; a new row becomes a new line, a new estimate section a new proposal
  section; a row that is gone flags its line rather than deleting it. A line
  typed by hand — haul-off, certified payroll, pumping — has no row and is
  never touched.
* **The tie-out.** Beside each section, the estimate section's sale against
  the proposal section's total; at the top, the job against the form. A
  fresh seed differs only by the rounding of a unit price to four places.
* **Excluded is a status, not a deletion.** The line keeps its quantity on
  the form and prices nothing — measured and excluded, not missed. The
  takeoff row behind it still prices; the estimate is untouched.
* **The standing text is a library under Settings**, seeded from the Sherry
  Pointe form as Chad uses it today (less the job-specific sales tax
  deduction). A new proposal copies it; a proposal already made keeps its
  own copy. A senior estimator edits the library; the day and hour rates in
  it are prices.
* **The download** builds the workbook cell for cell to the NEW FORM —
  fonts, fills, borders, widths, row heights and page setup read off the
  template — with the print area stopping at E. Wrapped rows are given their
  height, since Excel does not re-fit on open.

## The page

`Proposal` on the estimate page. A header form with the drawings; a sections
grid (title, order, lines, proposal against estimate); one lines grid per
section (description, quantity, unit, status, unit price, extended, and
where the line came from); the six standing blocks as text, one bullet per
line; Refresh from estimate; Download .xlsx.

## Held

`tests/test_proposals.py`: the seed across three shapes with the tie-out;
the refresh moving numbers and keeping words; the grids, the blocks, the
header and the file name; every write model refusing a misspelled field;
the workbook read back — the letterhead, the header row, `=C*F`, `=SUM`,
the lump sum over three section totals, the blocks and the acceptance page
in order, the print area at E, an excluded line with its quantity and no
price; the library's roles.

## Left alone

An excluded flag on the takeoff row itself; a Word or PDF form; eTakeoff.
The workbook's `COST` sheet is not carried — it is the supplier rate book,
and the catalog is that here.
