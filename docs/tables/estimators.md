# `estimators`

People who create and own projects / estimates. Roles mirror mono.md (Admin / Estimator / Viewer); **permission enforcement is app-side later**.

| | |
|--|--|
| **Type** | Table |
| **Created in** | `sql/001_schema.sql` |
| **Expanded in** | `sql/003_estimators_expand.sql` |
| **API** | FastAPI `GET/POST/PATCH/DELETE /api/estimators` — see `backend/README.md` |
| **Seeded** | `chad` (role `admin`) |

---

## Columns

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| `id` | uuid | NO | `gen_random_uuid()` | PK |
| `username` | text | NO | | Unique login handle |
| `full_name` | text | NO | | Display name |
| `email` | text | YES | | |
| `phone` | text | YES | | Office or mobile |
| `title` | text | YES | | e.g. Senior Estimator |
| `role` | text | NO | `'estimator'` | `admin` \| `estimator` \| `viewer` |
| `notes` | text | YES | | |
| `is_active` | boolean | NO | `true` | Soft disable |
| `created_at` | timestamptz | NO | `now()` | |
| `updated_at` | timestamptz | NO | `now()` | |

### Constraints

- PK: `id`
- UNIQUE: `username`
- CHECK: `role IN ('admin', 'estimator', 'viewer')`

---

## Roles (from mono.md)

| Role | Intent |
|------|--------|
| `admin` | Manage rates, catalogs, users |
| `estimator` | Create/edit estimates |
| `viewer` | Read-only (later) |

API DELETE soft-deactivates (`is_active = false`) so FK history on projects/estimates is kept.

---

## Relationships

| Direction | Table | Column | On delete |
|-----------|-------|--------|-----------|
| ← referenced by | `projects` | `created_by` | SET NULL |
| ← referenced by | `estimates` | `estimator_id` | SET NULL |
| ← referenced by | `etakeoff_imports` | `imported_by` | SET NULL |

---

## Current seed

From Notion Estimator multi-select + admin:

| username | full_name | role | title |
|----------|-----------|------|-------|
| chad | Chad | admin | Administrator |
| edward | Edward | estimator | Estimator |
| sam | Sam | estimator | Estimator |
| henry | Henry | estimator | Estimator |

Add more people via API or SQL:

```sql
INSERT INTO estimators (username, full_name, email, phone, title, role)
VALUES ('jsmith', 'Jane Smith', 'jane@example.com', '512-555-0100', 'Estimator', 'estimator');
```

```bash
curl -s -X POST http://127.0.0.1:8001/api/estimators \
  -H 'Content-Type: application/json' \
  -d '{"username":"jsmith","full_name":"Jane Smith","role":"estimator","title":"Estimator"}'
```

---

## API quick reference

| Method | Path | Action |
|--------|------|--------|
| GET | `/api/estimators` | List (`?active_only=true`, `?role=admin`) |
| GET | `/api/estimators/{id}` | Get one |
| POST | `/api/estimators` | Create |
| PATCH | `/api/estimators/{id}` | Partial update |
| DELETE | `/api/estimators/{id}` | Soft-delete |

Interactive docs: http://127.0.0.1:8001/docs (when server is running).

---

## Example SQL

```sql
SELECT username, full_name, role, phone, title, is_active
FROM estimators
ORDER BY full_name;

SELECT * FROM estimators WHERE is_active AND role = 'estimator';
```
