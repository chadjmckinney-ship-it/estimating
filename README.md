# Estimate Projects

Local workspace for the S&S Concrete web estimating system (Mono Slab first).

## Layout

```
Estimate_Projects/
  workbooks/             # Source Excel estimates (reference only)
  docs/
    mono.md              # Mono Slab design (source of truth for rules)
    materials.md         # Browseable materials / unit-cost catalog
    notes.md             # Database / ops notes
    todo.md              # Feature backlog
    REQUIREMENTS.md      # Short requirements baseline
    tables/              # One MD per DB table (+ variance view)
      README.md
  sql/
    001_schema.sql
    002_materials.sql
    003_estimators_expand.sql
    004_projects_from_notion.sql
    005_mix_designs.sql
    006_mix_designs_sc_ash_air.sql
    007_materials_from_new_current.sql
    008_equipment.sql
    009_mono_slab_rebar_pt_rates.sql
    010_pt_cable_lf.sql
    011_gb_concrete_cy.sql
  backend/               # FastAPI (estimators, projects, mix designs, equipment)
  README.md
```

## App UI + API (local)

```bash
cd ~/Estimate_Projects/backend
../.venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8001
```

Binding to `0.0.0.0` makes the app reachable from other devices on the LAN. To open the port (ufw), scoped to the local network:

```bash
sudo ufw allow from 192.168.0.0/24 to any port 8001 proto tcp
```

| | | |
|--|--|--|
| **Web UI** | local | http://127.0.0.1:8001/ |
| | LAN | http://192.168.0.142:8001/ |
| **API docs** | local | http://127.0.0.1:8001/docs |

> Note: the app has no authentication — anyone on the LAN can view/edit while the port is open. Use `--host 127.0.0.1` to restrict to this machine only.

Frontend: `frontend/` (static SPA, no build). See `frontend/README.md` and `backend/README.md`.

## Database

- **Name:** `estimating`
- **Owner:** `chad` (peer auth via local `psql`)
- **Apply / re-apply schema:**

```bash
psql -d estimating -f ~/Estimate_Projects/sql/001_schema.sql
```

> Note: re-running the full script will fail if objects already exist. For a clean reset:

```bash
psql -d postgres -c 'DROP DATABASE estimating;'
psql -d postgres -c 'CREATE DATABASE estimating OWNER chad;'
psql -d estimating -f ~/Estimate_Projects/sql/001_schema.sql
```

### Quick connect

```bash
psql -d estimating
```

### Core tables

| Table | Purpose |
|-------|---------|
| `estimators` | Multi-user estimators |
| `projects` / `estimates` | Job + estimate versions |
| `mono_slabs` | Main slab quantity inputs |
| `grade_beams` | Bar schedule per slab |
| `bar_weights` | #3–#11 lb/ft |
| `mix_designs` | Mix lookup |
| `supplier_bids` | Quoted rebar/PT |
| `supplier_bid_variance` | View: calc vs quote |
| `etakeoff_imports` | CSV import audit |
| `system_settings` | Waste factors, PT rate |
| `materials` | Pricing-tab unit catalog (Whitecap lumber + steel/mesh/PT/sand) |

Locked calc helpers: `calc_concrete_cy`, `calc_sand_cy`, `calc_support_rebar_lb`, `calc_pt_cable_lb`, `calc_long_bar_lb`, `calc_stirrup_lb`.

### Materials

Seeded from **Pricing** on `Updated Estimate Worksheet.xlsm` (Whitecap 5/12/2025):

```bash
psql -d estimating -f ~/Estimate_Projects/sql/002_materials.sql
```

| Category | Examples |
|----------|----------|
| lumber | 2x4–2x10, ply, stakes, nails, keyway |
| structural_accessories | chairs, pier sleds/boots, tie wire |
| site_accessories | paving chairs, snap ties, poly |
| vapor_barrier / foam | Stego, RW Meadows, foam fill |
| steel / mesh / pt | rebar, wire mesh, PT cables |
| aggregate / chemical | sand, rock, cure, form release |

**Not imported yet** (still on Pricing tab): equipment rental day rates, Metro joint/sawcutting prices, concrete supplier mix bid grid.

## Workbooks

Most relevant for Mono Slab / SOG:  
`workbooks/Pearl_Landing/SOG and Paving Estimate Sheet.xlsm`
