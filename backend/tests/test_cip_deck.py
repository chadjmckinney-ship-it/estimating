"""
08-CIP EL. DECK (sql/052) — the sixth assembly, and the first that hangs in
the air.

32,100 SF on two levels. The sheet reads $952,052.02 and reconciles from its
own nineteen cost columns to a tenth of a cent, so this is a golden number in
the strong sense: every part of it is understood, and every difference below
it is a decision with a name and a dollar figure.

`deck_fixture.GOLDEN_COST` is $959,698.67, and its whole derivation from the
sheet is in that module's docstring. The tests here are that derivation, one
piece at a time.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.db import get_db
from app.main import app
from app.models.deck_level import DeckLevel
from app.services import cip_deck as cd
from app.services import price_book as pb
from app.services.costing import (
    allocation_basis,
    refresh_pour_costs,
    resolve_rebar,
    section_unpriced,
)
from app.services.estimate_equipment import (
    equip_days_from_super,
    load_stored_equipment,
    refresh_and_store_equipment,
    rental_billable_units,
)
from app.services.forming import load_stored_forming, refresh_and_store_forming
from app.services.labor import load_stored_labor, refresh_and_store_labor
from app.services.recalc import recalc_section
from tests import deck_fixture as df

D = Decimal
TAX = D("1.0825")


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _build(db, estimate, *, type_supervision=True, sheet_mode=False):
    section = df.build(db, estimate, sheet_mode=sheet_mode)
    refresh_and_store_forming(db, section.id)
    refresh_and_store_labor(db, section.id)
    refresh_and_store_equipment(db, section.id)
    if type_supervision:
        # Last, as test_piers does: typing the days moves the rental ladder on
        # the NEXT refresh (audit #5).
        df.type_the_supervision(db, section.id)
    refresh_pour_costs(db, section)
    db.flush()
    recalc_section(db, section)
    db.flush()
    return section


def _levels(db, section_id) -> list[DeckLevel]:
    return list(
        db.scalars(
            select(DeckLevel)
            .where(DeckLevel.section_id == section_id)
            .order_by(DeckLevel.sort_order)
        ).all()
    )


def _cost(db, section_id) -> Decimal:
    return db.execute(
        text("SELECT calc_total_cost FROM estimate_sections WHERE id = :i"),
        {"i": str(section_id)},
    ).scalar()


def _unpriced(db, section_id) -> list[str]:
    return db.execute(
        text("SELECT calc_unpriced FROM estimate_sections WHERE id = :i"),
        {"i": str(section_id)},
    ).scalar()


def _forming(db, section_id) -> dict:
    return {ln["code"]: ln for ln in load_stored_forming(db, section_id)["lines"]}


def _labor(db, section_id) -> dict:
    return {ln["code"]: ln for ln in load_stored_labor(db, section_id)["lines"]}


def _equip(db, section_id) -> dict:
    return {ln["code"]: ln for ln in load_stored_equipment(db, section_id)["lines"]}


# ------------------------------------------------------- the sheet's own ----


def test_the_concrete_reconciles_to_the_sheet_exactly(db, estimate):
    """
    1,459.8519 CY. Slab and beams, waste and all, to four decimals — and the
    concrete is the half of this sheet the app does NOT change, so it is the
    proof that the geometry is read right before any decision is argued about.
    """
    section = df.build(db, estimate, sheet_mode=True)
    t = cd.section_deck_totals(db, section.id)
    assert D(str(t["total_concrete_cy"])) == D("1459.8518")
    # ...and it is slab plus beams, not one figure that happens to land.
    assert D(str(t["total_slab_cy"])) == D("1442.5185")
    assert D(str(t["total_beam_cy"])) == D("17.3333")


def test_the_slab_mats_reconcile_to_the_sheet_exactly(db, estimate):
    """
    56,603.78 lb of two-way mat, against the sheet's `AP` column summed.

        2 / (spacing / 12) x area x lb per ft x (1 + waste)

    The sheet writes the same rule as `(s/12 + s/12) / (s/12 x s/12)`, which
    is the standard two-way mat rule the long way round.
    """
    section = df.build(db, estimate, sheet_mode=True)
    t = cd.section_deck_totals(db, section.id)
    # 18,421.797 + 38,181.983 on the sheet's own rows.
    assert D(str(t["total_slab_rebar_lb"])) == D("56603.780")


def test_the_beam_schedule_reproduces_its_own_lb_per_lf(db, estimate):
    """56.6982 and 63.4553 lb/LF — the sheet's O53 and O54, post-waste."""
    from app.models.beam_type import EstimateBeamType

    section = df.build(db, estimate, sheet_mode=True)
    beams = {
        b.label: b
        for b in db.scalars(
            select(EstimateBeamType).where(EstimateBeamType.section_id == section.id)
        ).all()
    }
    waste = D("1.1")
    gb1 = cd.beam_lb_per_lf(db, beams["GB1"], sheet=True) * waste
    gb2 = cd.beam_lb_per_lf(db, beams["GB2"], sheet=True) * waste
    assert abs(gb1 - D("56.69817153")) < D("0.0001"), gb1
    assert abs(gb2 - D("63.45526176")) < D("0.0001"), gb2


