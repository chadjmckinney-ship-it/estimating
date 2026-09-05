-- 043: piers buys steel from the catalog, not from a rate typed on a sheet.
--
-- sql/037 seeded assembly_rates('piers','rebar_cost_per_lb') = 0.75, copied from
-- `01-Piers!G53` in the LBJ workbook. On 2026-09-01 that cell turned out to be
-- one of five in the workbook whose Pricing lookup had been typed over with a
-- constant. Chad reconnected it to `Pricing!D22` — the row labelled
-- **REBAR PIERS / PT slabs** — and it reads **$0.60**, the same steel a PT slab
-- buys. The $0.75 was never a real pier premium; it was a stale keystroke that
-- this app then faithfully reproduced.
--
-- 73,771 lb of pier steel on LBJ alone: $11,065.72 of material, $11,978.64 with
-- tax.
--
-- The fix is not to retype 0.60 here. An assembly_rates override says "this
-- assembly buys at a price no catalog item carries", and that is now false —
-- the catalog has an item named for this exact use. Removing the row lets
-- `resolve_rebar` reach REBAR PIERS / PT slabs, so the price tracks the catalog
-- the way paving already tracks REBAR PAVING (docs/specs/design-decisions.md, "A
-- price comes from the catalog; the assembly says which item, or states a
-- rate"). The companion change is in costing.resolve_rebar.
--
-- To restate a genuine pier premium later, put it back — the mechanism is
-- intact, and a row here is a deliberate statement rather than an accident.

DELETE FROM assembly_rates
 WHERE kind = 'piers'
   AND key  = 'rebar_cost_per_lb';
