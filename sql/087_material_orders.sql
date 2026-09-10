-- 087_material_orders.sql
--
-- Material orders: rebar, post-tension and the rest, beside the concrete
-- orders they go with.
--
-- Chad, 2026-09-09: "the next section... this is going to be like concrete
-- orders.. but materials.. mostly to track post tension and rebar for
-- projects.. so actually concrete orders should be there too..." — on the
-- shape, "build it". The two now sit together in an Orders group on the
-- dock; this table is the material side.
--
-- A material order is the kind (rebar | post_tension | other), the date
-- ordered, the job from the daily report form's list, the supplier as
-- typed (rebar and post-tension come from different houses than concrete,
-- so the ones used before are offered rather than a fixed list), what it
-- is in words — sizes, lengths, the shop-drawing reference — a quantity
-- and its unit (LB, TON, EA, LF, SF, bundles...), needed on site by,
-- delivered on, the order number, who ordered, notes, and a status:
-- ordered, confirmed, delivered, canceled. Foremen may file and read
-- (app/policy.py); the office edits; a senior deletes.

CREATE TABLE IF NOT EXISTS material_orders (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    kind          text NOT NULL CHECK (kind IN ('rebar', 'post_tension', 'other')),
    ordered_on    date NOT NULL DEFAULT current_date,
    job_id        integer NOT NULL REFERENCES field_jobs (id),
    supplier      text NOT NULL,
    description   text NOT NULL,
    quantity      numeric(12, 2) CHECK (quantity IS NULL OR quantity >= 0),
    unit          text,
    needed_by     date,
    delivered_on  date,
    order_number  text,
    ordered_by    text,
    notes         text,
    status        text NOT NULL DEFAULT 'ordered'
                  CHECK (status IN ('ordered', 'confirmed', 'delivered', 'canceled')),
    created_by    uuid REFERENCES estimators (id) ON DELETE SET NULL,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    updated_by    uuid REFERENCES estimators (id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS material_orders_needed_idx ON material_orders (needed_by);
CREATE INDEX IF NOT EXISTS material_orders_job_idx ON material_orders (job_id, kind);
CREATE INDEX IF NOT EXISTS material_orders_created_by_idx ON material_orders (created_by);
CREATE INDEX IF NOT EXISTS material_orders_updated_by_idx ON material_orders (updated_by);
COMMENT ON TABLE material_orders IS 'A material order (sql/087): rebar, post-tension or other for a job — what, how much, from whom, needed by when.';
COMMENT ON COLUMN material_orders.unit IS 'As typed, uppercased: LB, TON, EA, LF, SF, BUNDLE, PALLET...';
