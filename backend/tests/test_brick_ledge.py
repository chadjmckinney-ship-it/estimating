"""
Brick ledge as its own beam kind (sql/028).

The ledge is a 6" x 10" formed void at the top of a widened grade beam: the beam
runs 18" wide to full depth and the notch is where the brick sits. Priced as a
6" full-depth thickening, so concrete, rebar and poly all behave exactly as they
would on a beam — the void makes concrete about 12.8 CY heavy on 830 LF, which
is accepted.

What the kind exists for: the forming and labor a ledge adds and a beam does
not, and the 0 x 0 case — a ledge that is only formed, with no thickening at all.
"""

from __future__ import annotations

from decimal import Decimal

from app.models.beam_type import EstimateBeamType
from app.models.grade_beam import GradeBeam
from app.services.calc import beam_kind_breakdown, refresh_mono_slab_calcs
from app.services.forming import calc_forming_materials, estimate_forming_drivers


def add_ledge(db, section, slab, *, width, height, lf, face=None, bars=False):
    fields = dict(
        section_id=section.id,
        label="Brick ledge",
        kind="brick_ledge",
        width_in=Decimal(str(width)),
        height_in=Decimal(str(height)),
        form_face_in=None if face is None else Decimal(str(face)),
    )
    if bars:
        fields.update(top_bars_count=2, top_bars_size=5)
    t = EstimateBeamType(**fields)
    db.add(t)
    db.flush()
    u = GradeBeam(mono_slab_id=slab.id, beam_type_id=t.id, length_lf=Decimal(str(lf)))
    db.add(u)
    db.flush()
    refresh_mono_slab_calcs(db, slab, section)
    db.flush()
    return u


def forming_line(db, section_id, code):
    lines = calc_forming_materials(db, section_id)["lines"]
    return next(x for x in lines if x["code"] == code)


# --------------------------------------------------------------------------
# Concrete
# --------------------------------------------------------------------------


def test_a_thickening_adds_its_own_concrete(db, section, estimate, pour):
    ledge = add_ledge(db, section, pour, width=6, height=32, lf=830)
    # 6 × 32 × 830 / 3888 × 1.05 (the estimate's concrete waste)
    assert ledge.calc_concrete_cy == Decimal("43.0370")
    assert pour.calc_gb_concrete_cy == Decimal("43.0370")


def test_a_ledge_with_no_thickening_adds_no_concrete(db, section, pour):
    """The case the old model could not express: forming only."""
    ledge = add_ledge(db, section, pour, width=0, height=0, lf=400, face=8)
    assert ledge.calc_concrete_cy == Decimal("0.0000")
    assert ledge.calc_rebar_lb == Decimal("0.000")


# --------------------------------------------------------------------------
# Poly — the point of the exercise
# --------------------------------------------------------------------------


def test_a_ledge_wraps_like_the_beam_it_thickens(db, section, pour):
    """
    Deliberate: the ledge is priced as the thickening it is, so poly follows the
    beam rules. (2 × 32 / 12) × 830.
    """
    ledge = add_ledge(db, section, pour, width=6, height=32, lf=830)
    assert ledge.calc_poly_sf == Decimal("4426.667")
    assert pour.calc_poly_gb_sf == Decimal("4426.667")


def test_a_ledge_carries_its_bar_schedule_like_any_beam(db, section, pour):
    ledge = add_ledge(db, section, pour, width=6, height=32, lf=830, bars=True)
    # 2 × 830 × 1.043 lb/ft (#5)
    assert ledge.calc_rebar_lb == Decimal("1731.380")


def test_the_breakdown_reports_ledges_separately(db, section, pour):
    add_ledge(db, section, pour, width=6, height=32, lf=830)
    kinds = beam_kind_breakdown(db, pour.id)
    assert kinds["brick_ledge"]["length_lf"] == Decimal("830.000")
    assert kinds["brick_ledge"]["concrete_cy"] == Decimal("43.0370")
    assert kinds["grade_beam"]["length_lf"] == Decimal("0")


# --------------------------------------------------------------------------
# Forming and labor — what the kind actually exists to add
# --------------------------------------------------------------------------


def test_ledge_drives_a_2x6_along_its_length(db, section, pour, setting):
    setting("form_percent", "0.50")
    add_ledge(db, section, pour, width=6, height=32, lf=830, face=8)

    d = estimate_forming_drivers(db, section.id)
    assert d["ledge_lf"] == Decimal("830.000")

    row = forming_line(db, section.id, "ledge_2x6")
    assert row["qty"] == Decimal("415.0000")  # 830 × 0.50


def test_ply_faces_the_form_face_not_the_concrete_depth(db, section, pour, setting):
    """
    A thickening of a trenched beam is 32" of concrete but only formed above
    grade. form_face_in is that depth; using height_in would triple the ply.
    """
    setting("form_percent", "0.50")
    add_ledge(db, section, pour, width=6, height=32, lf=830, face=8)

    d = estimate_forming_drivers(db, section.id)
    # 830 LF × 8" / 12 = 553.33 SF of face
    assert d["ledge_face_sf"].quantize(Decimal("0.01")) == Decimal("553.33")

    row = forming_line(db, section.id, "ledge_ply")
    # 553.33 / 32 = 17.2917 sheets, × 0.50 × 1.1, at the 3dp the line stores
    assert row["qty"] == Decimal("9.510")


