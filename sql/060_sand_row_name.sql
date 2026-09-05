-- 060_sand_row_name.sql
--
-- The sand row is named for the wrong unit.
--
-- The catalog row came in from the workbook's Pricing tab (sql/002) as
-- "SAND DELIVERED PER TON" with unit CY at $25.00 -- the label said one thing
-- and the unit said another, and docs/materials.md has carried the note "Excel
-- label says per ton, unit shown /YD" since the first sync. The 2026-09-04
-- full check put the question to Chad; 2026-09-05: "sand is per CY." The $25
-- is right and the unit is right; the name is the wrong half. No money moves:
-- every lookup finds this row by the fragment "SAND" (services/costing.py
-- _find_material), and price sheets key on the row's id, not its name.
--
-- The seed in sql/002 is left as the record of what the workbook said.
-- "ROCK DELEVERED PER TON" next to it (unit CY, workbook spelling) is the
-- same shape and is NOT touched here -- nobody has said what rock is per.

UPDATE materials
   SET name = 'SAND DELIVERED PER CY'
 WHERE name = 'SAND DELIVERED PER TON'
   AND unit = 'CY';
