"""
Naming the vapor barrier instead of guessing it (sql/030).

The old rule searched the catalog for a name containing "10 mil" and "20". On
the LBJ job that found "POLY 10 mil 20 x 100 Black" at $105/roll — $0.0525/SF —
against the 10 mil Yellow Guard at $0.125/SF the job was actually bid on. Worth
$9,008, and Yellow Guard could not have won that search at any price: its name
has no "20" in it. The roll that did win is filed under site_accessories, not
vapor_barrier, so nothing about the match was meaningful.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import text

from app.services.costing import (
    _poly_cost,
    _tape_cost,
    barrier_rolls,
    refresh_pour_costs,
    resolve_vapor_barrier,
    resolve_vapor_tape,
    roll_coverage_sf,
)

YELLOW = "10 mil Yellow Guard 14' x 210'"  # 2,940 SF a roll


def material(db, name, unit_cost, unit="ROLL", category="vapor_barrier") -> int:
    """Find or create — the seeded catalog already carries most of these names."""
    found = db.execute(
        text("SELECT id FROM materials WHERE name = :n AND unit = :u"),
        {"n": name, "u": unit},
    ).scalar()
    if found:
        db.execute(
            text("UPDATE materials SET unit_cost = :p, category = :c WHERE id = :i"),
            {"p": unit_cost, "c": category, "i": found},
        )
        db.flush()
        return found
    new = db.execute(
        text(
            "INSERT INTO materials (name, category, unit, unit_cost) "
            "VALUES (:n, :c, :u, :p) RETURNING id"
        ),
        {"n": name, "c": category, "u": unit, "p": unit_cost},
    ).scalar()
    db.flush()
    return new


# --------------------------------------------------------------------------
# Resolution order
# --------------------------------------------------------------------------


def test_the_estimate_choice_wins(db, section):
    yellow = material(db, "10 mil Yellow Guard 14' x 210'", Decimal("310"))
    section.vapor_barrier_material_id = yellow
    db.flush()

    mat = resolve_vapor_barrier(db, section)
    assert mat["id"] == yellow
    assert "Yellow Guard" in mat["name"]


def test_the_company_default_is_used_when_the_estimate_has_none(db, section, setting):
    yellow = material(db, "10 mil Yellow Guard 14' x 210'", Decimal("310"))
    setting("default_vapor_barrier_material_id", str(yellow))

    assert section.vapor_barrier_material_id is None
    assert resolve_vapor_barrier(db, section)["id"] == yellow


def test_the_estimate_overrides_the_company_default(db, section, setting):
    default = material(db, "10 mil Yellow Guard 14' x 210'", Decimal("310"))
    stego = material(db, "15 mil Stego Wrap 14' x 140'", Decimal("370"))
    setting("default_vapor_barrier_material_id", str(default))
    section.vapor_barrier_material_id = stego
    db.flush()

    assert resolve_vapor_barrier(db, section)["id"] == stego


def test_it_falls_back_to_the_old_search_when_nothing_is_set(db, section):
    """
    Estimates nobody has set keep their old numbers rather than silently
    dropping to $0 poly.
    """
    assert section.vapor_barrier_material_id is None
    mat = resolve_vapor_barrier(db, section)
    assert mat is not None
    assert "10 mil" in mat["name"]


# --------------------------------------------------------------------------
# What it costs
# --------------------------------------------------------------------------


def test_a_roll_prices_by_its_coverage(db):
    mat = {"name": "10 mil Yellow Guard 14' x 210'", "unit": "ROLL", "unit_cost": Decimal("310")}
    # 14 × 210 = 2,940 SF a roll → $0.10544/SF, on 10,000 SF
    assert _poly_cost(db, Decimal("10000"), mat) == Decimal("1054.42")


def test_the_wrong_roll_really_is_half_price(db):
    """The two rolls side by side, on the LBJ poly area."""
    area = Decimal("158108.864")
    yellow = {"name": "10 mil Yellow Guard 14' x 210'", "unit": "ROLL", "unit_cost": Decimal("310")}
    black = {"name": "POLY 10 mil 20 x 100 Black", "unit": "ROLL", "unit_cost": Decimal("105")}
    assert _poly_cost(db, area, yellow) == Decimal("16671.34")
    assert _poly_cost(db, area, black) == Decimal("8300.72")


def test_a_material_priced_per_sf_needs_no_coverage(db):
    mat = {"name": "House brand vapor barrier", "unit": "SF", "unit_cost": Decimal("0.11")}
    assert _poly_cost(db, Decimal("10000"), mat) == Decimal("1100.00")


def test_a_roll_with_no_dimensions_in_its_name_prices_nothing(db):
    """
    Stego Tape is in the vapor_barrier category with no dimensions. Picking it
    is a configuration mistake, and it reads as $0 rather than a wrong number.
    """
    assert roll_coverage_sf("Stego Tape") is None
    mat = {"name": "Stego Tape", "unit": "EA", "unit_cost": Decimal("49.50")}
    assert _poly_cost(db, Decimal("10000"), mat) == Decimal("0.00")


def test_no_poly_area_costs_nothing(db):
    mat = {"name": "10 mil Yellow Guard 14' x 210'", "unit": "ROLL", "unit_cost": Decimal("310")}
    assert _poly_cost(db, Decimal("0"), mat) == Decimal("0.00")


# --------------------------------------------------------------------------
# End to end
# --------------------------------------------------------------------------


def test_choosing_the_product_moves_the_pour_cost(db, section, pour):
    black = material(db, "POLY 10 mil 20 x 100 Black", Decimal("105"), category="site_accessories")
    section.vapor_barrier_material_id = black
    db.flush()
    refresh_pour_costs(db, section)
    db.flush()
    cheap = pour.calc_direct_cost

    yellow = material(db, "10 mil Yellow Guard 14' x 210'", Decimal("310"))
    section.vapor_barrier_material_id = yellow
    db.flush()
    refresh_pour_costs(db, section)
    db.flush()

    assert pour.calc_direct_cost > cheap
    # 11,000 SF of poly on the fixture pour × ($310/2940 − $105/2000)
    delta = pour.calc_direct_cost - cheap
    assert delta == Decimal("582.36")


def test_the_recalc_report_names_the_roll_it_used(db, section, pour):
    yellow = material(db, "10 mil Yellow Guard 14' x 210'", Decimal("310"))
    section.vapor_barrier_material_id = yellow
    db.flush()
    out = refresh_pour_costs(db, section)
    assert "Yellow Guard" in out["vapor_barrier"]


# --------------------------------------------------------------------------
# Seam tape (sql/031)
#
# Tape is bought per roll of wrap, not per SF of slab, so the driver is the
# barrier's roll count. Change the wrap and the tape changes with it.
# --------------------------------------------------------------------------


def test_tape_comes_from_the_estimate_then_the_company_default(db, section, setting):
    house = material(db, "Yellow Guard Tape 4in x 180ft", Decimal("18.75"), unit="EA")
    stego = material(db, "Stego Tape 3.75in x 180ft", Decimal("49.50"), unit="EA")
    setting("default_vapor_tape_material_id", str(house))

    assert resolve_vapor_tape(db, section)["id"] == house

    section.vapor_tape_material_id = stego
    db.flush()
    assert resolve_vapor_tape(db, section)["id"] == stego


def test_no_tape_is_set_anywhere_and_none_is_guessed(db, section):
    """
    Unlike the barrier there is no legacy name search to fall back on — an
    unset tape is no tape, not a lucky match on something in the catalog.
    """
    assert section.vapor_tape_material_id is None
    assert resolve_vapor_tape(db, section) is None


def test_rolls_of_wrap_drive_the_count(db):
    yellow = {"name": YELLOW, "unit": "ROLL", "unit_cost": Decimal("310")}
    assert barrier_rolls(Decimal("5880"), yellow) == Decimal("2")


def test_a_barrier_priced_per_sf_has_no_rolls_and_so_no_tape(db):
    """
    A house-brand barrier quoted in $/SF carries no roll count, so there is
    nothing to tape per roll. It reads as $0 rather than a made-up number.
    """
    sf_priced = {"name": "House brand vapor barrier", "unit": "SF", "unit_cost": Decimal("0.11")}
    tape = {"name": "Stego Tape", "unit": "EA", "unit_cost": Decimal("49.50")}
    assert barrier_rolls(Decimal("10000"), sf_priced) == Decimal("0.00")
    assert _tape_cost(db, Decimal("10000"), sf_priced, tape, Decimal("1")) == Decimal("0.00")


def test_the_ratio_multiplies_the_rolls(db):
    yellow = {"name": YELLOW, "unit": "ROLL", "unit_cost": Decimal("310")}
    tape = {"name": "Stego Tape", "unit": "EA", "unit_cost": Decimal("49.50")}
    # 5,880 SF = 2 rolls of wrap
    assert _tape_cost(db, Decimal("5880"), yellow, tape, Decimal("1")) == Decimal("99.00")
    assert _tape_cost(db, Decimal("5880"), yellow, tape, Decimal("2")) == Decimal("198.00")
    assert _tape_cost(db, Decimal("5880"), yellow, tape, Decimal("0.5")) == Decimal("49.50")


def test_partial_rolls_are_not_rounded_up(db):
    """
    The barrier itself prices fractionally (a roll and a bit of poly costs a
    roll and a bit), and the tape follows the same rule so the two stay in
    step. Rounding tape up per pour would double-count on a multi-pour job.
    """
    yellow = {"name": YELLOW, "unit": "ROLL", "unit_cost": Decimal("310")}
    tape = {"name": "Stego Tape", "unit": "EA", "unit_cost": Decimal("49.50")}
    # 4,410 SF = 1.5 rolls → 1.5 × $49.50
    assert _tape_cost(db, Decimal("4410"), yellow, tape, Decimal("1")) == Decimal("74.25")


def test_no_tape_and_no_price_both_cost_nothing(db):
    yellow = {"name": YELLOW, "unit": "ROLL", "unit_cost": Decimal("310")}
    unpriced = {"name": "Stego Tape", "unit": "EA", "unit_cost": None}
    assert _tape_cost(db, Decimal("5880"), yellow, None, Decimal("1")) == Decimal("0.00")
    assert _tape_cost(db, Decimal("5880"), yellow, unpriced, Decimal("1")) == Decimal("0.00")
    assert _tape_cost(db, Decimal("0"), yellow, {"name": "t", "unit": "EA",
                                                 "unit_cost": Decimal("49.50")},
                      Decimal("1")) == Decimal("0.00")


def test_a_zero_ratio_turns_tape_off(db):
    """The seeded default. A company that doesn't line-item tape pays none."""
    yellow = {"name": YELLOW, "unit": "ROLL", "unit_cost": Decimal("310")}
    tape = {"name": "Stego Tape", "unit": "EA", "unit_cost": Decimal("49.50")}
    assert _tape_cost(db, Decimal("5880"), yellow, tape, Decimal("0")) == Decimal("0.00")


