# Estimating API (FastAPI)

Local backend for the S&S estimating system. Starts with **estimators** CRUD.

## Setup

```bash
cd ~/Estimate_Projects
source .venv/bin/activate   # or: python3 -m venv .venv && pip install -r backend/requirements.txt
psql -d estimating -f sql/003_estimators_expand.sql
```

## Run

```bash
cd ~/Estimate_Projects/backend
../.venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

- **UI:** http://127.0.0.1:8001/  
- Docs: http://127.0.0.1:8001/docs  
- Health: http://127.0.0.1:8001/health  

Static files are served from `../frontend/`.

## Estimators endpoints

| Method | Path | Action |
|--------|------|--------|
| GET | `/api/estimators` | List (`?active_only=true`, `?role=admin`) |
| GET | `/api/estimators/{id}` | Get one |
| POST | `/api/estimators` | Create |
| PATCH | `/api/estimators/{id}` | Update fields |
| DELETE | `/api/estimators/{id}` | Soft-delete (`is_active=false`) |

## Projects endpoints (Notion bid list shape)

| Method | Path | Action |
|--------|------|--------|
| GET | `/api/projects` | List (`?status=`, `?gc=`, `?q=`) |
| GET | `/api/projects/{id}` | Get one |
| POST | `/api/projects` | Create |
| PATCH | `/api/projects/{id}` | Update |
| DELETE | `/api/projects/{id}` | Archive (`status=archived`) |
| GET | `/api/projects/meta/project-types` | Type options |
| GET | `/api/projects/meta/statuses` | Status values |

Fields: `name`, `gc`, `location`, `project_types[]`, `status`, `bid_due`, `bid_date`, `plans_url`, `bid_price`, `rev_*`, `notes`, `estimator_ids[]`, Notion sync ids.

## Mix designs / suppliers / prices

| Method | Path | Action |
|--------|------|--------|
| GET | `/api/mix-designs` | Catalog (`?strength_psi=3000`) |
| POST/PATCH/DELETE | `/api/mix-designs`… | CRUD (DELETE = soft off) |
| GET/POST/PATCH | `/api/concrete-suppliers`… | Ready-mix companies |
| GET/POST/PATCH | `/api/mix-prices`… | Supplier $/CY |

## Equipment

| Method | Path | Action |
|--------|------|--------|
| GET | `/api/equipment` | List (`?category=earthwork`) |
| GET | `/api/equipment/meta/categories` | Categories |
| POST/PATCH/DELETE | `/api/equipment`… | CRUD (DELETE = soft off) |

## Mono slabs

| Method | Path | Action |
|--------|------|--------|
| GET | `/api/mono-slabs?estimate_id=` | List pours |
| GET | `/api/mono-slabs/totals?estimate_id=` | Rollup calcs |
| POST | `/api/mono-slabs` | Create + calculate |
| PATCH | `/api/mono-slabs/{id}` | Update + recalculate |
| POST | `/api/mono-slabs/{id}/recalc` | Refresh calcs only |
| DELETE | `/api/mono-slabs/{id}` | Delete pour |

## Grade beams (per mono pour)

| Method | Path | Action |
|--------|------|--------|
| GET | `/api/grade-beams?mono_slab_id=` | List types on a pour |
| PUT | `/api/mono-slabs/{id}/grade-beams` | Replace all types (bulk save) |
| POST/PATCH/DELETE | `/api/grade-beams`… | Single-row CRUD |

UI shows ≥5 type slots; more allowed. Skips blank rows.

### Create examples

```bash
# default port in docs is 8001
curl -s http://127.0.0.1:8001/api/estimators | jq

curl -s -X POST http://127.0.0.1:8001/api/estimators \
  -H 'Content-Type: application/json' \
  -d '{
    "username": "jsmith",
    "full_name": "Jane Smith",
    "email": "jane@example.com",
    "phone": "512-555-0100",
    "title": "Estimator",
    "role": "estimator"
  }' | jq

curl -s -X POST http://127.0.0.1:8001/api/projects \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "Crunch Fitness- Waxahachie",
    "location": "Waxahachie, TX",
    "gc": "MEC General Contractors",
    "project_types": ["Retail"],
    "status": "not_started",
    "bid_due": "2026-08-18",
    "estimator_ids": []
  }' | jq
```

## Config

`DATABASE_URL` env (optional). Default: `postgresql+psycopg2:///estimating` (local peer auth).
