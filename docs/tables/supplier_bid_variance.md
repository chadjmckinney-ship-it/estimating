# `supplier_bid_variance`

**View** — calculated rebar/PT totals for an estimate vs each supplier quote.

| | |
|--|--|
| **Type** | View (read-only) |
| **Created in** | `sql/001_schema.sql` |
| **Based on** | `supplier_bids` + sum of `mono_slabs` calc columns |

---

## Columns

| Column | Type | Notes |
|--------|------|-------|
| `bid_id` | uuid | `supplier_bids.id` |
| `estimate_id` | uuid | |
| `supplier_name` | text | |
| `calc_rebar_lb` | numeric | Sum of `mono_slabs.calc_total_rebar_lb` |
| `quoted_rebar_weight_lb` | numeric | From bid |
| `rebar_variance_lb` | numeric | quoted − calculated |
| `rebar_variance_pct` | numeric | (quoted − calc) / calc × 100, 2 decimals |
| `calc_pt_lb` | numeric | Sum of `mono_slabs.calc_pt_cable_lb` |
| `quoted_pt_qty` | numeric | From bid |
| `pt_variance` | numeric | quoted − calculated |
| `quoted_rebar_price` | numeric | $ |
| `quoted_pt_price` | numeric | $ |
| `bid_date` | date | |

Variance is **NULL** if either side is missing (or calc rebar is 0 for %).

---

## Logic (summary)

```
calc totals = SUM(mono_slabs.calc_total_rebar_lb), SUM(calc_pt_cable_lb)
              for slabs on the same estimate_id

rebar_variance_lb  = quoted_rebar_weight_lb - calc_rebar_lb
rebar_variance_pct = (quoted - calc) / calc * 100
pt_variance        = quoted_pt_qty - calc_pt_lb
```

Positive variance ⇒ supplier quote is **higher** than theoretical.

---

## Example

```sql
SELECT supplier_name,
       calc_rebar_lb, quoted_rebar_weight_lb,
       rebar_variance_lb, rebar_variance_pct,
       calc_pt_lb, quoted_pt_qty, pt_variance
FROM supplier_bid_variance
ORDER BY supplier_name;
```

---

## Notes / TODO

- Depends on `calc_*` columns being populated on `mono_slabs`.
- Does not include price $/lb efficiency metrics yet (easy app-side add).