def test_tape_reaches_the_pour_cost(db, section, pour, setting):
    yellow = material(db, YELLOW, Decimal("310"))
    section.vapor_barrier_material_id = yellow
    db.flush()
    refresh_pour_costs(db, section)
    db.flush()
    untaped = pour.calc_direct_cost

    tape = material(db, "Stego Tape 3.75in x 180ft", Decimal("49.50"), unit="EA")
    section.vapor_tape_material_id = tape
    setting("vapor_tape_rolls_per_barrier_roll", "1.0")
    db.flush()
    out = refresh_pour_costs(db, section)
    db.flush()

    # 11,000 SF of poly on the fixture pour ÷ 2,940 SF a roll × $49.50
    rolls = Decimal("11000") / Decimal("2940")
    assert pour.calc_direct_cost - untaped == (rolls * Decimal("49.50")).quantize(Decimal("0.01"))
    assert "Stego Tape" in out["vapor_tape"]


def test_changing_the_wrap_changes_the_tape(db, section, pour, setting):
    """
    The point of pricing tape off rolls: a wider roll is fewer rolls, and the
    tape drops with it. A per-SF tape rule would not move at all.
    """
    tape = material(db, "Stego Tape 3.75in x 180ft", Decimal("49.50"), unit="EA")
    section.vapor_tape_material_id = tape
    setting("vapor_tape_rolls_per_barrier_roll", "1.0")

    section.vapor_barrier_material_id = material(db, YELLOW, Decimal("310"))
    db.flush()
    refresh_pour_costs(db, section)
    db.flush()
    wide = pour.calc_direct_cost

    # 20 x 100 = 2,000 SF a roll — narrower coverage, so more rolls, more tape
    section.vapor_barrier_material_id = material(
        db, "POLY 10 mil 20 x 100 Black", Decimal("105"), category="site_accessories"
    )
    db.flush()
    refresh_pour_costs(db, section)
    db.flush()

    def q(x):
        return x.quantize(Decimal("0.01"))

    sf = Decimal("11000")
    # Poly and tape each round to the cent before they are summed.
    poly_delta = q(sf / 2000 * Decimal("105")) - q(sf / 2940 * Decimal("310"))
    tape_delta = q(sf / 2000 * Decimal("49.50")) - q(sf / 2940 * Decimal("49.50"))
    assert tape_delta > 0  # narrower roll → more rolls → more tape
    assert pour.calc_direct_cost - wide == poly_delta + tape_delta


