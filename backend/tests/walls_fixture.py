"""
06-Walls & Footings, rebuilt as data.

652 LF of retaining wall on a continuous 70" x 12" footing, in 16 types that
differ only in length and height. 3,452.55 form feet, 33,727.83 lb of steel,
284.86 CY, $230,548.73 sale.

Prices are stated HERE, the way mono_slab_fixture.py, paving_fixture.py and
piers_fixture.py do it, so the catalog is free to hold whatever is current.

## Two rates this sheet does not share with the others

The walls sheet TYPES the skid steer at $275/day where 04-PT Slab uses $225 —
one catalog, two sheets, bid at different times. And it prices steel at
$0.55/lb where the slab pays $0.60 for PT bar. Both are the workbook's, both
are set below, and neither is evidence that anything is wrong.

## Supervision is typed, and so is the expense line

10 superintendent days, 5 foreman, 5 expense. Note the expense line does NOT
ride the superintendent's days here — the sheet types 5 against 10. On a wall
job the super is on site through the pour and cure while the crew that eats the
per-diem is not, so the two genuinely differ.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import text

from app.models.estimate_section import EstimateSection
from app.models.wall_run import WallRun
from app.services.walls import refresh_wall_run_calcs

# ---------------------------------------------------------------- prices ----
WALL_MIX_CODE = "4000-AIR-ASH"      # sheet mix 5
WALL_MIX_COST = Decimal("145.00")
FOOTING_MIX_CODE = "3500-AIR-ASH"   # sheet R8 = 3 — cheaper concrete in the ground
FOOTING_MIX_COST = Decimal("140.00")

MATERIAL_PRICES = {
    "REBAR GRADE BEAM": Decimal("0.5500"),   # 06 F56 / Pricing!D23
    "ACCESSORIES": Decimal("0.0400"),
}

EQUIPMENT_PRICES = {
    "MINI EXCAVATOR": Decimal("475.00"),
    "SKID STEER": Decimal("275.00"),          # typed on this sheet, not $225
    "TOWER LIGHT w/ GENERATOR": Decimal("100.00"),
}

SETTINGS = {
    "sales_tax_pct": "0.0825",
    "equip_fuel_maint_pct": "0.50",
    "labor_super_day_rate": "425",
    "labor_foreman_day_rate": "250",
    "labor_expense_day_rate": "100",
    "labor_pm_day_rate": "200",
    "labor_super_days_per_week": "7",
    "waste_poly": "0.10",
}

SECTION = dict(
    kind="walls_footings",
    name="06-Walls & Footings",
    unit="FF",
    margin_pct=Decimal("0.15"),
    contingency_pct=Decimal("0.00"),
    tax_exempt=None,
    waste_concrete=Decimal("0.06"),
    waste_rebar=Decimal("0.10"),
)

# ---------------------------------------------------------------- takeoff ---
# length ft, wall height in. Everything else is identical on all 16 rows:
# 12" wall, #5 @ 12" both ways both faces, 70" x 12" footing with #5 @ 12"
# two mats, backfilled.
RUNS = [
    (135, "36"),    (57, "34.8"),   (28, "61.2"),   (65, "75.48"),
    (32, "70.8"),   (32, "63.6"),   (32, "67.2"),   (32, "75"),
    (32, "81"),     (32, "79.68"),  (32, "80.16"),  (32, "86.16"),
    (32, "78.24"),  (26, "92.4"),   (38, "70.44"),  (15, "71.28"),
]

COMMON = dict(
    backfill=True,
    wall_thick_in=Decimal("12"),
    horiz_spacing_in=Decimal("12"), horiz_size=5, horiz_mats=2,
    vert_spacing_in=Decimal("12"), vert_size=5, vert_mats=2,
    ftg_width_in=Decimal("70"), ftg_thick_in=Decimal("12"),
    ftg_spacing_in=Decimal("12"), ftg_size=5, ftg_mats=2,
)

SUPER_DAYS = Decimal("10")
FOREMAN_DAYS = Decimal("5")
EXPENSE_DAYS = Decimal("5")

# ------------------------------------------------------------ the sheet ----
SHEET = {
    "runs": 16,
    "wall_lf": Decimal("652"),
    "form_ff": Decimal("3452.55"),
    "footing_sf": Decimal("3803.3333"),
    "steel_lb": Decimal("33727.8323"),
    "concrete_cy": Decimal("284.8607"),
    "wall_cy": Decimal("135.5446"),
    "footing_cy": Decimal("149.3160"),
    "sand_cy": Decimal("384"),
    "backfill_cy": Decimal("979"),
    "drain_lf": Decimal("652"),
    # The sheet's 3088 divisor; the app computes 141 from the honest 3888.
    "excavate_cy_sheet": Decimal("181"),
    "excavate_cy_honest": Decimal("141"),
    "total_cost": Decimal("200477.1561"),
    "total_sale": Decimal("230548.7296"),
    "sale_per_ff": Decimal("66.7764"),
}


def price_the_catalog(db) -> dict:
    """Bid prices for the life of this test. Rolled back with everything else."""
    ids = {}
    for code, cost, key in (
        (WALL_MIX_CODE, WALL_MIX_COST, "wall_mix_id"),
        (FOOTING_MIX_CODE, FOOTING_MIX_COST, "footing_mix_id"),
    ):
        mid = db.execute(
            text("UPDATE mix_designs SET unit_cost = :c WHERE code = :k RETURNING id"),
            {"c": cost, "k": code},
        ).scalar()
        assert mid is not None, f"no mix design {code} in the catalog"
        ids[key] = int(mid)

    for name, cost in MATERIAL_PRICES.items():
        found = db.execute(
            text("UPDATE materials SET unit_cost = :c WHERE name = :n RETURNING id"),
            {"c": cost, "n": name},
        ).scalar()
        assert found is not None, f"no catalog material named {name!r}"

    for name, cost in EQUIPMENT_PRICES.items():
        db.execute(
            text("UPDATE equipment SET unit_cost = :c WHERE name = :n"),
            {"c": cost, "n": name},
        )

    for key, value in SETTINGS.items():
        db.execute(
            text(
                "INSERT INTO system_settings (key, value) "
                "VALUES (:k, to_jsonb(CAST(:v AS text))) "
                "ON CONFLICT (key) DO UPDATE SET value = excluded.value"
            ),
            {"k": key, "v": value},
        )

    db.flush()
    return ids


def build_section(db, estimate, ids: dict, *, sheet_mode: bool = False) -> EstimateSection:
    section = EstimateSection(
        estimate_id=estimate.id,
        footing_mix_design_id=ids["footing_mix_id"],
        **SECTION,
    )
    db.add(section)
    db.flush()

    for i, (length, height) in enumerate(RUNS):
        run = WallRun(
            section_id=section.id,
            label=f"W{i + 1}",
            mix_design_id=ids["wall_mix_id"],
            length_ft=Decimal(length),
            wall_height_in=Decimal(height),
            sort_order=(i + 1) * 10,
            **COMMON,
        )
        db.add(run)
        db.flush()
        refresh_wall_run_calcs(db, run, section, sheet_mode=sheet_mode)
    db.flush()
    return section


def type_the_supervision(db, section_id) -> None:
    """
    10 super days, 5 foreman, 5 expense — entered, not derived.

    A wall job's duration comes from pour sequence and cure, not from area, so
    `labor_super_sf_per_week` is 0 for this assembly and somebody has to say how
    long it runs. The equipment ladder rides whatever they said.
    """
    from app.services.labor import update_labor_line

    update_labor_line(db, section_id, "superintendent", qty=SUPER_DAYS, mark_manual=True)
    update_labor_line(db, section_id, "foreman", qty=FOREMAN_DAYS, mark_manual=True)
    update_labor_line(db, section_id, "expense", qty=EXPENSE_DAYS, mark_manual=True)


def build(db, estimate, *, sheet_mode: bool = False) -> EstimateSection:
    priced = price_the_catalog(db)
    # Pull the sheet AFTER pricing the catalog (sql/048), so this section
    # prices from an estimate sheet the way every real estimate does. If any
    # golden number in the tests moves because of this line, the book is
    # wrong — that is the whole point of running the suite through it.
    from app.services.price_book import pull_prices

    pull_prices(db, estimate.id)
    return build_section(db, estimate, priced, sheet_mode=sheet_mode)
