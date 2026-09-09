# Daily reports from the field (sql/084, 2026-09-09)

## Why

Chad: "this is a daily reports for projects.. right now we use jotform then
import into notion", then "I think we need to just import everything from
jotform then set a form page to fill out here instead of the extra step of
importing"; on the proposal, "build it".

What the foremen fill in today is Jotform form `210626162682150`, "S and S
Daily Construction Report": bilingual, twenty-two questions, in use since
March 2021 (the newest submission the day before this was built). An older
twelve-question form, `210135509985156`, carried January to March 2021. A
07:35 timer on the office box copied each submission into a Notion
database. Notion is going, and the extra step with it.

## What was built

### The tables

* `field_jobs` and `field_foremen`: the two pick-lists the form offers,
  the way the Jotform dropdowns did. Seeded with the dropdowns as they
  stood on 2026-09-09 (fifteen jobs, ten foremen), added to by the import
  for every name it meets in an old report (those inactive, so they are
  kept but not offered), and kept by the office from the Daily reports page
  (add, rename, on or off the form). A job may point at the project it is;
  nothing depends on it.
* `daily_reports`: the day, the job, the foremen (the Jotform field allowed
  several on one report, and some carry four), the four texts, the pour
  block (poured, yards, supplier, what), tax exempt, the maintenance checks
  as keys, and where it came from: `app`, or `jotform` with the form and
  submission ids, the submission id unique so the hourly pull cannot double
  a report. The old form's "issues" and "progress/delays" fold into delays,
  its "comments/requests" into comments.
* `daily_report_crew`: the man-power grid, one row per trade;
  `daily_report_subs`: the sub-labor grid, one row per subcontractor crew.
  Each keeps workers and hours as entered and a `man_hours` figure.

### Man-hours

The app form asks hours EACH, so a row is workers × hours. The Jotform grids
said only "Hrs worked" and were filled both ways over the years: "3
workers, 30 hrs" in March 2021, "12 workers, 8 hrs" in September 2026. The
import reads a row's hours over sixteen as the row's total for the day and
anything else as hours each. Nobody works a seventeen-hour day. The totals
by job and month use `man_hours` and nothing else.

### The API

`/api/daily-reports`: the list newest first (job, foreman, dates, pours
only, a search across the texts), file, read, edit, delete; `/meta` for
what the form offers (the two lists with their report counts, the suppliers
— the Jotform six plus the catalog's active ones — the grids' rows and the
checks with both languages); `/summary` for reports, pours, yards and
man-hours by job and month; `/jobs` and `/foremen` to keep the lists —
add, edit, and delete (a job with reports must say which job they move
to first; a foreman's name may stay on the reports as typed or move to
another foreman, which is how a Jotform typo folds into the right name);
`/import` for raw Jotform submissions.

**Management notes** (sql/085; Chad: "another field only visible by
senior estimators and above.. called management notes"): a text column
the API returns only to senior estimators, management and admins and only
they may write — an estimator sending the key gets the 403 that names the
role, and everyone below a senior, foremen included, reads the report with
the field blank. The import never touches it. On screen: a box on the edit
form and a line in the report modal for those roles, nothing for the rest.
The **management** role (same commit) is a senior estimator by another
name: the same rank in `app/policy.py`, the same rights and refusals.

Deleting is a senior estimator's, here and everywhere whole (Chad,
2026-09-09: "estimators and lower.. no delete of anything"); an estimator
deletes only rows inside a takeoff, on estimates whose project lists
them (`app/ownership.py`).

### The foreman role

A fifth role, `foreman`, apart from the ladder (user, estimator, senior
estimator, admin each include the ones below): reads under
`/api/daily-reports` and files a report, nothing else — a foreman asking
for an estimate gets the 403 that names both roles. The nav shows a
foreman one button, Daily report, and signing in lands there. The office
makes the accounts from Estimators with the role, and sets the passwords.

### The pages

* **Daily reports** (the office): the reports newest first with the
  filters, a strip of totals for what is shown, the totals by job and month
  folded under it, the whole report in a modal (the grids with man-hours,
  the pour, every text, the checks, the signature link when Jotform had
  one), Edit and Delete for estimators and above, and the two pick-lists
  behind a Jobs & foremen button.
* **Daily report** (the form): the Jotform form rebuilt for a phone. One
  column, sixteen-pixel inputs so iOS does not zoom, big checkboxes, a
  language toggle that relabels in place without losing what was typed —
  the Spanish is the Jotform form's own. Date (today), job (the active
  list), the foremen as checkboxes (a foreman's own name preselected when
  it is on the list), the man-power grid (workers, hours each; a count typed
  with no hours beside it fills in eight), the sub-labor grid, the four
  texts, poured yes/no opening yards, supplier, what and tax exempt, the
  five checks, Send. Then "Report sent" with "Another report". The office
  edits a report through the same page.

### The import

`backend/import_daily_reports.py` on the box: both forms from the Jotform
API (the key from the env file the Notion importer read, never printed),
every submission normalised by question id — the date dict, the multi-value
dropdowns, the two grids with their bilingual and HTML-wrapped row labels,
the checks matched by their English word, yards parsed out of "42.5 yds" —
and upserted by submission id. A rerun: a submission unchanged in Jotform
is counted unchanged, whether or not the office edited the report here; one
changed in Jotform is updated when nothing was edited here, and skipped
when something was (the app's version stands). Jobs and foremen met for the
first time are added inactive. `--dry-run`, `--json-out` to keep the raw
fetch, `--from-json` to import a saved one.

On the box it runs hourly (`daily-reports-pull.timer`, a user unit) until
the crews use the app's form; the 07:35 Notion sync is retired.

## Tests

`backend/tests/test_daily_reports.py`: the form's payload files a report
with its grids and man-hours, an edit replaces the grid it sends and leaves
the other, delete; the list newest first and every filter; the totals by
job and month; the pick-lists (the seeds, add, case-insensitive duplicate a
409, off the form, report counts); the man-hours rule; the foreman role
(files, reads, and nine things it may not do, each a 403 naming a foreman,
plus the policy table); a viewer reads and does not write; a misspelled
field, an unknown check, an unknown trade a 422, an unknown job a 400; the
import of three submissions in the shapes the API returned on 2026-09-09
(both forms), the rerun, the edit-here cases, and what is not a report.
`test_forbid_and_the_screens.py` carries the form's payload as the phone
sends it; `test_auth.py` the policy rows.

## Not done here

* Photos on a report. Jotform had none either.
* A foreman editing their own report after sending; the office edits.
* The Notion "Daily Labor Reports" database (superintendent, labor
  breakdown, subcontractor hours): its source was never traced; nothing
  reads it.
* Retiring the Jotform form itself: once the foremen have accounts and the
  hourly pull has brought nothing new for a while.
