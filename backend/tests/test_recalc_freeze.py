"""
Bulk recalcs must not reprice work that has already gone out.

A catalog price change or a company-default change sweeps every estimate. That
sweep is what would otherwise move a bid submitted last spring. `final` and
`archived` estimates are frozen: skipped by the sweep, reported by name, and
still repriceable one at a time from their own Recalculate button.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.models.estimate import Estimate
from app.models.estimate_section import EstimateSection
from app.models.mono_slab import MonoSlab
from app.routers.system_settings import update_setting
from app.schemas.system_setting import SystemSettingUpdate
from app.services.calc import refresh_mono_slab_calcs
from app.services.recalc import (
    FROZEN_STATUSES,
    is_frozen,
    recalc_all_estimates,
    recalc_estimate,
)


@pytest.fixture
def estimate_of_status(db, project):
    """A second estimate with one pour, at whatever status the test needs."""

    def _make(status: str, name: str | None = None) -> tuple[Estimate, EstimateSection, MonoSlab]:
        est = Estimate(
            project_id=project.id, name=name or f"{status} estimate", status=status
        )
        db.add(est)
        db.flush()
        sect = EstimateSection(
            estimate_id=est.id,
            kind="mono_slab",
            name="Mono slab on grade",
            unit="SF",
            margin_pct=Decimal("0.20"),
            contingency_pct=Decimal("0.03"),
        )
        db.add(sect)
        db.flush()
        slab = MonoSlab(
            section_id=sect.id,
            description="Pour A",
            square_footage=Decimal("10000"),
            thickness_in=Decimal("5"),
            slab_bar_size=4,
            slab_bar_spacing_in=Decimal("18"),
        )
        db.add(slab)
        db.flush()
        refresh_mono_slab_calcs(db, slab, sect)
        db.flush()
        return est, sect, slab

    return _make


def test_the_frozen_statuses_are_final_and_archived(db):
    assert FROZEN_STATUSES == {"final", "archived"}


@pytest.mark.parametrize("status", ["draft", "in_review"])
def test_open_estimates_are_not_frozen(db, estimate_of_status, status):
    est, _, _ = estimate_of_status(status)
    assert is_frozen(est) is False


@pytest.mark.parametrize("status", ["final", "archived"])
def test_finished_estimates_are_frozen(db, estimate_of_status, status):
    est, _, _ = estimate_of_status(status)
    assert is_frozen(est) is True


def test_a_bulk_recalc_skips_frozen_estimates(db, estimate, pour, estimate_of_status, setting):
    final_est, final_sect, final_pour = estimate_of_status("final")
    assert pour.calc_support_rebar_lb == Decimal("1000.000")
    assert final_pour.calc_support_rebar_lb == Decimal("1000.000")

    setting("support_rebar_lb_per_sf", "0.25")
    out = recalc_all_estimates(db)

    db.refresh(pour)
    db.refresh(final_pour)
    assert pour.calc_support_rebar_lb == Decimal("2500.000")  # open: repriced
    assert final_pour.calc_support_rebar_lb == Decimal("1000.000")  # final: untouched

    assert [s["name"] for s in out["skipped"]] == [final_est.name]
    assert [r["estimate_id"] for r in out["recalculated"]] == [str(estimate.id)]


def test_include_frozen_reprices_them_deliberately(db, estimate_of_status, setting):
    _, _, final_pour = estimate_of_status("final")

    setting("support_rebar_lb_per_sf", "0.25")
    out = recalc_all_estimates(db, include_frozen=True)

    db.refresh(final_pour)
    assert final_pour.calc_support_rebar_lb == Decimal("2500.000")
    assert out["skipped"] == []


def test_a_settings_patch_leaves_a_finished_bid_alone(db, pour, estimate_of_status):
    """The regression this rule exists for: PATCH used to rewrite everything."""
    _, _, archived_pour = estimate_of_status("archived")

    report = update_setting(
        key="support_rebar_lb_per_sf",
        body=SystemSettingUpdate(value=Decimal("0.25")),
        recalc=True,
        db=db,
    )

    db.refresh(pour)
    db.refresh(archived_pour)
    assert pour.calc_support_rebar_lb == Decimal("2500.000")
    assert archived_pour.calc_support_rebar_lb == Decimal("1000.000")
    assert len(report.skipped) == 1
    assert report.skipped[0].status == "archived"
    assert "bid numbers" in (report.note or "")


def test_a_frozen_estimate_can_still_be_repriced_one_at_a_time(
    db, estimate_of_status, setting
):
    """The estimate's own Recalculate button is the deliberate override."""
    final_est, final_sect, final_pour = estimate_of_status("final")

    setting("support_rebar_lb_per_sf", "0.25")
    recalc_estimate(db, final_est)

    db.refresh(final_pour)
    assert final_pour.calc_support_rebar_lb == Decimal("2500.000")


def test_editing_a_frozen_estimate_still_recalculates_it(db, estimate_of_status):
    """
    The freeze governs the sweep, not direct edits. If someone changes a pour on
    a final estimate, its stored numbers must still follow — a frozen estimate
    that disagrees with its own inputs is worse than one that moved.
    """
    final_est, final_sect, final_pour = estimate_of_status("final")
    final_sect.waste_concrete = Decimal("0.10")
    db.flush()

    recalc_estimate(db, final_est)

    db.refresh(final_pour)
    assert final_pour.calc_slab_concrete_cy == Decimal("169.7531")
