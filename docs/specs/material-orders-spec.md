# Material orders (sql/087, 2026-09-09)

## Why

Chad: "the next section... this is going to be like concrete orders.. but
materials.. mostly to track post tension and rebar for projects.. so
actually concrete orders should be there too..."; on the shape, "build it".
So the dock gains an **Orders** group holding Concrete orders and Material
orders, and this is the material side.

## What was built

### The order

`material_orders`: the kind — rebar, post-tension, other — the date ordered
(today when left blank), the job from the daily report form's list, the
supplier as typed (rebar and post-tension come from different houses than
concrete, so the ones used before are offered rather than a fixed list),
what it is in words — sizes, lengths, the shop-drawing reference — a
quantity and its unit (uppercased: LB, TON, EA, LF, SF, BUNDLE...), needed
on site by, delivered on (filled with today when the status turns
delivered and no date was given), the order number, ordered by (the
signed-in person when left blank), notes, and a status: ordered,
confirmed, delivered, canceled.

### The API

`/api/material-orders`: the list by needed-by date, nothing needed last
(kind, job, supplier, status, needed-by window, a search across the job,
supplier, description, order number, ordered by and notes), file, read,
edit, delete; `/meta` for the kinds in both languages, the units, the
statuses and the suppliers used before, most recent first; `/summary` for
what each job has ordered by kind and unit, canceled left out — the
tracking the section is for. A blank on an edit never empties what an
order must have. The foreman role files and reads here as with daily
reports and concrete orders; the office edits; deleting is a senior's.

### The pages

* **Material orders**: needed-by first with today badged and a late badge
  on anything past its date and not delivered, filters for kind, job,
  supplier, status (ordered + confirmed by default) and dates, a search,
  the quantities totalled by unit for what is shown, a **By job** fold with
  the summary, the status changed in the row, View (the whole order in a
  modal with Edit and, for seniors, Delete), Edit.
* **Material order**, the form: the same phone page as the other two,
  English and Spanish, the kind chosen first, the supplier and unit offered
  from what was used before. Foremen get its button beside Daily report and
  Concrete order; the office reaches it from "+ New order".
* **The calendar** draws deliveries on their needed-by date in amber beside
  the blue ordered pours and the green reported ones; the switch offers
  everything, reports only, concrete orders only, deliveries only. A
  delivered order is dimmed, a canceled one not drawn.
* **The dashboard**'s field card adds the deliveries due today and
  tomorrow.
* **The 6:30 email** gains a section, "materials due on site" for the next
  seven days, with the kind, job, what, quantity, supplier, order number,
  who ordered and the status; delivered and canceled left out. A week with
  no pours but deliveries still goes, saying "no pours".

## Tests

`backend/tests/test_material_orders.py`: an order with every field, the
blanks filled, the unit uppercased, delivered filling its date; the list by
needed-by and every filter; the summary by job, kind and unit and the meta
with the suppliers most recent first; an edit, a blank keeping what the
order must have, the delete rule; the foreman; what is refused (a
misspelled field, a made-up kind, a negative quantity, a made-up status, a
blank description, an unknown job). `test_email_concrete_orders.py` gains
the deliveries section; the screens test the form's payload; `test_auth.py`
the policy rows.

## Not done here

* Matching what a job ordered against its estimate's takeoff (rebar
  tonnage, PT footage) — the summary by job and unit is the half of that
  which exists now; the other half is the estimate's figure beside it.
* A price on an order; the supplier's invoice is where that lives today.
