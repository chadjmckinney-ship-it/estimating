# `system_settings`

Key/value store for **company defaults** used by calculations (waste factors, lb/SF rates). Per-estimate overrides live on `estimates.waste_*`.

| | |
|--|--|
| **Type** | Table |
| **Created in** | `sql/001_schema.sql` |
| **Seeded** | Yes — 5 keys |

---

## Columns

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| `key` | text | NO | | PK |
| `value` | jsonb | NO | | Flexible scalar/object |
| `description` | text | YES | | Human note |
| `updated_at` | timestamptz | NO | `now()` | |

### Constraints

- PK: `key`

---

## Seeded keys

| Key | Value | Description |
|-----|-------|-------------|
| `waste_concrete` | `0.05` | Default concrete waste (5%) — **TBD confirm** |
| `waste_sand` | `0.05` | Default sand waste — **TBD confirm** |
| `waste_rebar` | `0.00` | Default rebar waste — **TBD confirm** |
| `pt_lb_per_sf` | `1.0` | PT cable quantity: SF × rate (lb/SF) |
| `support_rebar_lb_per_sf` | `1.0` | Slab support rebar: SF × rate (lb/SF) |

Values are JSON numbers; cast when reading:

```sql
SELECT key, value, value::text::numeric AS as_numeric
FROM system_settings
ORDER BY key;
```

---

## Relationships

None (global). Read by app when estimate waste columns are NULL.

---

## Example

```sql
-- Update waste after field decision
UPDATE system_settings
SET value = '0.07'::jsonb, updated_at = now()
WHERE key = 'waste_concrete';

SELECT * FROM system_settings;
```

---

## Notes / TODO

- Confirm all defaults with field/estimating practice (mono.md open decisions).
- No history of setting changes yet.
