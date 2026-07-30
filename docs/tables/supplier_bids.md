# `supplier_bids`

Supplier quotes for rebar and PT on an estimate. System theoretical quantities live on `mono_slabs.calc_*`; this table stores what the supplier bid.

For variance (calc vs quote), use the view [supplier_bid_variance.md](./supplier_bid_variance.md).

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
| `estimate_id` | uuid | NO | | FK → `estimates` |
| `supplier_name` | text | NO | | Rebar / PT supplier |
| `quoted_rebar_weight_lb` | numeric(14,3) | YES | | Quoted weight (lb) |
| `quoted_rebar_price` | numeric(14,2) | YES | | $ |
| `quoted_pt_qty` | numeric(14,3) | YES | | Quoted PT quantity |
| `quoted_pt_price` | numeric(14,2) | YES | | $ |
| `bid_date` | date | YES | | |
| `notes` | text | YES | | |
| `created_at` | timestamptz | NO | `now()` | |
| `updated_at` | timestamptz | NO | `now()` | |

### Constraints

- PK: `id`
- FK: `estimate_id` → `estimates(id)` ON DELETE CASCADE
- Index: `supplier_bids_estimate_id_idx`

---

## Relationships

| Direction | Table | Notes |
|-----------|-------|-------|
| → | `estimates` | Parent estimate |
| used by | `supplier_bid_variance` | View joins bids + mono_slab totals |

---

## Example

```sql
INSERT INTO supplier_bids (
  estimate_id, supplier_name,
  quoted_rebar_weight_lb, quoted_rebar_price,
  quoted_pt_qty, quoted_pt_price, bid_date
) VALUES (
  (SELECT id FROM estimates LIMIT 1),
  'Example Rebar Co',
  12500, 18750.00,
  9500, 14250.00,
  CURRENT_DATE
);

SELECT * FROM supplier_bid_variance
WHERE estimate_id = (SELECT id FROM estimates LIMIT 1);
```

---

## Notes / TODO

- PT quantity unit not fixed (lb vs SF) — match whatever you quote.
- Tons conversion for display can be app-side (`lb / 2000`).
- Multiple suppliers per estimate allowed (no unique on name).
