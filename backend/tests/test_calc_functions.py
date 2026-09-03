"""
Golden numbers for the locked SQL calc helpers.

Every expected value below is hand computed from the documented rule and
written out in the assertion. These functions price real bids, so a failure
here means either the arithmetic in sql/ changed or a rule was redefined —
in both cases the number in this file should only move deliberately.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import text


def call(db, sql: str, **params):
    return db.execute(text(f"SELECT {sql}"), params).scalar()


# --------------------------------------------------------------------------
# Concrete and sand: SF × in / 12 / 27, then waste, rounded to 4dp
# --------------------------------------------------------------------------


def test_concrete_cy_no_waste(db):
    # 10,000 SF × 5" = 50,000 / 324 = 154.320987...
    assert call(db, "calc_concrete_cy(10000, 5, 0)") == Decimal("154.3210")


def test_concrete_cy_with_waste(db):
    # 154.320987... × 1.05
    assert call(db, "calc_concrete_cy(10000, 5, 0.05)") == Decimal("162.0370")


def test_concrete_cy_null_waste_is_none(db):
    # coalesce(waste, 0) — a missing factor must not null out the yardage
    assert call(db, "calc_concrete_cy(10000, 5, NULL)") == Decimal("154.3210")


def test_sand_cy(db):
    # 10,000 SF × 2" = 20,000 / 324 = 61.7283... × 1.05
    assert call(db, "calc_sand_cy(10000, 2, 0.05)") == Decimal("64.8148")


def test_sand_cy_is_null_without_a_sand_bed(db):
    # NULL, not 0: "no sand on this pour" is different from "0 CY of sand"
    assert call(db, "calc_sand_cy(10000, NULL, 0.05)") is None


# --------------------------------------------------------------------------
# Slab mat: 12 / spacing bars per foot, × SF, × 2 for each way
# --------------------------------------------------------------------------


def test_slab_mat_lf(db):
    # 2 × 10,000 × 12 / 18
    assert call(db, "calc_slab_mat_rebar_lf(10000, 18)") == Decimal("13333.333")


@pytest.mark.parametrize("spacing", ["0", "NULL"])
def test_slab_mat_lf_without_spacing_is_zero(db, spacing):
    assert call(db, f"calc_slab_mat_rebar_lf(10000, {spacing})") == Decimal("0")


def test_slab_mat_lf_zero_sf_is_zero(db):
    assert call(db, "calc_slab_mat_rebar_lf(0, 18)") == Decimal("0")


def test_slab_mat_lb(db):
    # 13,333.333 LF × 0.668 lb/ft (#4)
    assert call(
        db, "calc_slab_mat_rebar_lb(10000, CAST(4 AS smallint), 18, 0)"
    ) == Decimal("8906.666")


def test_slab_mat_lb_waste_is_the_lap_allowance(db):
    # waste_rebar applies to the mat only: 8906.6664 × 1.10
    assert call(
        db, "calc_slab_mat_rebar_lb(10000, CAST(4 AS smallint), 18, 0.10)"
    ) == Decimal("9797.333")


def test_slab_mat_lb_without_a_bar_size_is_zero(db):
    assert call(
        db, "calc_slab_mat_rebar_lb(10000, CAST(NULL AS smallint), 18, 0)"
    ) == Decimal("0")


# --------------------------------------------------------------------------
# Support steel and PT: flat lb/SF rates
# --------------------------------------------------------------------------


def test_support_rebar_is_chairs_and_dowels_only(db):
    # 0.1 lb/SF is the post-sql/021 basis: mat steel is priced separately
    assert call(db, "calc_support_rebar_lb(10000, 0.1)") == Decimal("1000.000")


def test_pt_lb_is_zero_when_the_pour_is_not_post_tensioned(db):
    assert call(db, "calc_pt_cable_lb(10000, false, 1.0)") == Decimal("0")


def test_pt_lb_uses_the_rate_when_post_tensioned(db):
    assert call(db, "calc_pt_cable_lb(10000, true, 1.0)") == Decimal("10000.000")


# --------------------------------------------------------------------------
# Beam steel
# --------------------------------------------------------------------------


def test_long_bar_lb(db):
    # 3 bars × 200 LF × 1.043 lb/ft (#5)
    assert call(
        db, "calc_long_bar_lb(3, CAST(5 AS smallint), 200)"
    ) == Decimal("625.800")


def test_long_bar_lb_missing_input_is_zero(db):
    assert call(
        db, "calc_long_bar_lb(NULL, CAST(5 AS smallint), 200)"
    ) == Decimal("0")


def test_stirrup_lb_measures_out_to_out_plus_a_one_foot_hook(db, section):
    # 200 LF × 12 / 18 = 133.33 stirrups
    # perimeter = 2 × (12 + 24) / 12 = 6.0 ft, + 1.0 ft hook allowance (sql/023)
    # 133.33 × 7.0 × 0.376 lb/ft (#3)
    #
    # This is the *current* rule and it is known to run heavy: the bar is
    # measured to the outside of the section with no concrete cover deducted
    # (docs/todo.md, "Confirm stirrup weight method"). When that decision is
    # settled this number moves — change it on purpose, not to make a red test
    # green.
    assert call(
        db, "calc_stirrup_lb(12, 24, 200, CAST(3 AS smallint), 18)"
    ) == Decimal("350.933")


@pytest.mark.parametrize("spacing", ["0", "NULL"])
def test_stirrup_lb_without_spacing_is_zero(db, spacing):
    assert call(
        db, f"calc_stirrup_lb(12, 24, 200, CAST(3 AS smallint), {spacing})"
    ) == Decimal("0")


# --------------------------------------------------------------------------
# Poly / Stego wrap on a beam: two sides only
# --------------------------------------------------------------------------


def test_poly_beam_sf_wraps_two_sides(db):
    # (2 × 24" / 12) × 200 LF — the bottom is already in the pour SF
    assert call(db, "calc_poly_beam_sf(12, 24, 200)") == Decimal("800.000")


def test_poly_beam_sf_is_null_without_a_height(db):
    assert call(db, "calc_poly_beam_sf(12, NULL, 200)") is None


# --------------------------------------------------------------------------
# Reference data the helpers read
# --------------------------------------------------------------------------


def test_bar_weights_are_the_standard_astm_values(db):
    rows = dict(
        db.execute(text("SELECT bar_size, weight_lb_per_ft FROM bar_weights")).all()
    )
    assert rows[3] == Decimal("0.3760")
    assert rows[4] == Decimal("0.6680")
    assert rows[5] == Decimal("1.0430")
    assert rows[8] == Decimal("2.6700")
    assert rows[11] == Decimal("5.3130")
