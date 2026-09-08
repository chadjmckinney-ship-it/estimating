"""
The fields the slab, paving, piers and walls SCREENS read, as a contract.

Columns and the deck had one of these (test_columns_ui_contract.py,
test_cip_deck_ui_contract.py); the four older pages — the ones that read the
most fields — had none, and the schema-drop failure they guard has happened
seven times by the tests' own count (audit 2026-09-04, P3 — batch 4,
2026-09-06). `num(undefined)` renders "—" with a 200 on every request.

Deliberately dumb: a list of key names per page, taken from what `app.js`
reaches for — the totals variable of each page (`totals.*`, `pierT.*`,
`wallT.*`), the grid's `f:` fields and its `derived: (r) => r.calc_*` cells,
the pour form and the pour table on the slab page, and the driver keys the
forming, labor and equipment card headers read under that page's kind. It
does not check that a number is right; the golden files do that.

If a card is added to one of these pages, add its driver here.
"""

from __future__ import annotations

import pytest

from app.services.costing import refresh_pour_costs
from tests import mono_slab_fixture as mf
from tests import paving_fixture as pf
from tests import piers_fixture as pif
from tests import walls_fixture as wf
from tests import spot_footings_fixture as sf
from tests import grade_beams_fixture as gbf
from tests import slabs_fixture as rsf
from tests import slab_on_deck_fixture as sodf
from tests import sidewalks_fixture as swf
from tests import panels_fixture as pnf

# What every mono-slab or paving page reads off /api/mono-slabs/totals.
SLAB_TOTALS = {
    "slab_count", "total_concrete_cy", "total_cost", "total_cost_per_sf", "total_curb_lf",
    "total_demo_lf", "total_edge_concrete_cy", "total_gb_concrete_cy", "total_poly_gb_sf",
    "total_poly_sf", "total_poly_slab_sf", "total_pt_cable_lb", "total_pt_cable_lf",
    "total_rebar_lb", "total_sale", "total_sale_per_sf", "total_sand_cy", "total_sf",
    "total_slab_bar_lb", "total_slab_bar_lf", "total_slab_concrete_cy", "total_slip_form_sf",
    "total_support_rebar_lb", "vapor_barrier", "vapor_barrier_source",
}

