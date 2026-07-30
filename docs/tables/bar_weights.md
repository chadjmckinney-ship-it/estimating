# `bar_weights`

Standard rebar unit weights (lb/ft) used by grade-beam calculations.

| | |
|--|--|
| **Type** | Table |
| **Created in** | `sql/001_schema.sql` |
| **Seeded** | Yes — 9 rows (#3–#11) |

---

## Columns

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| `bar_size` | smallint | NO | | PK; 3–11 |
| `weight_lb_per_ft` | numeric(8,4) | NO | | lb per linear foot |
| `description` | text | YES | generated | Always `'#' \|\| bar_size` (e.g. `#5`) |

### Constraints

- PK: `bar_size`
- CHECK: `bar_size BETWEEN 3 AND 11`

---

## Seeded data

| Bar | lb/ft | description |
|-----|------:|-------------|
| 3 | 0.3760 | #3 |
| 4 | 0.6680 | #4 |
| 5 | 1.0430 | #5 |
| 6 | 1.5020 | #6 |
| 7 | 2.0440 | #7 |
| 8 | 2.6700 | #8 |
| 9 | 3.4000 | #9 |
| 10 | 4.3030 | #10 |
| 11 | 5.3130 | #11 |

Matches [../mono.md](../mono.md) standard bar weights.

---

## Relationships

Referenced by `grade_beams`:

- `top_bars_size`, `bottom_bars_size`, `mid_bars_size`
- `stirrup_size`, `l_bars_size`

---

## Example

```sql
SELECT * FROM bar_weights ORDER BY bar_size;

-- 4 bars of #6 over 100 LF
SELECT 4 * 100 * weight_lb_per_ft AS lb
FROM bar_weights WHERE bar_size = 6;
```
