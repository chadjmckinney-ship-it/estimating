# Database Notes

General notes for the local **PostgreSQL** estimating database.  
Design rules for Mono Slab live in [mono.md](./mono.md). Materials catalog: [materials.md](./materials.md). Per-table docs: [tables/](./tables/). Feature backlog: [todo.md](./todo.md).

**Last updated:** 2026-07-28

---

## Connection

| Item | Value |
|------|--------|
| Host | localhost (this laptop) |
| Database | `estimating` |
| Owner / app user | `chad` |
| Auth | Peer (local `psql` as OS user `chad`) |
| Server target (later) | Office Fedora box — same schema, migrate when ready |

```bash
psql -d estimating
```

---

## Schema migrations

Scripts are ordered and applied manually for now:

| File | What it does |
|------|----------------|
| `sql/001_schema.sql` | Core Mono Slab schema, bar weights, calc functions, supplier variance view |
| `sql/002_materials.sql` | `materials` table + Pricing-tab seed (58 rows) |
| `sql/003_estimators_expand.sql` | Estimator role/phone/title/notes + seed `chad` as admin |
| `sql/004_projects_from_notion.sql` | Projects = Notion bid list fields; `project_estimators`; seed Edward/Sam/Henry |
| `sql/005_mix_designs.sql` | Expand mix_designs; concrete_suppliers; mix_prices |
| `sql/006_mix_designs_sc_ash_air.sql` | Mix matrix: SC / ASH / Air-ASH per PSI + 3000 integral color |
| `sql/007_materials_from_new_current.sql` | Materials prices/items from New Current Worksheet Pricing |
| `sql/008_equipment.sql` | Equipment rental catalog + seed from Pricing |

```bash
# Fresh laptop install
psql -d postgres -c 'CREATE DATABASE estimating OWNER chad;'
psql -d estimating -f ~/Estimate_Projects/sql/001_schema.sql
psql -d estimating -f ~/Estimate_Projects/sql/002_materials.sql
```

**Reset (destroys all data):**

```bash
psql -d postgres -c 'DROP DATABASE estimating;'
psql -d postgres -c 'CREATE DATABASE estimating OWNER chad;'
psql -d estimating -f ~/Estimate_Projects/sql/001_schema.sql
psql -d estimating -f ~/Estimate_Projects/sql/002_materials.sql
```

> Re-running `001` / `002` on an existing DB will fail on “already exists”. Prefer new numbered scripts for changes (`003_….sql`) once we have real data.

---

## Current tables

| Table | Role | Seeded? |
|-------|------|---------|
| `estimators` | People who create estimates | chad, edward, sam, henry |
| `projects` | Job/bid header (Notion-shaped) | sample rows via API |
| `project_estimators` | Assigned estimators M2M | |
| `estimates` | Versioned estimate under a project | empty |
| `mono_slabs` | Main slab quantity inputs + stored calcs | empty |
| `grade_beams` | Bar schedule per mono slab | empty |
| `bar_weights` | #3–#11 lb/ft | **9 rows** |
| `mix_designs` | SC / ASH / Air-ASH × PSI + 3000 integral color | **16 rows** |
| `concrete_suppliers` | Ready-mix companies | Martin Marietta, SRM, Argos |
| `mix_prices` | Supplier $/CY | empty until re-quoted |
| `materials` | Unit-price catalog (New Current Worksheet) | **72 active** (+3 inactive) |
| `equipment` | Rental rates from Pricing | **16 rows** |
| `supplier_bids` | Quoted rebar/PT vs calc | empty |
| `etakeoff_imports` | CSV import audit / mapping | empty |
| `system_settings` | Waste factors, PT & support rebar rates | **5 keys** |

**View:** `supplier_bid_variance` — calculated totals vs each supplier quote.

---

## Locked calculation functions

| Function | Formula / behavior |
|----------|--------------------|
| `calc_concrete_cy(sf, thickness_in, waste)` | `(SF × thk/12/27) × (1+waste)` |
| `calc_sand_cy(sf, sand_thickness_in, waste)` | same pattern for sand |
| `calc_support_rebar_lb(sf, lb_per_sf)` | default 1.0 lb/SF |
| `calc_pt_cable_lb(sf, post_tension, lb_per_sf)` | 1.0 lb/SF if PT else 0 |
| `calc_long_bar_lb(count, size, length_lf)` | count × LF × bar weight |
| `calc_stirrup_lb(...)` | **provisional** — count from spacing; perimeter + 0.5 ft hook allowance |

