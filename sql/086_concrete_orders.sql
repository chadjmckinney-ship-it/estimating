-- 086_concrete_orders.sql
--
-- Concrete orders: a pour planned, beside the daily report of the pour.
--
-- Chad, 2026-09-09: "another section under daily reports... 'concrete
-- orders' basically like a daily report.. Date ordered, dropdown for job,
-- concrete supplier, date of pour, Time of pour, Yards ordered, mix design,
-- order number, ordered by. then the list and calender." On the mix: "mix
-- design will be entered... each supplier has mix numbers" — so the mix is
-- text as typed, the supplier's own number, not a link to the catalog.
--
-- The job and the supplier come from the same lists the daily report form
-- offers (field_jobs; the form's suppliers plus the catalog's). ordered_by
-- is a name: the signed-in person unless typed otherwise. A status keeps a
-- canceled pour on record without it sitting on the calendar. Foremen may
-- file and read orders (app/policy.py); the office edits; a senior deletes.

CREATE TABLE IF NOT EXISTS concrete_orders (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    ordered_on    date NOT NULL DEFAULT current_date,
    job_id        integer NOT NULL REFERENCES field_jobs (id),
    supplier      text NOT NULL,
    pour_date     date NOT NULL,
    pour_time     time,
    yards         numeric(10, 2) NOT NULL CHECK (yards > 0),
    mix           text,
    order_number  text,
    ordered_by    text,
    notes         text,
    status        text NOT NULL DEFAULT 'ordered'
                  CHECK (status IN ('ordered', 'confirmed', 'poured', 'canceled')),
    created_by    uuid REFERENCES estimators (id) ON DELETE SET NULL,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    updated_by    uuid REFERENCES estimators (id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS concrete_orders_pour_idx ON concrete_orders (pour_date, pour_time);
CREATE INDEX IF NOT EXISTS concrete_orders_job_idx ON concrete_orders (job_id, pour_date);
CREATE INDEX IF NOT EXISTS concrete_orders_created_by_idx ON concrete_orders (created_by);
CREATE INDEX IF NOT EXISTS concrete_orders_updated_by_idx ON concrete_orders (updated_by);
COMMENT ON TABLE concrete_orders IS 'A concrete order (sql/086): the pour planned — job, supplier, when, how many yards, the supplier''s mix number, the order number, who ordered.';
COMMENT ON COLUMN concrete_orders.mix IS 'The supplier''s own mix number, as typed (Chad: "each supplier has mix numbers").';
