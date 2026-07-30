-- Stirrup hook allowance 0.5 ft -> 1.0 ft per stirrup.
--
-- Two 135-degree hooks with 6db extensions on a #3 run roughly 4-5 inches each,
-- so the old 6 inch total was light. 1.0 ft covers the hooks with room for bend
-- radius and fabrication tolerance.
--
--   count  = length_lf × 12 / spacing_in
--   bar_ft = 2 × (W + H) / 12 + 1.0        <-- was + 0.5
--   weight = count × bar_ft × lb/ft(size)
--
-- Effect on current data (~16.5k LF of #3 stirrups): 12.22 -> 13.08 tons, +7.0%.
--
-- STILL OPEN (docs/todo.md: "Confirm stirrup weight method"), deliberately NOT
-- changed here:
--   * No concrete cover deduction. The bar is measured out-to-out of the beam,
--     but a stirrup is tied inside the cage — 2 × ((W-2c) + (H-2c)). Against
--     earth ACI wants c = 3in; formed faces 1.5-2in. This runs the bar long.
--   * Count omits the end stirrup and is not rounded: a 100 LF beam at 24in
--     gives exactly 50 rather than ceil(...)+1 = 51, and short beams can yield
--     fractional stirrups.
-- These offset each other in part; the cover omission is the larger of the two.
--
-- Stored grade_beams.calc_rebar_lb must be rewritten after applying:
--   curl -s -X POST localhost:8001/api/system-settings/recalc-all
--
-- Apply: psql -d estimating -f sql/023_stirrup_hook_allowance.sql

BEGIN;

CREATE OR REPLACE FUNCTION calc_stirrup_lb(
    width_in    numeric,
    height_in   numeric,
    length_lf   numeric,
    stirrup_size smallint,
    spacing_in  numeric
) RETURNS numeric
LANGUAGE sql STABLE AS $$
    SELECT CASE
        WHEN stirrup_size IS NULL OR spacing_in IS NULL OR spacing_in <= 0 THEN 0
        ELSE round(
            (length_lf * 12.0 / spacing_in)
            * ((2.0 * (width_in + height_in) / 12.0) + 1.0)
            * (SELECT weight_lb_per_ft FROM bar_weights
               WHERE bar_weights.bar_size = calc_stirrup_lb.stirrup_size),
            3
        )
    END;
$$;

COMMENT ON FUNCTION calc_stirrup_lb IS
    'Stirrup weight: (L×12/spacing) × (2×(W+H)/12 + 1.0 ft hooks) × lb/ft(size). '
    'Hook allowance 1.0 ft. No cover deduction and no end stirrup — see sql/023.';

COMMIT;
