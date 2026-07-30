# `projects`

Job / bid header. Column set aligned with Notion **Concrete Estimating Bid list**.

| | |
|--|--|
| **Type** | Table |
| **Created in** | `sql/001_schema.sql` |
| **Expanded in** | `sql/004_projects_from_notion.sql` |
| **API** | `/api/projects` — see `backend/README.md` |
| **Related** | `project_estimators`, `project_type_options` |

---

## Notion → Postgres map

| Notion property | Type in Notion | Postgres column | Notes |
|-----------------|----------------|-----------------|-------|
| Project Name | title | `name` | Required |
| Project Type | multi_select | `project_types` text[] | See options below |
| GC | rich_text | `gc` | General contractor |
| Location | rich_text | `location` | |
| Bid Due | date | `bid_due` | Submission deadline |
| Bid Date | date | `bid_date` | Date we bid |
| Status | status | `status` | Mapped values |
| Estimator | multi_select | `project_estimators` | Chad, Edward, Sam, Henry |
| Notes | rich_text | `notes` | |
| Link to plans | url | `plans_url` | BuildingConnected etc. |
| Bid Price | number | `bid_price` | Submitted $ |
| Rev date | date | `rev_date` | |
| Rev Price | number | `rev_price` | |
| Message ID | rich_text | `notion_message_id` | Gmail sync key |
| *(page id)* | — | `notion_page_id` | For future sync |
| — | — | `job_number` | Internal # (not on Notion) |
| — | — | `created_by` | FK → estimators |

### Not on `projects` (stay on estimate / takeoff later)

Notion also has SOG SF/Price, Paving SF/Price, thickness, CY, labor/material costs, markup, actual cost, parking garage formulas. Those belong on **estimate assemblies / results**, not the project header.

---

## Columns

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| `id` | uuid | NO | `gen_random_uuid()` | PK |
| `name` | text | NO | | Project Name |
| `job_number` | text | YES | | Internal |
| `location` | text | YES | | |
| `gc` | text | YES | | |
| `project_types` | text[] | NO | `'{}'` | Multi type tags |
| `status` | text | NO | `'not_started'` | See status map |
| `bid_due` | date | YES | | |
| `bid_date` | date | YES | | |
| `plans_url` | text | YES | | |
| `bid_price` | numeric(14,2) | YES | | |
| `rev_date` | date | YES | | |
| `rev_price` | numeric(14,2) | YES | | |
| `notes` | text | YES | | |
| `notion_message_id` | text | YES | | Unique when set |
| `notion_page_id` | text | YES | | |
| `created_by` | uuid | YES | | FK estimators |
| `created_at` | timestamptz | NO | `now()` | |
| `updated_at` | timestamptz | NO | `now()` | |

### Status map (Notion → DB)

| Notion | DB |
|--------|-----|
| Not started | `not_started` |
| In progress | `in_progress` |
| Submitted | `submitted` |
| Awarded | `awarded` |
| *(extra)* | `lost`, `no_bid`, `archived` |

### Project types (Notion options)

`Multifamily`, `Retail`, `Commercial`, `Warehouse`, `Parking Lot`, `Elevated Deck`, `Retaining Wall`, `Other`  
Reference table: `project_type_options`.

---

## `project_estimators`

Many-to-many: which estimators are assigned (Notion multi-select).

| Column | Type |
|--------|------|
| `project_id` | uuid → projects CASCADE |
| `estimator_id` | uuid → estimators CASCADE |

---

## Relationships

```
estimators ──created_by──► projects ◄── project_estimators ──► estimators
                              │
                              └── estimates (CASCADE)
```

---

## API

| Method | Path | Action |
|--------|------|--------|
| GET | `/api/projects` | List (`?status=`, `?gc=`, `?q=`) |
| GET | `/api/projects/{id}` | Get one |
| POST | `/api/projects` | Create |
| PATCH | `/api/projects/{id}` | Update |
| DELETE | `/api/projects/{id}` | Soft archive (`status=archived`) |
| GET | `/api/projects/meta/project-types` | Type options |
| GET | `/api/projects/meta/statuses` | Status values |

```bash
curl -s -X POST http://127.0.0.1:8001/api/projects \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "Crunch Fitness- Waxahachie",
    "location": "Waxahachie, TX",
    "gc": "MEC General Contractors",
    "project_types": ["Retail"],
    "status": "not_started",
    "bid_due": "2026-08-18",
    "estimator_ids": ["<uuid>", "<uuid>"]
  }'
```

---

## Example SQL

```sql
SELECT name, gc, location, status, bid_due, project_types
FROM projects
WHERE status = 'not_started'
ORDER BY bid_due NULLS LAST;

SELECT p.name, e.full_name
FROM projects p
JOIN project_estimators pe ON pe.project_id = p.id
JOIN estimators e ON e.id = pe.estimator_id;
```