def test_naming_a_product_reprices_without_a_full_recalc(db, section, pour, setting):
    """
    Picking a barrier or a tape changes a price, not a quantity, so the PATCH
    re-costs the pours and leaves the takeoffs alone. The section router relies
    on this — it does not follow the change with a full recalc.
    """
    from app.routers.estimate_sections import _COSTING_FIELDS, _POUR_FIELDS

    assert "vapor_barrier_material_id" in _COSTING_FIELDS
    assert "vapor_tape_material_id" in _COSTING_FIELDS
    assert not (_COSTING_FIELDS & _POUR_FIELDS)

    section.vapor_barrier_material_id = material(db, YELLOW, Decimal("310"))
    db.flush()
    refresh_pour_costs(db, section)
    db.flush()
    before = pour.calc_direct_cost
    assert before > 0

    section.vapor_tape_material_id = material(
        db, "Stego Tape 3.75in x 180ft", Decimal("49.50"), unit="EA"
    )
    setting("vapor_tape_rolls_per_barrier_roll", "1.0")
    db.flush()
    refresh_pour_costs(db, section)
    db.flush()

    rolls = Decimal("11000") / Decimal("2940")
    assert pour.calc_direct_cost - before == (rolls * Decimal("49.50")).quantize(Decimal("0.01"))