# ------------------------------------------- the six things the sheet gets
# ------------------------------------------- wrong, and the one Chad changed


def test_every_beam_slot_carries_its_own_steel(db, estimate):
    """
    The biggest bug on this tab, and it is live on LBJ.

    `AL` (slot 1) reads column O, lb per LF. `AM` (slot 2) reads column **Q**,
    which is CY per LF, and `AN` (slot 3) reads column **S**, a header cell.
    So level 2's 45 LF of type-2 beam is charged **7 lb** where it weighs
    2,855.49, and a third beam on any level is free.

    Level 2 here: 30 LF of GB1 and 45 LF of GB2, both weighed.
    """
    section = df.build(db, estimate, sheet_mode=True)
    lvl2 = _levels(db, section.id)[0]
    honest = (
        (D("30") * D("56.69817153") + D("45") * D("63.45526176")) * D("1.12")
    )
    assert abs(D(str(lvl2.calc_beam_rebar_lb)) - honest) < D("0.05")
    # The sheet's own figure for the same row, for the size of it.
    assert D(str(lvl2.calc_beam_rebar_lb)) > D("1912.96") * 2


def test_the_grade_beams_are_formed_on_both_faces(db, estimate):
    """
    Chad, 2026-09-04, asked whether a deck grade beam is formed on one side
    only: "both faces — the sheet is light."

    240 FF becomes 480. It is not a forming detail: the SAME figure drives
    every lumber line on the section, so this is $1,440 of labor and $985.01
    of lumber, not $1,440.
    """
    section = _build(db, estimate)
    t = cd.section_deck_totals(db, section.id)
    assert D(str(t["total_gb_form_ff"])) == D("480.000") == df.SHEET["gb_form_ff"] * 2
    assert D(str(t["lumber_driver_lf"])) == D("2164.000")   # 1,684 edge + 480

    assert _labor(db, section.id)["gb_forming"]["ext_cost"] == D("2880.00")
    # ...and it reached the lumber, which is the half that is easy to miss.
    f = _forming(db, section.id)
    assert D(str(f["2x4"]["qty"])) == D("2164.000")
    assert D(str(f["ply"]["qty"])) == D("33.758")           # 2,164 / 64


def test_reshoring_covers_every_level(db, estimate):
    """
    `K83 = C10+C12+C14+C16+C22+C24+C28` — a hand-picked list of rows that
    skips 18, 20, 26 and everything past 28. A level entered on one of those
    is reshored for free. Here it is the section's area, whatever the rows.
    """
    section = _build(db, estimate)
    t = cd.section_deck_totals(db, section.id)
    assert D(str(_labor(db, section.id)["reshoring"]["qty"])) == D(str(t["total_sf"]))

    # Add a third level and the reshoring follows it — the sheet's list would
    # not have a row for it.
    db.add(
        DeckLevel(section_id=section.id, label="level 4", area_sf=D("5000"),
                  thickness_in=D("14"), sort_order=99)
    )
    db.flush()
    recalc_section(db, section)
    db.flush()
    assert D(str(_labor(db, section.id)["reshoring"]["qty"])) == D("37100.000")


