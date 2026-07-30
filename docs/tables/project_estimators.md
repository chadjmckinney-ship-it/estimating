# `project_estimators`

Join table: **many estimators per project** (Notion bid list “Estimator” multi-select: Edward, Chad, Sam, Henry).

| | |
|--|--|
| **Type** | Table |
| **Created in** | `sql/004_projects_from_notion.sql` |
| **Parent docs** | [projects.md](./projects.md), [estimators.md](./estimators.md) |

## Columns

| Column | Type | Notes |
|--------|------|-------|
| `project_id` | uuid | PK part, FK → `projects` ON DELETE CASCADE |
| `estimator_id` | uuid | PK part, FK → `estimators` ON DELETE CASCADE |

Managed via API field `estimator_ids` on create/update project.
