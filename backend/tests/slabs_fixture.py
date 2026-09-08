"""
05-Slabs on the Pearl Landing Podium estimate, rebuilt as data (sql/074).

Two conventional pours — 35,307 SF at 5" and 21,215 SF at 6", #3 bars at 12"
each way, 2" of sand, mix 3, 815 LF of perimeter on the first — 56,522 SF,
994 CY, 46,720 lb of steel, 349 CY of sand, a Yellow Guard barrier over all
of it. $349,626.42 cost, $419,551.70 sale, $7.42/SF.

Prices are stated HERE, the way mono_slab_fixture.py does it.

## What the sheet says, and where this deliberately differs

  * **ACCESSORIES AT THE CATALOG'S $0.04/lb** where the tab types $0.02
    (X100). Prices live in the catalog (sql/044). **+$1,013.01**, taxed.
  * **FUEL AND TAX ON MISCELLANEOUS**, the one equipment line the sheet
    leaves without the uplift; here it is an ordinary rental, as everywhere.
    **+$288.34.**
  * **BAR WEIGHT** is the catalog's 0.376 lb/ft for a #3 where the tab's own
    constant (10.6870159) makes it 0.3757: 35 lb of steel, **+$24.90** with
    its tax and **+$6.18** of tie labor on it.
  * **CONCRETE HAUL-OFF IS NOT TAXED** — a service (sql/036) — where this
    tab taxes its whole lumber column, and its loads are kept to three
    places. **−$68.42.** (The line itself is the tab's V97, a live CY / 300
    formula that the 04 tab leaves blank — it is on the slabs kind alone.)
  * **THE LUMBER BLOCK** lands eight cents over — the 2x4 at the catalog's
    four decimals, the 2x10, anchors and tie wire each a cent — and the
    concrete and the barrier a cent each.
  * **THE VAPOR TAPE** has no line on this tab; the section names no tape.

Rounding across pieces each stated to the cent may leave a cent.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import text

from app.models.estimate_section import EstimateSection
from app.models.mono_slab import MonoSlab
from app.services.calc import refresh_mono_slab_calcs

# ---------------------------------------------------------------- prices ----
MIX_CODE = "3500-AIR-ASH"        # the sheet's mix 3, "3,500 PSI 5.5sk /Ash and Air"
MIX_COST = Decimal("155.00")     # G66

MATERIAL_PRICES = {
    "REBAR GRADE BEAM": Decimal("0.6500"),             # G70 = Pricing!D23
    "SAND DELIVERED PER CY": Decimal("14.0000"),       # G73
    "ACCESSORIES": Decimal("0.0400"),                  # the catalog; the tab types 0.02 (X100)
    "10 mil Yellow Guard 14' x 210'": Decimal("330.0000"),   # X88 = 305 + 25
    "2 X 4  X 16'": Decimal("0.859375"),               # X66
    "2 X 6 X 16'": Decimal("1.4453"),                  # X69
    "2 X 10 X 16'": Decimal("1.0938"),                 # X71
    "2 x 2 x 30 Stakes": Decimal("24.00"),             # X74
    "16p NAILS DUPLEX": Decimal("68.20"),              # X75
    "8p DUPLEX": Decimal("68.20"),                     # X76
    'ANCHOR BOLTS 1/2" x 8" Galv': Decimal("45.24"),   # X78
    "SLAB CHAIRS": Decimal("27.00"),                   # X98
    "TIE WIRE": Decimal("37.80"),                      # X99
    "SLAB CURE": Decimal("567.50"),                    # X105
    "CONCRETE HAUL OFF": Decimal("250.00"),            # X97
}

EQUIPMENT_PRICES = {
    "MINI EXCAVATOR": Decimal("475.00"),     # G97
    "TRENCHER": Decimal("325.00"),           # G98, 0 days
    "SKID STEER": Decimal("225.00"),         # G99, no days
    "Concrete Pumping": Decimal("10.00"),    # G106 — the mono engine prices the pump off the catalog item first
}

SETTINGS = {
    "sales_tax_pct": "0.0825",
    "equip_fuel_maint_pct": "0.50",
    "labor_super_day_rate": "425",
    "labor_foreman_day_rate": "250",
    "labor_expense_day_rate": "100",
    "labor_pm_day_rate": "200",
    "labor_super_days_per_week": "7",
    "equip_vault_day_rate": "25",            # G100
    "equip_misc_day_rate": "55",             # G101
    "waste_poly": "0",                       # V88 = DC47 / 2940, no allowance
}

# The rates the tab types, set on the section — the assembly's own values
# (sql/074), stated here so the golden does not move with the assembly table.
SECTION_RATES = {
    "labor_forming_sf": "0.25",              # E79
    "labor_grading_sf": "0.5",               # E80
    "labor_place_finish_sf": "0.5",          # E81
    "labor_wreck_sf": "0.2",                 # E82
    "labor_tie_steel_ton": "350",            # E87
    "labor_tie_steel_free_lb_per_sf": "0.35",   # U10
    "support_rebar_lb_per_sf": "0",
    "waste_sand": "0",                       # K73 blank
    "concrete_pump_cy": "10",                # G106
    "haul_off_cy": "12",                     # G107
    "saw_cutting_lf": "0.55",                # G105
    "saw_joint_spacing_ft": "20",            # L105
}

SECTION = dict(
    kind="slabs",
    name="05-Slabs",
    unit="SF",
    margin_pct=Decimal("0.20"),      # M45
    contingency_pct=Decimal("0.00"),
    tax_exempt=None,
    form_percent=Decimal("1"),       # W65
    waste_concrete=Decimal("0.06"),  # K65
    waste_sand=Decimal("0"),         # K73 blank
    waste_rebar=Decimal("0.10"),     # K70
)

VAPOR_BARRIER = "10 mil Yellow Guard 14' x 210'"   # U88 = Y

# ---------------------------------------------------------------- takeoff ---
# description, SF, thickness, perimeter LF, bar size, bar spacing — 2" of sand,
# mix 3, no cable, no mesh (row 10 and row 12 of the tab).
POURS = [
    ("01", 35307, 5, 815, 3, 12),
    ("03", 21215, 6, 0, 3, 12),
]

SUPER_DAYS = Decimal("20")        # E91, typed; foreman, expense and PM read it (E92:E94)

# ------------------------------------------------------------ the sheet ----
SHEET = {
    "total_sf": Decimal("56522"),              # D42
    "concrete_cy": Decimal("993.9954"),        # Q42
    "steel_lb": Decimal("46719.6092"),         # BN42
    "sand_cy": Decimal("348.9012"),            # CJ42
    "tie_steel_tons": Decimal("13.4685"),      # I87 = U42 / 2000
    "poly_rolls": Decimal("19.2252"),          # V88 = 56,522 / 2,940
    "concrete_cost": Decimal("166779.9982"),   # O66, taxed
    "steel_cost": Decimal("32873.0850"),       # O70, taxed
    "sand_cost": Decimal("5287.5982"),         # O73, taxed
    "labor": Decimal("86670.8591"),            # O89
    "supervision": Decimal("19500.00"),        # M92 + O94
    "equipment": Decimal("7616.25"),           # M98
    "saw_cutting": Decimal("3108.71"),         # O105
    "pump": Decimal("9939.9537"),              # O106
    "lumber": Decimal("17849.9650"),           # Z110, the barrier in it
    "total_cost": Decimal("349626.4192"),      # V45
    "total_sale": Decimal("419551.7031"),      # E45
    "sale_per_sf": Decimal("7.4228"),          # C45
}

# What the APP reads — the sheet plus every difference named in the module
# docstring. Set from the first run (2026-09-07) and held since.
GOLDEN_COST = Decimal("350890.51")


def _price_material(db, name: str, cost: Decimal) -> int:
    mid = db.execute(
        text("UPDATE materials SET unit_cost = :c WHERE name = :n RETURNING id"),
        {"c": cost, "n": name},
    ).scalar()
    assert mid is not None, f"no catalog material named {name!r}"
    return int(mid)


def price_the_catalog(db) -> dict:
    """Bid prices for the life of this test. Rolled back with everything else."""
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
    section = EstimateSection(
        estimate_id=estimate.id,
        vapor_barrier_material_id=ids[VAPOR_BARRIER],
        vapor_tape_material_id=None,
        **SECTION,
    )
    db.add(section)
    db.flush()
    for key, value in SECTION_RATES.items():
        db.execute(
            text("INSERT INTO section_rates (section_id, key, value, note) VALUES (:s, :k, :v, '05-Slabs') "
                 "ON CONFLICT (section_id, key) DO UPDATE SET value = excluded.value"),
            {"s": str(section.id), "k": key, "v": value},
        )
    for i, (desc, sf, thick, perimeter, bar_size, bar_sp) in enumerate(POURS):
        slab = MonoSlab(
            section_id=section.id,
            description=desc,
            square_footage=Decimal(sf),
            thickness_in=Decimal(thick),
            sand_thickness_in=Decimal("2"),
            perimeter_edge_lf=Decimal(perimeter),
            post_tension=False,
            wire_mesh=False,
            mix_design_id=ids["mix_id"],
            slab_bar_size=bar_size,
            slab_bar_spacing_in=Decimal(bar_sp),
            sort_order=(i + 1) * 10,
        )
        db.add(slab)
        db.flush()
        refresh_mono_slab_calcs(db, slab, section)
    db.flush()
    return section


def type_the_supervision(db, section_id) -> None:
    """E91 and the three lines that read it — entered, not derived."""
    from app.services.labor import update_labor_line

    for code in ("superintendent", "foreman", "expense", "pm"):
        update_labor_line(db, section_id, code, qty=SUPER_DAYS, mark_manual=True)


def build(db, estimate) -> EstimateSection:
    priced = price_the_catalog(db)
    from app.services.price_book import pull_prices

    pull_prices(db, estimate.id)
    return build_section(db, estimate, priced)