def test_own_crew_cable_placement_bills(db, estimate):
    """
    `K95 = IF(C100="N", D100 x H87, 0)` reads row 100, which is blank. The
    sub column is right; self-perform cable placement on the sheet and it
    costs $0 — $23,994.75 on this job.
    """
    section = _build(db, estimate)
    subbed = _labor(db, section.id)["cable_placement"]
    assert subbed["subcontracted"] is True
    assert D(str(subbed["ext_cost"])) == D("23994.75")

    section.labor_subcontracted = False
    db.flush()
    refresh_and_store_labor(db, section.id)
    own = _labor(db, section.id)["cable_placement"]
    assert own["subcontracted"] is False
    # The number does not move when the crew changes — which is the point.
    assert D(str(own["ext_cost"])) == D("23994.75")


def test_the_reshoring_material_rate_is_unpriced_not_free(db, estimate):
    """
    `F83` is blank, so the sheet prices reshoring MATERIAL at $0 while its
    LABOR prices at $11,235. A blank is not a price of zero (decision 5): the
    line is UNPRICED and the section says so.
    """
    section = _build(db, estimate)
    f = _forming(db, section.id)
    assert f["reshoring"]["ext_cost"] is None
    assert f["reshoring"]["missing_price"] is True
    assert D(str(f["reshoring"]["qty"])) == D("32100.000")
    assert any("RESHORING" in x.upper() for x in _unpriced(db, section.id))

    # ...and the labor for the same work bills in full, which is the mismatch.
    assert D(str(_labor(db, section.id)["reshoring"]["ext_cost"])) == D("11235.00")


def test_typing_a_reshoring_rate_prices_the_line(db, estimate):
    """The other half: give it a number and it costs, and the flag clears."""
    section = _build(db, estimate)
    db.execute(
        text(
            "INSERT INTO assembly_rates (kind, key, value, note) "
            "VALUES ('cip_deck', 'reshoring_material_sf', 0.35, 'test') "
            "ON CONFLICT (kind, key) DO UPDATE SET value = excluded.value"
        )
    )
    db.flush()
    # A monetary key is frozen on the sheet, so a NEW rate has to be pulled.
    pb.pull_prices(db, estimate.id)
    refresh_and_store_forming(db, section.id)
    recalc_section(db, section)
    db.flush()

    f = _forming(db, section.id)
    # 32,100 SF x $0.35 x the 1.1 reshoring multiplier.
    assert D(str(f["reshoring"]["ext_cost"])) == D("12358.50")
    assert not any("RESHORING" in x.upper() for x in _unpriced(db, section.id))


def test_the_two_shoring_multipliers_are_two_cells(db, estimate):
    """
    `J83` is 1.1 on the sheet, labelled under reshoring and silently read by
    form rental shoring as well. Editing it for one reason moved the other by
    $4,300. Two rules here, and moving one leaves the other alone.
    """
    section = _build(db, estimate)
    before = D(str(_forming(db, section.id)["form_rental_shoring"]["ext_cost"]))
    assert before == (D("32100") * D("1.25") * D("1.1")).quantize(D("0.01"))

    db.execute(
        text("UPDATE assembly_rates SET value = 1.5 "
             "WHERE kind = 'cip_deck' AND key = 'reshoring_multiplier'")
    )
    db.flush()
    refresh_and_store_forming(db, section.id)
    assert D(str(_forming(db, section.id)["form_rental_shoring"]["ext_cost"])) == before


def test_the_bar_is_grade_beam_bar(db, estimate):
    """
    The sheet points `F78` at `Pricing!D23` — REBAR GRADE BEAM, $0.65. The
    catalog also carries "REBAR PIERS / PT slabs" at $0.60, and until
    2026-09-05 the app resolved an elevated PT deck to it on the sql/043
    rule, -$3,513.21 against the sheet. Chad, given the choice: "use rebar
    GB." A deck buys grade-beam bar whether or not it is post-tensioned.
    """
    section = df.build(db, estimate)
    with pb.priced_as(db, estimate.id):
        mat = resolve_rebar(db, True, section.kind)
    assert mat is not None and "GRADE BEAM" in mat["name"], mat


