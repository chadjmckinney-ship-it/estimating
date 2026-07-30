# `mix_designs`

Concrete **mix catalog**. Naming standard:

- **`{PSI} PSI - SC`** — straight cement (no ash, no air)
- **`{PSI} PSI - ASH`** — fly ash
- **`{PSI} PSI - Air - ASH`** — air entrained + fly ash  
  for **3000 / 3500 / 4000 / 4500 / 5000**
- **`3000 PSI - Integral Color`** — integral color (3000 only)

| | |
|--|--|
| **Type** | Table |
| **Created in** | `sql/001_schema.sql` |
| **Expanded** | `sql/005_mix_designs.sql` |
| **Catalog rebuild** | `sql/006_mix_designs_sc_ash_air.sql` |
| **API** | `/api/mix-designs` |
| **Related** | [concrete_suppliers.md](./concrete_suppliers.md), [mix_prices.md](./mix_prices.md) |

---

## Columns

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| `id` | serial | NO | | PK |
| `code` | text | NO | | e.g. `3000-ASH`, `4000-AIR-ASH` |
| `name` | text | NO | | Display: `3000 PSI - ASH` |
| `description` | text | YES | | |
| `strength_psi` | integer | YES | | 3000–5000 |
| `has_ash` | boolean | NO | `false` | |
| `has_air` | boolean | NO | `false` | |
| `sack_count` | numeric(4,1) | YES | | optional |
| `typical_use` | text | YES | | e.g. Integral color |
| `unit` | text | NO | `'CY'` | |
| `unit_cost` | numeric(12,4) | YES | | Default $/CY (fill via API or `mix_prices`) |
| `sort_order` | integer | NO | `0` | |
| `notes` | text | YES | | |
| `is_active` | boolean | NO | `true` | |
| `created_at` / `updated_at` | timestamptz | NO | | |

### Constraints

- UNIQUE `code`
- FK from `mono_slabs.mix_design_id` ON DELETE SET NULL

---

## Catalog (16 mixes)

| code | name | psi | ash | air |
|------|------|----:|:---:|:---:|
| `3000-SC` | 3000 PSI - SC | 3000 | | |
| `3000-ASH` | 3000 PSI - ASH | 3000 | ✓ | |
| `3000-AIR-ASH` | 3000 PSI - Air - ASH | 3000 | ✓ | ✓ |
| `3000-INT-COLOR` | 3000 PSI - Integral Color | 3000 | | |
| `3500-SC` | 3500 PSI - SC | 3500 | | |
| `3500-ASH` | 3500 PSI - ASH | 3500 | ✓ | |
| `3500-AIR-ASH` | 3500 PSI - Air - ASH | 3500 | ✓ | ✓ |
| `4000-SC` | 4000 PSI - SC | 4000 | | |
| `4000-ASH` | 4000 PSI - ASH | 4000 | ✓ | |
| `4000-AIR-ASH` | 4000 PSI - Air - ASH | 4000 | ✓ | ✓ |
| `4500-SC` | 4500 PSI - SC | 4500 | | |
| `4500-ASH` | 4500 PSI - ASH | 4500 | ✓ | |
| `4500-AIR-ASH` | 4500 PSI - Air - ASH | 4500 | ✓ | ✓ |
| `5000-SC` | 5000 PSI - SC | 5000 | | |
| `5000-ASH` | 5000 PSI - ASH | 5000 | ✓ | |
| `5000-AIR-ASH` | 5000 PSI - Air - ASH | 5000 | ✓ | ✓ |

**SC** = straight cement (no ash, no air). Unit costs start empty — set via API or `mix_prices` per supplier.

---

## Relationships

```
mix_designs
    ├── mono_slabs.mix_design_id
    └── mix_prices ──► concrete_suppliers
```

---

## API

| Method | Path | Action |
|--------|------|--------|
| GET | `/api/mix-designs` | List (`?strength_psi=3000`, `?active_only=true`) |
| GET | `/api/mix-designs/{id}` | Get one + prices |
| POST / PATCH | `/api/mix-designs`… | Create / update |
| DELETE | `/api/mix-designs/{id}` | Soft deactivate |

```bash
curl -s 'http://127.0.0.1:8001/api/mix-designs' | jq '.[].name'
curl -s 'http://127.0.0.1:8001/api/mix-designs?strength_psi=3000' | jq '.[].code'
```

---

## Example SQL

```sql
SELECT code, name, strength_psi, has_ash, has_air
FROM mix_designs
WHERE is_active
ORDER BY sort_order;

-- Set a default unit cost
UPDATE mix_designs SET unit_cost = 155, updated_at = now()
WHERE code = '3000-ASH';
```

---

## Notes

- Old Pricing-tab names (e.g. “3000 PSI W/ ASH PIERS, SOG”) replaced by this standard matrix.
- Re-quote suppliers into `mix_prices` after catalog rebuild (prices cleared in `006`).
- Integral color currently only at **3000**; add more strengths if needed.
