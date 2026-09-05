-- 061_rock_row_name.sql
--
-- The rock row: the same fix as the sand row (sql/060), on Chad's word,
-- 2026-09-05: "rename the rock row."
--
-- "ROCK DELEVERED PER TON" came in from the workbook's Pricing tab (sql/002)
-- with the workbook's own spelling, kept on purpose at the time
-- (docs/materials.md: "Names and spellings match the Excel sheet") -- and
-- named for a unit it is not priced in: the unit is CY, and it has been since
-- the first seed. Both halves go: the spelling and the unit.
--
-- No money moves. The only lookup is the fragment "ROCK"
-- (services/forming.py, the manual ROCK line on the forming package), this is
-- the only catalog row that carries it, and price sheets key on the row's id.
-- sql/002 and sql/007 are left as the record of what the workbook said.

UPDATE materials
   SET name = 'ROCK DELIVERED PER CY'
 WHERE name = 'ROCK DELEVERED PER TON'
   AND unit = 'CY';