Defaults for waste / lb-per-SF live in `system_settings` and can be overridden per `estimates` row (waste columns).

```sql
SELECT key, value FROM system_settings ORDER BY key;
SELECT * FROM bar_weights ORDER BY bar_size;
SELECT calc_concrete_cy(1000, 5, 0.05);
```

---

## Design shape (important)

We did **not** implement the generic assembly engine sketched in mono.md yet.

| mono.md concept | Current physical tables |
|-----------------|-------------------------|
| projects | `projects` |
| project assemblies / quantities / results | `mono_slabs` + `grade_beams` + `calc_*` columns |
| users + roles | `estimators` only (no roles) |
| rate_tables | partial → `materials`, `mix_designs` |
| cost_codes | `materials.code` reserved, empty |
| etakeoff_imports | `etakeoff_imports` |

Mono Slab first is intentional. A later migration to generic `assemblies` is possible once more types (paving, sidewalks, etc.) force it.

---

## Materials source

- Workbook: `workbooks/Downloads/Updated Estimate Worksheet.xlsm`
- Sheet: **Pricing**
- Whitecap lumber/access list dated **2025-05-12**
- Names kept as in Excel (including spellings like POLSTERS, ROCK DELEVERED) — ROCK DELEVERED became ROCK DELIVERED PER CY on 2026-09-05 (`sql/061`), and the sand row PER CY the same day (`sql/060`)

**Not in `materials` yet:** equipment day rates, Metro saw/joint prices, concrete supplier mix bid grid (Martin Marietta columns, etc.).

---

## Excel reference workbooks

All under `~/Estimate_Projects/workbooks/`. Most relevant for SOG / Mono:

- `Pearl_Landing/SOG and Paving Estimate Sheet.xlsm`
- `Downloads/Updated Estimate Worksheet.xlsm` (Pricing master used for materials)

Originals also remain in `~/Estimate/`, `~/Pearl Landing/`, etc.

---

## Conventions

- Money / unit costs: `numeric(12,4)` or similar — no float
- IDs for transactional rows: `uuid` + `gen_random_uuid()`
- Reference lists: `serial` is fine (`materials`, `mix_designs`)
- Timestamps: `timestamptz` with `now()` defaults
- Soft flags: `is_active` rather than hard deletes on catalogs
- Calc results may be stored on the row for history/reporting; functions remain source of truth for the formula

---

## Quick useful queries

```sql
-- Catalog by category
SELECT category, count(*) FROM materials GROUP BY 1 ORDER BY 1;

-- Full materials list
SELECT id, category, name, unit, unit_cost, unit_note
FROM materials ORDER BY sort_order;

-- Empty operational tables (expect 0 until we seed a sample job)
SELECT 'projects' AS t, count(*) FROM projects
UNION ALL SELECT 'estimates', count(*) FROM estimates
UNION ALL SELECT 'mono_slabs', count(*) FROM mono_slabs;
```

---

## Open technical risks

1. **Stirrup formula** is provisional — confirm hooks/perimeter with field practice before locking.
2. **L-bar weight** has columns but no dedicated calc function yet.
3. **Waste factors** are placeholders (5% concrete/sand, 0% rebar).
4. **PT at 1.0 lb/SF** — confirm; Pricing also has PT as **$/SF** (`POST TENSION CABLES` material) which is a unit-cost, not the quantity rule.
5. No migration tool (Alembic/Flyway) yet — numbered SQL files only.
6. ~~No backup job on the laptop DB~~ **Backups, since 2026-09-05** (Chad:
   "lets do the pg_dump backups"). `backend/backup_db.py` dumps the app's
   DATABASE_URL with `pg_dump -Fc` to `~/Backups/estimating/`, proves the
   dump reads with `pg_restore --list`, keeps the newest 30, and can copy
   each dump to a second disk (`--copy-to`, OneDrive). `apply_sql.py` takes
   one before every migration it applies (`--no-backup` to go without).
   `python backend/register_backup_task.py` registers the daily Task Scheduler
   job — Python, not PowerShell, so the execution policy is not in the way.

```bash
python backend/backup_db.py                 # now
python backend/backup_db.py --list          # what is there
python backend/backup_db.py --restore-help  # into a NEW database first, look, then swap
```
