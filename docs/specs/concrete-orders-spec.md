# Concrete orders (sql/086, 2026-09-09)

## Why

Chad: "another section under daily reports... 'concrete orders' basically
like a daily report.. Date ordered, dropdown for job, concrete supplier,
date of pour, Time of pour, Yards ordered, mix design, order number, ordered
by. then the list and calender." On the mix design: "mix design will be
entered... each supplier has mix numbers" — so the mix is text as typed,
the supplier's own number, not a link to the catalog. Then "build it".

## What was built

### The order

`concrete_orders`: date ordered (today when left blank), the job from the
daily report form's list, the supplier from the same list (the Jotform six
plus the catalog's active ones), pour date and time, yards (more than
zero), the mix as typed, the order number, ordered by (the signed-in person
when left blank), notes, and a status — ordered, confirmed, poured,
canceled — so a canceled pour stays on record and off the calendar. Who
filed it is kept apart from who ordered it.

### The API

`/api/concrete-orders`: the list by pour date and hour (job, supplier,
status, pour-date window, a search across the job, supplier, mix, order
number, ordered by and notes), file, read, edit, delete; `/meta/statuses`.
The job and supplier lists come from `/api/daily-reports/meta`. A blank on
an edit never empties what an order must have (job, supplier, pour date,
yards).

Who may: the foreman role files and reads orders as it does daily reports
(`app/policy.py`, the second field prefix); the office edits; deleting is a
senior estimator's, as everywhere.

### The pages

* **Concrete orders**, under the Daily reports group: soonest pour first,
  today's badged, the last seven days and everything ahead by default (or
  thirty, all time, a date range), filters for job, supplier and status
  (ordered + confirmed by default), a search, the yards totalled for what is
  shown, the status changed in the row, View (the whole order in a modal
  with Edit and, for seniors, Delete), Edit.
* **Concrete order**, the form: one phone-sized page like the daily report,
  English and Spanish on the same toggle. A foreman gets a "Concrete order"
  button beside "Daily report" and lands on either; the office reaches it
  from "+ New order". Date ordered, job, supplier, date and time of pour,
  yards, mix, order number, ordered by (prefilled with the signed-in
  person), notes; the status on an edit. Then "Order sent" with "Another
  order".
* **The calendar** shows orders on their pour date in blue beside the
  reports' green pours, with a switch for reports, orders or both, and the
  month's orders and yards ordered in the totals. A canceled order is not
  drawn; a poured one is dimmed. Clicking one opens the order.
* **The dashboard**'s field card adds the pours ordered for today and
  tomorrow with their yards.

## Tests

`backend/tests/test_concrete_orders.py`: an order with every field, the
blanks filled (today, the signed-in person), the statuses; the list by pour
date and hour and every filter; an edit, a blank keeping what the order must
have, an estimator's edit allowed and delete refused, a senior's delete; the
foreman files and reads and is refused an edit and a delete, with the policy
rows; a misspelled field, zero yards, a made-up status, a blank supplier
refused, an unknown job a 400. The screens test carries the form's payload
as the phone sends it; `test_auth.py` the policy rows.

### The morning email

Chad, the same afternoon: "is it possible to have it send an email daily
with a list of concrete orders for the next 7 days?" —
`backend/email_concrete_orders.py`, every morning at 06:30 on the box
(`concrete-orders-email.timer`), through the Outlook sender the bid email
uses: the next seven days a day at a time, TODAY and TOMORROW marked,
each order with its time, job, yards, supplier, mix, order number, who
ordered and when, status and notes, the totals at the top; canceled
orders left out; a week with nothing ordered still gets a message saying
so. `backend/tests/test_email_concrete_orders.py` pins the window and the
message. The runbook has the unit and the addresses.

## Not done here

* A link from an order to the daily report that reported the pour; the
  calendar puts them in the same cell, which is what was asked.
* Sending the order to the supplier; the order number is typed from the
  supplier's confirmation.
