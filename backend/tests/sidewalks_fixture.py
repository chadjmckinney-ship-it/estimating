"""
The SIDEWALKS tab Chad populated on 2026-09-08, rebuilt as data (sql/076).

workbooks/Downloads/Updated_Estimate_Worksheet_from_Estimate_Project.xlsm,
SIDEWALKS: three walk types — 12,500 SF broom finish with 50 LF of 6" x 12"
stair treads, 7,575 SF stamped with integral color, 20,000 SF acid etched —
all 4" on 2" of sand, #3 bars at 18" each way, mix 6. 40,075 SF, 536 CY,
22,083 lb of steel, 260 CY of sand; $394,411.82 cost, $485,126.54 sale at 20%
margin and the Summary's 3% contingency, $12.11/SF.

Chad, on the mix: "I know the mixes dont line up but you can use the 3000
psi w/ air and ash" — so the tab's mix 6 is 3000-AIR-ASH here, at the tab's
$155.

Prices are stated HERE, from the tab and its Pricing sheet.

## What the sheet says, and where this deliberately differs

  * **ACCESSORIES AT THE CATALOG'S $0.04/lb** where the tab types $0.02
    (W67). Prices live in the catalog (sql/044). **+$515.26**, taxed.
  * **THE ACCESSORY LINES ARE TAXED.** The tab's tack strip, tie wire, cure
    and dowels are W x U with no tax term; purchased materials are taxed
    here, as on every other tab. **+$402.83.**
  * **FUEL AND TAX ON MISCELLANEOUS**, the one equipment line the sheet
    leaves without the uplift; here it is an ordinary rental, as everywhere.
    **+$655.31.**
  * **BAR WEIGHT** is the catalog's 0.376 lb/ft for a #3 where the tab's
    constant (10.6870159) makes it 0.3757: 17 lb of steel, **+$11.77** with
    its tax.
  * **QUANTITIES TO THREE PLACES** on the stakes and the cure: seventeen
    cents.
  * **THE CONTINGENCY** the tab reads off the Summary (P64, 3%) is the
    section's own here.

Rounding across pieces each stated to the cent may leave a cent.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import text

from app.models.estimate_section import EstimateSection
from app.models.mono_slab import MonoSlab
from app.services.calc import refresh_mono_slab_calcs

# ---------------------------------------------------------------- prices ----
MIX_CODE = "3000-AIR-ASH"        # the tab's mix 6, "3000 PSI Sidewalk and Hardscape", per Chad
MIX_COST = Decimal("155.00")     # F38

MATERIAL_PRICES = {
    "REBAR PAVING": Decimal("0.6500"),                 # F41 = Pricing!D23
    "SAND DELIVERED PER CY": Decimal("25.0000"),       # F44
    "ACCESSORIES": Decimal("0.0400"),                  # the catalog; the tab types 0.02 (W67)
    "2 X 4  X 16'": Decimal("0.5625"),                 # W38
    '1 X 2 X 18" STAKES': Decimal("18.00"),            # W44
    "16p NAILS DUPLEX": Decimal("42.00"),              # W45
    "8p DUPLEX": Decimal("42.00"),                     # W46
    "1 X 4 RED WOOD": Decimal("1.00"),                 # W51
    "1 X 8 RED WOOD": Decimal("0.90"),                 # W52
    "TIE WIRE": Decimal("4.00"),                       # W66
    "SLAB CURE": Decimal("540.00"),                    # W72
    '1/2" SMOOTH DOWELS & CAP': Decimal("1.75"),       # W78
    "1 X 1 TACT STRIP": Decimal("0.15"),              # W54 (the catalog spells it TACT)
}

EQUIPMENT_PRICES = {
    "BACK HOE": Decimal("385.00"),           # F61, no days
    "SKID STEER": Decimal("350.00"),         # F62 — the tab's BOB CATS, on the ladder
    "TRENCHER": Decimal("300.00"),           # F63, no days
    "TOWER LIGHT w/ GENERATOR": Decimal("65.00"),    # F64, no days
    "Concrete Pumping": Decimal("0.00"),     # no pump line on the tab
}

SETTINGS = {
    "sales_tax_pct": "0.0825",
    "equip_fuel_maint_pct": "0.50",
    "labor_super_day_rate": "390",           # F57
    "labor_foreman_day_rate": "295",         # F58, no days
    "labor_expense_day_rate": "100",         # F59
    "labor_pm_day_rate": "200",              # no PM on this tab
    "labor_super_days_per_week": "7",
    "equip_misc_day_rate": "25",             # F65
    "waste_poly": "0.10",
}

# The tab's rates, set on the section — the assembly's own values (sql/076),
# stated here so the golden does not move with the assembly table.
SECTION_RATES = {
    "labor_forming_sf": "1.75",              # D49
    "labor_place_finish_sf": "1",            # D50
    "labor_wreck_sf": "0.25",                # D51
    "labor_ada_ramp_ea": "400",              # D52
    "labor_thick_edge_lf": "10",             # D53
    "labor_stair_tread_lf": "2",             # D54
    "labor_super_days_per_cy": "0.15",       # D57
    "labor_super_days_fixed": "5",           # D57
    "support_rebar_lb_per_sf": "0",
    "vapor_barrier_enabled": "0",
    "thick_edge_width_ft": "1.8",            # V10
    "thick_edge_bars": "2",                  # U10
    "thick_edge_bar_size": "3",              # Y34
    "joint_construction_spacing_ft": "15",   # N68
    "joint_control_spacing_ft": "5",         # N69
    "joint_construction_lf": "0",            # D68
    "joint_control_lf": "0",                 # D69
    "saw_cutting_lf": "0",                   # D70
    "haul_off_cy": "4",                      # D71
    "demo_lf": "8",                          # D72
    "stamping_sf": "3.5",                    # D73
    "integral_color_cy": "100",              # D74
    "acid_etch_sf": "2",                     # D75
    "concrete_pump_cy": "0",
    "lumber_2x4_per_sf": "0.25",             # U38
    "stakes_sf_per_bundle": "400",           # U44
    "nails_16p_per_sf": "6000",              # U45
    "nails_8p_per_sf": "6000",               # U46
    "tie_wire_sf_per_roll": "15000",         # U66
    "cure_sf_per_drum": "16000",             # U72
    "dowel_spacing_in": "18",                # U77
}

SECTION = dict(
    kind="sidewalk",
    name="Sidewalks",
    unit="SF",
    margin_pct=Decimal("0.20"),      # O31 = Summary!P63
    contingency_pct=Decimal("0.03"), # Summary!P64, read into D31
    tax_exempt=None,
    form_percent=Decimal("1"),
    waste_concrete=Decimal("0.08"),  # M38
    waste_sand=Decimal("0.05"),      # M44
    waste_rebar=Decimal("0.10"),     # M41
)

# ---------------------------------------------------------------- takeoff ---
# description, SF, thick, sand, thick edge LF, stamped, color, acid, stairs (LF, rise, run)
AREAS = [
    ("Broom finish", 12500, 4, 2, 0, False, False, False, (50, 6, 12)),
    ("Stamped w/ intragal color", 7575, 4, 2, 0, True, True, False, None),
    ("Acid etched", 20000, 4, 2, 0, False, False, True, None),
]
BAR_SIZE, BAR_SPACING_IN = 3, Decimal("18")

# ------------------------------------------------------------ the sheet ----
SHEET = {
    "total_sf": Decimal("40075"),              # C27
    "concrete_cy": Decimal("536.3333"),        # V27
    "steel_lb": Decimal("22083.2990"),         # N41
    "sand_cy": Decimal("259.7454"),            # N44
    "stair_cy": Decimal("2.0000"),             # the treads' share of V10: 50 x 6 x (12 + 12) / 3888 x 1.08
    "super_days": Decimal("85.45"),            # D57 = 536.33 / 10 x 1.5 + 5
    "stamped_sf": Decimal("7575"),             # AO27
    "color_cy": Decimal("101.0000"),           # AP27
    "acid_sf": Decimal("20000"),               # AQ27
    "expansion_lf": Decimal("2672"),           # F68 = AR27
    "control_lf": Decimal("13358"),            # F69
    "dowels": Decimal("1782"),                 # U78
    "concrete_cost": Decimal("89990.0292"),    # Q38
    "steel_cost": Decimal("15538.3613"),       # Q41
    "sand_cost": Decimal("7029.3591"),         # Q44
    "labor": Decimal("120325.00"),             # Q55
    "supervision": Decimal("41870.50"),        # O58
    "equipment": Decimal("26049.3750"),        # O63
    "contract": Decimal("76612.50"),           # SUM(Q68:R77)
    "lumber": Decimal("16996.6968"),           # Y79
    "total_cost": Decimal("394411.8213"),      # W31
    "total_sale": Decimal("485126.5402"),      # D31
    "sale_per_sf": Decimal("12.1055"),         # B31
}

# What the APP reads — the sheet plus every difference named in the module
# docstring. Set from the first run (2026-09-08) and held since.
GOLDEN_COST = Decimal("395997.18")


def _price_material(db, name: str, cost: Decimal) -> int:
    mid = db.execute(
        text("UPDATE materials SET unit_cost = :c WHERE name = :n RETURNING id"),
        {"c": cost, "n": name},
    ).scalar()
    assert mid is not None, f"no catalog material named {name!r}"
    return int(mid)


def price_the_catalog(db) -> dict:
    mix_id = db.execute(
        text("UPDATE mix_designs SET unit_cost = :c WHERE code = :k RETURNING id"),
        {"c": MIX_COST, "k": MIX_CODE},
    ).scalar()
    assert mix_id is not None, f"no mix design {MIX_CODE} in the catalog"
    ids = {name: _price_material(db, name, cost) for name, cost in MATERIAL_PRICES.items()}
    for name, cost in EQUIPMENT_PRICES.items():
        found = db.execute(
            text("UPDATE equipment SET unit_cost = :c WHERE name = :n RETURNING id"),
            {"c": cost, "n": name},
        ).scalar()
        assert found is not None, f"no equipment named {name!r}"
    for key, value in SETTINGS.items():
        db.execute(
            text("INSERT INTO system_settings (key, value) VALUES (:k, to_jsonb(CAST(:v AS text))) "
                 "ON CONFLICT (key) DO UPDATE SET value = excluded.value"),
            {"k": key, "v": value},
        )
    db.flush()
    return {"mix_id": int(mix_id), **ids}


def build_section(db, estimate, ids: dict) -> EstimateSection:
    section = EstimateSection(estimate_id=estimate.id, vapor_barrier_material_id=None,
                              vapor_tape_material_id=None, **SECTION)
    db.add(section)
    db.flush()
    for key, value in SECTION_RATES.items():
        db.execute(
            text("INSERT INTO section_rates (section_id, key, value, note) VALUES (:s, :k, :v, 'SIDEWALKS') "
                 "ON CONFLICT (section_id, key) DO UPDATE SET value = excluded.value"),
            {"s": str(section.id), "k": key, "v": value},
        )
    for i, (desc, sf, thick, sand, edge, stamped, color, acid, stairs) in enumerate(AREAS):
        slab = MonoSlab(
            section_id=section.id,
            description=desc,
            square_footage=Decimal(sf),
            thickness_in=Decimal(thick),
            sand_thickness_in=Decimal(sand),
            thick_edge_lf=Decimal(edge),
            mix_design_id=ids["mix_id"],
            post_tension=False,
            wire_mesh=False,
            slab_bar_size=BAR_SIZE,
            slab_bar_spacing_in=BAR_SPACING_IN,
            stamped=stamped,
            integral_color=color,
            acid_etch=acid,
            stair_tread_lf=Decimal(stairs[0]) if stairs else None,
            stair_tread_rise_in=Decimal(stairs[1]) if stairs else None,
            stair_tread_run_in=Decimal(stairs[2]) if stairs else None,
            sort_order=(i + 1) * 10,
        )
        db.add(slab)
        db.flush()
        refresh_mono_slab_calcs(db, slab, section)
    db.flush()
    return section


def build(db, estimate) -> EstimateSection:
    priced = price_the_catalog(db)
    from app.services.price_book import pull_prices

    pull_prices(db, estimate.id)
    return build_section(db, estimate, priced)
