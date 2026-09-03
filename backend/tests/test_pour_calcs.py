"""
Pour-level quantities: what refresh_mono_slab_calcs writes to mono_slabs.calc_*.

The fixture pour is 10,000 SF, 5" slab, 2" sand, #4 mat @ 18" o.c., no PT,
with the seeded company defaults (5% concrete waste, 5% sand, 0% rebar,
10% poly, 0.1 lb/SF support steel).
"""

from __future__ import annotations

from decimal import Decimal

from app.services.calc import estimate_mono_totals, refresh_mono_slab_calcs


def test_slab_only_pour(db, pour):
    # 10,000 × 5 / 324 × 1.05
    assert pour.calc_slab_concrete_cy == Decimal("162.0370")
    # 10,000 × 2 / 324 × 1.05
    assert pour.calc_sand_cy == Decimal("64.8148")
    # 2 × 10,000 × 12 / 18, then × 0.668 lb/ft
    assert pour.calc_slab_bar_lf == Decimal("13333.333")
    assert pour.calc_slab_bar_lb == Decimal("8906.666")
    # 10,000 × 0.1 lb/SF
    assert pour.calc_support_rebar_lb == Decimal("1000.000")


def test_slab_steel_is_mat_plus_support(db, pour):
    assert pour.calc_total_rebar_lb == Decimal("9906.666")  # 8906.666 + 1000
    assert pour.calc_grade_beam_rebar_lb == Decimal("0")


def test_no_beams_means_pour_cy_is_slab_cy(db, pour):
    assert pour.calc_gb_concrete_cy == Decimal("0.0000")
    assert pour.calc_concrete_cy == pour.calc_slab_concrete_cy


def test_poly_is_pour_sf_plus_waste(db, pour):
    assert pour.calc_poly_slab_sf == Decimal("10000.000")
    assert pour.calc_poly_gb_sf == Decimal("0.000")
    assert pour.calc_poly_sf == Decimal("11000.000")  # × 1.10


def test_a_pour_with_no_mat_prices_no_mat_steel(db, make_pour):
    pour = make_pour(slab_bar_size=None, slab_bar_spacing_in=None)
    assert pour.calc_slab_bar_lf == Decimal("0")
    assert pour.calc_slab_bar_lb == Decimal("0")
    # support steel still applies — chairs and dowels do not depend on a mat
    assert pour.calc_support_rebar_lb == Decimal("1000.000")


def test_sand_is_null_when_the_pour_has_no_sand_bed(db, make_pour):
    pour = make_pour(sand_thickness_in=None)
    assert pour.calc_sand_cy is None


# --------------------------------------------------------------------------
# Beams roll into the pour
# --------------------------------------------------------------------------


def test_grade_beam_rolls_into_the_pour(db, pour, make_beam):
    make_beam(pour)
    # 3-#5 top + 3-#5 bottom (625.800 each) + #3 stirrups @ 18" (350.933)
    assert pour.calc_grade_beam_rebar_lb == Decimal("1602.533")
    # 12 × 24 × 200 / (144 × 27) × 1.05
    assert pour.calc_gb_concrete_cy == Decimal("15.5556")
    # slab + beam
    assert pour.calc_concrete_cy == Decimal("177.5926")
    assert pour.calc_total_rebar_lb == Decimal("11509.199")


def test_beam_poly_wraps_two_sides(db, pour, make_beam):
    make_beam(pour)
    assert pour.calc_poly_gb_sf == Decimal("800.000")  # (2 × 24 / 12) × 200
    assert pour.calc_poly_sf == Decimal("11880.000")  # (10,000 + 800) × 1.10


def test_exposed_and_drops_share_the_beam_rules(db, section, pour, make_beam):
    make_beam(pour, kind="exposed", label="EXP-1")
    exposed_rebar = pour.calc_grade_beam_rebar_lb
    make_beam(pour, kind="drop", label="DROP-1")
    # A drop of the same section adds the same steel — the stored rollups cover
    # all three kinds (the column names predate the split).
    assert pour.calc_grade_beam_rebar_lb == exposed_rebar * 2
    breakdown = pour._beam_breakdown
    assert breakdown["exposed"]["rebar_lb"] == Decimal("1602.533")
    assert breakdown["drop"]["rebar_lb"] == Decimal("1602.533")
    assert breakdown["grade_beam"]["rebar_lb"] == Decimal("0")


def test_only_grade_beams_carry_pt_cables(db, make_pour, make_beam):
    pour = make_pour(post_tension=True, pt_spacing_in=Decimal("48"))
    make_beam(pour, pt_cables_count=2)
    # slab: 10,000 SF × 12 / 48" spacing
    assert pour.calc_pt_slab_lf == Decimal("2500.000")
    # beam: 2 cables × 200 LF
    assert pour.calc_pt_gb_lf == Decimal("400.000")
    assert pour.calc_pt_cable_lf == Decimal("2900.000")


