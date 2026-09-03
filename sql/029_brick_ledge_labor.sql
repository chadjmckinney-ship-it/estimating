-- 029: brick ledge labor rate
--
-- The ledge is a 6" x 10" formed void at the top of a widened grade beam: the
-- beam is 18" wide to full depth, and the ledge is the notch the brick sits on.
-- Pricing it as a 6" full-depth thickening overstates concrete by the void —
-- about 12.8 CY on 830 LF — which is small enough to accept.
--
-- What it really costs is forming and labor. Forming came in with sql/028 (a
-- 2x6 along the length, ply over the face depth). This is the labor half:
-- a per-LF line alongside the existing DROPS line.
--
-- Seeded at 0 so no existing estimate moves until the rate is set.

BEGIN;

INSERT INTO system_settings (key, value, description) VALUES
    ('labor_brick_ledge_lf', '0'::jsonb,
     'Brick ledge labor $/LF. 0 until set — the line shows with a zero rate.')
ON CONFLICT (key) DO NOTHING;

COMMIT;
