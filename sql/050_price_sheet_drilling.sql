-- 050 — the estimate price sheet, stage 4: drilling rates by shaft diameter
--
-- claude/estimate-price-sheet-spec.md. The last table-held price that was
-- still read live: pier_drill_rates.drill_per_lf, ~20% of a piers section.
-- One sheet row per diameter (ref_key = the diameter, "24" for 24.00), so a
-- driller's break on this job's 30" shafts lands on this job and nowhere
-- else — and the comparison shown beside a drilling quote ("what the table
-- would charge") is at THIS job's rates.
--
-- casing_per_lf and deduct_per_lf are not read by any service and stay in
-- the table as reference data. A rate of 0 or NULL is unpriced and skipped,
-- like a $0 machine in 049; the pull reports it.
--
-- The backfill moves no number: every existing estimate gets the table's
-- current rates, which is what it was pricing from a moment ago.

INSERT INTO estimate_prices
    (estimate_id, kind, ref_key, label, unit, category, catalog_value, value)
SELECT e.id, 'drill_rate',
       trim(trailing '.' FROM trim(trailing '0' FROM d.diameter_in::text)),
       'Drilling ' || trim(trailing '.' FROM trim(trailing '0' FROM d.diameter_in::text)) || '" shaft',
       'LF', 'drilling', d.drill_per_lf, d.drill_per_lf
  FROM estimates e
 CROSS JOIN pier_drill_rates d
 WHERE d.drill_per_lf IS NOT NULL AND d.drill_per_lf > 0
ON CONFLICT DO NOTHING;
