-- 082_bid_requests.sql
--
-- The bid list, as its own table. Chad, 2026-09-09: "instead of importing
-- the notions database into projects how about we create a new table and it
-- be seperate so we are not scrolling thru a ton of jobs to find the one i
-- want.. then when we choose that we are estimating, it gets copied over" —
-- and, on the proposal, "build it". docs/specs/bid-list-spec.md.
--
-- Bids are a stream: 192 of them on the Notion "Concrete Estimating Bid list"
-- this morning, 169 never started. Projects are the few that were chosen.
-- So a bid request is its own row with the Notion fields — name, GC,
-- location, project type, status, estimators, bid due (with an optional
-- time), the invite date, the plans link, the notes written at intake, the
-- bid price and its revision — and the two ids that keep an invite from
-- being entered twice: the Outlook message id, and the Notion page id the
-- import carries over. "Estimate this" copies a bid into a new project and
-- links the two; the bid keeps its own status from there.
--
-- Statuses are Notion's own, in the app's spelling: not_started, in_progress,
-- submitted, awarded, canceled (Notion: "Cancelation").

CREATE TABLE IF NOT EXISTS bid_requests (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name            text NOT NULL,
    gc              text,
    location        text,
    project_types   text[] NOT NULL DEFAULT '{}',
    status          text NOT NULL DEFAULT 'not_started' CHECK (status IN (
                        'not_started', 'in_progress', 'submitted', 'awarded', 'canceled')),
    bid_due         date,
    -- The hour, when the invite names one ("5 PM"); NULL is a day.
    bid_due_time    time,
    -- The day the invite came in — Notion's "Bid Date".
    bid_date        date,
    plans_url       text,
    bid_price       numeric(14, 2),
    rev_date        date,
    rev_price       numeric(14, 2),
    notes           text,
    message_id      text,
    notion_page_id  text,
    -- What the import last wrote, hashed: a rerun updates a row only while it
    -- still equals this, so an edit made here is never overwritten by Notion.
    import_fingerprint text,
    -- Set by "Estimate this": the project this bid became. NULL until then.
    project_id      uuid REFERENCES projects (id) ON DELETE SET NULL,
    updated_by      uuid REFERENCES estimators (id) ON DELETE SET NULL,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS bid_requests_message_id_uidx
    ON bid_requests (message_id) WHERE message_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS bid_requests_notion_page_id_uidx
    ON bid_requests (notion_page_id) WHERE notion_page_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS bid_requests_status_idx     ON bid_requests (status);
CREATE INDEX IF NOT EXISTS bid_requests_bid_due_idx    ON bid_requests (bid_due);
CREATE INDEX IF NOT EXISTS bid_requests_gc_idx         ON bid_requests (gc);
CREATE INDEX IF NOT EXISTS bid_requests_project_id_idx ON bid_requests (project_id);
CREATE INDEX IF NOT EXISTS bid_requests_updated_by_idx ON bid_requests (updated_by);

COMMENT ON TABLE bid_requests IS
    'The bid list (sql/082): every invite, as it came in. A project is the bid that was '
    'chosen — "Estimate this" copies the row over and links the two.';
COMMENT ON COLUMN bid_requests.message_id IS
    'The Outlook message id of the invite; unique when present, so the intake cannot enter '
    'the same email twice. Notion''s "Message ID".';
COMMENT ON COLUMN bid_requests.notion_page_id IS
    'The Notion page this row was imported from; unique when present, so the import can run '
    'again without doubling up.';

-- Who is on the bid: the same shape as project_estimators.
CREATE TABLE IF NOT EXISTS bid_request_estimators (
    bid_request_id  uuid NOT NULL REFERENCES bid_requests (id) ON DELETE CASCADE,
    estimator_id    uuid NOT NULL REFERENCES estimators (id) ON DELETE CASCADE,
    PRIMARY KEY (bid_request_id, estimator_id)
);
CREATE INDEX IF NOT EXISTS bid_request_estimators_estimator_idx
    ON bid_request_estimators (estimator_id);
