# `materials`

Company-wide **unit-price catalog** from the estimate workbook Pricing tab (Whitecap lumber/accessories + steel/mesh/PT/sand rates).

| | |
|--|--|
| **Type** | Table |
| **Created in** | `sql/002_materials.sql` |
| **Seeded** | Yes — **58 rows** |
| **Browse full list** | [../materials.md](../materials.md) |

---

## Columns

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| `id` | serial | NO | nextval | PK |
| `code` | text | YES | | Cost code (reserved, mostly empty) |
| `name` | text | NO | | Material name as in Excel |
| `category` | text | NO | | See allowed list |
| `unit` | text | NO | | LF, SF, LB, EA, BOX, … |
| `unit_cost` | numeric(12,4) | YES | | Default unit price |
| `unit_note` | text | YES | | Pack/size note |
| `description` | text | YES | | Extra detail |
| `supplier_ref` | text | YES | | e.g. Whitecap |
| `price_as_of` | date | YES | | Price date |
| `is_active` | boolean | NO | `true` | |
| `sort_order` | integer | NO | `0` | Display order |
| `source_sheet` | text | YES | `'Pricing'` | Excel sheet |
| `source_row` | integer | YES | | Excel row |
| `created_at` | timestamptz | NO | `now()` | |
| `updated_at` | timestamptz | NO | `now()` | |

### Constraints

- PK: `id`
- UNIQUE: `code` (when set)
- UNIQUE: `(name, unit)` — allows same name with different units (e.g. FOAM FILL VOID EA vs CF)
- CHECK: `category` in  
  `lumber`, `form_accessories`, `structural_accessories`, `site_accessories`,  
  `vapor_barrier`, `foam`, `steel`, `mesh`, `pt`, `aggregate`, `chemical`, `other`
- Indexes: `category`, `name`

---

## Category counts (seed)

| Category | Count |
|----------|------:|
| lumber | 18 |
| structural_accessories | 12 |
| site_accessories | 6 |
| vapor_barrier | 5 |
| steel | 5 |
| chemical | 3 |
| mesh | 3 |
| aggregate | 2 |
| foam | 2 |
| form_accessories | 1 |
| pt | 1 |

---

## Relationships

Standalone catalog for now — not FK’d from `mono_slabs` yet (mesh gage, rebar unit price, etc. can link later).

---

## Example

```sql
SELECT category, name, unit, unit_cost, unit_note
FROM materials
WHERE is_active
ORDER BY sort_order;

SELECT * FROM materials WHERE category = 'steel';
SELECT * FROM materials WHERE name ILIKE '%mesh%';
```

---

## Notes / TODO

- Not imported: equipment rental, Metro saw/joint prices, concrete mix bid grid.
- Job-level price overrides not modeled.
- `POST TENSION CABLES` unit cost is **$/SF**; quantity rule is **lb/SF** (see mono.md).
