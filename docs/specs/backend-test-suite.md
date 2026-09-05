# Backend test suite (2026-08-30)

64 pytest tests for the estimating app backend, in `~/Estimate_Projects/backend/tests/`.

## Running

```bash
cd ~/Estimate_Projects/backend
../.venv/bin/pip install -r requirements-dev.txt
../.venv/bin/pytest                     # builds estimating_test on first run
REBUILD_TEST_DB=1 ../.venv/bin/pytest   # rebuild from sql/ first
../.venv/bin/python tests/dbsetup.py    # rebuild only
```

`TEST_DATABASE_URL` overrides the target (default `postgresql+psycopg2:///estimating_test`).

## Safety

Two guards keep the live bids out of reach:

1. `dbsetup.test_database_url()` raises unless the database name ends in `_test`.
   Pointing the suite at `estimating` fails at collection.
2. Each test runs on a connection whose outer transaction the test owns, with the
   session in `join_transaction_mode="create_savepoint"`. The services call
   `db.commit()` themselves; those commits release savepoints, and the outer
   rollback still undoes everything. Verified: after a full run the test database
   has zero projects/estimates/pours/labor lines and untouched `system_settings`.

## Files

| File | Covers |
|------|--------|
| `dbsetup.py` | Builds `estimating_test` by applying every `sql/*.sql` in filename order |
| `conftest.py` | Engine, rolled-back session, and estimate/pour/beam-type factories |
| `test_calc_functions.py` | Golden numbers for the nine locked SQL helpers (23 tests) |
| `test_pour_calcs.py` | `refresh_mono_slab_calcs` — CY, mat + support steel, poly, PT, beam rollups, overrides (16) |
| `test_staleness.py` | "Edit X, assert Y follows" — the stored-not-derived traps (14) |
| `test_costing.py` | Pre-existing pure allocation/markup helpers, no DB (11) |

## Fixture pour

10,000 SF, 5" slab on 2" sand, #4 mat @ 18" o.c., no PT, seeded company defaults
(5% concrete waste, 5% sand, 0% rebar, 10% poly, 0.1 lb/SF support). Default beam
type: 12" × 24", 3-#5 top and bottom, #3 stirrups @ 18", 200 LF. Every expected
value is hand computed from those numbers and written out in the assertion.

## Regression tests for the three shipped bugs

- Changing `estimates.waste_concrete` rewrites every pour, slab CY and beam CY.
- `PATCH /system-settings/{key}` rewrites affected pours and stored labor lines;
  `recalc=false` returns the "now stale" note and leaves them alone.
- Editing a beam type or a usage length rewrites the pour and the labor takeoff.
- `is_manual` lines survive a recalc — and freeze their qty as well as their rate.
- `recalc_estimate` does not conjure takeoffs for an estimate nobody has costed.

## Verified by injecting a fault

Removing the stirrup hook allowance from `calc_stirrup_lb` in the test database
turned four tests red across three layers (SQL helper, pour rollup, labor tie-steel
line). `REBUILD_TEST_DB=1` restored green.

## Side finding

Migrations `001`–`026` apply cleanly in filename order to an empty database,
including the two files sharing the `015_` prefix (forming, then poly-sides-only).
Nothing yet records which migrations a given database has had applied.

## Still untested

Forming and equipment **line formulas** (the tests prove they refresh, not what
they compute), the routers, and `costing.refresh_pour_costs`.
