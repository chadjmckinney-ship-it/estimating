-- 042_wall_footing_split.sql
--
-- Split each wall run's cost into the WALL and the FOOTING.
--
-- Chad: "you have each row calculating cost per ff and that includes the
-- footing. so I would like those separated. makes it easier to spot an error."
--
-- That is the right reason to want it. One blended $/FF hides a bad footing
-- schedule inside a plausible-looking wall rate; two numbers priced on their
-- own drivers do not. A 70" footing and a 36" wall have nothing to do with
-- each other except that they share a length.
--
-- ---------------------------------------------------------------------------
-- Where the sheet is followed, and where it is not
-- ---------------------------------------------------------------------------
--
-- The workbook already splits these -- B42 reads $42.82/FF for the wall and
-- F42 reads $21.75 per SF of footing. Both are reproduced here EXCEPT for one
-- thing, on Chad's call: the sheet leaves **all** the steel in the wall
-- column, footing bar included. On LBJ that is 17,454 lb -- 51.7% of the
-- job's rebar, $12,281 -- sitting under "wall". A footing schedule entered
-- wrong would move the wall's $/FF and leave the footing's looking fine,
-- which defeats the point of splitting them at all.
--
-- So the footing carries its own steel here. The two figures no longer tie to
-- the sheet's B42/F42, and that is deliberate:
--
--     sheet   wall $37.24/FF   footing $18.91/SF
--     app     wall ~$33.68/FF  footing ~$22.14/SF
--
-- The SECTION total is identical either way -- this only moves money between
-- two columns.
--
-- ---------------------------------------------------------------------------
-- The rule
-- ---------------------------------------------------------------------------
--
--   WALL      wall concrete, horizontal + vertical + lap steel, sand, the
--             forming package, forming/place/wreck/rub labor, backfill and the
--             french drain (both are against the wall, not under the footing)
--   FOOTING   footing concrete, footing steel, footing labor, excavation
--             (the trench is dug for the footing)
--   SHARED    supervision, equipment, pumping -- split by form feet against
--             footing SF, which is the sheet's own basis (BF36 + BG36)
--
-- Tie-steel labor follows the steel it ties; pumping follows the concrete.
-- Both are directly attributable, so neither goes in the shared pool.
--
-- calc_wall_cost + calc_footing_cost = calc_cost, exactly. The footing half is
-- computed and the wall takes the remainder, so the two can never drift apart
-- from the row total -- which is what makes them usable for spotting an error.

ALTER TABLE wall_runs
    ADD COLUMN IF NOT EXISTS calc_wall_cost           numeric(14, 2),
    ADD COLUMN IF NOT EXISTS calc_wall_sale           numeric(14, 2),
    ADD COLUMN IF NOT EXISTS calc_wall_cost_per_ff    numeric(12, 4),
    ADD COLUMN IF NOT EXISTS calc_wall_sale_per_ff    numeric(12, 4),
    ADD COLUMN IF NOT EXISTS calc_footing_cost        numeric(14, 2),
    ADD COLUMN IF NOT EXISTS calc_footing_sale        numeric(14, 2),
    ADD COLUMN IF NOT EXISTS calc_footing_cost_per_sf numeric(12, 4),
    ADD COLUMN IF NOT EXISTS calc_footing_sale_per_sf numeric(12, 4);

COMMENT ON COLUMN wall_runs.calc_wall_cost IS
    'calc_cost less calc_footing_cost. The wall takes the remainder so the two '
    'halves always sum to the row -- never computed independently.';

COMMENT ON COLUMN wall_runs.calc_footing_cost_per_sf IS
    'Per SF of footing PLAN AREA (width x length), not per form foot and not '
    'per CY. Same denominator footing labor is priced on at $8/SF, and the '
    'same one the sheet''s F42 uses.';
