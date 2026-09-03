-- 031: seam tape for the vapor barrier
--
-- Tape is a consumable that scales with the barrier, not with the slab: you buy
-- rolls of tape per roll of wrap. It sits in the vapor_barrier category next to
-- the rolls (Stego Tape, Yellow Guard Tape) with unit EA and no dimensions in
-- its name, so it has never been priced — nothing looked for it, and if the
-- barrier picker landed on it by accident the poly priced at $0.
--
-- Named on the estimate, same as the barrier itself (sql/030). Quantity is
-- barrier rolls x the company ratio, so changing the wrap changes the tape.
--
-- A barrier priced per SF has no roll count, so it carries no tape.

BEGIN;

ALTER TABLE estimates
    ADD COLUMN IF NOT EXISTS vapor_tape_material_id integer
    REFERENCES materials(id) ON DELETE SET NULL;

COMMENT ON COLUMN estimates.vapor_tape_material_id IS
    'Seam tape for the vapor barrier. NULL falls back to the company default.';

INSERT INTO system_settings (key, value, description) VALUES
    ('default_vapor_tape_material_id', '0'::jsonb,
     'materials.id of the default seam tape. 0 = no tape priced.'),
    ('vapor_tape_rolls_per_barrier_roll', '1.0'::jsonb,
     'Rolls of seam tape per roll of vapor barrier.')
ON CONFLICT (key) DO NOTHING;

COMMIT;
