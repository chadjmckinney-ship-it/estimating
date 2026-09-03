"""
Forming and accessory quantities, checked against the LBJ workbook cell by cell.

This was the last untested corner of the calc, and it read as −$4,383 against the
bid until the workbook's own detail block was opened. Almost all of that gap was
a mis-filed line: cost code 40011 "Patch/Grout" is not patch or grout, it is
**poly tape** — row 95, `V95 = V88 × 2.5`, barrier rolls × 2.5 at $33/roll. Move
it where it belongs and the forming package agrees with the sheet to $16 on
$29,600.

What is left is four real differences, all of them the app being right:

  8p / 20p nails   the sheet sums K11:K42 and K12:K47 — ranges that slipped down
                   and swallowed K42, the perimeter TOTAL cell — so it buys 24
                   boxes where 16p (correct range, K10:K41) buys 13
  2x4 bracing      the sheet's `SUM(W10:X41)*3` adds a section-NUMBER column to a
                   length column: 144 + 865 = 1,009 LF instead of 865
  siding           the sheet is the only form material it does not scale by form%
  accessories      the sheet prices at $0.02/lb; the catalog carries $0.04

LBJ drivers used throughout: 62,723 SF, 4,890 LF perimeter, 865 FF drops,
form% 0.50, no mesh.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import text

from app.services.forming import calc_forming_materials


@pytest.fixture
def lbj(db, section, make_pour, make_beam):
    """
    One pour carrying the LBJ totals — the forming lines only read the sums.
    The 865 FF of drops are a beam of kind 'drop' (sql/022), which is where
    drops_ff comes from.
    """
    section.form_percent = Decimal("0.50")
    slab = make_pour(
        square_footage=Decimal("62723"),
        perimeter_edge_lf=Decimal("4890"),
        slab_bar_size=None,
        slab_bar_spacing_in=None,
    )
    make_beam(slab, kind="drop", label="Drop 9", width_in=Decimal("12"),
              height_in=Decimal("12"), length_lf=Decimal("865"))
    db.flush()
    section._slab = slab
    return section


def lines(db, section_id) -> dict[str, dict]:
    out = calc_forming_materials(db, section_id)
    return {ln["code"]: ln for ln in out["lines"]}


def price(db, name: str, unit_cost: str) -> None:
    db.execute(
        text("UPDATE materials SET unit_cost = :p WHERE name ILIKE :n"),
        {"p": Decimal(unit_cost), "n": f"%{name}%"},
    )
    db.flush()


# --------------------------------------------------------------------------
# Form lumber — scaled by form%
# --------------------------------------------------------------------------


def test_form_lumber_quantities_match_the_workbook(db, lbj):
    ln = lines(db, lbj.id)

    # V69 = K42 × W65 — perimeter × form%
    assert ln["2x6"]["qty"] == Decimal("2445.000")
    # V66 = (V69 × 3 + I83) × W65 — 2x6 LF ×3 plus drops, all × form%
    assert ln["2x4"]["qty"] == Decimal("4100.000")
    # V71 = CE42 × W65 × 2
    assert ln["2x10"]["qty"] == Decimal("4890.000")
    # V74 = ROUND(V71 / 25) — stakes follow the 2x10 count
    assert ln["stakes"]["qty"] == Decimal("196")


def test_siding_is_scaled_by_form_percent_and_the_workbook_forgot_to(db, lbj):
    """
    V72 = ROUNDUP(SUM(K10:K41) × 0.03 / 16) — every other form material in the
    sheet is multiplied by form%, this one is not. Ten sheets there, five here.
    Consistency wins: masonite is form material like the rest.
    """
    ln = lines(db, lbj.id)
    assert ln["siding"]["qty"] == Decimal("5")  # ceil(4890 × 0.5 × 0.03 / 16)


def test_ply_follows_the_drops(db, lbj):
    # V73 = I83 / 32 × W65 × 1.1
    ln = lines(db, lbj.id)
    assert ln["ply"]["qty"] == Decimal("14.867")


def test_form_percent_scales_the_lumber_and_nothing_else(db, lbj):
    before = lines(db, lbj.id)
    lbj.form_percent = Decimal("1.00")
    db.flush()
    after = lines(db, lbj.id)

    assert after["2x6"]["qty"] == before["2x6"]["qty"] * 2
    assert after["2x10"]["qty"] == before["2x10"]["qty"] * 2
    # Nails, anchors, chairs and accessories are bought for the job, not the
    # share of forms owned.
    for code in ("16p", "anchors", "chairs", "accessories", "cure"):
        assert after[code]["qty"] == before[code]["qty"], code


# --------------------------------------------------------------------------
# The two spreadsheet bugs
# --------------------------------------------------------------------------


def test_all_three_nail_boxes_use_the_same_perimeter(db, lbj):
    """
    The sheet buys 13 boxes of 16p and 24 each of 8p and 20p, off the same
    perimeter. 16p reads SUM(K10:K41); 8p reads K11:K42 and 20p reads K12:K47 —
    both of which include K42, the row holding the perimeter TOTAL. Every box
    here is ceil(4,890 × 1.25 / 500) = 13.
    """
    ln = lines(db, lbj.id)
    assert ln["16p"]["qty"] == Decimal("13")
    assert ln["8p"]["qty"] == Decimal("13")
    assert ln["20p"]["qty"] == Decimal("13")


def test_bracing_is_three_times_the_drops_only(db, section, lbj):
    """
    The sheet's `SUM(W10:X41) × 3` sums a beam-section-NUMBER column together
    with the length column beside it: 144 + 865 = 1,009 LF of bracing for 865 FF
    of drops. Bracing is 3 × drops.
    """
    ln = lines(db, lbj.id)
    assert ln["2x4_brace"]["qty"] == Decimal("2595.000")  # 3 × 865


def test_bracing_does_not_move_with_form_percent(db, lbj):
    before = lines(db, lbj.id)["2x4_brace"]["qty"]
    lbj.form_percent = Decimal("1.00")
    db.flush()
    assert lines(db, lbj.id)["2x4_brace"]["qty"] == before


# --------------------------------------------------------------------------
# Accessories — bought for the job
# --------------------------------------------------------------------------


def test_accessories_track_the_rebar_weight(db, lbj, make_beam):
    """V100 = L70 + L71 × 0.75 — rebar lb plus three-quarters of the mesh SF."""
    before = lines(db, lbj.id)["accessories"]["qty"]
    assert before > 0

    make_beam(lbj._slab, label="GB-extra")
    after = lines(db, lbj.id)["accessories"]["qty"]
    assert after > before


def test_chairs_tie_wire_and_cure_come_off_the_slab_area(db, lbj):
    ln = lines(db, lbj.id)
    # V98 = ROUNDUP(D42 / 15000); V99 = I79 / 15000; V105 = ROUNDUP(I79/300/55)
    assert ln["chairs"]["qty"] == Decimal("5")
    assert ln["tie_wire"]["qty"] == Decimal("4.182")
    assert ln["cure"]["qty"] == Decimal("4")


def test_anchor_bolts_come_off_the_perimeter(db, lbj):
    # V78 = CE42 / 150
    assert lines(db, lbj.id)["anchors"]["qty"] == Decimal("32.600")


def test_the_manual_lines_start_empty(db, lbj):
    """Keyway, chamfer, redwood and form release are blank in the sheet too."""
    ln = lines(db, lbj.id)
    for code in ("keyway", "chamfer", "rw6", "rw8", "form_release"):
        assert ln[code]["qty"] == Decimal("0.000"), code
        assert ln[code]["ext_cost"] == Decimal("0.00"), code


# --------------------------------------------------------------------------
# Extended cost
# --------------------------------------------------------------------------


def test_the_package_prices_at_catalog(db, lbj):
    price(db, "2 X 6 X 16", "1.4453")
    price(db, "2 X 4 X 16", "0.8594")
    ln = lines(db, lbj.id)

    assert ln["2x6"]["ext_cost"] == Decimal("3533.76")   # 2,445 × 1.4453
    assert ln["2x4"]["ext_cost"] == Decimal("3523.54")   # 4,100 × 0.8594
    assert ln["2x4_brace"]["ext_cost"] == Decimal("2230.14")  # 2,595 × 0.8594


def test_form_waste_multiplies_the_extended_cost(db, lbj, setting):
    """Waste rides the extended cost, not the quantity — you buy 10% more money
    of the same board count."""
    base = lines(db, lbj.id)["2x6"]
    setting("form_waste", "0.10")
    after = lines(db, lbj.id)["2x6"]

    assert after["qty"] == base["qty"]
    expected = (base["qty"] * base["unit_cost"] * Decimal("1.10")).quantize(Decimal("0.01"))
    assert after["ext_cost"] == expected
    assert after["ext_cost"] > base["ext_cost"]


def test_no_perimeter_means_no_forming(db, estimate, make_pour):
    """A pour with no edge buys no lumber rather than a division-by-zero."""
    make_pour(square_footage=Decimal("5000"), perimeter_edge_lf=Decimal("0"))
    ln = lines(db, estimate.id)
    for code in ("2x6", "2x4", "2x10", "siding", "16p", "anchors"):
        assert ln[code]["qty"] == 0, code


# ------------------------------------------------- catalog name resolution ----


def test_6p_nails_do_not_resolve_to_16p(db):
    """
    `%6p%` matches "16p NAILS DUPLEX". It sorted first on id, so every assembly
    in the app — slab, paving, piers, walls, columns, all five call
    `_find_material(db, "6p")` — put 16p nails on its 6p line.

    It cost nothing the day it was found, because all three nail boxes are
    $68.20, and that is what made it invisible: the extension was right and the
    material name beside it was not. This asserts the NAME, which is the part
    that was wrong.
    """
    from app.services.forming import _find_material
    from app.services.price_book import catalog_only

    # This test is about which ROW a name resolves to, not what it costs, so
    # it reads the catalog explicitly rather than an estimate's sheet.
    with catalog_only():
        six = _find_material(db, "6p")
        sixteen = _find_material(db, "16p")
        eight = _find_material(db, "8p")
    assert six is not None, "no 6p nail in the catalog"
    assert "16p" not in six["name"].lower(), f"6p resolved to {six['name']!r}"
    assert six["name"].lower().startswith("6p")

    # The neighbours still resolve to themselves.
    assert "16p" in sixteen["name"].lower()
    assert eight["name"].lower().startswith("8p")


def test_ranking_did_not_break_the_multi_part_lookups(db):
    """
    The fix RANKS rather than filters, so a fragment that only ever matched
    mid-name must still find its material. These are the shapes the line sets
    actually use.
    """
    from app.services.forming import _find_material
    from app.services.price_book import catalog_only

    for parts, expect in [
        (("2 X 4",), "2 x 4"),
        (("3/4", "PLY"), "ply"),
        (("CHAMFER",), "chamfer"),
        (("ACCESSORIES",), "accessories"),
        (("FORM RELEASE",), "form release"),
    ]:
        with catalog_only():
            found = _find_material(db, *parts)
        assert found is not None, f"{parts} found nothing"
        assert expect in found["name"].lower(), f"{parts} -> {found['name']!r}"