def test_a_blank_form_face_falls_back_to_the_section_height(db, section, pour, setting):
    setting("form_percent", "0.50")
    add_ledge(db, section, pour, width=6, height=32, lf=830, face=None)

    d = estimate_forming_drivers(db, section.id)
    # 830 × 32/12 — three times the face above, which is why form_face_in exists
    assert d["ledge_face_sf"].quantize(Decimal("0.01")) == Decimal("2213.33")


def test_forming_only_ledge_still_forms(db, section, pour, setting):
    setting("form_percent", "0.50")
    add_ledge(db, section, pour, width=0, height=0, lf=400, face=10)

    assert forming_line(db, section.id, "ledge_2x6")["qty"] == Decimal("200.0000")
    # 400 × 10/12 = 333.33 SF, / 32 × 0.5 × 1.1
    assert forming_line(db, section.id, "ledge_ply")["qty"] == Decimal("5.729")


def test_no_ledge_means_no_ledge_lines(db, section, pour):
    d = estimate_forming_drivers(db, section.id)
    assert d["ledge_lf"] == Decimal("0")
    assert forming_line(db, section.id, "ledge_2x6")["qty"] == Decimal("0.0000")
    assert forming_line(db, section.id, "ledge_ply")["qty"] == Decimal("0.0000")


def test_ledge_gets_its_own_labor_line(db, section, pour, setting):
    from app.services.labor import calc_labor_materials, labor_drivers

    add_ledge(db, section, pour, width=6, height=32, lf=830, face=10)
    setting("labor_brick_ledge_lf", "4.25")

    assert labor_drivers(db, section.id)["ledge_lf"] == Decimal("830.000")
    row = next(
        x for x in calc_labor_materials(db, section.id)["lines"]
        if x["code"] == "brick_ledge"
    )
    assert row["qty"] == Decimal("830.0000")
    assert row["ext_cost"] == Decimal("3527.50")  # 830 × 4.25


def test_ledge_labor_is_zero_until_the_rate_is_set(db, section, pour):
    from app.services.labor import calc_labor_materials

    add_ledge(db, section, pour, width=6, height=32, lf=830, face=10)
    row = next(
        x for x in calc_labor_materials(db, section.id)["lines"]
        if x["code"] == "brick_ledge"
    )
    assert row["ext_cost"] == Decimal("0.00")
    assert "labor_brick_ledge_lf" in (row["notes"] or "")


def test_a_manual_line_can_be_handed_back_to_the_default(db, section, pour, setting):
    """
    Before this, is_manual was a one-way door: an estimator who overrode a rate
    had no way to put the line back on the company default.
    """
    from app.services.labor import refresh_and_store_labor, update_labor_line

    add_ledge(db, section, pour, width=6, height=32, lf=830, face=10)
    setting("labor_brick_ledge_lf", "1.00")
    refresh_and_store_labor(db, section.id)

    # override it
    update_labor_line(db, section.id, "brick_ledge", rate=Decimal("4"), mark_manual=True)
    row = _labor_line(db, section.id, "brick_ledge")
    assert row.is_manual is True and row.rate == Decimal("4.0000")

    # the company default moves; the manual line does not follow
    setting("labor_brick_ledge_lf", "2.00")
    refresh_and_store_labor(db, section.id)
    assert _labor_line(db, section.id, "brick_ledge").rate == Decimal("4.0000")

    # hand it back
    update_labor_line(db, section.id, "brick_ledge", mark_manual=False)
    refresh_and_store_labor(db, section.id)
    row = _labor_line(db, section.id, "brick_ledge")
    assert row.is_manual is False
    assert row.rate == Decimal("2.0000")
    assert row.ext_cost == Decimal("1660.00")  # 830 × 2


def test_toggling_enabled_leaves_the_manual_flag_alone(db, section, pour, setting):
    from app.services.labor import refresh_and_store_labor, update_labor_line

    add_ledge(db, section, pour, width=6, height=32, lf=830, face=10)
    refresh_and_store_labor(db, section.id)
    update_labor_line(db, section.id, "brick_ledge", rate=Decimal("3"), mark_manual=True)

    update_labor_line(db, section.id, "brick_ledge", enabled=False, mark_manual=None)
    row = _labor_line(db, section.id, "brick_ledge")
    assert row.enabled is False
    assert row.is_manual is True


def _labor_line(db, section_id, code):
    from sqlalchemy import select

    from app.models.estimate_labor import EstimateLaborLine

    return db.scalars(
        select(EstimateLaborLine).where(
            EstimateLaborLine.section_id == section_id,
            EstimateLaborLine.code == code,
        )
    ).one()
