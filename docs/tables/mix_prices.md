# `mix_prices`

Supplier-specific **$/CY** for a mix design. Complements `mix_designs.unit_cost` (company default).

| | |
|--|--|
| **Type** | Table |
| **Created in** | `sql/005_mix_designs.sql` |
| **API** | `/api/mix-prices` |

## Columns

| Column | Type | Notes |
|--------|------|-------|
| `id` | serial | PK |
| `mix_design_id` | int | FK → mix_designs CASCADE |
| `supplier_id` | int | FK → concrete_suppliers CASCADE |
| `unit_cost` | numeric(12,4) | $/CY |
| `price_as_of` | date | NULL = current undated quote |
| `notes` | text | |
| `created_at` / `updated_at` | timestamptz | |

### Uniqueness

- Unique `(mix_design_id, supplier_id, price_as_of)` when date set  
- Partial unique: one current (`price_as_of IS NULL`) row per mix+supplier  

## Seeded

Martin Marietta current prices for primary Pricing mixes (3000-ASH-SOG through 3000-SW).

## API

| Method | Path |
|--------|------|
| GET | `/api/mix-prices?mix_design_id=&supplier_id=` |
| POST | `/api/mix-prices` |
| PATCH | `/api/mix-prices/{id}` |
