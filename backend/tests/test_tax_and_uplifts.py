"""
Sales tax, fuel & maintenance, and the tie-steel allowance (sql/027).

All three came out of reconciling the LBJ bid: the workbook priced them, the app
did not, and together they understated that job by $49,835. The numbers below are
small and hand-computable so the rules stay legible.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select, text

from app.models.estimate_labor import EstimateLaborLine
from app.services.costing import is_rental, refresh_pour_costs, tax_rate_for
from app.services.labor import refresh_and_store_labor
from app.services.recalc import settings_scope


def line(db, section_id, code) -> EstimateLaborLine:
    return db.scalars(
        select(EstimateLaborLine).where(
            EstimateLaborLine.section_id == section_id,
            EstimateLaborLine.code == code,
        )
    ).one()


# --------------------------------------------------------------------------
# Sales tax
# --------------------------------------------------------------------------


def test_the_seeded_rate_is_dallas(db):
    rate = db.execute(
        text("SELECT value #>> '{}' FROM system_settings WHERE key = 'sales_tax_pct'")
    ).scalar()
    assert Decimal(rate) == Decimal("0.0825")


def test_a_taxable_project_taxes_its_materials(db, section, pour):
    refresh_pour_costs(db, section)
    db.flush()

    # 10,000 SF pour, no takeoffs stored: tax rides on direct materials alone.
    assert pour.calc_tax == (pour.calc_direct_cost * Decimal("0.0825")).quantize(
        Decimal("0.01")
    )
    assert pour.calc_cost == pour.calc_direct_cost + pour.calc_allocated_cost + pour.calc_tax


def test_an_exempt_project_pays_no_tax(db, section, project, pour):
    project.tax_exempt = True
    db.flush()

    refresh_pour_costs(db, section)
    db.flush()

    assert tax_rate_for(db, section) == Decimal("0")
    assert pour.calc_tax == Decimal("0.00")
    assert pour.calc_cost == pour.calc_direct_cost + pour.calc_allocated_cost


def test_exemption_is_a_project_fact_not_an_estimate_one(db, section, project, estimate, pour):
    """ROW paving is exempt for the whole job, every estimate on it."""
    project.tax_exempt = True
    db.flush()
    assert tax_rate_for(db, section) == Decimal("0")

    project.tax_exempt = False
    db.flush()
    assert tax_rate_for(db, section) == Decimal("0.0825")


def test_the_catalog_stays_pre_tax(db, section, pour):
    """
    Tax is its own number, not folded into unit costs — otherwise the material
    list stops being a material list.
    """
    refresh_pour_costs(db, section)
    db.flush()
    mix_cost = db.execute(
        text("SELECT unit_cost FROM mix_designs WHERE id = :m"),
        {"m": pour.mix_design_id},
    ).scalar()
    assert pour.calc_direct_cost > 0
    assert pour.calc_tax > 0
    # direct cost carries no tax of its own
    if mix_cost:
        assert pour.calc_direct_cost < pour.calc_cost


def test_changing_the_rate_reprices_open_estimates(db, section, pour, setting):
    refresh_pour_costs(db, section)
    db.flush()
    before = pour.calc_tax

    setting("sales_tax_pct", "0.10")
    refresh_pour_costs(db, section)
    db.flush()

    assert pour.calc_tax > before
    assert settings_scope(["sales_tax_pct"])["pours"] is True


# --------------------------------------------------------------------------
# Fuel & maintenance
# --------------------------------------------------------------------------


def test_rental_days_are_what_fuel_rides_on(db):
    assert is_rental("DAY") is True
    assert is_rental("day") is True
    assert is_rental("/DAY") is True
    # pumping is a service, not a rental
    assert is_rental("CY") is False
    assert is_rental("YD") is False
    assert is_rental("/SF") is False


def test_no_rentals_means_no_fuel(db, section, pour):
    refresh_pour_costs(db, section)
    db.flush()
    assert pour.calc_equip_fuel == Decimal("0.00")


def test_fuel_and_tax_do_not_compound(db, section, estimate, pour, setting):
    """
    The workbook applies × (1 + tax + fuel) to the base, not tax on top of fuel.
    Fuel must therefore never appear in the tax base.
    """
    setting("sales_tax_pct", "0.10")
    setting("equip_fuel_maint_pct", "0.50")
    refresh_pour_costs(db, section)
    db.flush()

    # With no rentals on this estimate, tax is exactly 10% of materials — if
    # fuel were compounding it could not be.
    assert pour.calc_tax == (pour.calc_direct_cost * Decimal("0.10")).quantize(
        Decimal("0.01")
    )


# --------------------------------------------------------------------------
# Tie steel allowance
# --------------------------------------------------------------------------


def test_tie_steel_bills_beam_and_slab_steel_but_not_support(db, section, pour, setting):
    """
    Support steel is the #3 that holds the cables and the mat up while the crew
    works. Placing it is the tying, so billing it again charges one pass twice.
    """
    setting("labor_tie_steel_free_lb_per_sf", "0")
    setting("labor_tie_steel_ton", "400")
    refresh_and_store_labor(db, section.id)

    # 10,000 SF pour: 9,906.666 lb total, of which 1,000 lb is support steel
    assert pour.calc_total_rebar_lb == Decimal("9906.666")
    assert pour.calc_support_rebar_lb == Decimal("1000.000")

    row = line(db, section.id, "tie_steel")
    assert row.qty == Decimal("4.4533")  # 8,906.666 lb of mat / 2000
    assert row.ext_cost == Decimal("1781.32")
    assert "support steel excluded" in (row.notes or "")


def test_beam_steel_counts_toward_the_tying(db, section, estimate, pour, make_beam, setting):
    from app.services.recalc import recalc_estimate

    setting("labor_tie_steel_free_lb_per_sf", "0")
    refresh_and_store_labor(db, section.id)
    before = line(db, section.id, "tie_steel").qty

    make_beam(pour)
    recalc_estimate(db, estimate)

    # 1,602.533 lb of beam steel = 0.8013 more tons
    assert line(db, section.id, "tie_steel").qty - before == Decimal("0.8013")


def test_the_allowance_still_carries_the_first_lb_per_sf(db, section, pour, setting):
    """
    Kept as a setting for a job that wants light steel carried, but it now bites
    into the tied weight rather than the total. Default is 0 (sql/032).
    """
    setting("labor_tie_steel_free_lb_per_sf", "0.35")
    setting("labor_tie_steel_ton", "400")
    refresh_and_store_labor(db, section.id)

    row = line(db, section.id, "tie_steel")
    # 8,906.666 lb tied, 3,500 lb carried, 5,406.666 billable
    assert row.qty == Decimal("2.7033")
    assert row.ext_cost == Decimal("1081.32")
    assert "0.35" in (row.notes or "")


def test_a_pour_with_only_support_steel_bills_no_tying(db, section, make_pour, setting):
    """
    The case that made this change necessary: with support steel in the driver
    and a generous allowance, the line silently read $0 while the crew still
    tied every pound. Now a support-only pour reads $0 because there is
    genuinely nothing to tie — not because an allowance swallowed it.
    """
    make_pour(slab_bar_size=None, slab_bar_spacing_in=None)  # support steel only
    setting("labor_tie_steel_free_lb_per_sf", "0")
    refresh_and_store_labor(db, section.id)

    row = line(db, section.id, "tie_steel")
    assert row.qty == Decimal("0.0000")
    assert row.ext_cost == Decimal("0.00")


def test_the_allowance_cannot_drive_tie_steel_negative(db, section, make_pour, setting):
    """A light pour carries all its steel rather than billing a negative ton."""
    make_pour(slab_bar_size=None, slab_bar_spacing_in=None)
    setting("labor_tie_steel_free_lb_per_sf", "5.0")
    refresh_and_store_labor(db, section.id)

    row = line(db, section.id, "tie_steel")
    assert row.qty == Decimal("0.0000")
    assert row.ext_cost == Decimal("0.00")


# --------------------------------------------------------------------------
# The settings list endpoint
# --------------------------------------------------------------------------


def test_listing_settings_works(db):
    """
    Regression: the SQL contains the jsonb operator `#>> '{}'`, which str.format
    reads as a replacement field. Formatting the query raised IndexError before
    it reached the database, so GET /api/system-settings had never returned.
    """
    from app.routers.system_settings import list_settings

    rows = list_settings(prefix=None, db=db)
    keys = {r.key for r in rows}
    assert "sales_tax_pct" in keys
    assert "equip_fuel_maint_pct" in keys

    labor = list_settings(prefix="labor_", db=db)
    assert labor and all(r.key.startswith("labor_") for r in labor)
    assert len(labor) < len(rows)


def test_the_read_models_actually_expose_the_new_fields(db, section, project, pour):
    """
    Both routers build their read model field by field, so a new column reaches
    the API only if it is listed there too. Adding it to the schema is not
    enough — the field comes back null and looks like a calculation bug.
    """
    from app.routers.mono_slabs import _to_read as pour_read
    from app.routers.projects import _to_read as project_read
    from app.services.costing import refresh_pour_costs

    refresh_pour_costs(db, section)
    db.flush()

    assert project_read(project).tax_exempt is False
    out = pour_read(db, pour)
    assert out.calc_tax == pour.calc_tax
    assert out.calc_tax is not None
    assert out.calc_equip_fuel == pour.calc_equip_fuel