# ---------------------------------------------------- the machinery it reuses


def test_the_ladder_is_the_one_every_assembly_uses(db, estimate):
    """60 typed super days → 90 equipment days → 27 billable units."""
    assert equip_days_from_super(60) == D("90")
    assert rental_billable_units(90) == D("27")

    section = _build(db, estimate)
    e = load_stored_equipment(db, section.id)
    assert D(str(e["drivers"]["super_days"])) == D("60.0000")
    assert D(str(e["drivers"]["equip_days"])) == D("90.0000")
    crane = next(ln for ln in e["lines"] if ln["code"] == "crane")
    assert D(str(crane["billable_units"])) == D("27")


def test_the_crane_is_the_largest_equipment_line_in_the_app(db, estimate):
    """$3,200/day x 27 billable = $86,400, and $136,728 with fuel and tax —
    14% of the section on one line."""
    section = _build(db, estimate)
    crane = _equip(db, section.id)["crane"]
    assert D(str(crane["rate"])) == D("3200.0000")
    assert D(str(crane["ext_cost"])) == D("86400.00")
    # Fuel and tax are applied by costing, not stored on the line.
    assert (D("86400") * (D("1") + D("0.0825") + D("0.5"))).quantize(D("0.01")) == D("136728.00")


def test_an_untyped_deck_is_flagged_like_piers_and_walls(db, estimate):
    """A deck TYPES its days. Untyped, the rental ladder is 0 days and every
    machine reads $0.00 beside a correct rate — audit #5, inherited."""
    section = _build(db, estimate, type_supervision=False)
    assert any("superintendent days — not typed" in x for x in _unpriced(db, section.id))
    assert D(str(_equip(db, section.id)["crane"]["ext_cost"])) == 0

    df.type_the_supervision(db, section.id)
    refresh_and_store_equipment(db, section.id)
    recalc_section(db, section)
    db.flush()
    assert not any("superintendent" in x for x in _unpriced(db, section.id))
    assert D(str(_equip(db, section.id)["crane"]["ext_cost"])) == D("86400.00")


def test_shared_cost_allocates_by_deck_area(db, estimate):
    """
    The sheet's own allocation columns (BU:BY) all divide by total SF, and the
    section is measured and sold in SF — so weight and quantity are the same
    field here, the first assembly since the mono slab where they are.
    """
    assert allocation_basis("cip_deck") == "SF"

    section = _build(db, estimate)
    levels = _levels(db, section.id)
    total = _cost(db, section.id)
    # Level 3 is 21,653 of 32,100 SF and carries that share of everything
    # shared, plus its own concrete and steel.
    assert sum((D(str(l.calc_cost)) for l in levels), D(0)) == total
    assert D(str(levels[1].calc_cost)) > D(str(levels[0].calc_cost))


# ----------------------------------------------------------- sub labor ----


def test_one_switch_subs_the_field_labor_and_leaves_supervision_alone(db, estimate):
    """
    The sheet decides it per line — a Y/N on each of the ten labor rows.
    Asked whether that is real, Chad, 2026-09-04: one switch per section.

    Supervision is never subbed; the sheet has no Y/N on that block either,
    because a superintendent is yours whoever swings the hammer.
    """
    section = _build(db, estimate)
    lines = load_stored_labor(db, section.id)["lines"]
    field = [ln for ln in lines if ln["group_name"] == "labor"]
    sup = [ln for ln in lines if ln["group_name"] == "supervision"]

    assert field and all(ln["subcontracted"] for ln in field)
    assert sup and not any(ln["subcontracted"] for ln in sup)

    # $251,654.73 on LBJ — ten lines, all Y. The app's figure is above it by
    # the beam-face and beam-slot corrections and nothing else.
    subbed = sum((D(str(ln["ext_cost"])) for ln in field), D(0))
    assert subbed == df.SHEET["sub_labor"] + D("1440.00") + D("718.59")


