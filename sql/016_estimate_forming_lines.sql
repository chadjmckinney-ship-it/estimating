-- Persist forming / lumber takeoff lines per estimate
-- Apply: psql -d estimating -f sql/016_estimate_forming_lines.sql

BEGIN;

CREATE TABLE IF NOT EXISTS estimate_forming_lines (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    estimate_id     uuid NOT NULL REFERENCES estimates (id) ON DELETE CASCADE,
    code            text NOT NULL,                 -- e.g. 2x6, ply, stakes
    label           text NOT NULL,
    qty             numeric(14, 4) NOT NULL DEFAULT 0,
    unit            text NOT NULL,
    formula         text,
    notes           text,
    material_id     integer REFERENCES materials (id) ON DELETE SET NULL,
    material_name   text,
    unit_cost       numeric(12, 4),
    ext_cost        numeric(14, 2),
    sort_order      integer NOT NULL DEFAULT 0,
    is_manual       boolean NOT NULL DEFAULT false, -- true = user override, keep on refresh
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (estimate_id, code)
);

CREATE INDEX IF NOT EXISTS estimate_forming_lines_estimate_id_idx
    ON estimate_forming_lines (estimate_id);

COMMENT ON TABLE estimate_forming_lines IS
    'Stored forming/lumber takeoff for an estimate (Excel 04 LUMBER AND ACCESS). Refresh recalculates from pours.';

-- Snapshot of drivers used for last refresh
CREATE TABLE IF NOT EXISTS estimate_forming_summary (
    estimate_id     uuid PRIMARY KEY REFERENCES estimates (id) ON DELETE CASCADE,
    pour_count      integer NOT NULL DEFAULT 0,
    total_sf        numeric(14, 3) NOT NULL DEFAULT 0,
    perimeter_lf    numeric(14, 3) NOT NULL DEFAULT 0,
    drops_ff        numeric(14, 3) NOT NULL DEFAULT 0,
    mesh_sf         numeric(14, 3) NOT NULL DEFAULT 0,
    total_rebar_lb  numeric(14, 3) NOT NULL DEFAULT 0,
    form_percent    numeric(8, 4) NOT NULL DEFAULT 0.50,
    form_waste      numeric(8, 4) NOT NULL DEFAULT 0,
    total_ext_cost  numeric(14, 2) NOT NULL DEFAULT 0,
    refreshed_at    timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE estimate_forming_summary IS
    'Last forming takeoff drivers + total $ for an estimate';

COMMIT;
