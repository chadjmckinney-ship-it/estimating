"""
08-CIP EL. DECK, rebuilt as data.

32,100 SF of post-tensioned elevated deck on two levels, with two grade beam
types running through them. The most filled-in of the unbuilt tabs, and the
first assembly in the app that hangs in the air.

The prices come from HERE, the way every other fixture states theirs.

## What the sheet says, and where this deliberately differs

The sheet reads **$952,052.02**, and it reconciles from its own parts to a
tenth of a cent — summing `BJ50:CC50` gives $952,052.0214 against the stated
$952,052.0215. Every piece of the gap below that was named in
`claude/cip-deck-spec.md` and sql/052 before a line of code was written.

  * **GRADE BEAM FORM FEET ARE BOTH FACES.** `U53 = C53/12` is one face. Chad,
    2026-09-04, asked whether a deck grade beam is formed on one side only:
    "both faces — the sheet is light." 240 FF becomes 480, and because that
    figure also drives the 2x4, 2x6, 2x10, plywood and stake lines, this is
    **+$2,425.01**: $1,440 of GB forming labor and $985.01 of lumber.

  * **BEAM SLOTS 2 AND 3 CARRY ALMOST NO STEEL.** `AL` (slot 1) reads column
    O — lb per LF. `AM` (slot 2) reads column **Q**, which is CY per LF, and
    `AN` (slot 3) reads column **S**, a header cell. Level 2 is charged
    **7 lb** for a 45 LF type-2 beam that weighs 2,855.49. +3,190.88 lb.

  * **ONE BAR WEIGHT.** The tab uses 10.6870159 for the slab mats and
    10.680159 for the beam schedule. The app reads ASTM `bar_weights`.

  * **ACCESSORIES AT THE CATALOG PRICE.** `U109` is a typed-over $0.02 where
    the catalog says $0.04 — the same cell sql/044 found on paving and
    columns.

  * **RESHORING MATERIAL IS UNPRICED, NOT FREE.** `F83` is blank, so that line
    costs $0 while its labor costs $11,235. The section reports it.

  * **THE BAR IS PT-SLAB BAR.** The sheet points `F78` at `Pricing!D23`, REBAR
    GRADE BEAM at $0.65. The catalog carries a row named for this exact case —
    "REBAR PIERS / PT slabs", $0.60 — and sql/043 already resolves a
    post-tensioned slab to it. An elevated PT deck is a PT slab. **-$3,513.21**,
    and the only piece of the gap that goes DOWN.

  * **MISCELLANEOUS IS A RENTAL.** The sheet's formula for that one equipment
    line ends without `x (1 + tax + fuel)` where the five above it carry it —
    the fifth sheet to do that. +$550.46.

## The golden number, reconciled

    952,052.02   the sheet
     + 2,247.26   steel the beam slots dropped
     +   718.59   tie-steel labor on that steel
     + 1,440.00   GB forming labor, both faces
     + 1,013.75   lumber on the doubled beam faces (+ tax on PAVECRETE)
     +   550.46   MISCELLANEOUS taxed and fuelled like the rental it is
     + 1,676.58   ACCESSORIES at the catalog $0.04, and tax on four lines
                  the sheet leaves untaxed
     - 3,513.21   bar at the PT-slab price, not the grade-beam price
    -----------
    956,185.45

`sheet_mode` restores the workbook's two bar constants so the bid can still be
reproduced deliberately. It does not restore the beam-slot bug, the one-face
beams or the typed-over accessories cell — those are decisions.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import text

from app.models.beam_type import EstimateBeamType
from app.models.deck_level import DeckLevel, DeckLevelBeam
from app.models.estimate_section import EstimateSection
from app.services.cip_deck import refresh_deck_level_calcs

# ---------------------------------------------------------------- prices ----
# Mix 8 on the Pricing sheet: 5,000 PSI / Ash no Air. Every CY on this deck.
MIX_CODE = "5000-ASH"
MIX_UNIT_COST = Decimal("175.00")

MATERIAL_PRICES = {
    "REBAR GRADE BEAM": Decimal("0.6500"),   # 08 F78 -> Pricing!D23
    "2 X 4  X 16'": Decimal("0.859375"),     # 08 U73
    "2 X 6 X 16'": Decimal("1.4453125"),     # 08 U74
    "2 X 10 X 16'": Decimal("1.09375"),      # 08 U78
    '3/4 " FORMING PLY': Decimal("74.75"),   # 08 U80
    "2 x 2 x 30 stakes": Decimal("24.00"),   # 08 U81
    "16p NAILS DUPLEX": Decimal("68.20"),    # 08 U82
    "8p DUPLEX": Decimal("68.20"),           # 08 U83
    "6p NAILS": Decimal("68.20"),            # 08 U84
    "PAVECRETE": Decimal("15.00"),           # 08 U104
    "SLAB CHAIRS": Decimal("27.00"),         # 08 U107
    # The typed-over cell. 08 U109 says 0.02; sql/044 says the catalog is the
    # source and the catalog says 0.04. Stated here at the CATALOG figure, so
    # the difference is a documented +$1,234.31 rather than a silent one.
    "ACCESSORIES": Decimal("0.0400"),
    "SLAB CURE": Decimal("567.50"),          # 08 U114
}

EQUIPMENT_PRICES = {
    "SKID STEER": Decimal("325.00"),                 # 08 F107 -> Pricing!D35
    "TOWER LIGHT w/ GENERATOR": Decimal("100.00"),   # 08 F108 -> Pricing!D39
    "SKY LIFT": Decimal("380.00"),                   # 08 F109 -> Pricing!D41
    # 08 F106. The catalog carries this machine at $2,400/day. On 27 billable
    # days that is $21,600 before fuel and tax — stated here at the BID's
    # figure so the section reproduces, and raised as a question rather than
    # buried. The catalog wins at runtime (sql/044), which is the right
    # default and the reason the gap has to be settled.
    "CRANE AND OPERATOR": Decimal("3200.00"),
    # 08 F105, the 20 TON LIFT, has no catalog row and 0 days on this job, so
    # it rides `equip_20_ton_lift_day_rate` — same as columns' STORAGE.
}

SETTINGS = {
    "sales_tax_pct": "0.0825",               # 08 V64
    "equip_fuel_maint_pct": "0.50",          # 08 I107
    "labor_super_day_rate": "425",           # 08 F100
    "labor_foreman_day_rate": "250",         # 08 F101
    "labor_expense_day_rate": "100",         # 08 F102
    "labor_pm_day_rate": "200",              # 08 F103
}

# --------------------------------------------------------------- section ----
SECTION = dict(
    kind="cip_deck",
    name="08-CIP El. Deck",
    unit="SF",
    margin_pct=Decimal("0.18"),
    contingency_pct=Decimal("0.00"),
    tax_exempt=None,
    # All ten labor lines are `Y` on this job — $251,654.73 subbed, and the
    # own-crew column zero throughout. Chad, 2026-09-04, asked whether the
    # per-line switch is real: one switch per section.
    labor_subcontracted=True,
)

SUPER_DAYS = Decimal("60")                   # 08 D100, typed

# label, SF, thickness in, cable, perm edge LF, top size, top space,
# bottom size, bottom space
LEVELS = [
    ("level 2", 10447, 14, True,  628, 4, 10, None, None),
    ("level 3", 21653, 14, True, 1056, 4, 10, None, None),
]

# beam #, width in, height in, top n/size, bottom n/size, mid n/size,
# stirrup size/spacing, L size/spacing/length ft
BEAMS = [
    (1, 18, 24, 4, 8, 4, 8, 4, 8, 4, 10, 4, 10, 4),   # 08 row 53 — 56.6982 lb/LF
    (2, 24, 24, 5, 8, 5, 8, 4, 8, 4, 10, 4, 10, 4),   # 08 row 54 — 63.4553 lb/LF
]

# level index -> [(beam #, LN FT)]. Level 2 runs both types; level 3 runs one.
# On the sheet the 45 LF of type 2 under level 2 is the beam that gets charged
# 7 lb instead of 2,855.49.
LEVEL_BEAMS = {
    0: [(1, 30), (2, 45)],
    1: [(2, 45)],
}

# ----------------------------------------------------------- the numbers ----
# What 08-CIP EL. DECK itself reads, on its own conventions.
SHEET = {
    "total_sf": Decimal("32100"),
    "concrete_cy": Decimal("1459.8518518518517"),
    "steel_lb": Decimal("61715.45971435001"),
    "pt_sf": Decimal("32100"),
    "pt_lb": Decimal("36915"),
    "perm_edge_lf": Decimal("1684"),
    "gb_form_ff": Decimal("240"),            # ONE face
    "super_days": Decimal("60"),
    "equip_days": Decimal("90"),
    "billable_units": Decimal("27"),
    "sub_labor": Decimal("251654.73"),
    "lumber_block": Decimal("11029.9177"),
    "total_cost": Decimal("952052.0215"),
    "total_sale": Decimal("1123421.3853"),
    "cost_per_sf": Decimal("29.6589"),
    # The nineteen cost columns the sheet totals itself with (BJ50:CC50),
    # which is what the app is reconciled against part by part.
    "parts": {
        "concrete": Decimal("276550.6852"),
        "steel": Decimal("43424.5403"),
        "cables": Decimal("50384.9625"),
        "labor_sf": Decimal("194205"),        # forming + place + wreck + reshore
        "edge_rails": Decimal("10104"),
        "gb_forming": Decimal("1440"),
        "rub_patch": Decimal("8025"),
        "cable_placement": Decimal("23994.75"),
        "tie_steel": Decimal("13885.9784"),
        "supervision": Decimal("58500"),
        "lumber": Decimal("8579.6098"),
        "shoring": Decimal("73840.03"),       # plywood forming + form rental
        "equipment": Decimal("172068.6375"),
        "contract": Decimal("14598.5185"),
        "accessories": Decimal("2450.3092"),
    },
}

# What the APP reads — the sheet plus every difference named in the module
# docstring above, each of which has its own test.
GOLDEN_COST = Decimal("956185.45")


def price_the_catalog(db) -> dict:
    """Bid prices for the life of this test. Rolled back with everything else."""
    mix_id = db.execute(
        text("UPDATE mix_designs SET unit_cost = :c WHERE code = :k RETURNING id"),
        {"c": MIX_UNIT_COST, "k": MIX_CODE},
    ).scalar()
    assert mix_id is not None, f"no mix design {MIX_CODE} in the catalog"

    for name, cost in MATERIAL_PRICES.items():
        found = db.execute(
            text(
                "UPDATE materials SET unit_cost = :c "
                "WHERE id = (SELECT id FROM materials WHERE name ILIKE :n "
                "            ORDER BY sort_order, id LIMIT 1) RETURNING id"
            ),
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

    beams: dict[int, EstimateBeamType] = {}
    for order, (
        num, w, h, tn, ts, bn, bs, mn, ms, ssz, ssp, lsz, lsp, llen
    ) in enumerate(BEAMS):
        bt = EstimateBeamType(
            section_id=section.id,
            label=f"GB{num}",
            kind="grade_beam",
            width_in=Decimal(w),
            height_in=Decimal(h),
            top_bars_count=tn, top_bars_size=ts,
            bottom_bars_count=bn, bottom_bars_size=bs,
            mid_bars_count=mn, mid_bars_size=ms,
            stirrup_size=ssz, stirrup_spacing_in=Decimal(ssp),
            l_bars_size=lsz, l_bars_spacing_in=Decimal(lsp),
            l_bars_length_ft=Decimal(llen),
            sort_order=order * 10,
        )
        db.add(bt)
        beams[num] = bt
    db.flush()

    levels = []
    for order, (lab, sf, th, cable, edge, tsz, tsp, bsz, bsp) in enumerate(LEVELS):
        row = DeckLevel(
            section_id=section.id,
            label=lab,
            area_sf=Decimal(sf),
            thickness_in=Decimal(th),
            has_cable=cable,
            mix_design_id=mix_id,
            perm_edge_lf=Decimal(edge),
            top_bar_size=tsz,
            top_bar_spacing_in=Decimal(tsp) if tsp else None,
            bot_bar_size=bsz,
            bot_bar_spacing_in=Decimal(bsp) if bsp else None,
            sort_order=order * 10,
        )
        db.add(row)
        db.flush()
        for i, (num, lf) in enumerate(LEVEL_BEAMS.get(order, [])):
            db.add(
                DeckLevelBeam(
                    deck_level_id=row.id,
                    beam_type_id=beams[num].id,
                    length_lf=Decimal(lf),
                    sort_order=i * 10,
                )
            )
        db.flush()
        levels.append(row)

    for row in levels:
        refresh_deck_level_calcs(db, row, section, sheet_mode=sheet_mode)
    db.flush()
    return section


def type_the_supervision(db, section_id) -> None:
    """
    A deck TYPES its days, like piers and walls — 60 on LBJ (08 D100).

    Run this AFTER the labor and equipment refreshes: typing the days moves
    the rental ladder on the NEXT refresh, which is audit #5 and the reason
    test_piers does it in this order.
    """
    from app.services.labor import update_labor_line

    # 60 days for all four — 08 D101, D102 and D103 are each `= D100`.
    for code in ("superintendent", "foreman", "expense", "pm"):
        update_labor_line(db, section_id, code, qty=SUPER_DAYS, mark_manual=True)


def build(db, estimate, *, sheet_mode: bool = False):
    priced = price_the_catalog(db)
    from app.services.price_book import pull_prices

    pull_prices(db, estimate.id)
    return build_section(db, estimate, priced["mix_id"], sheet_mode=sheet_mode)
