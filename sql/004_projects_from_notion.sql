-- Expand projects to match Notion "Concrete Estimating Bid list"
-- Apply: psql -d estimating -f sql/004_projects_from_notion.sql

BEGIN;

-- ---------------------------------------------------------------------------
-- Seed estimators from Notion multi-select: Edward, Chad, Sam, Henry
-- ---------------------------------------------------------------------------
INSERT INTO estimators (username, full_name, role, title, is_active)
VALUES
    ('chad',   'Chad',   'admin',     'Administrator', true),
    ('edward', 'Edward', 'estimator', 'Estimator',     true),
    ('sam',    'Sam',    'estimator', 'Estimator',     true),
    ('henry',  'Henry',  'estimator', 'Estimator',     true)
ON CONFLICT (username) DO UPDATE SET
    full_name = EXCLUDED.full_name,
    is_active = true,
    updated_at = now();

-- ---------------------------------------------------------------------------
-- Project header fields (Notion bid list)
-- ---------------------------------------------------------------------------
ALTER TABLE projects
    ADD COLUMN IF NOT EXISTS gc              text,
    ADD COLUMN IF NOT EXISTS project_types   text[] NOT NULL DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS status          text NOT NULL DEFAULT 'not_started',
    ADD COLUMN IF NOT EXISTS bid_due         date,
    ADD COLUMN IF NOT EXISTS bid_date        date,
    ADD COLUMN IF NOT EXISTS plans_url       text,
    ADD COLUMN IF NOT EXISTS bid_price       numeric(14, 2),
    ADD COLUMN IF NOT EXISTS rev_date        date,
    ADD COLUMN IF NOT EXISTS rev_price       numeric(14, 2),
    ADD COLUMN IF NOT EXISTS notion_message_id text,
    ADD COLUMN IF NOT EXISTS notion_page_id  text;

ALTER TABLE projects DROP CONSTRAINT IF EXISTS projects_status_check;
ALTER TABLE projects
    ADD CONSTRAINT projects_status_check
    CHECK (status IN (
        'not_started',   -- Notion: Not started
        'in_progress',   -- Notion: In progress
        'submitted',     -- Notion: Submitted
        'awarded',       -- Notion: Awarded
        'lost',          -- extra (not awarded)
        'no_bid',        -- declined / no bid
        'archived'
    ));

-- Unique Notion message id when present (email sync dedupe)
CREATE UNIQUE INDEX IF NOT EXISTS projects_notion_message_id_uidx
    ON projects (notion_message_id)
    WHERE notion_message_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS projects_status_idx ON projects (status);
CREATE INDEX IF NOT EXISTS projects_bid_due_idx ON projects (bid_due);
CREATE INDEX IF NOT EXISTS projects_gc_idx ON projects (gc);

COMMENT ON COLUMN projects.name IS 'Notion: Project Name (title)';
COMMENT ON COLUMN projects.gc IS 'Notion: GC (general contractor)';
COMMENT ON COLUMN projects.project_types IS
    'Notion: Project Type multi-select — Elevated Deck, Retaining Wall, Parking Lot, Other, Multifamily, Retail, Warehouse, Commercial';
COMMENT ON COLUMN projects.status IS
    'Notion Status mapped: not_started | in_progress | submitted | awarded (+ lost, no_bid, archived)';
COMMENT ON COLUMN projects.bid_due IS 'Notion: Bid Due';
COMMENT ON COLUMN projects.bid_date IS 'Notion: Bid Date (date submitted)';
COMMENT ON COLUMN projects.plans_url IS 'Notion: Link to plans';
COMMENT ON COLUMN projects.bid_price IS 'Notion: Bid Price (submitted $)';
COMMENT ON COLUMN projects.rev_date IS 'Notion: Rev date';
COMMENT ON COLUMN projects.rev_price IS 'Notion: Rev Price';
COMMENT ON COLUMN projects.notion_message_id IS 'Notion: Message ID (Gmail sync key)';
COMMENT ON COLUMN projects.notion_page_id IS 'Notion page UUID for bidirectional sync later';
COMMENT ON COLUMN projects.location IS 'Notion: Location';
COMMENT ON COLUMN projects.notes IS 'Notion: Notes';
COMMENT ON COLUMN projects.job_number IS 'Internal job # (not on Notion bid list)';

-- ---------------------------------------------------------------------------
-- Many estimators per project (Notion Estimator multi-select)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS project_estimators (
    project_id    uuid NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    estimator_id  uuid NOT NULL REFERENCES estimators (id) ON DELETE CASCADE,
    PRIMARY KEY (project_id, estimator_id)
);

CREATE INDEX IF NOT EXISTS project_estimators_estimator_id_idx
    ON project_estimators (estimator_id);

COMMENT ON TABLE project_estimators IS
    'Assigned estimators for a project (Notion: Estimator multi-select)';

-- ---------------------------------------------------------------------------
-- Known project type values (reference; not enforced strictly — Notion may grow)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS project_type_options (
    name        text PRIMARY KEY,
    sort_order  integer NOT NULL DEFAULT 0
);

INSERT INTO project_type_options (name, sort_order) VALUES
    ('Multifamily', 10),
    ('Retail', 20),
    ('Commercial', 30),
    ('Warehouse', 40),
    ('Parking Lot', 50),
    ('Elevated Deck', 60),
    ('Retaining Wall', 70),
    ('Other', 99)
ON CONFLICT (name) DO NOTHING;

COMMIT;