def test_a_non_pt_pour_reports_no_pt(db, pour, make_beam):
    make_beam(pour, pt_cables_count=2)
    assert pour.calc_pt_cable_lb == Decimal("0")
    assert pour.calc_pt_cable_lf == Decimal("0.000")


def test_pt_pour_without_spacing_has_no_cable_lf(db, make_pour):
    """
    The live gap in docs/todo.md: a PT pour with no pt_spacing_in prices zero
    cable LF and rides entirely on the flat lb/SF rate. This test pins the
    current behaviour so the day the rule changes, it says so.
    """
    pour = make_pour(post_tension=True, pt_spacing_in=None)
    assert pour.calc_pt_cable_lf == Decimal("0.000")
    assert pour.calc_pt_cable_lb == Decimal("10000.000")  # 10,000 SF × 1.0 lb/SF


# --------------------------------------------------------------------------
# Per-pour overrides
# --------------------------------------------------------------------------


def test_pour_overrides_beat_the_company_default(db, make_pour):
    pour = make_pour(support_rebar_lb_per_sf=Decimal("0.25"))
    assert pour.calc_support_rebar_lb == Decimal("2500.000")


def test_estimate_waste_beats_the_company_default(db, section, make_pour):
    section.waste_concrete = Decimal("0.10")
    db.flush()
    pour = make_pour()
    assert pour.calc_slab_concrete_cy == Decimal("169.7531")  # 154.320987 × 1.10


# --------------------------------------------------------------------------
# Estimate rollup
# --------------------------------------------------------------------------


def test_estimate_totals_sum_the_pours(db, estimate, make_pour):
    make_pour()
    make_pour(description="Pour B", square_footage=Decimal("5000"))
    totals = estimate_mono_totals(db, estimate.id)
    assert totals["slab_count"] == 2
    assert totals["total_sf"] == Decimal("15000.000")
    # 162.0370 + (5,000 × 5 / 324 × 1.05 = 81.0185)
    assert totals["total_concrete_cy"] == Decimal("243.0555")


def test_refresh_is_idempotent(db, section, pour, make_beam):
    make_beam(pour)
    before = (pour.calc_concrete_cy, pour.calc_total_rebar_lb, pour.calc_poly_sf)
    refresh_mono_slab_calcs(db, pour, section)
    db.flush()
    assert (pour.calc_concrete_cy, pour.calc_total_rebar_lb, pour.calc_poly_sf) == before


# --------------------------------------------------------------------------
# Waste on beam steel
#
# The workbook ends every section's lb/LF with × (1 + waste) — invisible in the
# schedule, which is why it read as an error for most of a day. The app applies
# the estimate's waste_rebar to beam steel the same way.
# --------------------------------------------------------------------------


def test_waste_rebar_scales_beam_steel(db, section, estimate, pour, make_beam):
    from app.services.calc import refresh_mono_slab_calcs

    make_beam(pour)
    refresh_mono_slab_calcs(db, pour, section)
    db.flush()
    assert pour.calc_grade_beam_rebar_lb == Decimal("1602.533")

    section.waste_rebar = Decimal("0.10")
    db.flush()
    refresh_mono_slab_calcs(db, pour, section)
    db.flush()

    # 1,602.533 × 1.10, rounded per beam
    assert pour.calc_grade_beam_rebar_lb == Decimal("1762.786")


def test_waste_rebar_leaves_support_steel_alone(db, section, estimate, pour, make_beam):
    """
    Support steel is already an allowance — 0.1 lb/SF standing in for the #3 bar
    that holds cables and rebar up. Wasting an allowance is slop on slop.
    """
    from app.services.calc import refresh_mono_slab_calcs

    make_beam(pour)
    section.waste_rebar = Decimal("0.10")
    db.flush()
    refresh_mono_slab_calcs(db, pour, section)
    db.flush()

    # 10,000 SF × 0.1 lb/SF, unwasted
    assert pour.calc_support_rebar_lb == Decimal("1000.000")
    assert pour.calc_total_rebar_lb == (
        pour.calc_slab_bar_lb + Decimal("1000.000") + pour.calc_grade_beam_rebar_lb
    )


def test_the_beam_row_carries_the_waste_too(db, section, estimate, pour, make_beam):
    """
    Stored on the beam, like concrete CY — so the beam row and the pour rollup
    can never disagree about how much steel is in that beam.
    """
    from app.services.calc import refresh_mono_slab_calcs

    beam = make_beam(pour)
    section.waste_rebar = Decimal("0.10")
    db.flush()
    refresh_mono_slab_calcs(db, pour, section)
    db.flush()
    db.refresh(beam)

    assert beam.calc_rebar_lb == Decimal("1762.786")
    assert pour.calc_grade_beam_rebar_lb == beam.calc_rebar_lb
