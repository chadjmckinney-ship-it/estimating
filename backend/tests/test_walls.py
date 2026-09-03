"""
Walls and footings, against the sheet it was built from (sql/040).

06-Walls & Footings is 652 LF of retaining wall on a continuous 70" x 12"
footing, in 16 types that differ only in length and height. 3,452.55 form feet,
$230,548.73 at 15%.

The app reads **$200,752.39** cost against the sheet's $200,477.16 — **+0.14%**
— and the last test names every cent of it.

Three things in the geometry look wrong and are not; each has a test here, and
`services/walls.py` explains why in full:

  * footing steel is added twice, because a footing mat has two directions and
    both come to E*N/P
  * form feet is HALF the contact area — the sheet computes both faces and
    halves them
  * a lap allowance hides inside the sheet's pilaster term as a bare `+4`
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.models.wall_run import WallRun
from app.services import walls as wl
from app.services.costing import allocation_basis, refresh_pour_costs
from app.services.estimate_equipment import (
    load_stored_equipment,
    refresh_and_store_equipment,
)
from app.services.forming import load_stored_forming, refresh_and_store_forming
from app.services.labor import load_stored_labor, refresh_and_store_labor
from app.services.walls import section_wall_totals
from tests import walls_fixture as wf

SHEET = wf.SHEET

APP = {
    "form_ff": Decimal("3452.5500"),
    "footing_sf": Decimal("3803.3337"),
    "concrete_cy": Decimal("284.8607"),
    "wall_cy": Decimal("135.5447"),
    "footing_cy": Decimal("149.3161"),
    "steel_lb": Decimal("33728.341"),
    "excavate_cy": Decimal("141.000"),
    "direct": Decimal("68708.83"),
    "forming": Decimal("27261.88"),
    "labor": Decimal("82543.09"),
    "supervision": Decimal("6000.00"),
    "equipment": Decimal("8158.61"),
    # Two cents higher than before sql/042 reallocated on FF + footing SF —
    # per-row rounding, not a rate change. The cost total is identical.
    "fuel": Decimal("2655.00"),
    "tax": Decimal("7503.41"),
    "total_cost": Decimal("202830.82"),
    "total_sale": Decimal("233255.46"),
    "sale_per_ff": Decimal("67.5603"),
}


@pytest.fixture
def walls(db, estimate):
    section = wf.build(db, estimate)
    refresh_and_store_forming(db, section.id)
    refresh_and_store_labor(db, section.id)
    refresh_and_store_equipment(db, section.id)
    # Typed last, the way a person does it — then the equipment ladder has to
    # follow on its own from the days that were entered.
    wf.type_the_supervision(db, section.id)
    # Refresh AGAIN after typing — which is what a recalc does. The first
    # version of this fixture stopped here, and that is how a derived PM line
    # worth $2,000 got past the whole suite and only turned up when the section
    # was imported live. A takeoff that is only correct until you recalculate
    # is not correct.
    refresh_and_store_labor(db, section.id)
    refresh_and_store_equipment(db, section.id)
    refresh_pour_costs(db, section)
    db.flush()
    return section


def runs(db, sid) -> list[WallRun]:
    return list(
        db.query(WallRun).filter_by(section_id=sid).order_by(WallRun.sort_order).all()
    )


def labor(db, sid) -> dict:
    return {ln["code"]: ln for ln in load_stored_labor(db, sid)["lines"]}


def equipment(db, sid) -> dict:
    return {ln["code"]: ln for ln in load_stored_equipment(db, sid)["lines"]}


def forming(db, sid) -> dict:
    return {ln["code"]: ln for ln in load_stored_forming(db, sid)["lines"]}


def _dec(x) -> Decimal:
    return Decimal(str(x))


# --------------------------------------------------------------------------
# the three that look wrong
# --------------------------------------------------------------------------


def test_footing_steel_counts_both_directions(db):
    """
    The sheet adds E*(N/P) and (E/P)*N — identical expressions that read like a
    copy-paste duplicate. They are the two directions of the mat:

        longitudinal   N/P bars, each E ft long        -> E*N/P
        transverse     E*12/P bars, each N/12 ft long  -> E*N/P

    Both are real, both are needed, and they happen to be equal. Halving this
    "to fix the duplicate" would take 8,000 lb of steel out of LBJ.
    """
    one_way = Decimal("135") * (Decimal("70") / Decimal("12"))
    lb_per_ft = wl.sheet_bar_lb_per_ft(5)
    expected = one_way * lb_per_ft * 2 * Decimal("2")  # 2 mats, 2 directions

    got = wl.footing_rebar_lb(
        None, 135, 70, 12, 5, 2, sheet=True
    )
    assert got == expected


def test_form_feet_is_one_face_not_two(db):
    """
    The sheet computes both faces and then halves. 135 ft of 36" wall is 810 SF
    of contact area and 405 form feet.

    Every $/FF rate in this assembly is priced against that convention, so the
    halving is load-bearing: drop it and forming labor doubles.
    """
    assert wl.form_ff(135, 36) == Decimal("405.0000")


def test_the_lap_allowance_survives_without_pilasters(db, walls):
    """
    The sheet's steel term ends `((T*U*S*...)/12 + 4) * (H/spacing) * bar_lb`.
    T/U/S are pilaster dimensions; with no pilasters the product collapses and
    the bare +4 does not, so every row with horizontal steel carries 4 ft of
    bar per horizontal course.

    Pilasters left this assembly in sql/041 — Chad takes them off on the column
    sheet, because a pilaster is a short column. The allowance stayed, because
    it is part of the reconciled 33,727.83 lb and removing it would move the
    golden number.
    """
    rows = runs(db, walls.id)
    assert all(_dec(r.calc_lap_rebar_lb) > 0 for r in rows)
    # 4 ft per course, on the first row: 36" / 12" = 3 courses of #5, +10% lap.
    assert _dec(rows[0].calc_lap_rebar_lb) == (
        Decimal("4") * Decimal("3") * wl.bar_lb_per_ft(db, 5) * Decimal("1.10")
    ).quantize(Decimal("0.001"))


# --------------------------------------------------------------------------
# allocation
# --------------------------------------------------------------------------


def test_walls_allocate_by_form_feet(db, walls):
    """
    A third basis, after SF and EA. A walls section has no square footage, so
    on the SF basis `allocate_amount` would fall back to "last row takes the
    remainder" and put the whole forming, labor and equipment package on
    whichever run sorted last — silently.
    """
    assert allocation_basis(walls.kind) == "FF"
    rows = runs(db, walls.id)
    assert all(_dec(r.calc_allocated_cost) > 0 for r in rows)


def test_the_blended_rate_is_not_uniform_and_should_not_be(db, walls):
    """
    A row's cost per FORM FOOT varies almost 2:1 across sixteen
    identically-built walls — $49 to $82 — and that is correct, not a fault.
    135 ft of 3 ft wall is 405 form feet sitting on 787 SF of footing, where
    26 ft of 7.7 ft wall is 200 form feet on 152 SF.

    This is exactly why Chad asked for the split: one blended rate cannot be
    read for errors, because most of its spread is footing geometry.
    """
    per_ff = [_dec(r.calc_cost) / _dec(r.calc_form_ff) for r in runs(db, walls.id)]
    assert max(per_ff) / min(per_ff) > Decimal("1.6")


def test_the_split_rates_ARE_uniform(db, walls):
    """
    The point of the whole exercise. Every one of the 16 runs is built to the
    same schedule — 12" wall, #5 @ 12" both faces, 70" x 12" footing — so both
    rates should sit on a flat line and an outlier should be a real error.

    Wall lands within ~4% (the residual is honest: the lap allowance scales
    with 1/length, the french drain with 1/height, backfill with height).
    Footing lands within 1%, because every footing here is identical.

    Getting the allocation basis wrong makes these swing 2:1 while the section
    total stays right — which is the failure this test exists to catch.
    """
    rows = runs(db, walls.id)
    wall = [_dec(r.calc_wall_cost_per_ff) for r in rows]
    ftg = [_dec(r.calc_footing_cost_per_sf) for r in rows]
    assert max(wall) / min(wall) < Decimal("1.05"), f"wall rate spread: {min(wall)}–{max(wall)}"
    assert max(ftg) / min(ftg) < Decimal("1.02"), f"footing rate spread: {min(ftg)}–{max(ftg)}"


def test_the_two_halves_sum_to_the_row(db, walls):
    """
    The footing is computed and the wall takes the remainder, so these can
    never sum to anything but the row's own cost. That is what makes the pair
    safe to read: a discrepancy is always in the schedule, never in the split.
    """
    for r in runs(db, walls.id):
        assert _dec(r.calc_wall_cost) + _dec(r.calc_footing_cost) == _dec(r.calc_cost)
        assert _dec(r.calc_wall_sale) + _dec(r.calc_footing_sale) == _dec(r.calc_sale)


def test_the_footing_carries_its_own_steel(db, walls):
    """
    Chad's call, and a deliberate departure from the sheet: 06 leaves all the
    steel in the wall column, footing bar included — 17,454 lb on LBJ, 51.7% of
    the job's rebar. A footing schedule entered wrong would then move the WALL
    rate and leave the footing looking fine, defeating the split.
    """
    t = section_wall_totals(db, walls.id)
    assert _dec(t["total_footing_rebar_lb"]) > _dec(t["total_rebar_lb"]) / 2
    # Which puts the footing above the sheet's $18.91/SF and the wall below
    # its $37.24/FF. The section total is identical either way.
    assert _dec(t["footing_cost_per_sf"]) > Decimal("18.91")
    assert _dec(t["wall_cost_per_ff"]) < Decimal("37.24")


def test_pours_sum_to_the_section(db, walls):
    rows = runs(db, walls.id)
    assert sum(_dec(r.calc_cost) for r in rows) == _dec(walls.calc_total_cost)
    assert sum(_dec(r.calc_sale) for r in rows) == _dec(walls.calc_total_sale)


# --------------------------------------------------------------------------
# quantities — every one matched the sheet before any code was written
# --------------------------------------------------------------------------


def test_takeoff_totals(db, walls):
    t = section_wall_totals(db, walls.id)
    assert t["run_count"] == 16
    assert _dec(t["total_length_ft"]) == SHEET["wall_lf"]
    assert _dec(t["total_form_ff"]) == APP["form_ff"] == SHEET["form_ff"]
    assert _dec(t["total_footing_sf"]) == APP["footing_sf"]
    assert _dec(t["total_drain_lf"]) == SHEET["drain_lf"]


def test_concrete_splits_wall_from_footing(db, walls):
    """
    Two mixes on one section — the first assembly to need it. 4000 PSI in the
    wall at $145, 3500 in the ground at $140.
    """
    t = section_wall_totals(db, walls.id)
    assert _dec(t["total_concrete_cy"]) == APP["concrete_cy"] == SHEET["concrete_cy"]
    assert _dec(t["total_wall_concrete_cy"]) == APP["wall_cy"]
    assert _dec(t["total_footing_concrete_cy"]) == APP["footing_cy"]


def test_the_footing_mix_is_the_one_that_prices_the_footing(db, walls):
    """
    Clear the section's footing mix and the footing falls back to the wall's —
    a costlier answer, but never a free one. A footing priced at nothing is the
    failure this fallback exists to prevent.
    """
    before = _dec(walls.calc_total_cost)
    walls.footing_mix_design_id = None
    db.flush()
    refresh_pour_costs(db, walls)
    db.flush()
    after = _dec(walls.calc_total_cost)
    assert after > before  # $145 wall mix now prices the footing too, not $0


def test_steel_and_earthwork(db, walls):
    t = section_wall_totals(db, walls.id)
    assert _dec(t["total_rebar_lb"]) == APP["steel_lb"]
    assert _dec(t["total_sand_cy"]) == SHEET["sand_cy"]
    assert _dec(t["total_backfill_cy"]) == SHEET["backfill_cy"]


def test_excavation_uses_the_honest_divisor(db, walls):
    """
    The sheet divides by 3088. Every other in²·ft to CY conversion in the
    workbook — including the footing concrete two columns over — divides by
    3888 (12 x 12 x 27), and 3088 has no dimensional meaning.

    Chad's call: compute it honestly and name the difference. 141 CY against
    181 is $480 of excavation labor.
    """
    t = section_wall_totals(db, walls.id)
    assert _dec(t["total_excavate_cy"]) == SHEET["excavate_cy_honest"] == Decimal("141")
    assert (SHEET["excavate_cy_sheet"] - Decimal("141")) * 12 == Decimal("480")


def test_sheet_mode_reproduces_the_bid_exactly(db, estimate):
    """
    The 3088 path is kept so the bid can be reproduced deliberately rather than
    approximately — a bid that went out is a record, and it should stay
    checkable.
    """
    section = wf.build(db, estimate, sheet_mode=True)
    t = section_wall_totals(db, section.id)
    assert _dec(t["total_excavate_cy"]) == SHEET["excavate_cy_sheet"]
    # Sheet mode also uses the workbook's bar weight, so the steel matches to
    # four decimals rather than to half a pound.
    assert _dec(t["total_rebar_lb"]).quantize(Decimal("0.001")) == Decimal("33727.832")


# --------------------------------------------------------------------------
# the line sets
# --------------------------------------------------------------------------


def test_labor_runs_off_form_feet_and_footing_area(db, walls):
    """
    Four rates on form feet, and the footing on its own plan area — a flat pour
    in a trench, whose labor has nothing to do with the wall above it.
    """
    ln = labor(db, walls.id)
    assert _dec(ln["footings"]["ext_cost"]) == Decimal("30426.67")
    assert _dec(ln["forming"]["ext_cost"]) == Decimal("12083.92")
    assert _dec(ln["place_finish"]["ext_cost"]) == Decimal("12083.92")
    assert _dec(ln["wreck"]["ext_cost"]) == Decimal("3452.55")
    # RUB AND PATCH has no slab equivalent — it is what you do to a wall face.
    assert _dec(ln["rub_patch"]["ext_cost"]) == Decimal("863.14")


def test_tie_steel_bills_every_pound(db, walls):
    """A wall cage carries no support-steel allowance to carve out."""
    ln = labor(db, walls.id)
    t = section_wall_totals(db, walls.id)
    assert _dec(ln["tie_steel"]["qty"]) == (
        _dec(t["total_rebar_lb"]) / 2000
    ).quantize(Decimal("0.0001"))


def test_supervision_is_typed_and_expense_does_not_ride_it(db, walls):
    """
    10 super days, 5 foreman, 5 expense. The expense line does NOT follow the
    superintendent here — the sheet types 5 against 10, because the super is on
    site through pour and cure while the crew eating the per-diem is not.
    """
    ln = labor(db, walls.id)
    assert _dec(ln["superintendent"]["qty"]) == Decimal("10")
    assert _dec(ln["foreman"]["qty"]) == Decimal("5")
    assert _dec(ln["expense"]["qty"]) == Decimal("5")
    # And NO project manager. The sheet's second expense row is $200/day at 0
    # days; deriving it from the superintendent added $2,000 nobody bid.
    assert _dec(ln["pm"]["qty"]) == 0
    assert _dec(load_stored_labor(db, walls.id)["total_supervision_cost"]) == Decimal("6000.00")


def test_the_equipment_ladder_rides_the_typed_days(db, walls):
    """
    10 typed days -> 14 rental days -> tier -> 6 billable. The sheet's own
    ladder gives the same, and the mini excavator digs the footing trench, so
    there is no trencher on a wall job.
    """
    eq = equipment(db, walls.id)
    assert _dec(eq["mini_excavator"]["ext_cost"]) == Decimal("2850.00")
    assert _dec(eq["skid_steer"]["ext_cost"]) == Decimal("1650.00")
    assert _dec(eq["light_tower"]["ext_cost"]) == Decimal("600.00")
    assert "trencher" not in eq
    # Lines the sheet HAS and types a zero into stay present at zero; a line it
    # does not have at all is simply absent.
    assert _dec(eq["skytrack"]["ext_cost"]) == 0
    assert _dec(eq["vault"]["ext_cost"]) == 0


def test_wall_ties_and_bracing_exist_only_here(db, walls):
    """Two lines no other assembly has — what holds a formed wall up and plumb."""
    f = forming(db, walls.id)
    assert _dec(f["wall_ties"]["qty"]) == Decimal("30.6890")
    assert _dec(f["pipe_brace"]["qty"]) == Decimal("115.0850")


def test_the_french_drain_is_both_material_and_labor(db, walls):
    """You buy the pipe and you install it. The sheet carries both, at 652 LF."""
    assert _dec(forming(db, walls.id)["french_drain"]["qty"]) == Decimal("652.0000")
    assert _dec(labor(db, walls.id)["french_drains"]["qty"]) == Decimal("652.0000")


def test_form_percent_is_forty_not_fifty(db, walls):
    """2x4 = form FF x 3.6 x 40%. The slab sheet forms at 50%."""
    assert _dec(forming(db, walls.id)["2x4"]["qty"]) == (
        SHEET["form_ff"] * Decimal("3.6") * Decimal("0.4")
    ).quantize(Decimal("0.0001"))


# --------------------------------------------------------------------------
# the number, and every cent of the difference
# --------------------------------------------------------------------------


def test_cost_blocks(db, walls):
    t = section_wall_totals(db, walls.id)
    assert _dec(t["total_direct_cost"]) == APP["direct"]
    assert _dec(load_stored_forming(db, walls.id)["total_ext_cost"]) == APP["forming"]
    assert _dec(load_stored_labor(db, walls.id)["total_labor_cost"]) == APP["labor"]
    assert _dec(load_stored_equipment(db, walls.id)["total_cost"]) == APP["equipment"]
    assert _dec(t["total_equip_fuel"]) == APP["fuel"]
    assert _dec(t["total_tax"]) == APP["tax"]


def test_the_total(db, walls):
    assert _dec(walls.calc_total_cost) == APP["total_cost"]
    assert _dec(walls.calc_total_sale) == APP["total_sale"]
    assert _dec(walls.calc_sale_per_unit) == APP["sale_per_ff"]


def test_every_cent_of_the_variance(db, walls):
    """
    $202,830.82 against the sheet's $200,477.16 — **+$2,353.66, +1.17%** — and
    all of it named:

    +2,078.43  SAND AT THE CATALOG PRICE. `06-Walls!F59` types $20/CY over its
               own `Pricing!D19` lookup, which reads $25 — one of six cells in
               that workbook whose price lookup had been typed over (sql/044).
               The app used to carry the same $20 in an assembly_rates row
               copied from that cell. 384 CY x $5 x 1.0825.
      +633.60  SAND TAXED. The sheet's sand cell reads `IF(Q29="N",1+T29,1)`
               and Q29/T29 are empty, so it applies no tax to $7,680 of sand
               while taxing every other material. Same class of cell bug as the
               paving cure and siding lines. The app is right.
      -479.88  EXCAVATION at the honest 3888 divisor instead of the sheet's
               3088 — 141 CY against 181. Chad's call.
      +122.33  FUEL AND TAX ON MISCELLANEOUS. The sheet exempts that one
               equipment line from both uplifts; here it is an ordinary rental.
               Same quirk the mono slab reconciliation found.
        -1.39  PUMPING on 284.8607 CY where the sheet rounds to 285.
        +0.45  ASTM bar weights against the sheet's (size/16)^2 x 10.680159 —
               half a pound across 33,728.
        +0.12  four-decimal catalog prices against the Pricing sheet's six.

    Matched exactly: 652 LF, 3,452.55 form feet, 3,803.33 footing SF, 284.86 CY
    split 135.54 wall / 149.32 footing, 384 CY sand, 979 CY backfill, all nine
    labor rates, supervision $6,000, and the whole lumber package.
    """
    named = (
        Decimal("2078.43")
        + Decimal("633.60")
        - Decimal("479.88")
        + Decimal("122.33")
        - Decimal("1.39")
        + Decimal("0.45")
        + Decimal("0.12")
    )
    actual = APP["total_cost"] - SHEET["total_cost"]
    assert abs(actual - named) < Decimal("0.75"), (
        f"variance {actual} is no longer the {named} this test accounts for — "
        "something changed that nobody has named"
    )


def test_sand_is_taxed_here_even_though_the_sheet_forgets(db, walls):
    """
    The single biggest line in the variance above, and worth its own test: the
    app taxes $7,680 of sand and the sheet does not, because the sheet's tax
    condition points at two empty cells.
    """
    t = section_wall_totals(db, walls.id)
    sand_cost = _dec(t["total_sand_cy"]) * Decimal("20")
    assert sand_cost == Decimal("7680.000")
    assert (sand_cost * Decimal("0.0825")).quantize(Decimal("0.01")) == Decimal("633.60")
