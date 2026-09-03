"""
"Edit X, assert Y follows."

Every quantity in this system is stored, not derived on read, so any change to
an upstream input leaves stale numbers behind until something rewrites them.
Three bugs of exactly that shape shipped in one session (estimate waste,
system_settings, beam edits). These tests are the ones that would have caught
them; each names the input it changes and the stored result that has to move.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select, text

from app.models.estimate_labor import EstimateLaborLine
from app.routers.system_settings import update_setting
from app.schemas.system_setting import SystemSettingUpdate
from app.services.estimate_equipment import refresh_and_store_equipment
from app.services.forming import refresh_and_store_forming
from app.services.labor import refresh_and_store_labor, update_labor_line
from app.services.recalc import recalc_estimate, settings_scope


def labor_line(db, section_id, code) -> EstimateLaborLine:
    return db.scalars(
        select(EstimateLaborLine).where(
            EstimateLaborLine.section_id == section_id,
            EstimateLaborLine.code == code,
        )
    ).one()


def cost_all(db, section):
    """Store the three takeoffs, as opening an estimate in the UI does."""
    refresh_and_store_forming(db, section.id)
    refresh_and_store_labor(db, section.id)
    refresh_and_store_equipment(db, section.id)


# --------------------------------------------------------------------------
# 1. Estimate-level inputs
# --------------------------------------------------------------------------


def test_changing_estimate_waste_rewrites_every_pour(db, section, estimate, make_pour):
    a = make_pour()
    b = make_pour(description="Pour B", square_footage=Decimal("5000"))
    assert a.calc_slab_concrete_cy == Decimal("162.0370")  # at the 5% default

    section.waste_concrete = Decimal("0.10")
    db.flush()
    recalc_estimate(db, estimate)

    db.refresh(a)
    db.refresh(b)
    assert a.calc_slab_concrete_cy == Decimal("169.7531")  # 154.320987 × 1.10
    assert b.calc_slab_concrete_cy == Decimal("84.8765")  # 77.160493 × 1.10


def test_changing_estimate_waste_rewrites_the_pour_total_too(db, section, estimate, pour, make_beam):
    make_beam(pour)
    assert pour.calc_concrete_cy == Decimal("177.5926")

    section.waste_concrete = Decimal("0.10")
    db.flush()
    recalc_estimate(db, estimate)

    db.refresh(pour)
    # slab 169.7531 + beam (14.814814 × 1.10 = 16.2963)
    assert pour.calc_gb_concrete_cy == Decimal("16.2963")
    assert pour.calc_concrete_cy == Decimal("186.0494")


# --------------------------------------------------------------------------
# 2. Company defaults (system_settings)
# --------------------------------------------------------------------------


def test_patching_a_setting_rewrites_affected_pours(db, pour):
    assert pour.calc_support_rebar_lb == Decimal("1000.000")

    update_setting(
        key="support_rebar_lb_per_sf",
        body=SystemSettingUpdate(value=Decimal("0.25")),
        recalc=True,
        db=db,
    )

    db.refresh(pour)
    assert pour.calc_support_rebar_lb == Decimal("2500.000")  # 10,000 × 0.25


def test_patching_a_setting_without_recalc_says_so_and_leaves_it_stale(db, pour):
    report = update_setting(
        key="support_rebar_lb_per_sf",
        body=SystemSettingUpdate(value=Decimal("0.25")),
        recalc=False,
        db=db,
    )
    db.refresh(pour)
    assert pour.calc_support_rebar_lb == Decimal("1000.000")
    assert report.recalculated == []
    assert "stale" in (report.note or "")


def test_a_labor_rate_change_reaches_the_stored_line(db, section, estimate, pour):
    cost_all(db, section)
    assert labor_line(db, section.id, "forming").rate == Decimal("0.4500")
    assert labor_line(db, section.id, "forming").ext_cost == Decimal("4500.00")

    update_setting(
        key="labor_forming_sf",
        body=SystemSettingUpdate(value=Decimal("0.60")),
        recalc=True,
        db=db,
    )

    row = labor_line(db, section.id, "forming")
    assert row.rate == Decimal("0.6000")
    assert row.ext_cost == Decimal("6000.00")  # 10,000 SF × 0.60


def test_settings_scope_maps_keys_to_the_work_they_invalidate(db):
    # A pour input ripples into everything downstream of a pour.
    assert settings_scope(["waste_concrete"]) == {
        "pours": True,
        "forming": True,
        "labor": True,
        "equipment": True,
    }
    # Equipment days ride on the superintendent duration, so labor_* touches both.
    assert settings_scope(["labor_super_day_rate"]) == {
        "pours": False,
        "forming": False,
        "labor": True,
        "equipment": True,
    }
    assert settings_scope(["equip_vault_day_rate"])["equipment"] is True
    assert settings_scope(["form_percent"])["forming"] is True
    # An unrecognised key invalidates nothing rather than rewriting the world.
    assert not any(settings_scope(["some_future_key"]).values())


def test_a_direct_psql_style_update_needs_recalc_all(db, estimate, pour, setting):
    """
    An UPDATE straight into system_settings cannot trigger anything — that is
    what POST /system-settings/recalc-all is for.
    """
    setting("support_rebar_lb_per_sf", "0.25")
    db.refresh(pour)
    assert pour.calc_support_rebar_lb == Decimal("1000.000")  # still stale

    recalc_estimate(db, estimate)
    db.refresh(pour)
    assert pour.calc_support_rebar_lb == Decimal("2500.000")


# --------------------------------------------------------------------------
# 3. Beam edits
# --------------------------------------------------------------------------


def test_editing_a_beam_type_rewrites_the_pour(db, estimate, pour, make_beam):
    beam = make_beam(pour)
    assert pour.calc_gb_concrete_cy == Decimal("15.5556")

    beam.beam_type.height_in = Decimal("36")
    db.flush()
    recalc_estimate(db, estimate)

    db.refresh(pour)
    # 12 × 36 × 200 / 3888 × 1.05
    assert pour.calc_gb_concrete_cy == Decimal("23.3333")
    assert pour.calc_poly_gb_sf == Decimal("1200.000")  # (2 × 36 / 12) × 200


def test_editing_a_drop_beam_rewrites_the_labor_takeoff(db, section, estimate, pour, make_beam):
    beam = make_beam(pour, kind="drop", label="DROP-1")
    cost_all(db, section)
    row = labor_line(db, section.id, "drops")
    assert row.qty == Decimal("200.0000")  # drop LF
    assert row.ext_cost == Decimal("1600.00")  # × $8/FF

    beam.length_lf = Decimal("300")
    db.flush()
    recalc_estimate(db, estimate)

    row = labor_line(db, section.id, "drops")
    assert row.qty == Decimal("300.0000")
    assert row.ext_cost == Decimal("2400.00")


def test_adding_a_beam_moves_the_tie_steel_line(db, section, estimate, pour, make_beam):
    cost_all(db, section)
    before = labor_line(db, section.id, "tie_steel").qty

    make_beam(pour)
    recalc_estimate(db, estimate)

    after = labor_line(db, section.id, "tie_steel").qty
    # 1,602.533 lb of beam steel = 0.8013 more tons
    assert after > before
    assert after - before == Decimal("0.8013")


# --------------------------------------------------------------------------
# 4. Manual overrides survive
# --------------------------------------------------------------------------


def test_a_manual_labor_line_survives_a_recalc(db, section, estimate, pour):
    cost_all(db, section)
    update_labor_line(
        db, section.id, "forming", rate=Decimal("1.25"), mark_manual=True
    )
    assert labor_line(db, section.id, "forming").rate == Decimal("1.2500")

    update_setting(
        key="labor_forming_sf",
        body=SystemSettingUpdate(value=Decimal("0.60")),
        recalc=True,
        db=db,
    )

    row = labor_line(db, section.id, "forming")
    assert row.is_manual is True
    assert row.rate == Decimal("1.2500")  # the estimator's number wins
    assert row.ext_cost == Decimal("12500.00")


def test_a_manual_line_freezes_its_quantity_too(db, section, estimate, pour):
    """
    Marking a line manual pins the whole line, not just the rate — a later pour
    change moves every other line but leaves this one where the estimator put
    it. This is the surprising half of the rule, so it gets a test.
    """
    cost_all(db, section)
    update_labor_line(
        db, section.id, "place_finish", rate=Decimal("0.90"), mark_manual=True
    )
    assert labor_line(db, section.id, "place_finish").ext_cost == Decimal("9000.00")

    pour.square_footage = Decimal("20000")
    db.flush()
    recalc_estimate(db, estimate)

    row = labor_line(db, section.id, "place_finish")
    assert row.rate == Decimal("0.9000")
    assert row.qty == Decimal("10000.0000")
    # while a line nobody touched follows the new SF
    assert labor_line(db, section.id, "forming").qty == Decimal("20000.0000")


# --------------------------------------------------------------------------
# 5. Takeoffs are only refreshed once they exist
# --------------------------------------------------------------------------


def test_recalc_does_not_conjure_takeoffs_for_an_uncosted_section(db, section, estimate, pour):
    done = recalc_estimate(db, estimate)
    assert len(done["sections"]) == 1
    sec = done["sections"][0]
    assert sec["pours"] == 1
    assert sec["forming"] is False
    assert sec["labor"] is False
    assert sec["equipment"] is False
    assert db.execute(
        text("SELECT count(*) FROM estimate_labor_lines WHERE section_id = :s"),
        {"s": str(section.id)},
    ).scalar() == 0


def test_recalc_refreshes_takeoffs_once_they_are_stored(db, section, estimate, pour):
    cost_all(db, section)
    done = recalc_estimate(db, estimate)
    sec = done["sections"][0]
    assert sec["forming"] is True
    assert sec["labor"] is True
    assert sec["equipment"] is True
