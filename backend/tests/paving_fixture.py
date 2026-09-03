"""
The 10-PAVING sheet, rebuilt as data.

Two decisions here are the point of the whole exercise.

It runs on the REAL seeded catalog — the one sql/002 builds, which is Chad's,
at the prices the LBJ bid was priced with. Inventing a catalog for the test
would have proved only that the arithmetic works on invented numbers. Running
on his catalog is what turns "the app disagrees with the sheet" into a finding
about which of the two is wrong.

And it sets nothing on the section that the app would not set for itself. The
waste factors, the form percentage, the labor rates and the supervision ladder
all arrive through assembly_rates because the section's kind is 'paving'. If a
number here had to be typed in to make the total come out, the assembly would
not really know how to price itself.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import text

from app.models.estimate_section import EstimateSection
from app.models.mono_slab import MonoSlab
from app.services.calc import refresh_mono_slab_calcs

# The sheet's mix 3, "3,500 PSI 5.5sk /Ash and Air" at $140/CY. The catalog has
# the mix; nothing has priced it, so the fixture does.
MIX_CODE = "3500-AIR-ASH"
MIX_UNIT_COST = Decimal("140")

# description, SF, thickness in, curb LF
AREAS = [
    ("Light Duty parking", "187752", "5", "6566"),
    ("Firelane", "82399", "6", "2882"),
    ("Heavy Duty", "2552", "6", "89"),
]

TOTAL_SF = Decimal("272703")
TOTAL_CURB_LF = Decimal("9537")

# What the sheet itself reads: 10-PAVING T39 / D39 and the cost-code block.
SHEET = {
    "total_cost": Decimal("1327183.47"),
    "total_sale": Decimal("1566076.49"),
    "lumber": Decimal("55243.88"),
    "sand": Decimal("48289.05"),
    "steel": Decimal("89468.66"),
    "reinf_accessories": Decimal("13190.03"),
    "concrete": Decimal("732352.10"),
    "cure": Decimal("8512.50"),
    "supervision": Decimal("40087.34"),
    "saw_cutting": Decimal("42270.10"),
    "labor": Decimal("272703.00"),
    "equipment": Decimal("25066.80"),
    "concrete_cy": Decimal("4832.4124"),
    "sand_cy": Decimal("1784.3530"),
    "steel_lb": Decimal("150272.786"),
    "construction_joint_lf": 4546,
    "control_joint_lf": 31815,
    "super_days": Decimal("76.35684"),
    "equip_days": Decimal("120"),
    "steel_rate": Decimal("0.55"),
}


def price_the_mix(db) -> int:
    """Put $140/CY on the paving mix and return its id."""
    mix_id = db.execute(
        text("UPDATE mix_designs SET unit_cost = :c WHERE code = :k RETURNING id"),
        {"c": MIX_UNIT_COST, "k": MIX_CODE},
    ).scalar()
    assert mix_id is not None, f"no mix design {MIX_CODE} in the catalog"
    db.flush()
    return int(mix_id)


def add_paving_equipment(db) -> None:
    """
    The sheet runs a Bob Cat; the catalog calls its skid steers by name.

    Priced from assembly_rates either way (sql/036), so this only gives the
    line something to point at.
    """
    db.execute(
        text(
            "INSERT INTO equipment (code, name, category, unit, unit_cost) "
            "VALUES ('BOBCAT', 'BOB CAT', 'earthwork', 'DAY', 325) "
            "ON CONFLICT (code) DO NOTHING"
        )
    )
    db.flush()


def build_section(db, estimate, mix_id: int) -> EstimateSection:
    """
    The paving section as the sheet has it: taxable, 18% markup, three areas.

    Taxable is the part worth noticing. This is paving, inside a job, paying
    full sales tax — the direct evidence for not defaulting tax_exempt from the
    section kind. Only ROW paving is exempt.
    """
    section = EstimateSection(
        estimate_id=estimate.id,
        kind="paving",
        name="10-PAVING",
        unit="SF",
        margin_pct=Decimal("0.18"),
        contingency_pct=Decimal("0.00"),
        tax_exempt=None,
    )
    db.add(section)
    db.flush()

    for order, (name, sf, thick, curb) in enumerate(AREAS):
        pour = MonoSlab(
            section_id=section.id,
            description=name,
            square_footage=Decimal(sf),
            thickness_in=Decimal(thick),
            sand_thickness_in=Decimal("2"),
            mix_design_id=mix_id,
            curb_lf=Decimal(curb),
            slab_bar_size=3,
            slab_bar_spacing_in=Decimal("18"),
            sort_order=order * 10,
        )
        db.add(pour)
        db.flush()
        refresh_mono_slab_calcs(db, pour, section)
    db.flush()
    return section


def build(db, estimate) -> EstimateSection:
    """A priced mix, a Bob Cat, and the section — ready to cost."""
    add_paving_equipment(db)
    mix_id = price_the_mix(db)
    # Pull the sheet AFTER pricing the catalog (sql/048), so this section
    # prices from an estimate sheet the way every real estimate does. If any
    # golden number in the tests moves because of this line, the book is
    # wrong — that is the whole point of running the suite through it.
    from app.services.price_book import pull_prices

    pull_prices(db, estimate.id)
    return build_section(db, estimate, mix_id)