def test_the_vapor_defaults_reprice_the_open_estimates(db):
    """
    A company default is only a fallback, but an estimate that names nothing
    takes it — so changing one moves money and has to sweep the open estimates.
    Saying "nothing needed rewriting" here would leave stale numbers on screen.
    """
    from app.services.recalc import settings_scope

    for key in (
        "default_vapor_barrier_material_id",
        "default_vapor_tape_material_id",
        "vapor_tape_rolls_per_barrier_roll",
    ):
        assert settings_scope([key])["pours"] is True, key


def test_a_default_change_reaches_an_estimate_that_named_nothing(db, section, pour, setting):
    from app.services.recalc import recalc_all_estimates

    setting("default_vapor_barrier_material_id", str(material(db, YELLOW, Decimal("310"))))
    refresh_pour_costs(db, section)
    db.flush()
    before = pour.calc_direct_cost

    tape = material(db, "Stego Tape 3.75in x 180ft", Decimal("49.50"), unit="EA")
    setting("default_vapor_tape_material_id", str(tape))
    setting("vapor_tape_rolls_per_barrier_roll", "2.0")
    recalc_all_estimates(db, pours=True)
    db.flush()

    rolls = Decimal("11000") / Decimal("2940")
    expected = (rolls * 2 * Decimal("49.50")).quantize(Decimal("0.01"))
    assert pour.calc_direct_cost - before == expected