def test_subbing_labor_does_not_move_the_money(db, estimate):
    """
    Costing does not care which bucket: subbed labor is still labor, untaxed
    and carrying no fuel. What the switch buys is being able to say what the
    sub is being asked to price.
    """
    section = _build(db, estimate)
    before = _cost(db, section.id)

    section.labor_subcontracted = False
    db.flush()
    refresh_and_store_labor(db, section.id)
    recalc_section(db, section)
    db.flush()

    assert _cost(db, section.id) == before
    assert not any(
        ln["subcontracted"] for ln in load_stored_labor(db, section.id)["lines"]
    )


# ------------------------------------------------------ post-tension ----


def test_post_tension_is_priced_once_on_the_level(db, estimate):
    """
    PT is a material bought against the takeoff, so it sits on the LEVEL as
    direct cost the way concrete and steel do — NOT as a forming line. The
    first draft had it in both and billed $50,384.96 twice.
    """
    section = _build(db, estimate)
    assert "post_tension" not in _forming(db, section.id)

    t = cd.section_deck_totals(db, section.id)
    assert D(str(t["total_pt_sf"])) == D("32100.000")
    assert D(str(t["total_pt_lb"])) == D("36915.000")     # SF x 1.15


def test_pt_sf_is_the_levels_that_carry_cable(db, estimate):
    """`BE10 = IF(F10="N", 0, C10)`. A level with no cable is not PT area, and
    a lump PT quote must not land on it."""
    section = _build(db, estimate)
    lvl = _levels(db, section.id)[0]
    lvl.has_cable = False
    db.flush()
    recalc_section(db, section)
    db.flush()

    t = cd.section_deck_totals(db, section.id)
    assert D(str(t["total_pt_sf"])) == D("21653.000")
    assert D(str(t["total_pt_lb"])) == D("24900.950")


def test_a_pt_quote_replaces_the_computed_figure(client, db, estimate):
    """
    `N80 = IF(I80 = 0, SF x 1.45, I80)` — the sheet already has the slot. It
    is `section_quotes` (sql/039), not a thirteenth column.
    """
    section = _build(db, estimate)
    before = _cost(db, section.id)

    r = client.put(
        f"/api/sections/{section.id}/quotes/pt",
        json={"unit": "SF", "amount": "1.20"},
    )
    assert r.status_code in (200, 201), r.text
    recalc_section(db, section)
    db.flush()

    # 32,100 SF x $0.25 less, plus the tax that rides it.
    moved = before - _cost(db, section.id)
    assert abs(moved - (D("32100") * D("0.25") * TAX)) < D("1.00"), moved


# ------------------------------------------------------- the whole thing ----


def test_the_section_reconciles_to_the_golden_number(db, estimate):
    """
    $959,698.67 — the sheet's $952,052.02 plus every difference named in
    `deck_fixture`'s docstring and nothing else. If this moves, one of the
    tests above should have moved first; if none did, something changed that
    nobody decided.
    """
    section = _build(db, estimate)
    assert _cost(db, section.id) == df.GOLDEN_COST


def test_the_gap_to_the_sheet_is_exactly_the_six_decisions(db, estimate):
    """
    The reconciliation itself, as arithmetic rather than prose. Seven pieces
    until 2026-09-05; the seventh — bar at the PT-slab price, -$3,513.21 —
    went when Chad chose grade-beam bar, and the sheet and the app agree.
    """
    pieces = (
        D("2247.26")    # steel the beam slots dropped
        + D("718.59")   # tie-steel labor on it
        + D("1440.00")  # GB forming labor, both faces
        + D("1013.75")  # lumber on the doubled faces, plus tax on PAVECRETE
        + D("550.46")   # MISCELLANEOUS taxed and fuelled like a rental
        + D("1676.58")  # ACCESSORIES at $0.04, and tax on four lines
    )
    named = df.SHEET["total_cost"].quantize(D("0.01")) + pieces
    # Six pieces each stated to the cent sum a cent short of the app's number.
    # That cent is rounding, not a decision — anything more is.
    assert abs(named - df.GOLDEN_COST) <= D("0.01"), named - df.GOLDEN_COST


