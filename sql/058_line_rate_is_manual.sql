-- 058_line_rate_is_manual.sql
--
-- A typed quantity pins the quantity. It no longer pins the rate.
--
-- `is_manual` on a labor or equipment line has meant "an estimator touched
-- this; a refresh leaves it alone" — quantity, rate and switch together. The
-- rule written down on 2026-09-04 was "`is_manual` is the only thing that pins
-- a quantity", and it was also, silently, the only thing that pinned a PRICE.
--
-- On piers, walls and decks the superintendent's days have to be typed (there
-- is no area to derive them from; the unpriced list demands it). So on every
-- one of those sections the supervision lines were manual from the first
-- entry, and from then on a change to `labor_super_day_rate` — on the price
-- sheet or in company settings — never reached them. The rates card said
-- $425; the line kept billing whatever the rate was the day the days were
-- typed; nothing on screen said so. Found by the 2026-09-04 full check.
--
-- This column says which half was typed. `is_manual` keeps its meaning for
-- the quantity and the switch; `rate_is_manual` is set only when a RATE was
-- typed, and a refresh re-resolves the rate through the ladder on every line
-- where it was not. Nothing is deleted from a manual line either way.
--
-- Existing rows: a line that was manual before this file was pinned whole,
-- because the flag could not tell a typed day count from a typed rate — and
-- the screen sent the rate box back on every save, so the data cannot tell
-- either. The backfill reads the two tables differently, on what each one's
-- manual rows actually are:
--
--   * LABOR — FALSE. A manual labor line is a typed day count on a piers,
--     walls or deck section; the rate beside it is the company's. On the live
--     database on 2026-09-04 every one of the seven manual labor lines carried
--     exactly the company day rate for its code (superintendent 425, foreman
--     250, PM 200, expense 100), so letting the rate follow the ladder again
--     moves no number and closes the trap. Where somebody has genuinely typed
--     a labor rate, typing it once more pins it.
--
--   * EQUIPMENT — TRUE where manual. A manual equipment line is usually a
--     typed PRICE: the three on the live database were two mobilizations
--     typed at $5,000 (the company figure was set to the same $5,000 the same
--     day; before that the key had no value at all, and a typed rate would
--     have been the only rate) and a haul-off at the assembly's own $6/CY.
--     Pinning them moves nothing today and cannot un-price a typed
--     mobilization tomorrow. A machine that was given days before this file
--     keeps its rate pinned; re-typing the days after it lets the rate follow.
--
-- Recorded once by apply_sql.py and never re-run, so the UPDATE below cannot
-- re-pin a line that was later handed back.

ALTER TABLE estimate_labor_lines
    ADD COLUMN IF NOT EXISTS rate_is_manual boolean NOT NULL DEFAULT false;

ALTER TABLE estimate_equipment_lines
    ADD COLUMN IF NOT EXISTS rate_is_manual boolean NOT NULL DEFAULT false;

UPDATE estimate_equipment_lines SET rate_is_manual = true WHERE is_manual;

COMMENT ON COLUMN estimate_labor_lines.rate_is_manual IS
    'The RATE on this line was typed. A refresh keeps it. FALSE with is_manual '
    'TRUE is a typed quantity whose rate still follows the price sheet and the '
    'rates ladder (sql/058).';
COMMENT ON COLUMN estimate_equipment_lines.rate_is_manual IS
    'The RATE on this line was typed. A refresh keeps it. FALSE with is_manual '
    'TRUE is a typed day count whose rate still follows the price sheet and the '
    'rates ladder (sql/058).';
