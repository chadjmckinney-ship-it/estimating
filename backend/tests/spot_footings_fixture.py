"""
06-Footings on the Pearl Landing Podium estimate, rebuilt as data.

Four pad footing types — 86 footings, 558 LF of them laid end to end, 4,078 SF
of footer, 320 CY, 36,145 lb of steel — entered on the walls tab with the wall
columns blank and the length typed as a count times a size (E10 = B10 * 10).
$187,680.06. The first assembly built without an LBJ tab to reconcile to.

Prices are stated HERE, the way walls_fixture.py does it.

## What the sheet says, and where this deliberately differs

  * **EXCAVATION DIVIDES BY 3888, NOT 3088.** The sheet's DD column reads
    `N x O / 3088 x E` — the typo Chad left in the walls tab ("typo, leave it
    at 3888", 2026-09-05) — so it digs 380 CY, rounded row by row, where the
    footings are 302. At $12/CY that is **-$936.00** of excavation labor the
    app does not charge.
  * **THE PUMP IS PAID ON THE POUR, NOT A ROUNDED POUR.** D90 rounds the CY
    to 320 before pricing the pump; the app pumps 320.1985 CY. **+$1.98.**
  * **FUEL AND TAX ON MISCELLANEOUS.** The sheet's N88 is the one equipment
    line whose formula ends without `x (1 + tax + fuel)`; here it is an
    ordinary rental, the way walls_fixture.py already names it. **+$122.33.**
  * **THE SKY TRACK AND THE VAULT ARE TYPED.** On the walls set they are off
    until someone says a job needs them; the sheet's D83 and D87 read the
    same 14-day ladder as the excavator (D83 = D84), so this fixture types
    14 days on each. Not a difference once typed — a thing to know.
  * **BAR WEIGHT** is the catalog's 1.502 lb/ft for a #6, where the sheet
    reads (6/16)^2 x 10.680159 = 1.5019: 2.47 lb more steel here, **+$1.74**
    on the bar with its tax, **+$0.53** on the tie-steel labor that rides
    it, and ten cents of accessories.
  * **THE LUMBER BLOCK** lands three cents over: the catalog's 2x10 is
    $1.0938 where Pricing!Q7 is $1.09375 (+$0.02), the haul-off loads are
    kept to three places (-$0.08), the accessories ride the bar weight
    (+$0.10). The sheet taxes 2x10, stakes, chamfer and water stop and not
    turnbuckles, haul-off or accessories; so does the app.
  * **WELD PLATES** are on every footing here and on none of the sheet's
    rows; with no catalog price yet they cost nothing and are REPORTED as
    unpriced, which is the whole point of that rule.

Rounding across pieces each stated to the cent may leave a cent.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import text

from app.models.estimate_section import EstimateSection
from app.models.wall_run import WallRun
from app.services.walls import refresh_wall_run_calcs

# ---------------------------------------------------------------- prices ----
MIX_CODE = "3500-AIR-ASH"        # the sheet's mix 8; the identity does not matter, the $170 does
MIX_COST = Decimal("170.00")     # 06 F52

MATERIAL_PRICES = {
    "REBAR GRADE BEAM": Decimal("0.6500"),   # 06 F56
    "ACCESSORIES": Decimal("0.0400"),        # 06 U85
}

EQUIPMENT_PRICES = {
    "MINI EXCAVATOR": Decimal("475.00"),     # 06 F84
    "SKID STEER": Decimal("275.00"),         # 06 F85
    "TOWER LIGHT w/ GENERATOR": Decimal("100.00"),   # 06 F86
}

SETTINGS = {
    "sales_tax_pct": "0.0825",
    "equip_fuel_maint_pct": "0.50",
    "labor_super_day_rate": "425",
    "labor_foreman_day_rate": "250",
    "labor_expense_day_rate": "100",
    "labor_pm_day_rate": "200",
    "labor_super_days_per_week": "7",
    "equip_skytrack_day_rate": "425",        # 06 F83
    "equip_vault_day_rate": "50",            # 06 F87
    "equip_misc_day_rate": "35",             # 06 F88
    "waste_poly": "0.10",
}

# The labor and contract rates the sheet types on this tab, set on the section.
SECTION_RATES = {
    "labor_footings_sf": "15",       # 06 D66
    "labor_tie_steel_ton": "450",    # 06 D71
    "labor_excavate_cy": "12",       # 06 D73
    "labor_backfill_cy": "8",        # 06 D74
    "concrete_pump_cy": "10",        # 06 F90
}

SECTION = dict(
    kind="spot_footings",
    name="06-Footings",
    unit="EA",
    margin_pct=Decimal("0.20"),      # L40
    contingency_pct=Decimal("0.00"),
    tax_exempt=None,
    waste_concrete=Decimal("0.06"),  # J51
    waste_rebar=Decimal("0.10"),     # J56
)

# ---------------------------------------------------------------- takeoff ---
# label, count, length of each (ft), width (in), spacing (in). All 24" thick,
# #6 both mats at the one spacing, mix 8, no backfill, a weld plate on each.
ROWS = [
    ("F5", 6, Decimal("10"), Decimal("144"), Decimal("6")),
    ("F6", 17, Decimal("8.5"), Decimal("102"), Decimal("10")),
    ("F7", 47, Decimal("6.5"), Decimal("78"), Decimal("10")),
    ("F8", 16, Decimal("3"), Decimal("36"), Decimal("10")),
]

COMMON = dict(
    backfill=False,
    wall_thick_in=Decimal("0"),
    wall_height_in=Decimal("0"),
    ftg_thick_in=Decimal("24"),
    ftg_bot_size=6,
    ftg_top_size=6,
    weld_plate=True,
)

SUPER_DAYS = Decimal("10")        # D78
FOREMAN_DAYS = Decimal("10")      # D79 = D78
EXPENSE_DAYS = Decimal("10")      # D80
PM_DAYS = Decimal("10")           # D81

# ------------------------------------------------------------ the sheet ----
SHEET = {
    "types": 4,
    "footings": 86,
    "length_lf": Decimal("558"),           # E36
    "footer_sf": Decimal("4078"),          # BG36
    "concrete_cy": Decimal("320.1985"),    # sum of W10:W13 before W36's ROUND
    "steel_lb": Decimal("36145.0223"),     # U36
    "excavate_cy_sheet": Decimal("380"),   # DD36, by 3088
    "concrete_cost": Decimal("58924.53"),  # BK37
    "steel_cost": Decimal("25432.54"),     # BJ37
    "footings_labor": Decimal("61170.00"), # BN37
    "tie_steel_labor": Decimal("8132.63"), # BO37
    "excavate_labor": Decimal("4560.00"),  # BP37
    "supervision": Decimal("9750.00"),     # L79 + N81
    "equipment": Decimal("12790.875"),     # L85
    "pump": Decimal("3200.00"),            # N90
    "lumber_block": Decimal("3719.4811"),  # W95
    "total_cost": Decimal("187680.0598"),  # S40
    "total_sale": Decimal("225216.0718"),  # D40
}

# What the APP reads — the sheet plus every difference named in the module
# docstring above. Set from the first run (2026-09-07) and held since.
GOLDEN_COST = Decimal("186870.68")


def price_the_catalog(db) -> dict:
    """Bid prices for the life of this test. Rolled back with everything else."""
    mid = db.execute(
        text("UPDATE mix_designs SET unit_cost = :c WHERE code = :k RETURNING id"),
        {"c": MIX_COST, "k": MIX_CODE},
    ).scalar()
    assert mid is not None, f"no mix design {MIX_CODE} in the catalog"
    for name, cost in MATERIAL_PRICES.items():
        found = db.execute(
            text("UPDATE materials SET unit_cost = :c WHERE name = :n RETURNING id"),
            {"c": cost, "n": name},
        ).scalar()
        assert found is not None, f"no catalog material named {name!r}"
    for name, cost in EQUIPMENT_PRICES.items():
        db.execute(text("UPDATE equipment SET unit_cost = :c WHERE name = :n"), {"c": cost, "n": name})
    for key, value in SETTINGS.items():
        db.execute(
            text("INSERT INTO system_settings (key, value) VALUES (:k, to_jsonb(CAST(:v AS text))) "
                 "ON CONFLICT (key) DO UPDATE SET value = excluded.value"),
            {"k": key, "v": value},
        )
    db.flush()
    return {"mix_id": int(mid)}


def build_section(db, estimate, ids: dict, *, sheet_mode: bool = False) -> EstimateSection:
    section = EstimateSection(estimate_id=estimate.id, footing_mix_design_id=ids["mix_id"], **SECTION)
    db.add(section)
    db.flush()
    for key, value in SECTION_RATES.items():
        db.execute(
            text("INSERT INTO section_rates (section_id, key, value, note) VALUES (:s, :k, :v, '06-Footings') "
                 "ON CONFLICT (section_id, key) DO UPDATE SET value = excluded.value"),
            {"s": str(section.id), "k": key, "v": value},
        )
    for i, (label, count, each, width, spacing) in enumerate(ROWS):
        run = WallRun(
            section_id=section.id, label=label, sort_order=(i + 1) * 10,
            footing_count=count, footing_each_ft=each, ftg_width_in=width,
            ftg_bot_spacing_in=spacing, ftg_top_spacing_in=spacing,
            **COMMON,
        )
        db.add(run)
        db.flush()
        refresh_wall_run_calcs(db, run, section, sheet_mode=sheet_mode)
    db.flush()
    return section


def type_the_supervision(db, section_id) -> None:
    """10 days each — super, foreman, expense and PM — entered, not derived (D78:D81)."""
    from app.services.labor import update_labor_line

    for code, days in (("superintendent", SUPER_DAYS), ("foreman", FOREMAN_DAYS),
                       ("expense", EXPENSE_DAYS), ("pm", PM_DAYS)):
        update_labor_line(db, section_id, code, qty=days, mark_manual=True)


LADDER_DAYS = Decimal("14")       # D84: ten superintendent days rent fourteen


def type_the_equipment(db, section_id) -> None:
    """The sky track and the vault, 14 days each — D83 = D84 and D87 = D84 on this tab."""
    from app.services.estimate_equipment import update_equipment_line

    for code in ("skytrack", "vault"):
        update_equipment_line(db, section_id, code, enabled=True, days_qty=LADDER_DAYS, mark_manual=True)


def build(db, estimate, *, sheet_mode: bool = False) -> EstimateSection:
    priced = price_the_catalog(db)
    from app.services.price_book import pull_prices

    pull_prices(db, estimate.id)
    return build_section(db, estimate, priced, sheet_mode=sheet_mode)
