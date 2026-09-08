"""
Garden style (sql/079): one pour row standing for `qty` buildings.

The workbook's "Mono Slab on Grade Garden Style" tab is the 04 tab with a QTY
column: one row per building TYPE, taken off once and multiplied. University
Hills is five type rows covering eight buildings. The app priced a garden-style
job as eight rows that had to agree, so this is a quantity on the pour row.

The contract, and the only thing worth asserting: **a row at qty 8 is eight
identical rows.** Every quantity to the last decimal — the pour's own stored
figures, the section totals, the forming, labor and equipment lines, the
material list — and the money to within the cents that per-row rounding
across eight rows can move. And qty 0 keeps the row on the list and out of
every total.

The building type here is the LBJ fixture's Pour 01 — 2,942 SF of 4"
post-tensioned slab on 2" of sand — given a #4 mat and 48" cable spacing it
did not have, and its five beam usages: two PT grade beams, a reinforced one,
a brick ledge and a drop. Every rollup the pour has is on it.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.models.beam_type import EstimateBeamType
from app.models.estimate_section import EstimateSection
from app.models.grade_beam import GradeBeam
from app.models.mono_slab import MonoSlab
from app.services.calc import refresh_mono_slab_calcs, section_mono_totals
from app.services.costing import refresh_pour_costs
from app.services.estimate_equipment import (
    load_stored_equipment,
    refresh_and_store_equipment,
)
from app.services.forming import (
    estimate_forming_drivers,
    load_stored_forming,
    refresh_and_store_forming,
)
from app.services.labor import load_stored_labor, refresh_and_store_labor
from app.services.material_costs import section_material_costs
from tests import mono_slab_fixture as mf

# Pour 01 of the LBJ fixture, and its beams.
DESC, SF, PERIMETER, _, _ = mf.POURS[0]
BEAMS = mf.BEAM_LF[0]

# Eight rows each quantized to the cent can sit this far from one row
# quantized once: direct, tax and sale each round per row.
CENTS = Decimal("0.25")


def _dec(x) -> Decimal:
    return Decimal(str(x))


def _build(db, estimate, ids: dict, qtys: list[int]) -> EstimateSection:
    """A mono slab section of Pour 01 rows, one per entry of `qtys`."""
    section = EstimateSection(
        estimate_id=estimate.id,
        vapor_barrier_material_id=ids[mf.VAPOR_BARRIER],
        vapor_tape_material_id=ids[mf.VAPOR_TAPE],
        **mf.SECTION,
    )
    db.add(section)
    db.flush()

    types = []
    for order, (label, kind, w, h, face, tn, ts, bn, bs, ss, sp) in enumerate(mf.BEAM_TYPES):
        bt = EstimateBeamType(
            section_id=section.id,
            label=label,
            kind=kind,
            width_in=Decimal(w),
            height_in=Decimal(h),
            form_face_in=Decimal(face) if face is not None else None,
            top_bars_count=tn,
            top_bars_size=ts,
            bottom_bars_count=bn,
            bottom_bars_size=bs,
            stirrup_size=ss,
            stirrup_spacing_in=Decimal(sp) if sp is not None else None,
            sort_order=(order + 1) * 10,
        )
        db.add(bt)
        db.flush()
        types.append(bt)

    for i, qty in enumerate(qtys):
        slab = MonoSlab(
            section_id=section.id,
            description=f"{DESC} × {qty}",
            square_footage=Decimal(SF),
            thickness_in=Decimal("4"),
            sand_thickness_in=Decimal("2"),
            perimeter_edge_lf=Decimal(PERIMETER),
            post_tension=True,
            pt_spacing_in=Decimal("48"),
            wire_mesh=False,
            mix_design_id=ids["mix_id"],
            slab_bar_size=4,
            slab_bar_spacing_in=Decimal("18"),
            qty=qty,
            sort_order=(i + 1) * 10,
        )
        db.add(slab)
        db.flush()
        for type_idx, lf in BEAMS:
            db.add(GradeBeam(mono_slab_id=slab.id, beam_type_id=types[type_idx].id, length_lf=Decimal(lf)))
        db.flush()
        refresh_mono_slab_calcs(db, slab, section)

    db.flush()
    refresh_and_store_forming(db, section.id)
    refresh_and_store_labor(db, section.id)
    refresh_and_store_equipment(db, section.id)
    refresh_pour_costs(db, section)
    db.flush()
    return section


@pytest.fixture
def priced(db, estimate) -> dict:
    ids = mf.price_the_catalog(db)
    from app.services.price_book import pull_prices

    pull_prices(db, estimate.id)
    return ids


@pytest.fixture
def one_row_of_eight(db, estimate, priced) -> EstimateSection:
    return _build(db, estimate, priced, [8])


@pytest.fixture
def eight_rows(db, estimate, priced) -> EstimateSection:
    return _build(db, estimate, priced, [1] * 8)


def _pours(db, sid) -> list[MonoSlab]:
    return list(db.query(MonoSlab).filter_by(section_id=sid).order_by(MonoSlab.sort_order).all())


def _lines(payload) -> dict[str, tuple[Decimal, Decimal]]:
    """code → (quantity, dollars). Equipment stores days and billable units."""
    out = {}
    for ln in payload["lines"]:
        q = ln["qty"] if "qty" in ln else ln["billable_units"]
        out[ln["code"]] = (_dec(q if q is not None else 0), _dec(ln["ext_cost"]))
    return out


# --------------------------------------------------------------------------
# a row at qty 8 is eight rows
# --------------------------------------------------------------------------

# Every total but the row count and the qty itself; the per-SF ratios follow.
QUANTITY_TOTALS = [
    "total_sf", "total_concrete_cy", "total_slab_concrete_cy", "total_gb_concrete_cy",
    "total_edge_concrete_cy", "total_sand_cy", "total_curb_lf", "total_thick_edge_lf",
    "total_stair_tread_lf", "total_stair_concrete_cy", "total_stamped_sf",
    "total_integral_color_cy", "total_acid_etch_sf", "total_demo_lf", "total_slip_form_sf",
    "total_traffic_control_sf", "total_paving_add", "total_slab_bar_lf", "total_slab_bar_lb",
    "total_support_rebar_lb", "total_pt_cable_lb", "total_pt_cable_lf",
    "total_grade_beam_rebar_lb", "total_rebar_lb", "total_poly_slab_sf", "total_poly_gb_sf",
    "total_poly_sf",
]
MONEY_TOTALS = [
    "total_direct_cost", "total_allocated_cost", "total_equip_fuel", "total_tax",
    "total_cost", "total_sale",
]


def test_the_row_carries_eight_buildings(db, one_row_of_eight):
    """The pour's stored figures are the row's totals: eight of everything."""
    (row,) = _pours(db, one_row_of_eight.id)
    assert row.qty == 8
    # 2,942 × 4 / 324 × 1.06 = 38.5002 per building, quantized THEN × 8, so the
    # row is exactly what eight rows would sum to.
    assert _dec(row.calc_slab_concrete_cy) == Decimal("38.5002") * 8
    # Cable LF, slab: 2,942 × 12 / 48 = 735.5 a building
    assert _dec(row.calc_pt_slab_lf) == Decimal("735.500") * 8
    # Support steel: 2,942 × 0.1 lb/SF
    assert _dec(row.calc_support_rebar_lb) == Decimal("294.2") * 8


@pytest.mark.parametrize("field", QUANTITY_TOTALS)
def test_section_quantities_are_identical(db, one_row_of_eight, eight_rows, field):
    a = section_mono_totals(db, one_row_of_eight.id)
    b = section_mono_totals(db, eight_rows.id)
    assert _dec(a[field]) == _dec(b[field]), field


def test_the_row_count_and_the_building_count(db, one_row_of_eight, eight_rows):
    a = section_mono_totals(db, one_row_of_eight.id)
    b = section_mono_totals(db, eight_rows.id)
    assert (a["slab_count"], a["total_qty"]) == (1, 8)
    assert (b["slab_count"], b["total_qty"]) == (8, 8)


def test_the_stored_totals_do_not_double_count(db, one_row_of_eight):
    """
    The section totals sum the stored calc_* columns as they are — a second
    multiply there would be qty squared. One building's slab concrete, × 8.
    """
    t = section_mono_totals(db, one_row_of_eight.id)
    assert _dec(t["total_slab_concrete_cy"]) == Decimal("38.5002") * 8
    assert _dec(t["total_sf"]) == Decimal(SF) * 8


def test_forming_is_identical(db, one_row_of_eight, eight_rows):
    a = load_stored_forming(db, one_row_of_eight.id)
    b = load_stored_forming(db, eight_rows.id)
    assert _lines(a) == _lines(b)
    assert _dec(a["total_ext_cost"]) == _dec(b["total_ext_cost"])
    da = {k: v for k, v in a["drivers"].items() if k != "pour_count"}
    db_ = {k: v for k, v in b["drivers"].items() if k != "pour_count"}
    assert da == db_
    # The perimeter, the drops and the brick ledge all ride the multiplier —
    # the beam lengths under the pour through the join.
    live = estimate_forming_drivers(db, one_row_of_eight.id)
    assert _dec(live["perimeter_lf"]) == Decimal(PERIMETER) * 8
    assert _dec(live["drops_ff"]) == Decimal("41") * 8
    assert _dec(live["ledge_lf"]) == Decimal("60") * 8
    assert _dec(live["ledge_face_sf"]) == (Decimal("60") * Decimal("10") / 12 * 8).quantize(Decimal("0.001"))
    assert _dec(live["mesh_sf"]) == 0


def test_labor_is_identical(db, one_row_of_eight, eight_rows):
    a = load_stored_labor(db, one_row_of_eight.id)
    b = load_stored_labor(db, eight_rows.id)
    assert _lines(a) == _lines(b)
    assert _dec(a["total_cost"]) == _dec(b["total_cost"])
    # Supervision derives from SF: 8 × 2,942 / 16,000 × 7 days, on both.
    assert _dec(a["drivers"]["super_days"]) == _dec(b["drivers"]["super_days"])
    assert _dec(a["drivers"]["total_sf"]) == Decimal(SF) * 8


def test_equipment_is_identical(db, one_row_of_eight, eight_rows):
    a = load_stored_equipment(db, one_row_of_eight.id)
    b = load_stored_equipment(db, eight_rows.id)
    assert _lines(a) == _lines(b)
    assert _dec(a["total_equipment_cost"]) == _dec(b["total_equipment_cost"])
    assert _dec(a["total_contract_cost"]) == _dec(b["total_contract_cost"])


def test_the_material_list_is_identical(db, one_row_of_eight, eight_rows):
    """Concrete, sand, steel, PT cable by the SF, poly, tape — the same buy."""
    a = {ln["key"]: ln for ln in section_material_costs(db, one_row_of_eight)["lines"]}
    b = {ln["key"]: ln for ln in section_material_costs(db, eight_rows)["lines"]}
    assert set(a) == set(b) and {"concrete", "sand", "rebar", "pt", "poly"} <= set(a)
    for key in a:
        assert _dec(a[key]["qty"]) == _dec(b[key]["qty"]), key
        assert abs(_dec(a[key]["cost"]) - _dec(b[key]["cost"])) <= Decimal("0.05"), key
    assert _dec(a["pt"]["qty"]) == Decimal(SF) * 8


@pytest.mark.parametrize("field", MONEY_TOTALS)
def test_the_money_agrees_to_the_cents_eight_roundings_can_move(
    db, one_row_of_eight, eight_rows, field
):
    a = section_mono_totals(db, one_row_of_eight.id)
    b = section_mono_totals(db, eight_rows.id)
    assert abs(_dec(a[field]) - _dec(b[field])) <= CENTS, (field, a[field], b[field])
    assert _dec(a["total_cost"]) > Decimal("50000")  # and it is a real number


def test_the_section_cost_and_the_per_sf(db, one_row_of_eight, eight_rows):
    assert abs(_dec(one_row_of_eight.calc_total_cost) - _dec(eight_rows.calc_total_cost)) <= CENTS
    assert abs(_dec(one_row_of_eight.calc_total_sale) - _dec(eight_rows.calc_total_sale)) <= CENTS
    (row,) = _pours(db, one_row_of_eight.id)
    each = _pours(db, eight_rows.id)[0]
    # The per-SF figures are per square foot of all eight buildings.
    assert abs(_dec(row.calc_cost_per_sf) - _dec(each.calc_cost_per_sf)) <= Decimal("0.0002")
    assert _dec(row.calc_sf_per_cy) == _dec(each.calc_sf_per_cy)


# --------------------------------------------------------------------------
# qty 0 — on the list, in nothing
# --------------------------------------------------------------------------


def test_a_row_at_zero_is_in_no_total(db, estimate, priced):
    with_zero = _build(db, estimate, priced, [0, 1])
    alone = _build(db, estimate, priced, [1])
    a = section_mono_totals(db, with_zero.id)
    b = section_mono_totals(db, alone.id)
    for field in QUANTITY_TOTALS:
        assert _dec(a[field]) == _dec(b[field]), field
    assert (a["slab_count"], a["total_qty"]) == (2, 1)
    assert _lines(load_stored_forming(db, with_zero.id)) == _lines(load_stored_forming(db, alone.id))
    assert _lines(load_stored_labor(db, with_zero.id)) == _lines(load_stored_labor(db, alone.id))
    assert _lines(load_stored_equipment(db, with_zero.id)) == _lines(load_stored_equipment(db, alone.id))
    assert abs(_dec(with_zero.calc_total_cost) - _dec(alone.calc_total_cost)) <= Decimal("0.05")
    zero, _ = _pours(db, with_zero.id)
    assert zero.qty == 0
    assert _dec(zero.calc_concrete_cy) == 0
    assert _dec(zero.calc_cost) == 0


# --------------------------------------------------------------------------
# the endpoints
# --------------------------------------------------------------------------


def test_the_form_sends_a_qty_and_reads_it_back(client, section):
    r = client.post(
        "/api/mono-slabs",
        json={"section_id": str(section.id), "description": "Type A", "square_footage": 9525,
              "thickness_in": 4, "qty": 7},
    )
    assert r.status_code == 201, r.text
    assert r.json()["qty"] == 7
    t = client.get(f"/api/mono-slabs/totals?section_id={section.id}").json()
    assert Decimal(str(t["total_sf"])) == Decimal("9525") * 7
    assert (t["slab_count"], t["total_qty"]) == (1, 7)
    # 9,525 × 4 / 324 × 1.05 = 123.4722 a building (the company 5% waste)
    assert Decimal(str(t["total_slab_concrete_cy"])) == Decimal("123.4722") * 7


def test_a_pour_without_a_qty_is_one(client, section):
    r = client.post(
        "/api/mono-slabs",
        json={"section_id": str(section.id), "square_footage": 1000, "thickness_in": 4},
    )
    assert r.status_code == 201, r.text
    assert r.json()["qty"] == 1


def test_a_blank_qty_reads_as_one_and_a_negative_is_refused(client, section):
    r = client.post(
        "/api/mono-slabs",
        json={"section_id": str(section.id), "square_footage": 1000, "thickness_in": 4, "qty": 3},
    )
    slab_id = r.json()["id"]
    # Clearing the box on the form must not zero a pour priced a moment ago.
    r = client.patch(f"/api/mono-slabs/{slab_id}", json={"qty": None})
    assert r.status_code == 200, r.text
    assert r.json()["qty"] == 1
    r = client.patch(f"/api/mono-slabs/{slab_id}", json={"qty": -1})
    assert r.status_code == 422


def test_the_grid_leaves_a_qty_it_did_not_send_alone(client, section):
    r = client.post(
        "/api/mono-slabs",
        json={"section_id": str(section.id), "square_footage": 1000, "thickness_in": 4, "qty": 5},
    )
    slab_id = r.json()["id"]
    # The paving and sidewalk grids carry no qty column; their saves must not
    # touch it.
    r = client.put(
        "/api/mono-slabs/bulk",
        json={"section_id": str(section.id), "rows": [{"id": slab_id, "square_footage": 1200}]},
    )
    assert r.status_code == 200, r.text
    (row,) = r.json()["rows"]
    assert (row["qty"], Decimal(str(row["square_footage"]))) == (5, Decimal("1200"))
    assert Decimal(str(r.json()["totals"]["total_sf"])) == Decimal("6000")
    # And a grid that does send it, sets it.
    r = client.put(
        "/api/mono-slabs/bulk",
        json={"section_id": str(section.id), "rows": [{"id": slab_id, "qty": 2}]},
    )
    assert r.json()["rows"][0]["qty"] == 2
    assert Decimal(str(r.json()["totals"]["total_sf"])) == Decimal("2400")
