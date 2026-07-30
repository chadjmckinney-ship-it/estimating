# Estimating System – Requirements Baseline

## Project Goal

Build a web-based estimating system (starting with **Mono Slab**) that:

- Replaces fragile Excel formulas with **locked calculation logic**
- Supports **multiple estimators**
- Imports quantities from **eTakeoff** (CSV)
- Calculates **rebar & PT** quantities, then allows comparison against **supplier bids**
- Runs on the office **Fedora** server with **Postgres** (laptop used for local development)

## Tech Direction

| Layer | Choice |
|-------|--------|
| Server | Fedora (office); local Postgres on laptop for now |
| Database | PostgreSQL (`estimating`) |
| Backend | TBD (Python/FastAPI or similar) |
| Frontend | TBD (Flutter Web preferred) |
| Import | eTakeoff Measurement List → CSV → mapped into the system |

## Source Excel Workbooks

Copied under `workbooks/` from:

- `~/Estimate/`
- `~/Pearl Landing/Estimate/` (includes **SOG and Paving Estimate Sheet.xlsm**)
- `~/Pearl Landing/Bid_Drawings/Estimate/`
- Sam Plans / Downloads copies

## Mono Slab – Quantity Inputs

### Main Slab

| Field | Type |
|-------|------|
| Description / Location | text |
| Square Footage | decimal |
| Thickness (inches) | decimal |
| Post Tension | boolean |
| Mix Design | lookup |
| Sand Thickness (inches) | decimal |
| Perimeter Edge (LF) | decimal |
| Wire Mesh | boolean |
| Drops (FF) | decimal |
| Notes | text |

### Grade Beams (one or more per slab)

| Field | Type |
|-------|------|
| Label | text |
| Width (in) | decimal |
| Height (in) | decimal |
| Length (LF) | decimal |
| Top Bars (# + size) | count + bar size |
| Bottom Bars (# + size) | count + bar size |
| Mid Bars (# + size) | optional |
| Stirrups (size + spacing) | size + inches |
| L-Bars (# + size + spacing) | optional |
| Notes | text |

## Calculation Rules (PT SOG)

| Item | Rule |
|------|------|
| Concrete CY | `(SF × Thickness_in / 12 / 27) × (1 + waste)` |
| Slab Support Rebar | `SF × 1.0 lb/SF` |
| PT Cable Quantity | `SF × 1.0 lb/SF` (when PT) |
| Grade Beam Rebar | From bar schedule using standard weights |
| Total Rebar | Support Rebar + Grade Beam Rebar |
| Sand CY | `(SF × Sand_Thickness_in / 12 / 27) × (1 + waste)` |

### Standard Bar Weights (lb/ft)

| Bar | lb/ft |
|-----|-------|
| #3 | 0.376 |
| #4 | 0.668 |
| #5 | 1.043 |
| #6 | 1.502 |
| #7 | 2.044 |
| #8 | 2.670 |
| #9 | 3.400 |
| #10 | 4.303 |
| #11 | 5.313 |

## Supplier Comparison

System calculates theoretical quantities, then allows entry of:

- Supplier name
- Quoted Rebar Weight
- Quoted Rebar Price
- Quoted PT Quantity / Price
- Variance (calculated vs quoted) — see `supplier_bid_variance` view

## Materials catalog

Master list lives in workbook **Pricing** tab (cols M–O lumber/accessories; left column steel/mesh/PT/sand).  
DB table: `materials` — see `sql/002_materials.sql` (58 rows seeded from Whitecap update 5/12/2025).

## Still Open / Next Decisions

- Concrete / rebar / sand **waste factors** (defaults seeded as placeholders in `system_settings`)
- Exact **PT calculation** confirmation (currently 1 lb/SF)
- Full list of **mix designs** and rate tables (Pricing concrete bid grid not yet a table)
- Equipment rental + Metro pricing tables
- **Cost code** mapping (`materials.code` reserved)
- **Permission** model
- Job-level price overrides vs company defaults
