"""
The 01-Piers sheet, rebuilt as data.

Same approach as the paving fixture: run on the REAL seeded catalog so a
difference between the app and the sheet is a difference in the rules, and set
nothing on the section that the app would not set for itself. The waste
factors, the steel price, the labor rates and the cage geometry all arrive
through assembly_rates because the section's kind is 'piers'.

The one thing typed in is supervision — 15 superintendent days, 10 foreman, 10
PM — because piers has no area to derive a duration from, and the workbook
types them too.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import text

from app.models.estimate_section import EstimateSection
from app.models.pier_group import PierGroup
from app.services.piers import refresh_pier_group_calcs

# The sheet's mix 5, "4,000 PSI /Ash and Air" at $145/CY.
MIX_CODE = "4000-AIR-ASH"
MIX_UNIT_COST = Decimal("145")

# label, qty, dia, base ft, rock ft, vert n, vert size, tie size, tie sp,
# dowel n, dowel size, dowel ft
GROUPS = [
    ("G", 12, 24, 16, 3, 7, 6, 3, 10, 4, 6, 8),
    ("G", 12, 24, 16, 5, 7, 6, 3, 10, 4, 6, 8),
    ("G", 46, 36, 16, 8, 8, 8, 3, 10, 4, 6, 8),
    ("G", 20, 42, 16, 6, 12, 8, 3, 10, 4, 6, 8),
    ("R", 4, 24, 16, 5, 7, 6, 3, 10, 4, 6, 8),
    ("R", 12, 42, 16, 4, 12, 8, 3, 10, 4, 6, 8),
]

# Confinement, as Chad calls it out: 3 #3 stirrups at 3" o.c. at the top.
BAND_COUNT = 3
BAND_SPACING_IN = Decimal("3")

SUPER_DAYS = Decimal("15")
FOREMAN_DAYS = Decimal("10")
PM_DAYS = Decimal("10")

# What 01-Piers itself reads.
SHEET = {
    "piers": 106,
    "total_lf": Decimal("2348"),
    "concrete_cy": Decimal("632.6993"),
    "steel_lb": Decimal("71736.48"),
    "drilling": Decimal("58032.00"),
    "concrete_cost": Decimal("99310.07"),
    "steel_cost": Decimal("46592.84"),
    "labor": Decimal("32040.71"),
    "supervision": Decimal("8875.00"),
    "pm": Decimal("2000.00"),
    "equipment": Decimal("7238.06"),
    "contract": Decimal("18594.02"),
    "lumber": Decimal("11270.30"),
    "total_cost": Decimal("283953.00"),
    "total_sale": Decimal("335064.54"),
    # sql/043: `01-Piers!G53` was a typed 0.75 overriding its own
    # Pricing lookup. Chad reconnected it to Pricing!D22 — REBAR PIERS /
    # PT slabs — on 2026-09-01. Piers and PT slabs buy the same bar.
    "steel_rate": Decimal("0.60"),
}


def price_the_mix(db) -> int:
    mix_id = db.execute(
        text("UPDATE mix_designs SET unit_cost = :c WHERE code = :k RETURNING id"),
        {"c": MIX_UNIT_COST, "k": MIX_CODE},
    ).scalar()
    assert mix_id is not None, f"no mix design {MIX_CODE} in the catalog"
    db.flush()
    return int(mix_id)


def build_section(db, estimate, mix_id: int) -> EstimateSection:
    section = EstimateSection(
        estimate_id=estimate.id,
        kind="piers",
        name="01-Piers",
        unit="EA",
        margin_pct=Decimal("0.18"),
        contingency_pct=Decimal("0.00"),
        tax_exempt=None,
    )
    db.add(section)
    db.flush()

    for order, (label, qty, dia, base, rock, vn, vs, ts, tsp, dn, ds, dl) in enumerate(GROUPS):
        g = PierGroup(
            section_id=section.id,
            label=label,
            qty=qty,
            diameter_in=Decimal(dia),
            base_depth_ft=Decimal(base),
            rock_penetration_ft=Decimal(rock),
            mix_design_id=mix_id,
            vert_bars_count=vn,
            vert_bars_size=vs,
            tie_size=ts,
            tie_spacing_in=Decimal(tsp),
            band_tie_count=BAND_COUNT,
            band_spacing_in=BAND_SPACING_IN,
            dowels_count=dn,
            dowels_size=ds,
            dowels_length_ft=Decimal(dl),
            sort_order=order * 10,
        )
        db.add(g)
        db.flush()
        refresh_pier_group_calcs(db, g, section)
    db.flush()
    return section


def type_the_supervision(db, section_id) -> None:
    """
    15 super days, 10 foreman, 10 PM — entered, not derived.

    This is the whole point of the piers supervision model: there is no area to
    divide, so somebody has to say how long the job is, and everything
    downstream (including the equipment ladder) rides what they said.
    """
    from app.services.labor import update_labor_line

    update_labor_line(db, section_id, "superintendent", qty=SUPER_DAYS, mark_manual=True)
    update_labor_line(db, section_id, "foreman", qty=FOREMAN_DAYS, mark_manual=True)
    update_labor_line(db, section_id, "pm", qty=PM_DAYS, mark_manual=True)


def build(db, estimate) -> EstimateSection:
    mix_id = price_the_mix(db)
    # Pull the sheet AFTER pricing the catalog (sql/048), so this section
    # prices from an estimate sheet the way every real estimate does. If any
    # golden number in the tests moves because of this line, the book is
    # wrong — that is the whole point of running the suite through it.
    from app.services.price_book import pull_prices

    pull_prices(db, estimate.id)
    return build_section(db, estimate, mix_id)
