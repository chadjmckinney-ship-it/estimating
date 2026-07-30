# `concrete_suppliers`

Ready-mix companies quoted on the Pricing / CONCRETE BIDS sheets.

| | |
|--|--|
| **Type** | Table |
| **Created in** | `sql/005_mix_designs.sql` |
| **API** | `/api/concrete-suppliers` |

## Columns

| Column | Type | Notes |
|--------|------|-------|
| `id` | serial | PK |
| `name` | text | Unique |
| `contact_name` | text | e.g. Justin |
| `phone` | text | |
| `notes` | text | |
| `is_active` | boolean | default true |
| `created_at` / `updated_at` | timestamptz | |

## Seeded

| name | contact | notes |
|------|---------|-------|
| Martin Marietta | Justin | Primary Pricing tab rates |
| SRM | | Older SOG workbook |
| Argos | | Blanket price mention |

## API

| Method | Path |
|--------|------|
| GET | `/api/concrete-suppliers` |
| POST | `/api/concrete-suppliers` |
| PATCH | `/api/concrete-suppliers/{id}` |
