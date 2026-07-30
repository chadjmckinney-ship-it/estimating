# Database Tables

One page per table (and the supplier variance view) in the **`estimating`** database.

| File | Object | Type | Purpose |
|------|--------|------|---------|
| [estimators.md](./estimators.md) | `estimators` | table | People who create estimates |
| [projects.md](./projects.md) | `projects` | table | Job / bid header (Notion bid list fields) |
| [project_estimators.md](./project_estimators.md) | `project_estimators` | table | Project ↔ estimator M2M |
| [estimates.md](./estimates.md) | `estimates` | table | Versioned estimate under a project |
| [mono_slabs.md](./mono_slabs.md) | `mono_slabs` | table | Main slab quantity inputs + stored calcs |
| [grade_beams.md](./grade_beams.md) | `grade_beams` | table | Per-pour GBs / exposed / drops (kind) |
| [poly_stego.md](./poly_stego.md) | poly SF calcs | columns + fn | Vapor barrier SF (pour + beam wrap) |
| [forming_materials.md](./forming_materials.md) | `estimate_forming_lines` + summary | tables | Stored lumber/access takeoff per estimate |
| [labor_supervision.md](./labor_supervision.md) | `estimate_labor_lines` + summary | tables | Slab labor + supervision per estimate |
| [estimate_equipment.md](./estimate_equipment.md) | `estimate_equipment_lines` + summary | tables | Day fleet + pumping per estimate |
| [bar_weights.md](./bar_weights.md) | `bar_weights` | table | #3–#11 lb/ft reference |
| [mix_designs.md](./mix_designs.md) | `mix_designs` | table | Concrete mix catalog (Pricing / bids) |
| [concrete_suppliers.md](./concrete_suppliers.md) | `concrete_suppliers` | table | Ready-mix suppliers |
| [mix_prices.md](./mix_prices.md) | `mix_prices` | table | Supplier $/CY by mix |
| [materials.md](./materials.md) | `materials` | table | Unit-price catalog (schema); full list → [../materials.md](../materials.md) |
| [equipment.md](./equipment.md) | `equipment` | table | Rental rates (Pricing EQUIPMENT RENTAL) |
| [supplier_bids.md](./supplier_bids.md) | `supplier_bids` | table | Quoted rebar/PT |
| [supplier_bid_variance.md](./supplier_bid_variance.md) | `supplier_bid_variance` | view | Calc vs quoted variance |
| [etakeoff_imports.md](./etakeoff_imports.md) | `etakeoff_imports` | table | CSV import audit |
| [system_settings.md](./system_settings.md) | `system_settings` | table | Waste factors, lb/SF rates |

**Migrations:** `sql/001_schema.sql`, `sql/002_materials.sql`  
**Design:** [../mono.md](../mono.md) · **Ops notes:** [../notes.md](../notes.md)

```bash
psql -d estimating -c '\dt' -c '\dv'
```

### Relationship sketch

```
estimators
    ├── projects.created_by
    ├── project_estimators ──► projects
    ├── estimates.estimator_id
    └── etakeoff_imports.imported_by

projects  (Notion bid list header: GC, types, bid due, status, plans…)
    ├── project_estimators
    └── estimates
            ├── mono_slabs
            │       └── grade_beams (kind: grade_beam|exposed|drop) ──► bar_weights
            │       └── mix_designs
            ├── supplier_bids ──► supplier_bid_variance (view)
            └── etakeoff_imports

materials          (standalone catalog)
system_settings    (standalone defaults)
project_type_options (Notion type list)
```
