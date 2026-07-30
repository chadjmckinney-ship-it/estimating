# `estimates`

A versioned estimating package under a project (e.g. “Base bid”, “VE option”, rev 2). Holds optional **waste overrides**; NULL means use `system_settings`.

| | |
|--|--|
| **Type** | Table |
| **Created in** | `sql/001_schema.sql` |
| **Seeded** | No (empty) |

---

## Columns

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| `id` | uuid | NO | `gen_random_uuid()` | PK |
| `project_id` | uuid | NO | | FK → `projects` |
| `name` | text | NO | | Estimate name |
| `status` | text | NO | `'draft'` | See check constraint |
| `estimator_id` | uuid | YES | | FK → `estimators` |
| `version` | integer | NO | `1` | With name, unique per project |
| `waste_concrete` | numeric(6,4) | YES | | Override; e.g. `0.05` = 5% |
| `waste_sand` | numeric(6,4) | YES | | |
| `waste_rebar` | numeric(6,4) | YES | | |
| `notes` | text | YES | | |
| `created_at` | timestamptz | NO | `now()` | |
| `updated_at` | timestamptz | NO | `now()` | |

### Constraints

- PK: `id`
- UNIQUE: `(project_id, name, version)`
- CHECK: `status IN ('draft', 'in_review', 'final', 'archived')`
- FK: `project_id` → `projects(id)` ON DELETE CASCADE
- FK: `estimator_id` → `estimators(id)` ON DELETE SET NULL
- Index: `estimates_project_id_idx`

---

## Relationships

| Direction | Table | On delete |
|-----------|-------|-----------|
| → | `projects` | CASCADE (estimate goes with project) |
| → | `estimators` | SET NULL |
| ← | `mono_slabs` | CASCADE |
| ← | `supplier_bids` | CASCADE |
| ← | `etakeoff_imports` | SET NULL |

---

## Example

```sql
INSERT INTO estimates (project_id, name, status, estimator_id, version)
VALUES (
  (SELECT id FROM projects WHERE name = 'Pearl Landing'),
  'Mono Slab base',
  'draft',
  (SELECT id FROM estimators WHERE username = 'chad'),
  1
)
RETURNING *;

-- Use system default waste when override is NULL
SELECT id, name, status,
       coalesce(waste_concrete,
         (SELECT value::text::numeric FROM system_settings WHERE key = 'waste_concrete')) AS waste_c
FROM estimates;
```

---

## Notes / TODO

- Status workflow not enforced beyond allowed values.
- Waste defaults still placeholders — see `system_settings` and mono.md open decisions.