PAGES = {
    "mono_slab": dict(
        build=mf.build,
        rows="/api/mono-slabs", totals="/api/mono-slabs/totals",
        totals_keys=SLAB_TOTALS,
        # the pour form's fields, then the pour table's calc cells
        row_keys={
            "id", "description", "location", "square_footage", "thickness_in", "sand_thickness_in",
            "perimeter_edge_lf", "mix_design_id", "post_tension", "wire_mesh", "slab_bar_size",
            "slab_bar_spacing_in", "support_rebar_lb_per_sf", "pt_lb_per_sf", "pt_spacing_in", "notes",
            "calc_allocated_cost", "calc_concrete_cy", "calc_cost", "calc_cost_per_sf",
            "calc_direct_cost", "calc_gb_concrete_cy", "calc_grade_beam_rebar_lb", "calc_poly_gb_sf",
            "calc_poly_sf", "calc_poly_slab_sf", "calc_pt_cable_lf", "calc_pt_gb_lf",
            "calc_pt_slab_lf", "calc_sale", "calc_sale_per_sf", "calc_sf_per_cy",
            "calc_slab_bar_lb", "calc_slab_bar_lf", "calc_slab_concrete_cy",
            "calc_support_rebar_lb", "calc_total_rebar_lb",
        },
        nonnull={"calc_concrete_cy", "calc_total_rebar_lb", "calc_cost"},
        forming={"kind", "perimeter_lf", "drops_ff", "form_percent"},
        labor={"total_sf", "drops_ff", "total_rebar_tons", "super_weeks", "super_days"},
        money={"concrete", "rebar"},
    ),
    # A rebar slab (sql/074): the mono page, the mono rows, its own rates.
    "slabs": dict(
        build=rsf.build,
        rows="/api/mono-slabs", totals="/api/mono-slabs/totals",
        totals_keys=SLAB_TOTALS,
        row_keys={
            "id", "description", "location", "square_footage", "thickness_in", "sand_thickness_in",
            "perimeter_edge_lf", "mix_design_id", "post_tension", "wire_mesh", "slab_bar_size",
            "slab_bar_spacing_in", "support_rebar_lb_per_sf", "pt_lb_per_sf", "pt_spacing_in", "notes",
            "calc_allocated_cost", "calc_concrete_cy", "calc_cost", "calc_cost_per_sf",
            "calc_direct_cost", "calc_poly_sf", "calc_sale", "calc_sale_per_sf", "calc_sf_per_cy",
            "calc_slab_bar_lb", "calc_slab_bar_lf", "calc_slab_concrete_cy",
            "calc_support_rebar_lb", "calc_total_rebar_lb",
        },
        nonnull={"calc_concrete_cy", "calc_total_rebar_lb", "calc_cost"},
        forming={"kind", "perimeter_lf", "drops_ff", "form_percent"},
        labor={"total_sf", "drops_ff", "total_rebar_tons", "super_weeks", "super_days"},
        money={"concrete", "rebar", "sand"},
    ),
    # A slab on metal deck (sql/075): the rebar slab's page with a deck's cells.
    "slab_on_deck": dict(
        build=sodf.build,
        rows="/api/mono-slabs", totals="/api/mono-slabs/totals",
        totals_keys=SLAB_TOTALS,
        row_keys={
            "id", "description", "location", "square_footage", "thickness_in", "sand_thickness_in",
            "perimeter_edge_lf", "mix_design_id", "post_tension", "wire_mesh", "slab_bar_size",
            "slab_bar_spacing_in", "support_rebar_lb_per_sf", "pt_lb_per_sf", "pt_spacing_in", "notes",
            "calc_allocated_cost", "calc_concrete_cy", "calc_cost", "calc_cost_per_sf",
            "calc_direct_cost", "calc_poly_sf", "calc_sale", "calc_sale_per_sf", "calc_sf_per_cy",
            "calc_slab_bar_lb", "calc_slab_bar_lf", "calc_slab_concrete_cy",
            "calc_support_rebar_lb", "calc_total_rebar_lb",
        },
        nonnull={"calc_concrete_cy", "calc_total_rebar_lb", "calc_cost"},
        forming={"kind", "perimeter_lf", "drops_ff", "form_percent"},
        labor={"total_sf", "drops_ff", "total_rebar_tons", "super_weeks", "super_days"},
        money={"concrete", "rebar"},
    ),
    "paving": dict(
        build=pf.build,
        rows="/api/mono-slabs", totals="/api/mono-slabs/totals",
        totals_keys=SLAB_TOTALS,
        row_keys={
            "id", "description", "square_footage", "thickness_in", "curb_lf", "thick_edge_lf",
            "mix_design_id", "sand_thickness_in", "slab_bar_size", "slab_bar_spacing_in",
            "mesh_gauge", "demo_lf", "paving_add_per_sf", "slip_form", "traffic_control",
            "calc_concrete_cy", "calc_cost", "calc_edge_concrete_cy", "calc_slab_concrete_cy",
            "calc_total_rebar_lb",
        },
        nonnull={"calc_concrete_cy", "calc_edge_concrete_cy", "calc_cost"},
        forming={"kind", "curb_lf", "construction_joint_lf", "control_joint_lf", "form_percent"},
        labor={"total_sf", "curb_lf", "total_rebar_tons", "super_weeks", "super_days"},
        money={"concrete", "rebar"},
    ),
    # Sidewalks (sql/076): the paving-family grid with finishes, stairs, an edge.
    "sidewalk": dict(
        build=swf.build,
        rows="/api/mono-slabs", totals="/api/mono-slabs/totals",
        totals_keys=SLAB_TOTALS | {
            "total_stair_tread_lf", "total_stair_concrete_cy", "total_stamped_sf",
            "total_integral_color_cy", "total_acid_etch_sf", "total_thick_edge_lf",
        },
        row_keys={
            "id", "description", "square_footage", "thickness_in", "sand_thickness_in", "mix_design_id",
            "thick_edge_lf", "stamped", "integral_color", "acid_etch", "traffic_control",
            "stair_tread_lf", "stair_tread_rise_in", "stair_tread_run_in",
            "slab_bar_size", "slab_bar_spacing_in", "wire_mesh", "mesh_gauge", "demo_lf",
            "calc_concrete_cy", "calc_slab_concrete_cy", "calc_edge_concrete_cy", "calc_stair_concrete_cy",
            "calc_total_rebar_lb", "calc_edge_rebar_lb", "calc_cost", "calc_cost_per_sf",
        },
        nonnull={"calc_concrete_cy", "calc_stair_concrete_cy", "calc_total_rebar_lb", "calc_cost"},
        forming={"kind", "total_sf", "construction_joint_lf", "control_joint_lf"},
        labor={"total_sf", "thick_edge_lf", "stair_tread_lf", "total_rebar_tons", "super_days"},
        money={"concrete", "rebar", "sand"},
    ),
    # Tilt-wall panels (sql/077): a panel type and its count, four openings.
    "panels": dict(
        build=pnf.build,
        rows="/api/panel-types", totals="/api/panel-types/totals",
        totals_keys={
            "type_count", "panel_count", "total_sf", "total_opening_sf", "total_opening_lf",
            "total_perimeter_lf", "total_bottom_lf", "total_concrete_cy", "total_rebar_lb",
            "total_cost", "total_sale", "total_cost_per_unit", "total_sale_per_unit",
            "cost_per_panel", "sale_per_panel",
        },
        row_keys={
            "id", "label", "qty", "mix_design_id", "length_ft", "thickness_in", "top_el_ft", "bot_el_ft",
            "open1_len_ft", "open1_wide_ft", "open2_len_ft", "open2_wide_ft",
            "open3_len_ft", "open3_wide_ft", "open4_len_ft", "open4_wide_ft",
            "horiz_spacing_in", "horiz_size", "horiz_mats", "vert_spacing_in", "vert_size", "vert_mats",
            "edge_bar_count", "edge_bar_size", "corner_bar_count", "corner_bar_size",
            "calc_height_ft", "calc_sf_each", "calc_sf", "calc_opening_sf", "calc_concrete_cy",
            "calc_steel_each_lb", "calc_total_rebar_lb", "calc_cost", "calc_cost_per_panel",
            "calc_sale_per_panel",
        },
        nonnull={"calc_sf", "calc_concrete_cy", "calc_total_rebar_lb", "calc_cost"},
        forming={"kind", "panel_count", "perimeter_lf", "opening_lf", "bottom_lf", "form_percent"},
        labor={"panel_count", "total_sf", "bottom_lf", "total_rebar_tons", "super_days"},
        money={"concrete", "rebar"},
    ),
    "piers": dict(
        build=pif.build,
        rows="/api/pier-groups", totals="/api/pier-groups/totals",
        totals_keys={
            "drill_quote_stale", "drill_source", "group_count", "groups_without_drill_rate",
            "pier_count", "total_bell_concrete_cy", "total_concrete_cy", "total_cost",
            "total_cost_per_unit", "total_dowel_rebar_lb", "total_drill_cost", "total_lf",
            "total_rebar_lb", "total_sale", "total_sale_per_unit", "total_shaft_concrete_cy",
            "total_tie_count", "total_tie_rebar_lb", "total_vert_rebar_lb",
        },
        row_keys={
            "id", "label", "qty", "diameter_in", "base_depth_ft", "rock_penetration_ft",
            "bell_size_in", "mix_design_id", "vert_bars_count", "vert_bars_size", "tie_size",
            "tie_spacing_in", "band_tie_count", "band_spacing_in", "dowels_count", "dowels_size",
            "dowels_length_ft",
            "calc_total_depth_ft", "calc_total_lf", "calc_concrete_cy", "calc_total_rebar_lb",
            "calc_vert_rebar_lb", "calc_tie_rebar_lb", "calc_tie_count", "calc_dowel_rebar_lb",
            "calc_drill_lf_rate", "calc_drill_cost", "calc_cost_per_unit",
        },
        nonnull={"calc_total_lf", "calc_concrete_cy", "calc_total_rebar_lb"},
        forming={"kind", "pier_count", "total_lf", "form_percent"},
        labor={"pier_count", "total_lf", "total_rebar_tons", "super_weeks", "super_days"},
        money={"concrete", "rebar"},
    ),
    "walls_footings": dict(
        build=wf.build,
        rows="/api/wall-runs", totals="/api/wall-runs/totals",
        totals_keys={
            "footing_cost_per_sf", "footing_sale_per_sf", "run_count", "total_backfill_cy",
            "total_concrete_cy", "total_cost", "total_drain_lf", "total_excavate_cy",
            "total_footing_concrete_cy", "total_footing_rebar_lb", "total_footing_sale",
            "total_footing_sf", "total_form_ff", "total_horiz_rebar_lb", "total_length_ft",
            "total_rebar_lb", "total_sale", "total_sand_cy", "total_vert_rebar_lb",
            "total_wall_concrete_cy", "total_wall_sale", "wall_cost_per_ff", "wall_sale_per_ff",
        },
        row_keys={
            "id", "label", "length_ft", "wall_thick_in", "ftg_width_in", "wall_height_in",
            "ftg_thick_in", "backfill", "mix_design_id", "footing_mix_design_id",
            "horiz_spacing_in", "ftg_bot_spacing_in", "horiz_size", "ftg_bot_size", "horiz_mats",
            "vert_spacing_in", "ftg_top_spacing_in", "vert_size", "ftg_top_size", "vert_mats",
            "calc_backfill_cy", "calc_concrete_cy", "calc_drain_lf", "calc_excavate_cy",
            "calc_footing_concrete_cy", "calc_footing_cost", "calc_footing_cost_per_sf",
            "calc_footing_rebar_lb", "calc_footing_sale_per_sf", "calc_footing_sf", "calc_form_ff",
            "calc_horiz_rebar_lb", "calc_lap_rebar_lb", "calc_sand_cy", "calc_total_rebar_lb",
            "calc_vert_rebar_lb", "calc_wall_concrete_cy", "calc_wall_cost", "calc_wall_cost_per_ff",
            "calc_wall_sale_per_ff",
        },
        nonnull={"calc_form_ff", "calc_concrete_cy", "calc_total_rebar_lb", "calc_wall_cost"},
        forming={"kind", "wall_lf", "form_ff", "footing_sf", "form_percent"},
        labor={"wall_lf", "form_ff", "footing_sf", "total_rebar_tons", "super_weeks", "super_days"},
        # the wall and its footing are priced as two concrete lines (sql/040)
        money={"wall_concrete", "footing_concrete", "rebar"},
    ),
    # Spot footings (sql/072): the walls page with the wall left blank — the
    # same rows and totals plus the count, the length of each and the plate.
    "spot_footings": dict(
        build=sf.build,
        rows="/api/wall-runs", totals="/api/wall-runs/totals",
        totals_keys={
            "footing_cost_per_sf", "footing_sale_per_sf", "run_count", "total_backfill_cy",
            "total_concrete_cy", "total_cost", "total_drain_lf", "total_excavate_cy",
            "total_footing_concrete_cy", "total_footing_rebar_lb", "total_footing_sale",
            "total_footing_sf", "total_form_ff", "total_horiz_rebar_lb", "total_length_ft",
            "total_rebar_lb", "total_sale", "total_sand_cy", "total_vert_rebar_lb",
            "total_wall_concrete_cy", "total_wall_sale", "wall_cost_per_ff", "wall_sale_per_ff",
            "footing_count", "weld_plate_count",
        },
        row_keys={
            "id", "label", "length_ft", "wall_thick_in", "ftg_width_in", "wall_height_in",
            "ftg_thick_in", "backfill", "mix_design_id", "footing_mix_design_id",
            "horiz_spacing_in", "ftg_bot_spacing_in", "horiz_size", "ftg_bot_size", "horiz_mats",
            "vert_spacing_in", "ftg_top_spacing_in", "vert_size", "ftg_top_size", "vert_mats",
            "footing_count", "footing_each_ft", "weld_plate",
            "calc_backfill_cy", "calc_concrete_cy", "calc_drain_lf", "calc_excavate_cy",
            "calc_footing_concrete_cy", "calc_footing_cost", "calc_footing_cost_per_sf",
            "calc_footing_rebar_lb", "calc_footing_sale_per_sf", "calc_footing_sf", "calc_form_ff",
            "calc_horiz_rebar_lb", "calc_lap_rebar_lb", "calc_sand_cy", "calc_total_rebar_lb",
            "calc_vert_rebar_lb", "calc_wall_concrete_cy", "calc_wall_cost", "calc_wall_cost_per_ff",
            "calc_wall_sale_per_ff",
        },
        nonnull={"calc_footing_sf", "calc_concrete_cy", "calc_total_rebar_lb", "calc_footing_cost"},
        forming={"kind", "footing_sf"},
        labor={"footing_sf", "total_rebar_tons", "super_days"},
        money={"footing_concrete", "rebar", "weld_plates"},
    ),
    # Separately poured grade beams and continuous footings (sql/073): one row
    # a beam type with a length, two kinds on one engine, sold per LF.
    "grade_beams": dict(
        build=gbf.build,
        rows="/api/beam-runs", totals="/api/beam-runs/totals",
        totals_keys={
            "run_count", "pilaster_count", "total_length_ft", "total_contact_ff", "total_face_ff",
            "total_pilaster_ff", "total_concrete_cy", "total_rebar_lb", "total_excavate_cy",
            "total_backfill_cy", "total_cost", "total_sale", "cost_per_ff", "sale_per_ff",
        },
        row_keys={
            "id", "label", "mix_design_id", "length_ft", "width_in", "height_in",
            "top_bars_count", "top_bars_size", "bottom_bars_count", "bottom_bars_size",
            "mid_bars_count", "mid_bars_size", "stirrup_size", "stirrup_spacing_in",
            "l_bars_size", "l_bars_spacing_in", "l_bars_length_ft",
            "pilaster_count", "pilaster_length_in", "pilaster_width_in",
            "calc_face_ff", "calc_contact_ff", "calc_concrete_cy", "calc_total_rebar_lb",
            "calc_excavate_cy", "calc_backfill_cy", "calc_cost", "calc_sale",
            "calc_cost_per_unit", "calc_sale_per_unit",
        },
        nonnull={"calc_face_ff", "calc_concrete_cy", "calc_total_rebar_lb", "calc_excavate_cy"},
        forming={"kind", "beam_lf", "face_ff", "contact_ff", "form_percent"},
        labor={"beam_lf", "face_ff", "total_rebar_tons", "super_days"},
        money={"concrete", "rebar"},
    ),
    "cont_footings": dict(
        build=gbf.build_footings,
        rows="/api/beam-runs", totals="/api/beam-runs/totals",
        totals_keys={
            "run_count", "pilaster_count", "total_length_ft", "total_contact_ff", "total_face_ff",
            "total_pilaster_ff", "total_concrete_cy", "total_rebar_lb", "total_excavate_cy",
            "total_backfill_cy", "total_cost", "total_sale", "cost_per_ff", "sale_per_ff",
        },
        row_keys={
            "id", "label", "mix_design_id", "length_ft", "width_in", "height_in",
            "top_bars_count", "top_bars_size", "bottom_bars_count", "bottom_bars_size",
            "mid_bars_count", "mid_bars_size", "stirrup_size", "stirrup_spacing_in",
            "l_bars_size", "l_bars_spacing_in", "l_bars_length_ft",
            "pilaster_count", "pilaster_length_in", "pilaster_width_in",
            "calc_face_ff", "calc_contact_ff", "calc_concrete_cy", "calc_total_rebar_lb",
            "calc_excavate_cy", "calc_backfill_cy", "calc_cost", "calc_sale",
            "calc_cost_per_unit", "calc_sale_per_unit",
        },
        nonnull={"calc_face_ff", "calc_concrete_cy", "calc_total_rebar_lb", "calc_excavate_cy"},
        forming={"kind", "beam_lf", "face_ff", "contact_ff", "form_percent"},
        labor={"beam_lf", "face_ff", "total_rebar_tons", "super_days"},
        money={"concrete", "rebar"},
    ),
}

