# `etakeoff_imports`

Audit trail for **eTakeoff Measurement List → CSV** imports: file name, mapping, preview, status. Does not yet store applied line items as separate quantity rows (those go into `mono_slabs` / `grade_beams` when applied).

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
| `estimate_id` | uuid | YES | | FK → `estimates` |
| `filename` | text | NO | | Original CSV name |
| `imported_by` | uuid | YES | | FK → `estimators` |
| `imported_at` | timestamptz | NO | `now()` | |
| `row_count` | integer | YES | | Rows in file |
| `column_map` | jsonb | YES | | eTakeoff column → system field |
| `status` | text | NO | `'pending'` | See check |
| `error_message` | text | YES | | Failure detail |
| `raw_preview` | jsonb | YES | | First N rows for mapping UI |

### Constraints

- PK: `id`
- CHECK: `status IN ('pending', 'mapped', 'applied', 'failed')`
- FK: `estimate_id` → `estimates(id)` ON DELETE SET NULL
- FK: `imported_by` → `estimators(id)` ON DELETE SET NULL

---

## Status flow (intended)

```
pending → mapped → applied
                 ↘ failed
```

---

## Example

```sql
INSERT INTO etakeoff_imports (
  estimate_id, filename, imported_by, row_count, status, column_map, raw_preview
) VALUES (
  (SELECT id FROM estimates LIMIT 1),
  'MeasurementList.csv',
  (SELECT id FROM estimators WHERE username = 'chad'),
  42,
  'pending',
  '{"Area":"square_footage","Thickness":"thickness_in"}'::jsonb,
  '[{"Area":9525,"Thickness":4}]'::jsonb
)
RETURNING *;
```

---

## Notes / TODO

- CSV parser + mapping UI not built.
- Consider storing full raw file path or blob later.
- Re-import / replace policy undecided.
