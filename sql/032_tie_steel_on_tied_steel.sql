-- 032: tie steel bills the steel that actually gets tied
--
-- The TIE STEEL line used to be driven by every pound of rebar on the pour and
-- then reduced by an allowance of 0.35 lb/SF. Both halves were artifacts of the
-- workbook:
--
--   * The workbook's beam steel carried Chad's support-bar padding inside each
--     section's lb/LF (x (1 + K$70)), so its tonnage was inflated and the 0.35
--     allowance was sized to cancel that inflation.
--   * Once the padding moved out of the beams and into the app's explicit
--     support-steel line, the allowance ate the whole job: 21,953 lb carried
--     against 21,945 lb of steel on LBJ, and the line silently billed $0 while
--     the crew still tied eleven tons.
--
-- The line now bills beam bars + slab mat and excludes support steel, which is
-- the #3 that holds cables and mat up: placing it IS the tying, so charging for
-- it again bills one pass twice. With a real driver, the allowance has no job
-- left to do, so it goes back to 0 and every ton is billable. Uncheck the line
-- on an estimate where a sub's price already includes tying.
--
-- Reversible: set the key back to 0.35 to restore the old carry.

BEGIN;

UPDATE system_settings
SET value = '0'::jsonb,
    description = 'Tie steel carried free, lb per SF of slab. 0 bills every ton. '
                  'Applies to beam + slab steel only; support steel is never billed here.'
WHERE key = 'labor_tie_steel_free_lb_per_sf';

COMMIT;