EQUIPMENT_DRIVERS = {"kind", "super_days", "equip_days", "total_concrete_cy"}


@pytest.fixture(params=sorted(PAGES))
def page(request, db, estimate):
    spec = PAGES[request.param]
    s = spec["build"](db, estimate)
    refresh_pour_costs(db, s)
    db.flush()
    return request.param, s, spec


def test_the_totals_payload_has_every_stat_card(client, page):
    kind, s, spec = page
    r = client.get(f"{spec['totals']}?section_id={s.id}")
    assert r.status_code == 200, r.text
    missing = spec["totals_keys"] - set(r.json())
    assert not missing, f"{kind}: stat cards read fields the API does not serve: {sorted(missing)}"


def test_a_grid_row_has_every_column_and_its_derived_cells(client, page):
    kind, s, spec = page
    r = client.get(f"{spec['rows']}?section_id={s.id}")
    assert r.status_code == 200, r.text
    rows = r.json()
    assert rows, f"{kind}: the fixture has rows"
    missing = spec["row_keys"] - set(rows[0])
    assert not missing, f"{kind}: the grid reads fields the API does not serve: {sorted(missing)}"
    for key in spec["nonnull"]:
        assert rows[0][key] is not None, f"{kind}: {key} came back null on a full row"


def test_the_forming_header_has_its_drivers(client, page):
    kind, s, spec = page
    r = client.get(f"/api/sections/{s.id}/forming-materials")
    assert r.status_code == 200, r.text
    d = r.json()["drivers"]
    missing = spec["forming"] - set(d)
    assert not missing, f"{kind}: forming drivers is missing {sorted(missing)}"
    assert d["kind"] == kind


def test_the_labor_header_has_its_drivers(client, page):
    kind, s, spec = page
    r = client.get(f"/api/sections/{s.id}/labor")
    assert r.status_code == 200, r.text
    d = r.json()["drivers"]
    missing = spec["labor"] - set(d)
    assert not missing, f"{kind}: labor drivers is missing {sorted(missing)}"


def test_the_equipment_header_has_its_day_counts(client, page):
    kind, s, spec = page
    r = client.get(f"/api/sections/{s.id}/equipment")
    assert r.status_code == 200, r.text
    d = r.json()["drivers"]
    missing = EQUIPMENT_DRIVERS - set(d)
    assert not missing, f"{kind}: equipment drivers is missing {sorted(missing)}"


def test_the_money_cards_get_their_lines(client, page):
    kind, s, spec = page
    r = client.get(f"/api/sections/{s.id}/material-costs")
    assert r.status_code == 200, r.text
    keys = {ln["key"] for ln in r.json()["lines"]}
    assert spec["money"] <= keys, f"{kind}: {sorted(keys)}"
