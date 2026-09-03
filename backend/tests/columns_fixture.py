"""
07-COLUMNS, rebuilt as data.

68 cast-in-place columns in four types, entered by Chad on 2026-09-01. Until
that morning the tab was empty and columns was going to be the first assembly
built with no golden number to check against.

The prices come from HERE, the way `mono_slab_fixture.py`, `walls_fixture.py`
and `piers_fixture.py` state theirs. The catalog is then free to hold whatever
is current and this test still fails when a RULE changes — which is the whole
point, and the reason the LBJ slab's $4,984.91 morning cannot happen again.

## What the sheet says, and where this deliberately differs

The sheet reads **$160,746.20**. This fixture will read above it, and every
piece of the gap was named in `claude/columns-spec.md` before a line of code
was written:

  * FORM AREA. The sheet's `AZ` is `height x (L x W / 36) / 2` — a
    cross-section, not a perimeter, and light by an amount that moves with the
    column's proportions. 6,660 SF against 7,716. The sheet already holds the
    honest figure in its own column X and spends it on one labor line.
  * VERTICAL BAR WASTE. The sheet's bracket closes after the first vertical
    set, so 10% lands on sets 2 and 3, the ties and the dowels but not on the
    biggest bar in the cage. +2,479 lb.
  * CHAMFER. `S81 = SUM(height column) x 4` never multiplies by quantity —
    240 LF on a 68-column job against 4,368.
  * CONCRETE. The sheet rounds each type UP to a whole CY. 128.2667 against
    130.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import text

from app.models.column_type import ColumnType
from app.models.estimate_section import EstimateSection
from app.services.columns import refresh_column_type_calcs

# ---------------------------------------------------------------- prices ----
# Mix 8 on the Pricing sheet: 5,000 PSI / Ash no Air.
MIX_CODE = "5000-ASH"
MIX_UNIT_COST = Decimal("175.00")

MATERIAL_PRICES = {
    "REBAR GRADE BEAM": Decimal("0.6500"),   # 07 F72 -> Pricing!D23
    "ACCESSORIES": Decimal("0.0200"),        # 07 U99
    "CHAMFER": Decimal("0.2500"),            # 07 U81
}

EQUIPMENT_PRICES = {
    "SkyTrack": Decimal("425.00"),           # 07 F97 -> Pricing!D32
    "MINI EXCAVATOR": Decimal("475.00"),     # 07 F98 -> Pricing!D33, billed as HOISTING
    "SKID STEER": Decimal("325.00"),         # 07 F100 -> Pricing!D35
}

SETTINGS = {
    "sales_tax_pct": "0.0825",
    "equip_fuel_maint_pct": "0.50",
    "labor_super_day_rate": "425",
    "labor_foreman_day_rate": "250",
    "labor_expense_day_rate": "100",
    "labor_pm_day_rate": "200",
}

# --------------------------------------------------------------- section ----
SECTION = dict(
    kind="columns",
    name="07-Columns",
    unit="EA",
    margin_pct=Decimal("0.18"),
    contingency_pct=Decimal("0.00"),
    tax_exempt=None,          # inherits the project; LBJ is taxable
)

# label, qty, height ft, L in, W in, vert n, vert size, tie size, tie sp,
# dowel n, dowel size, dowel ft
TYPES = [
    ("C1", 38, 12, 18, 24,  8,  8, 4, 6,  8,  8, 5),
    ("C2", 23, 24, 18, 24,  8,  8, 4, 6,  8,  8, 5),
    ("C3",  1, 12, 18, 24,  8,  8, 4, 6,  8,  8, 5),
    ("C4",  6, 12, 18, 30, 10, 10, 4, 6, 10, 10, 5),
]

# ----------------------------------------------------------- the numbers ----
# What 07-COLUMNS itself reads. Its steel and form figures are the SHEET's
# conventions, which this assembly deliberately does not reproduce — see the
# module docstring.
SHEET = {
    "columns": 68,
    "steel_lb": Decimal("44825.9163"),
    "form_sf": Decimal("6660"),
    "concrete_cy": Decimal("130"),
    "chamfer_lf": Decimal("240"),
    "super_days": Decimal("17"),
    "total_cost": Decimal("160746.1950"),
    "cost_per_column": Decimal("2363.9146"),
    "sale_per_column": Decimal("2789.4193"),
}


def price_the_catalog(db) -> dict:
    """Bid prices for the life of this test. Rolled back with everything else."""
    mix_id = db.execute(
        text("UPDATE mix_designs SET unit_cost = :c WHERE code = :k RETURNING id"),
        {"c": MIX_UNIT_COST, "k": MIX_CODE},
    ).scalar()
    assert mix_id is not None, f"no mix design {MIX_CODE} in the catalog"

    for name, cost in MATERIAL_PRICES.items():
        found = db.execute(
            text("UPDATE materials SET unit_cost = :c WHERE name = :n RETURNING id"),
            {"c": cost, "n": name},
        ).scalar()
        assert found is not None, f"no catalog material named {name!r}"

    for name, cost in EQUIPMENT_PRICES.items():
        found = db.execute(
            text("UPDATE equipment SET unit_cost = :c WHERE name = :n RETURNING id"),
            {"c": cost, "n": name},
        ).scalar()
        assert found is not None, f"no equipment named {name!r}"

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
    return {"mix_id": int(mix_id)}


def build_section(db, estimate, mix_id: int, *, sheet_mode: bool = False):
    section = EstimateSection(estimate_id=estimate.id, **SECTION)
    db.add(section)
    db.flush()

    for order, (lab, q, ht, ln, wd, vn, vs, ts, tsp, dn, ds, dl) in enumerate(TYPES):
        row = ColumnType(
            section_id=section.id,
            label=lab,
            qty=q,
            mix_design_id=mix_id,
            height_ft=Decimal(ht),
            length_in=Decimal(ln),
            width_in=Decimal(wd),
            vert1_count=vn,
            vert1_size=vs,
            tie_size=ts,
            tie_spacing_in=Decimal(tsp),
            dowel_count=dn,
            dowel_size=ds,
            dowel_length_ft=Decimal(dl),
            sort_order=order * 10,
        )
        db.add(row)
        db.flush()
        refresh_column_type_calcs(db, row, section, sheet_mode=sheet_mode)
    db.flush()
    return section


def build(db, estimate, *, sheet_mode: bool = False):
    priced = price_the_catalog(db)
    # Pull the sheet AFTER pricing the catalog (sql/048), so this section
    # prices from an estimate sheet the way every real estimate does. If any
    # golden number in the tests moves because of this line, the book is
    # wrong — that is the whole point of running the suite through it.
    from app.services.price_book import pull_prices

    pull_prices(db, estimate.id)
    return build_section(db, estimate, priced["mix_id"], sheet_mode=sheet_mode)
