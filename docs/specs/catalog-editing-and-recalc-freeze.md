# Editable catalogs + recalc freeze (2026-08-30)

## The reported problem

Mix designs, materials and equipment pricing couldn't be changed in the interface.

**Cause:** missing UI, not a missing backend. `PATCH /api/materials/{id}`,
`PATCH /api/equipment/{id}` and the full `/api/mix-designs` CRUD already existed;
`frontend/assets/js/api.js` only ever exposed `listMaterials`, `listMixes` and
`listEquipment`, and the three catalog pages rendered read-only tables.

## What changed

**Frontend** — all three catalog pages now edit, add and deactivate/reactivate,
with a show-inactive toggle. The mix page also opens a per-supplier $/CY grid
(add / edit / remove quotes) that states which basis costing will use: the mix's
own unit cost, else the cheapest quote, else $0. Shared `openRowModal()` helper
drives every form.

**Backend gaps filled** — `POST` and `DELETE /api/materials` (soft delete),
a wider `MaterialUpdate`, and `DELETE /api/mix-prices/{id}`.

**Bug fixed** — modals hang off `document.body` and survived page changes.
`closeAllModals()` now runs on navigation (not on `render()`, since some modals
re-render the page behind themselves while staying open) and Escape closes them.

## The recalc freeze — Chad's rule

Catalog prices feed stored estimate costs; costing reads them at recalc time.
A price edit therefore had to be decided, not defaulted. Chad: *"I don't want it
to recalculate on estimates I am not currently working on so an older project
that we have already completed doesn't change the cost later. Should be a button
for updating."*

Implemented against the existing `estimates.status`:

- Catalog `PATCH` never recalculates. A **Reprice open estimates** button on each
  catalog page calls `POST /api/system-settings/recalc-all`.
- `recalc_all_estimates()` touches `draft` and `in_review` only. `final` and
  `archived` are frozen, skipped, and returned by name in the response's
  `skipped` list.
- **This also fixed existing behavior**: `PATCH /api/system-settings/{key}` used
  to rewrite every estimate, archived ones included — a labor-rate change moved
  bids that had already gone out.
- Two deliberate overrides: `recalc-all?include_frozen=true`, or an estimate's
  own `POST /api/estimates/{id}/recalc`, which always runs.
- A direct edit to an estimate still recalculates it whatever its status — a
  frozen estimate that disagrees with its own inputs is worse than one that moved.

`backend/tests/test_recalc_freeze.py` covers all of it (10 tests; suite now 74).

## Finding: concrete is priced at $0/CY

All 16 mix designs have `unit_cost` NULL **and** zero rows in `mix_prices`, so
`_mix_unit_cost()` returns 0 and `costing._direct_cost` adds nothing for concrete.

On `04-PT Slab on Grade`: 17 pours, 2,161.75 CY, total cost $370,854.93 — with
zero dollars of concrete inside it. At ~$150/CY that estimate is roughly $324k
light. Suppliers Argos, Martin Marietta and SRM exist with no quotes against them.

Fixable from the new Mix designs page: enter a unit cost per mix or the
per-supplier quotes, then Reprice open estimates. Logged in `docs/todo.md` under
"Live data problems".
