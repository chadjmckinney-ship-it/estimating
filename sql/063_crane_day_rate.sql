-- 063_crane_day_rate.sql
--
-- The crane's catalog day rate catches up with the price Chad settled.
--
-- 2026-09-04, while the CIP deck was reconciled: "$3,200/day is again someone
-- editing the tab instead of the price sheet, and is current daily price." So
-- the CATALOG was the thing that was wrong -- CRANE AND OPERATOR has carried
-- $2,400 since sql/008 -- and the fix was noted as "one field on the Equipment
-- screen" and never done. 2026-09-05, on the list of unsettled prices:
-- "update it."
--
-- The deck already priced its crane at $3,200 through the cip_deck assembly
-- rate equip_crane_day_rate; this row is what every other assembly and every
-- fresh pull sees. Existing price sheets stay frozen at what they pulled and
-- report the move as drift until pulled again -- the sheet's own rule.

UPDATE equipment
   SET unit_cost = 3200.0000
 WHERE code = 'CRANE-OPERATOR'
   AND unit_cost = 2400.0000;