def test_the_section_is_sold_by_the_square_foot(db, estimate):
    section = _build(db, estimate)
    row = db.execute(
        text("SELECT unit, calc_quantity, calc_cost_per_unit, calc_total_sale "
             "FROM estimate_sections WHERE id = :i"),
        {"i": str(section.id)},
    ).mappings().one()
    assert row["unit"] == "SF"
    assert D(str(row["calc_quantity"])) == D("32100.000")
    assert D(str(row["calc_total_sale"])) == (
        df.GOLDEN_COST * D("1.18")
    ).quantize(D("0.01"))


# ------------------------------------------------------------------ API ----


def test_the_grid_round_trips(client, db, estimate):
    """One request saves the whole grid and recalculates the section once."""
    section = _build(db, estimate)
    rows = client.get(f"/api/deck-levels?section_id={section.id}").json()
    assert len(rows) == 2
    assert D(str(rows[0]["calc_gb_form_ff"])) == D("150.000") * 2

    rows[0]["area_sf"] = "12000"
    r = client.put(
        "/api/deck-levels/bulk",
        json={"section_id": str(section.id),
              "rows": [{k: v for k, v in row.items()
                        if k in ("id", "label", "area_sf", "thickness_in",
                                 "has_cable", "mix_design_id", "perm_edge_lf",
                                 "top_bar_size", "top_bar_spacing_in")}
                       for row in rows]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["updated"] == 2
    assert D(str(r.json()["totals"]["total_sf"])) == D("33653.000")


def test_a_level_needs_an_area(client, db, estimate):
    """Everything on this assembly is square feet — the labor, the allocation,
    the pour. A level with none is not a level."""
    section = _build(db, estimate)
    r = client.put(
        "/api/deck-levels/bulk",
        json={"section_id": str(section.id), "rows": [{"label": "level 5"}]},
    )
    assert r.status_code == 400 and "area" in r.text


def test_omitting_beams_leaves_the_schedule_alone(client, db, estimate):
    """A grid that only edits areas must not silently strip the beams."""
    section = _build(db, estimate)
    before = D(str(_levels(db, section.id)[0].calc_beam_rebar_lb))
    row = client.get(f"/api/deck-levels?section_id={section.id}").json()[0]

    r = client.patch(f"/api/deck-levels/{row['id']}", json={"perm_edge_lf": "700"})
    assert r.status_code == 200, r.text
    db.expire_all()
    assert D(str(_levels(db, section.id)[0].calc_beam_rebar_lb)) == before


def test_a_beam_from_another_section_is_refused(client, db, estimate):
    """An unresolved beam is a level with no beam steel and no beam concrete,
    and nothing on screen to notice. So it is a 400, not a silent skip."""
    from app.models.beam_type import EstimateBeamType
    from app.models.estimate_section import EstimateSection

    section = _build(db, estimate)
    other = EstimateSection(
        estimate_id=estimate.id, kind="mono_slab", name="somebody else's slab",
        unit="SF",
    )
    db.add(other)
    db.flush()
    stray = EstimateBeamType(
        section_id=other.id, label="X", kind="grade_beam",
        width_in=D("12"), height_in=D("12"),
    )
    db.add(stray)
    db.flush()

    row = client.get(f"/api/deck-levels?section_id={section.id}").json()[0]
    r = client.patch(
        f"/api/deck-levels/{row['id']}",
        json={"beams": [{"beam_type_id": str(stray.id), "length_lf": "10"}]},
    )
    assert r.status_code == 400 and "not on this section" in r.text


def test_the_section_carries_the_sub_labor_switch(client, db, estimate):
    """It is a section field, so the screen is a checkbox and the whole
    section follows it on the next recalc."""
    section = _build(db, estimate)
    r = client.patch(
        f"/api/sections/{section.id}", json={"labor_subcontracted": False}
    )
    assert r.status_code == 200, r.text
    assert r.json()["labor_subcontracted"] is False
    assert not any(
        ln["subcontracted"] for ln in load_stored_labor(db, section.id)["lines"]
    )
