# `equipment`

Equipment rental / use rates from the Pricing **EQUIPMENT RENTAL** section.

| | |
|--|--|
| **Type** | Table |
| **Created in** | `sql/008_equipment.sql` |
| **Primary source** | `New Current Worksheet.xlsm` → Pricing |
| **API** | `/api/equipment` |

---

## Columns

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| `id` | serial | NO | | PK |
| `code` | text | YES | | Unique short code |
| `name` | text | NO | | As on Pricing sheet |
| `category` | text | NO | `'other'` | earthwork, lifting, power, hauling, pumping, other |
| `unit` | text | NO | `'DAY'` | DAY, YD, HOUR… |
| `unit_cost` | numeric(12,4) | YES | | Rate |
| `unit_note` | text | YES | | |
| `description` | text | YES | | |
| `is_owned` | boolean | NO | `false` | Company-owned vs pure rental |
| `is_active` | boolean | NO | `true` | Soft disable |
| `sort_order` | integer | NO | `0` | |
| `source_sheet` | text | YES | | |
| `source_row` | integer | YES | | Excel row |
| `price_as_of` | date | YES | | |
| `created_at` / `updated_at` | timestamptz | NO | | |

UNIQUE `(name, unit)`.

---

## Seeded catalog (16)

### From New Current Worksheet

| code | name | category | unit | $/unit |
|------|------|----------|------|-------:|
| SKYTRACK | SkyTrack | lifting | DAY | 425 |
| MINI-EXCAVATOR | MINI EXCAVATOR | earthwork | DAY | 475 |
| TRENCHER | TRENCHER | earthwork | DAY | 325 |
| SKID-STEER | SKID STEER | earthwork | DAY | 325 |
| BOXBLADE | BOXBLADE | earthwork | DAY | 350 |
| CHIPPING-HAMMER | CHIPPING HAMMER | power | DAY | 45 |
| COMPRESSOR | COMPRESSOR | power | DAY | 100 |
| TOWER-LIGHT | TOWER LIGHT w/ GENERATOR | power | DAY | 100 |
| GENERATOR | GENERATOR | power | DAY | 32 |
| SKY-LIFT | SKY LIFT | lifting | DAY | 380 |
| CRANE-OPERATOR | CRANE AND OPERATOR | lifting | DAY | 2400 |
| DUMPTRUCK-5-6YD | 5-6 YD Dumptruck | hauling | DAY | 240 |
| BACKHOE | BACK HOE | earthwork | DAY | 425 |
| WATER-TRUCK | Water Truck | hauling | DAY | 450 |

### Also from older Updated Estimate Worksheet

| code | name | category | unit | $/unit |
|------|------|----------|------|-------:|
| CONCRETE-PUMP | Concrete Pumping | pumping | **YD** | 16 |
| COMPACTOR | COMPACTOR | earthwork | DAY | 200 |

---

## API

| Method | Path | Action |
|--------|------|--------|
| GET | `/api/equipment` | List (`?active_only=true`, `?category=earthwork`) |
| GET | `/api/equipment/meta/categories` | Category list |
| GET | `/api/equipment/{id}` | Get one |
| POST | `/api/equipment` | Create |
| PATCH | `/api/equipment/{id}` | Update |
| DELETE | `/api/equipment/{id}` | Soft deactivate |

```bash
curl -s 'http://127.0.0.1:8001/api/equipment' | jq
curl -s 'http://127.0.0.1:8001/api/equipment?category=lifting' | jq '.[].name'
```

---

## Example SQL

```sql
SELECT category, name, unit, unit_cost
FROM equipment
WHERE is_active
ORDER BY sort_order;
```

---

## Notes / TODO

- Job-level rental days / equipment takeoff not linked yet (estimate line items later).
- Whitecap sheet had different day rates (e.g. crane $1260 vs $2400) — New Current is primary.
- `is_owned` reserved for company fleet vs pure rental.
