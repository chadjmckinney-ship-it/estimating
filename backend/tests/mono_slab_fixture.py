"""
04-PT Slab on Grade, rebuilt as data.

This is the fixture that should have existed all along.

`claude/lbj-workbook-reconciliation.md` pinned this section at **$671,712.74**
and that number lived in a document, asserted nowhere. The catalog was frozen at
LBJ bid prices to protect it — a hold maintained by intention rather than by
anything that runs. On 2026-08-31 two equipment day rates were edited, the
section moved $4,984.91, and the whole suite passed. It took a morning to work
out that nothing was broken.

So the prices come from HERE, written into the fixture, the way
`paving_fixture.py` and `piers_fixture.py` already do it. Once this runs, the
catalog is free to hold whatever is current and the golden number is pinned by
something that fails.

Everything else — the takeoff, the section settings, the beam schedule — is what
estimate 152b3611 actually carries, read out of the live database on 2026-08-31.

## Two conventions worth knowing before you edit this

`waste_rebar` on a mono slab carries the **lap**, not waste. On piers the same
column is genuine waste, because those cages are cut to length. Same field, two
meanings, decided by the assembly.

The grade beams carry **no bar** on GB 1 and GB 2. That is not an omission —
they are 13,755 LF of PT grade beam where the tendons do the reinforcing, and
Chad confirmed the only loose steel is the #3 supporting cables and mat. The
workbook's schedule for those sections was a support allowance folded into a
beam type, which is where its phantom ~44,000 lb came from.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import text

from app.models.beam_type import EstimateBeamType
from app.models.estimate_section import EstimateSection
from app.models.grade_beam import GradeBeam
from app.models.mono_slab import MonoSlab
from app.services.calc import refresh_mono_slab_calcs

# ---------------------------------------------------------------- prices ----
# What LBJ was bid at. The catalog may hold anything; these are what this
# section's golden numbers were computed from, and they belong to the test.

MIX_CODE = "3000-AIR-ASH"
MIX_UNIT_COST = Decimal("134.00")

# name fragment -> unit cost. Matched the way the catalog lookup matches, so a
# renamed item fails loudly here instead of silently repricing the fixture.
MATERIAL_PRICES = {
    "REBAR PIERS / PT slabs": Decimal("0.6000"),
    "POST TENSION CABLES": Decimal("0.8500"),
    "SAND DELIVERED PER TON": Decimal("25.0000"),
    "ACCESSORIES": Decimal("0.0400"),
    "10 mil Yellow Guard 14' x 210'": Decimal("340.0000"),
    "Yellow Guard Tape": Decimal("23.6500"),
}

EQUIPMENT_PRICES = {
    "MINI EXCAVATOR": Decimal("475.00"),
    "TRENCHER": Decimal("325.00"),
    "SKID STEER": Decimal("225.00"),
}

# Company settings the bid was priced under. Four of these are on the restore
# list in claude/price-restore-checklist.md — pinning them here is what lets
# that list finally be applied.
SETTINGS = {
    "labor_grading_sf": "0.65",
    "labor_place_finish_sf": "0.65",
    "labor_wreck_sf": "0.10",
    "labor_tie_steel_ton": "400",
    "labor_forming_sf": "0.45",
    "labor_drops_ff": "8",
    "labor_brick_ledge_lf": "1",
    "labor_super_day_rate": "425",
    "labor_super_sf_per_week": "16000",
    "labor_super_days_per_week": "7",
    "labor_expense_day_rate": "100",
    "labor_pm_day_rate": "200",
    "labor_foreman_day_rate": "250",
    "pt_lb_per_sf": "1.0",
    "sales_tax_pct": "0.0825",
    "equip_fuel_maint_pct": "0.50",
    "vapor_tape_rolls_per_barrier_roll": "2.5",
    "waste_poly": "0.10",
    "waste_sand": "0.05",
}

# --------------------------------------------------------------- section ----
SECTION = dict(
    kind="mono_slab",
    name="Mono slab on grade",
    unit="SF",
    margin_pct=Decimal("0.15"),
    contingency_pct=Decimal("0.00"),
    tax_exempt=None,          # inherits the project; LBJ is taxable
    form_percent=Decimal("0.50"),
    waste_concrete=Decimal("0.06"),
    waste_sand=None,          # inherits the company 5%
    waste_rebar=Decimal("0.10"),   # the LAP on a slab, not waste
)

VAPOR_BARRIER = "10 mil Yellow Guard 14' x 210'"
VAPOR_TAPE = "Yellow Guard Tape"

# ---------------------------------------------------------------- takeoff ---
# description, SF, thickness, perimeter LF, bar size, bar spacing
# All 17 pours are 4" post-tensioned on 2" of sand, mix 3, no mesh. Only the
# leaveout carries a mat.
POURS = [
    ("Pour 01", 2942, 262, None, None),
    ("Pour 02", 3992, 296, None, None),
    ("Pour 03", 5805, 345, None, None),
    ("Pour 04", 4775, 343, None, None),
    ("Pour 05", 5503, 357, None, None),
    ("Pour 06", 3478, 344, None, None),
    ("Pour 07", 3875, 285, None, None),
    ("Pour 08", 3722, 287, None, None),
    ("Pour 09", 3739, 277, None, None),
    ("Pour 10", 4076, 314, None, None),
    ("Pour 11", 6872, 421, None, None),
    ("Pour 12", 6217, 446, None, None),
    ("Pour 13", 2153, 208, None, None),
    ("Pour 14", 2440, 228, None, None),
    ("Pour 15", 2091, 199, None, None),
    ("Pour 16", 515, 115, None, None),
    ("Pour 25 Leaveouts", 528, 163, 3, 18),
]

# label, kind, width, height, form_face, top n/size, bottom n/size,
# stirrup size/spacing
BEAM_TYPES = [
    ("GB 1 — 12x32", "grade_beam", 12, 32, None, 0, None, None, None, None, None),
    ("GB 2 — 10x30", "grade_beam", 10, 30, None, None, None, None, None, None, None),
    ("GB 3 — 10x30 2+2", "grade_beam", 10, 30, None, 2, 5, 2, 5, 3, 16),
    ("Brick ledge — 6\" widening, 6x10 formed", "brick_ledge", 6, 32, 10, 2, 5, None, None, 3, 16),
    ("Drop 9 — 12x12", "drop", 12, 12, None, 2, 5, 2, 5, 3, 16),
]

# pour index -> [(beam type index, LF)]
BEAM_LF = {
    0:  [(3, 60), (4, 41), (0, 262), (1, 447), (2, 52)],
    1:  [(3, 83), (0, 296), (1, 629)],
    2:  [(3, 123), (4, 28), (0, 345), (1, 944), (2, 129)],
    3:  [(3, 47), (4, 83), (0, 343), (1, 690), (2, 51)],
    4:  [(3, 49), (4, 41), (0, 357), (1, 733), (2, 106)],
    5:  [(3, 67), (4, 215), (0, 344), (1, 427), (2, 68)],
    6:  [(3, 63), (4, 92), (0, 285), (1, 562), (2, 20)],
    7:  [(3, 29), (4, 81), (0, 287), (1, 530), (2, 36)],
    8:  [(3, 48), (0, 277), (1, 502), (2, 66)],
    9:  [(3, 35), (0, 314), (1, 564), (2, 82)],
    10: [(3, 91), (0, 421), (1, 959), (2, 169)],
    11: [(3, 82), (4, 183), (0, 446), (1, 1077), (2, 47)],
    12: [(3, 38), (4, 43), (0, 208), (1, 242), (2, 33)],
    13: [(3, 15), (0, 228), (1, 311), (2, 42)],
    14: [(4, 58), (0, 199), (1, 316)],
    15: [(0, 115), (1, 95)],
    16: [],
}

# ----------------------------------------------------------- the numbers ----
# Quantities first — these are the takeoff, and they moved for nobody.
GOLDEN_QTY = {
    "slab_count": 17,
    "total_sf": Decimal("62723.000"),
    "total_concrete_cy": Decimal("2205.1955"),
    "total_slab_concrete_cy": Decimal("820.8197"),
    "total_gb_concrete_cy": Decimal("1384.3758"),
    "total_sand_cy": Decimal("406.5380"),
    "total_slab_bar_lb": Decimal("291.174"),
    "total_support_rebar_lb": Decimal("6272.300"),
    "total_grade_beam_rebar_lb": Decimal("15381.503"),
    "total_rebar_lb": Decimal("21944.977"),
    "total_pt_cable_lb": Decimal("62723.000"),
    "total_poly_slab_sf": Decimal("62723.000"),
    "total_poly_gb_sf": Decimal("81012.333"),
    "total_poly_sf": Decimal("158108.864"),
}

# Then the money, by block, so a failure names what moved rather than just
# saying the total is wrong.
GOLDEN_COST = {
    "direct": Decimal("393605.54"),
    "forming": Decimal("29615.36"),
    "labor": Decimal("126922.07"),
    "supervision": Decimal("19894.94"),
    "equipment_rental": Decimal("19890.00"),
    "equipment_contract": Decimal("35283.13"),
    "fuel": Decimal("9944.98"),
    "tax": Decimal("36556.64"),
    "total_cost": Decimal("671712.66"),
    "total_sale": Decimal("772469.56"),
    "cost_per_sf": Decimal("10.7092"),
}

# Supervision is derived here, unlike piers: 62,723 / 16,000 = 3.92019 weeks,
# x7 = 27.4413 days, quantized ONCE. Quantizing weeks first and then
# multiplying is a double round and costs 8 cents across the three lines that
# ride these days — which is exactly the gap between this fixture and the
# $671,712.74 in the reconciliation doc.
SUPER_DAYS = Decimal("27.4413")


def _price_material(db, name: str, cost: Decimal) -> int:
    mid = db.execute(
        text("UPDATE materials SET unit_cost = :c WHERE name = :n RETURNING id"),
        {"c": cost, "n": name},
    ).scalar()
    assert mid is not None, f"no catalog material named {name!r}"
    return int(mid)


def price_the_catalog(db) -> dict:
    """
    Put the bid's prices on the catalog for the life of this test.

    Rolled back with everything else. The point is that the fixture states its
    own prices instead of trusting the catalog to still be holding them.
    """
    mix_id = db.execute(
        text("UPDATE mix_designs SET unit_cost = :c WHERE code = :k RETURNING id"),
        {"c": MIX_UNIT_COST, "k": MIX_CODE},
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
            text(
                # CAST(...) rather than ::text — SQLAlchemy reads ":v::text" as
                # a parameter named "v:" and the statement never reaches Postgres.
                "INSERT INTO system_settings (key, value) "
                "VALUES (:k, to_jsonb(CAST(:v AS text))) "
                "ON CONFLICT (key) DO UPDATE SET value = excluded.value"
            ),
            {"k": key, "v": value},
        )

    db.flush()
    return {"mix_id": int(mix_id), **ids}


def build_section(db, estimate, ids: dict) -> EstimateSection:
    section = EstimateSection(
        estimate_id=estimate.id,
        vapor_barrier_material_id=ids[VAPOR_BARRIER],
        vapor_tape_material_id=ids[VAPOR_TAPE],
        **SECTION,
    )
    db.add(section)
    db.flush()

    types = []
    for order, (label, kind, w, h, face, tn, ts, bn, bs, ss, sp) in enumerate(BEAM_TYPES):
        bt = EstimateBeamType(
            section_id=section.id,
            label=label,
            kind=kind,
            width_in=Decimal(w),
            height_in=Decimal(h),
            form_face_in=Decimal(face) if face is not None else None,
            top_bars_count=tn,
            top_bars_size=ts,
            bottom_bars_count=bn,
            bottom_bars_size=bs,
            stirrup_size=ss,
            stirrup_spacing_in=Decimal(sp) if sp is not None else None,
            sort_order=(order + 1) * 10,
        )
        db.add(bt)
        db.flush()
        types.append(bt)

    for i, (desc, sf, perimeter, bar_size, bar_sp) in enumerate(POURS):
        slab = MonoSlab(
            section_id=section.id,
            description=desc,
            square_footage=Decimal(sf),
            thickness_in=Decimal("4"),
            sand_thickness_in=Decimal("2"),
            perimeter_edge_lf=Decimal(perimeter),
            post_tension=True,
            wire_mesh=False,
            mix_design_id=ids["mix_id"],
            slab_bar_size=bar_size,
            slab_bar_spacing_in=Decimal(bar_sp) if bar_sp is not None else None,
            sort_order=(i + 1) * 10,
        )
        db.add(slab)
        db.flush()

        for type_idx, lf in BEAM_LF[i]:
            db.add(
                GradeBeam(
                    mono_slab_id=slab.id,
                    beam_type_id=types[type_idx].id,
                    length_lf=Decimal(lf),
                )
            )
        db.flush()
        refresh_mono_slab_calcs(db, slab, section)

    db.flush()
    return section


def build(db, estimate) -> EstimateSection:
    priced = price_the_catalog(db)
    # Pull the sheet AFTER pricing the catalog (sql/048), so this section
    # prices from an estimate sheet the way every real estimate does. If any
    # golden number in the tests moves because of this line, the book is
    # wrong — that is the whole point of running the suite through it.
    from app.services.price_book import pull_prices

    pull_prices(db, estimate.id)
    return build_section(db, estimate, priced)
