"""
09-SLAB ON DECK, exercised (sql/075).

No workbook in the folder has priced a slab on deck — every 09 tab is the
empty template — so there is no bid to reconcile to. This fixture takes the
TEMPLATE's own cells (the LBJ workbook's 09-SLAB ON DECK) and runs them on a
takeoff of its own: one 12,000 SF level, 4" thick, #4 bars at 12" each way,
440 LF of edge, mix 2, no sand, a 15-mil barrier. The tests then check each
line against the template's formula worked by hand, and hold the total as a
regression golden.

Prices are stated HERE, from the template's typed cells where it types one.

## Where the app differs from the template, by design

  * **ACCESSORIES AT THE CATALOG'S $0.04/lb** where the tab types $0.02
    (X100). Prices live in the catalog (sql/044).
  * **CONCRETE HAUL-OFF IS NOT TAXED** — a service (sql/036) — where the tab
    taxes its lumber column. Its $500 a load is stated on the catalog item
    here; on a real job a deck-priced catalog item (any name with HAUL OFF
    and DECK in it) wins over the ground price.
  * **FUEL AND TAX ON MISCELLANEOUS**, as on every tab.
  * **BAR WEIGHT** is the catalog's 0.668 lb/ft for a #4 where the tab's
    constant makes it 0.6679.
  * **THE BARRIER** rolls come from the roll's own coverage with the company
    poly waste, where the tab divides by 1,760 SF for a 14' x 140' roll — the
    same lap allowance, stated differently.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import text

from app.models.estimate_section import EstimateSection
from app.models.mono_slab import MonoSlab
from app.services.calc import refresh_mono_slab_calcs

# ---------------------------------------------------------------- prices ----
MIX_CODE = "3000-ASH"            # the template's mix 2, "3,000 PSI / Ash no Air"
MIX_COST = Decimal("145.00")     # G66

MATERIAL_PRICES = {
    "REBAR PIERS / PT slabs": Decimal("0.6000"),       # G70 = Pricing!D22
    "ACCESSORIES": Decimal("0.0400"),                  # the catalog; the tab types 0.02
    "Yellow Guard 15 mil 14' x 140'": Decimal("355.0000"),   # X90 is blank; the 05 tab's Stego price
    "2 X 4  X 16'": Decimal("0.9172"),                 # X66
    "2 X 6 X 16'": Decimal("1.4453"),                  # X69
    "2 X 10 X 16'": Decimal("1.0938"),                 # X71
    "2 x 2 x 30 Stakes": Decimal("24.00"),             # X74
    "16p NAILS DUPLEX": Decimal("68.20"),              # X75
    "8p DUPLEX": Decimal("68.20"),                     # X76
    'ANCHOR BOLTS 1/2" x 8" Galv': Decimal("45.24"),   # X78
    "SLAB CHAIRS": Decimal("27.00"),                   # X98
    "TIE WIRE": Decimal("37.80"),                      # X99
    "SLAB CURE": Decimal("225.00"),                    # X105 — the ground tabs type 567.50
    "CONCRETE HAUL OFF": Decimal("500.00"),            # X97 — the ground tabs type 250
}

EQUIPMENT_PRICES = {
    "MINI EXCAVATOR": Decimal("475.00"),     # G97, blank days
    "TRENCHER": Decimal("325.00"),           # G98, on the ladder
    "SKID STEER": Decimal("225.00"),         # G99, blank days
    "Concrete Pumping": Decimal("20.00"),    # G106 — the mono engine prices the pump off the catalog item first
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
    "waste_poly": "0.10",
}

SECTION_RATES = {
    "labor_forming_sf": "0.05",              # E79
    "labor_grading_sf": "0.1",               # E80, SLAB PREP
    "labor_place_finish_sf": "0.5",          # E81
    "labor_wreck_sf": "0.2",                 # E82
    "labor_tie_steel_ton": "350",            # E87
    "labor_tie_steel_free_lb_per_sf": "0.45",   # U10
    "support_rebar_lb_per_sf": "0",
    "waste_sand": "0",
    "concrete_pump_cy": "20",                # G106
    "haul_off_cy": "12",                     # G107
    "demo_lf": "1.75",                       # G103
    "saw_cutting_lf": "0.35",                # G105
    "saw_joint_spacing_ft": "20",            # L105
}

SECTION = dict(
    kind="slab_on_deck",
    name="09-Slab on deck",
    unit="SF",
    margin_pct=Decimal("0.18"),      # M45 on the template
    contingency_pct=Decimal("0.00"),
    tax_exempt=None,
    form_percent=Decimal("0.5"),     # W65
    waste_concrete=Decimal("0.06"),  # K65
    waste_sand=Decimal("0"),
    waste_rebar=Decimal("0.10"),     # K70
)

VAPOR_BARRIER = "Yellow Guard 15 mil 14' x 140'"

# ---------------------------------------------------------------- takeoff ---
SF = Decimal("12000")
THICK_IN = Decimal("4")
PERIMETER_LF = Decimal("440")
BAR_SIZE = 4
BAR_SPACING_IN = Decimal("12")
SUPER_DAYS = Decimal("10")        # E91, typed; the three lines under it read it

# ------------------------------------------------- the template, by hand ----
# Q10 = SF x thick / 324 x (1 + K65)
CONCRETE_CY = (SF * THICK_IN / Decimal("324") * Decimal("1.06")).quantize(Decimal("0.0001"))
# BO10 = 2 x SF x 12 / spacing x lb/ft x (1 + K70) — the catalog's 0.668 for a #4
STEEL_LB = (Decimal("2") * SF * Decimal("12") / BAR_SPACING_IN * Decimal("0.668") * Decimal("1.10")).quantize(Decimal("0.001"))
# I87 = (P - SF x 0.45) / 2000
TIE_TONS = ((STEEL_LB - SF * Decimal("0.45")) / Decimal("2000")).quantize(Decimal("0.0001"))

# What the APP reads. Set from the first run (2026-09-08) and held since.
GOLDEN_COST = Decimal("70873.46")


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
            text("INSERT INTO section_rates (section_id, key, value, note) VALUES (:s, :k, :v, '09-SLAB ON DECK') "
                 "ON CONFLICT (section_id, key) DO UPDATE SET value = excluded.value"),
            {"s": str(section.id), "k": key, "v": value},
        )
    slab = MonoSlab(
        section_id=section.id,
        description="Level 2",
        square_footage=SF,
        thickness_in=THICK_IN,
        sand_thickness_in=None,
        perimeter_edge_lf=PERIMETER_LF,
        post_tension=False,
        wire_mesh=False,
        mix_design_id=ids["mix_id"],
        slab_bar_size=BAR_SIZE,
        slab_bar_spacing_in=BAR_SPACING_IN,
        sort_order=10,
    )
    db.add(slab)
    db.flush()
    refresh_mono_slab_calcs(db, slab, section)
    db.flush()
    return section


def type_the_supervision(db, section_id) -> None:
    from app.services.labor import update_labor_line

    for code in ("superintendent", "foreman", "expense", "pm"):
        update_labor_line(db, section_id, code, qty=SUPER_DAYS, mark_manual=True)


def build(db, estimate) -> EstimateSection:
    priced = price_the_catalog(db)
    from app.services.price_book import pull_prices

    pull_prices(db, estimate.id)
    return build_section(db, estimate, priced)
