"""
Sections — the assemblies of a job (sql/033–034).

An estimate used to BE a mono-slab worksheet. It is now a list of sections, each
owning its own work, its own markup and optionally its own tax treatment. These
tests cover what only became possible once that was true: two assemblies in one
job, priced differently, rolling up to one contract price.

The shape comes from the workbook. LBJ is $1,388,113 across three filled sheets
(01-PIERS 106 EA, 04-PT SLABS 62,723 SF, 06-WALLS 3,452 FF), each with its own
labor rates — paving's forming labor is $0.30/SF against the slab sheet's $0.45.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.estimate_section import DEFAULT_UNIT_BY_KIND, EstimateSection
from app.models.mono_slab import MonoSlab
from app.services.calc import refresh_mono_slab_calcs
from app.services.costing import refresh_estimate_totals, refresh_pour_costs, tax_rate_for


@pytest.fixture
def make_section(db, estimate):
    def _make(kind="paving", **overrides) -> EstimateSection:
        fields = dict(
            estimate_id=estimate.id,
            kind=kind,
            name=kind.replace("_", " ").title(),
            unit=DEFAULT_UNIT_BY_KIND.get(kind, "SF"),
            margin_pct=Decimal("0.20"),
            contingency_pct=Decimal("0.00"),
        )
        fields.update(overrides)
        row = EstimateSection(**fields)
        db.add(row)
        db.flush()
        return row

    return _make


def add_pour(db, section, sf="10000") -> MonoSlab:
    row = MonoSlab(
        section_id=section.id,
        description="Pour A",
        square_footage=Decimal(sf),
        thickness_in=Decimal("5"),
        sand_thickness_in=Decimal("2"),
        perimeter_edge_lf=Decimal("400"),
        slab_bar_size=4,
        slab_bar_spacing_in=Decimal("18"),
    )
    db.add(row)
    db.flush()
    refresh_mono_slab_calcs(db, row, section)
    db.flush()
    return row


# --------------------------------------------------------------------------
# Tax: a project fact with a section exception
# --------------------------------------------------------------------------


def test_a_section_inherits_the_project_by_default(db, section, project, setting):
    setting("sales_tax_pct", "0.0825")
    assert section.tax_exempt is None
    assert tax_rate_for(db, section) == Decimal("0.0825")

    db.execute(
        text("UPDATE projects SET tax_exempt = true WHERE id = :i"), {"i": str(project.id)}
    )
    db.flush()
    assert tax_rate_for(db, section) == Decimal("0")


def test_an_exempt_section_inside_a_taxable_job(db, make_section, setting):
    """
    ROW paving and sidewalks are exempt inside jobs that are otherwise taxable.
    The workbook has one exemption flag per job and cannot express this.
    """
    setting("sales_tax_pct", "0.0825")
    paving = make_section("paving", tax_exempt=True)
    slab = make_section("mono_slab")

    assert tax_rate_for(db, paving) == Decimal("0")
    assert tax_rate_for(db, slab) == Decimal("0.0825")


def test_a_section_can_be_taxable_inside_an_exempt_project(db, project, make_section, setting):
    """The override reads both ways — false is not the same as unset."""
    setting("sales_tax_pct", "0.0825")
    db.execute(
        text("UPDATE projects SET tax_exempt = true WHERE id = :i"), {"i": str(project.id)}
    )
    db.flush()

    inherits = make_section("mono_slab")
    taxable = make_section("paving", tax_exempt=False)

    assert tax_rate_for(db, inherits) == Decimal("0")
    assert tax_rate_for(db, taxable) == Decimal("0.0825")


def test_exemption_is_never_defaulted_from_the_kind(db, make_section):
    """
    Plenty of paving is not ROW. A paving section that came up exempt on its own
    would be a wrong number with nothing on screen to notice — the failure this
    project keeps finding.
    """
    assert make_section("paving").tax_exempt is None
    assert make_section("sidewalk").tax_exempt is None


# --------------------------------------------------------------------------
# Markup lives on the section
# --------------------------------------------------------------------------


def test_two_sections_price_at_their_own_markup(db, estimate, make_section):
    cheap = make_section("mono_slab", margin_pct=Decimal("0.10"))
    dear = make_section("paving", margin_pct=Decimal("0.30"))
    add_pour(db, cheap)
    add_pour(db, dear)

    refresh_pour_costs(db, cheap)
    refresh_pour_costs(db, dear)
    db.flush()

    assert cheap.calc_total_sale == (cheap.calc_total_cost * Decimal("1.10")).quantize(
        Decimal("0.01")
    )
    assert dear.calc_total_sale == (dear.calc_total_cost * Decimal("1.30")).quantize(
        Decimal("0.01")
    )


def test_the_job_is_the_sum_of_its_sections(db, estimate, make_section):
    a = make_section("mono_slab", margin_pct=Decimal("0.15"))
    b = make_section("paving", margin_pct=Decimal("0.25"))
    add_pour(db, a)
    add_pour(db, b, sf="4000")
    refresh_pour_costs(db, a)
    refresh_pour_costs(db, b)
    db.flush()

    out = refresh_estimate_totals(db, estimate)

    assert out["sections"] == 2
    assert estimate.calc_total_cost == a.calc_total_cost + b.calc_total_cost
    assert estimate.calc_total_sale == a.calc_total_sale + b.calc_total_sale
    assert estimate.calc_total_tax == a.calc_total_tax + b.calc_total_tax


def test_a_job_total_carries_no_per_unit_figure(db, estimate, make_section):
    """
    Sections are measured in EA, SF, FF and LS. A job-level "per SF" would be
    adding unlike units, so the rollup deliberately leaves it blank.
    """
    piers = make_section("piers")
    assert piers.unit == "EA"
    add_pour(db, make_section("mono_slab"))
    refresh_estimate_totals(db, estimate)

    assert estimate.calc_cost_per_sf is None
    assert estimate.calc_sale_per_sf is None


# --------------------------------------------------------------------------
# The work belongs to the section
# --------------------------------------------------------------------------


def test_pours_do_not_leak_between_sections(db, make_section):
    from app.services.calc import section_mono_totals

    a = make_section("mono_slab")
    b = make_section("paving")
    add_pour(db, a, sf="10000")
    add_pour(db, b, sf="4000")

    assert section_mono_totals(db, a.id)["total_sf"] == Decimal("10000.000")
    assert section_mono_totals(db, b.id)["total_sf"] == Decimal("4000.000")


def test_the_job_total_spans_every_section(db, estimate, make_section):
    from app.services.calc import estimate_mono_totals

    add_pour(db, make_section("mono_slab"), sf="10000")
    add_pour(db, make_section("paving"), sf="4000")

    assert estimate_mono_totals(db, estimate.id)["total_sf"] == Decimal("14000.000")


def test_waste_is_a_section_setting(db, make_section):
    """Each assembly wastes at its own rate — the workbook has one per sheet."""
    a = make_section("mono_slab", waste_concrete=Decimal("0.05"))
    b = make_section("paving", waste_concrete=Decimal("0.20"))
    pa = add_pour(db, a)
    pb = add_pour(db, b)

    assert pb.calc_slab_concrete_cy > pa.calc_slab_concrete_cy
    # 10,000 SF × 5" = 154.3210 CY raw
    assert pa.calc_slab_concrete_cy == Decimal("162.0370")
    assert pb.calc_slab_concrete_cy == Decimal("185.1852")


def test_deleting_a_section_takes_its_pours_with_it(db, estimate, make_section):
    doomed = make_section("paving")
    add_pour(db, doomed)
    keep = make_section("mono_slab")
    add_pour(db, keep)

    db.delete(doomed)
    db.flush()

    # Scoped to this estimate: a bare count(*) over mono_slabs passes or fails
    # on whatever else happens to be in the database.
    remaining = db.execute(
        text(
            "SELECT count(*) FROM mono_slabs ms "
            "JOIN estimate_sections s ON s.id = ms.section_id "
            "WHERE s.estimate_id = :e"
        ),
        {"e": str(estimate.id)},
    ).scalar()
    assert remaining == 1


# --------------------------------------------------------------------------
# Rates belong to the assembly type (sql/035)
#
# Every workbook sheet carries its own. Paving forms at $0.30/SF against the
# slab sheet's $0.45, places at $0.55 against $0.65, wrecks at $0.15 against
# $0.10, has no GRADING line at all, and runs its supervision ladder at
# SF/25,000 rather than SF/16,000.
# --------------------------------------------------------------------------


def labor_lines(db, section_id) -> dict[str, object]:
    from app.services.labor import calc_labor_materials

    return {ln["code"]: ln for ln in calc_labor_materials(db, section_id)["lines"]}


def test_paving_prices_its_own_labor(db, make_section, setting):
    setting("labor_forming_sf", "0.45")
    setting("labor_place_finish_sf", "0.65")
    setting("labor_wreck_sf", "0.10")

    slab = make_section("mono_slab")
    paving = make_section("paving")
    add_pour(db, slab)
    add_pour(db, paving)

    s = labor_lines(db, slab.id)
    p = labor_lines(db, paving.id)

    assert s["forming"]["rate"] == Decimal("0.4500")
    assert p["forming"]["rate"] == Decimal("0.3000")
    assert s["place_finish"]["rate"] == Decimal("0.6500")
    assert p["place_finish"]["rate"] == Decimal("0.5500")
    assert s["wreck"]["rate"] == Decimal("0.1000")
    assert p["wreck"]["rate"] == Decimal("0.1500")


def test_paving_carries_no_grading_line_at_all(db, make_section, setting):
    """
    10-PAVING has no GRADING / CABLES row, and after sql/036 neither does the
    app: paving has its own line set, not the slab set with some rates zeroed.

    Phase 2 kept the line at $0 on the reasoning that a zero on screen can be
    questioned while an absent line cannot. That was right while paving was
    borrowing the slab's lines. It stopped being right once the set itself came
    from the sheet: what paving shows now — FORMING, PLACE AND FINISH, WRECK,
    REBAR, CURB — is the sheet, and a $0 GRADING row sitting in it would read
    as work that exists and has not been priced. The zeroed rate stays in
    assembly_rates as a backstop for anyone who puts the line back.
    """
    setting("labor_grading_sf", "0.65")
    paving = make_section("paving")
    add_pour(db, paving, sf="100000")

    lines = labor_lines(db, paving.id)
    assert "grading" not in lines
    assert "drops" not in lines
    assert "tie_steel" not in lines
    assert {"forming", "place_finish", "wreck", "rebar", "curb"} <= set(lines)

    # And the three SF lines still come to exactly $1.00/SF, as they do on the
    # sheet: 0.30 + 0.55 + 0.15.
    sf_lines = sum(
        lines[c]["ext_cost"] for c in ("forming", "place_finish", "wreck")
    )
    assert sf_lines == Decimal("100000.00")


def test_the_supervision_ladder_follows_the_assembly(db, make_section):
    """SF / 25,000 a week on paving, SF / 16,000 on the slab."""
    from app.services.labor import labor_drivers

    slab = make_section("mono_slab")
    paving = make_section("paving")
    add_pour(db, slab, sf="50000")
    add_pour(db, paving, sf="50000")

    assert labor_drivers(db, slab.id)["sf_per_week"] == Decimal("16000")
    assert labor_drivers(db, paving.id)["sf_per_week"] == Decimal("25000")
    # Same area, fewer weeks — paving covers ground faster.
    assert labor_drivers(db, paving.id)["super_days"] < labor_drivers(db, slab.id)["super_days"]


def test_an_assembly_with_no_opinion_still_follows_the_company(db, make_section, setting):
    """
    A row in assembly_rates means "this assembly differs", not "this is the
    value". mono_slab has no rows, so a company rate change must still reach it
    — seeding it from system_settings at migration time would have shadowed
    every future change behind a copy.
    """
    slab = make_section("mono_slab")
    add_pour(db, slab)

    setting("labor_forming_sf", "0.45")
    assert labor_lines(db, slab.id)["forming"]["rate"] == Decimal("0.4500")

    setting("labor_forming_sf", "0.70")
    assert labor_lines(db, slab.id)["forming"]["rate"] == Decimal("0.7000")


def test_a_company_change_does_not_override_an_assembly_that_differs(db, make_section, setting):
    """The other direction: paving keeps its own rate when the company moves."""
    paving = make_section("paving")
    add_pour(db, paving)

    setting("labor_forming_sf", "0.99")
    assert labor_lines(db, paving.id)["forming"]["rate"] == Decimal("0.3000")


def test_paving_labor_matches_the_workbook_per_sf(db, make_section):
    """
    10-PAVING: forming + place & finish + wreck = $0.30 + $0.55 + $0.15 = $1.00
    per SF, which is exactly what the sheet's "Total Sub Labor" cost code holds
    (272,703 SF → $272,703). That code is a SUBTOTAL of the three, not a fourth
    line — adding it double-counts the whole labor package.
    """
    paving = make_section("paving")
    add_pour(db, paving, sf="272703")

    ln = labor_lines(db, paving.id)
    three = sum(
        (ln[c]["ext_cost"] for c in ("forming", "place_finish", "wreck")),
        Decimal("0"),
    )
    assert three == Decimal("272703.00")
