"""
Forming / lumber material quantities, one line set per assembly.

Each sheet in the workbook is its own takeoff. The building-slab sheet forms
off the pour PERIMETER; the paving sheet forms off CURB LF, which is the single
biggest structural difference between them and the reason this module now
dispatches on the section's kind instead of running one set of formulas for
everything.

  MONO SLAB (Excel 04-PT Slab on Grade → LUMBER AND ACCESS)

    2x6 LF        = perimeter_lf × form%
    2x4 LF        = (2x6_LF × 3 + drops_ff) × form%
    2x10 LF       = perimeter_lf × form% × 2
    2x4 bracing   = 3 × drops_ff
    siding sheets = ceil(perimeter_lf × form% × 0.03 / 16)
    forming ply   = drops_ff / 32 × form% × 1.1
    stakes bndls  = round(2x10_LF / 25)
    16p/8p/20p    = ceil(perimeter_lf × 1.25 / 500)
    anchor bolts  = perimeter_lf / 150
    slab chairs   = ceil(total_sf / 15000)
    tie wire      = total_sf / 15000
    accessories   = steel_lb + mesh_sf × 0.75
    slab cure     = ceil(total_sf / 300 / 55)

  PAVING (Excel 10-PAVING, same block; see docs/specs/paving-spec.md)

    2x4 / 2x6 / 2x10 = curb_lf × form%      ← curb, not perimeter
    siding sheets    = ceil(curb_lf × 0.03 / 16)
    stakes bndls     = round(2x10_LF / 25)
    16p              = ceil(curb_lf × 1.25 / 1500)   ← 1500, not 500
    8p, 6p           = ceil(curb_lf × 1.25 / 3000)
    1x6 / 1x8 redwd  = joint LF, split at 8" thickness
    1x1 tack strip   = 1x6 + 1x8
    3/4" dowels      = construction joint LF
    paving chairs    = ceil(total_sf / 15000)
    tie wire         = total_sf / 15000
    accessories      = steel_lb                     ← no mesh term
    cure             = ceil(total_sf / 350 / 55)    ← 350, not 300

Prices come from the catalog. Two things can override that, both visible on the
line as `price_source`: an `<code>_unit_cost` row in assembly_rates, which says
this assembly buys the same item at a different number, and — only when the
catalog has no match at all — the price the workbook types, so a missing
catalog entry shows up as a wrong-looking number rather than as a silent $0.
"""

from __future__ import annotations

import math
import re
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services import paving as pv
from app.models.estimate_section import (
    COLUMN_KINDS,
    DECK_KINDS,
    PAVING_KINDS,
    PIER_KINDS,
    WALL_KINDS,
)
from app.services.calc import (
    _rate_numeric,
    _rate_optional,
    _setting_numeric,
    section_kind,
)
from app.services.price_book import for_section, priced_as, require_book



def _ceil(x: float) -> int:
    return int(math.ceil(x - 1e-12)) if x > 0 else 0


def _round0(x: float) -> int:
    return int(round(x)) if x > 0 else 0


def _d(x: Any) -> Decimal:
    return Decimal(str(x or 0))


def _pier_forming_drivers(db: Session, section_id: UUID, kind: str | None) -> dict[str, Any]:
    """Piers counts nothing by area — its lumber runs off piers, LF and steel."""
    row = db.execute(
        text(
            "SELECT count(*)::int AS n, coalesce(sum(qty), 0)::int AS piers, "
            "       coalesce(sum(calc_total_lf), 0) AS lf, "
            "       coalesce(sum(calc_total_rebar_lb), 0) AS steel, "
            "       coalesce(sum(calc_concrete_cy), 0) AS cy "
            "FROM pier_groups WHERE section_id = :sid"
        ),
        {"sid": str(section_id)},
    ).mappings().one()
    return {
        "section_id": section_id,
        "kind": kind,
        "pour_count": int(row["n"] or 0),
        "pier_count": int(row["piers"] or 0),
        "total_lf": _d(row["lf"]),
        "total_concrete_cy": _d(row["cy"]),
        "total_sf": Decimal("0"),
        "perimeter_lf": Decimal("0"),
        "curb_lf": Decimal("0"),
        "thin_sf": Decimal("0"),
        "thick_sf": Decimal("0"),
        "drops_ff": Decimal("0"),
        "total_rebar_lb": _d(row["steel"]),
        "support_rebar_lb": Decimal("0"),
        "mesh_sf": Decimal("0"),
        "ledge_lf": Decimal("0"),
        "ledge_face_sf": Decimal("0"),
        "construction_joint_lf": Decimal("0"),
        "control_joint_lf": Decimal("0"),
        "form_percent": _rate_numeric(db, kind, "form_percent", Decimal("0.50")),
        "form_percent_is_override": False,
        "form_percent_system_default": _rate_numeric(db, kind, "form_percent", Decimal("0.50")),
        "form_waste": _rate_numeric(db, kind, "form_waste", Decimal("0")),
    }


def _wall_forming_drivers(db: Session, section_id: UUID, kind: str | None) -> dict[str, Any]:
    """
    Walls run off FORM FEET and wall LENGTH, and nothing runs off an area.

    form_ff is one face (sql/040) — the sheet computes both faces and halves
    them. Every $/FF rate in this assembly is priced against that convention.
    """
    row = db.execute(
        text(
            "SELECT count(*)::int AS n, "
            "       coalesce(sum(length_ft), 0) AS lf, "
            "       coalesce(sum(calc_form_ff), 0) AS ff, "
            "       coalesce(sum(calc_footing_sf), 0) AS ftg_sf, "
            "       coalesce(sum(calc_total_rebar_lb), 0) AS steel, "
            "       coalesce(sum(calc_concrete_cy), 0) AS cy, "
            "       coalesce(sum(calc_drain_lf), 0) AS drain "
            "FROM wall_runs WHERE section_id = :sid"
        ),
        {"sid": str(section_id)},
    ).mappings().one()
    form_pct = _rate_numeric(db, kind, "form_percent", Decimal("0.50"))
    return {
        "section_id": section_id,
        "kind": kind,
        "pour_count": int(row["n"] or 0),
        "wall_lf": _d(row["lf"]),
        "form_ff": _d(row["ff"]),
        "footing_sf": _d(row["ftg_sf"]),
        "drain_lf": _d(row["drain"]),
        "total_concrete_cy": _d(row["cy"]),
        "total_rebar_lb": _d(row["steel"]),
        "pier_count": 0,
        "total_lf": Decimal("0"),
        "total_sf": Decimal("0"),
        "perimeter_lf": Decimal("0"),
        "curb_lf": Decimal("0"),
        "thin_sf": Decimal("0"),
        "thick_sf": Decimal("0"),
        "drops_ff": Decimal("0"),
        "support_rebar_lb": Decimal("0"),
        "mesh_sf": Decimal("0"),
        "ledge_lf": Decimal("0"),
        "ledge_face_sf": Decimal("0"),
        "construction_joint_lf": Decimal("0"),
        "control_joint_lf": Decimal("0"),
        "form_percent": form_pct,
        "form_percent_is_override": False,
        "form_percent_system_default": form_pct,
        "form_waste": _rate_numeric(db, kind, "form_waste", Decimal("0")),
    }


def _column_forming_drivers(
    db: Session, section_id: UUID, kind: str | None
) -> dict[str, Any]:
    """
    Columns run off FORM CONTACT AREA and a COUNT. Nothing runs off a length.

    form_sf is all four faces (sql/045), not one — a column is wrapped, where a
    wall is formed on the face you can reach. That difference is why the $/SF
    rates here look small beside the wall sheet's $/FF.
    """
    row = db.execute(
        text(
            "SELECT count(*)::int AS n, "
            "       coalesce(sum(qty), 0)::int AS columns_n, "
            "       coalesce(sum(calc_form_sf), 0) AS form_sf, "
            "       coalesce(sum(calc_total_rebar_lb), 0) AS steel, "
            "       coalesce(sum(calc_concrete_cy), 0) AS cy, "
            "       coalesce(sum(calc_chamfer_lf), 0) AS chamfer "
            "FROM column_types WHERE section_id = :sid"
        ),
        {"sid": str(section_id)},
    ).mappings().one()
    form_pct = _rate_numeric(db, kind, "form_percent", Decimal("0.50"))
    return {
        "section_id": section_id,
        "kind": kind,
        "pour_count": int(row["n"] or 0),
        "column_count": int(row["columns_n"] or 0),
        "form_sf": _d(row["form_sf"]),
        "chamfer_lf": _d(row["chamfer"]),
        "total_concrete_cy": _d(row["cy"]),
        "total_rebar_lb": _d(row["steel"]),
        "pier_count": 0,
        "wall_lf": Decimal("0"),
        "form_ff": Decimal("0"),
        "footing_sf": Decimal("0"),
        "drain_lf": Decimal("0"),
        "total_lf": Decimal("0"),
        "total_sf": _d(row["form_sf"]),
        "perimeter_lf": Decimal("0"),
        "drops_ff": Decimal("0"),
        "ledge_lf": Decimal("0"),
        "curb_lf": Decimal("0"),
        "thick_edge_lf": Decimal("0"),
        "demo_lf": Decimal("0"),
        "construction_joint_lf": Decimal("0"),
        "control_joint_lf": Decimal("0"),
        "poly_sf": Decimal("0"),
        "mesh_sf": Decimal("0"),
        "form_percent": form_pct,
        "form_percent_is_override": False,
        "form_percent_system_default": form_pct,
        "form_waste": _rate_numeric(db, kind, "form_waste", Decimal("0")),
    }


def _deck_forming_drivers(
    db: Session, section_id: UUID, kind: str | None
) -> dict[str, Any]:
    """
    A CIP deck runs off DECK AREA and off `perm edge LF + GB form FF`.

    The second of those is the one to watch: the entire lumber block — 2x4,
    2x6, 2x10, plywood, stakes and both nail lines — rides it, which is why
    doubling the grade beam faces was worth $985.01 of lumber on LBJ on top of
    the $1,440 of GB forming labor (sql/052).
    """
    row = db.execute(
        text(
            "SELECT count(*)::int AS n, "
            "       coalesce(sum(area_sf), 0) AS sf, "
            "       coalesce(sum(perm_edge_lf), 0) AS edge, "
            "       coalesce(sum(mesh_sf), 0) AS mesh, "
            "       coalesce(sum(stud_rail_lb), 0) AS stud, "
            "       coalesce(sum(carton_form_sf), 0) AS carton, "
            "       coalesce(sum(calc_gb_form_ff), 0) AS gb_ff, "
            "       coalesce(sum(calc_total_rebar_lb), 0) AS steel, "
            "       coalesce(sum(calc_concrete_cy), 0) AS cy, "
            "       coalesce(sum(calc_pt_sf), 0) AS pt_sf, "
            "       coalesce(sum(calc_pt_lb), 0) AS pt_lb "
            "FROM deck_levels WHERE section_id = :sid"
        ),
        {"sid": str(section_id)},
    ).mappings().one()
    form_pct = _rate_numeric(db, kind, "form_percent", Decimal("0.50"))
    sf = _d(row["sf"])
    edge = _d(row["edge"])
    gb_ff = _d(row["gb_ff"])
    return {
        "section_id": section_id,
        "kind": kind,
        "pour_count": int(row["n"] or 0),
        "level_count": int(row["n"] or 0),
        "total_sf": sf,
        "perm_edge_lf": edge,
        "gb_form_ff": gb_ff,
        # The one figure the whole lumber block rides.
        "lumber_driver_lf": edge + gb_ff,
        "stud_rail_lb": _d(row["stud"]),
        "carton_form_sf": _d(row["carton"]),
        "pt_sf": _d(row["pt_sf"]),
        "pt_lb": _d(row["pt_lb"]),
        "total_concrete_cy": _d(row["cy"]),
        "total_rebar_lb": _d(row["steel"]),
        "mesh_sf": _d(row["mesh"]),
        "column_count": 0,
        "pier_count": 0,
        "form_sf": Decimal("0"),
        "chamfer_lf": Decimal("0"),
        "wall_lf": Decimal("0"),
        "form_ff": Decimal("0"),
        "footing_sf": Decimal("0"),
        "drain_lf": Decimal("0"),
        "total_lf": Decimal("0"),
        "perimeter_lf": edge,
        "drops_ff": Decimal("0"),
        "ledge_lf": Decimal("0"),
        "curb_lf": Decimal("0"),
        "thick_edge_lf": Decimal("0"),
        "demo_lf": Decimal("0"),
        "construction_joint_lf": Decimal("0"),
        "control_joint_lf": Decimal("0"),
        "poly_sf": Decimal("0"),
        "form_percent": form_pct,
        "form_percent_is_override": False,
        "form_percent_system_default": form_pct,
        "form_waste": _rate_numeric(db, kind, "form_waste", Decimal("0")),
    }


def estimate_forming_drivers(db: Session, section_id: UUID) -> dict[str, Any]:
    """Roll up pour-level drivers used by forming formulas."""
    kind_now = section_kind(db, section_id)
    if kind_now in PIER_KINDS:
        return _pier_forming_drivers(db, section_id, kind_now)
    if kind_now in WALL_KINDS:
        return _wall_forming_drivers(db, section_id, kind_now)
    if kind_now in COLUMN_KINDS:
        return _column_forming_drivers(db, section_id, kind_now)
    if kind_now in DECK_KINDS:
        return _deck_forming_drivers(db, section_id, kind_now)

    row = db.execute(
        text(
            """
            SELECT
              count(*)::int AS pour_count,
              coalesce(sum(square_footage), 0) AS total_sf,
              coalesce(sum(perimeter_edge_lf), 0) AS perimeter_lf,
              -- Drops are grade beams (kind='drop') since sql/022; the flat
              -- mono_slabs.drops_ff column is gone.
              coalesce((
                  SELECT sum(gb.length_lf)
                  FROM grade_beam_details gb
                  JOIN mono_slabs dm ON dm.id = gb.mono_slab_id
                  WHERE dm.section_id = :sid AND gb.kind = 'drop'
              ), 0) AS drops_ff,
              coalesce(sum(calc_total_rebar_lb), 0) AS total_rebar_lb,
              coalesce(sum(calc_support_rebar_lb), 0) AS support_rebar_lb,
              coalesce(sum(CASE WHEN wire_mesh THEN square_footage ELSE 0 END), 0)
                AS mesh_sf,
              -- Paving (sql/036). Curb drives the whole lumber package, and
              -- the thickness split decides 1x6 against 1x8 sealant board.
              coalesce(sum(curb_lf), 0) AS curb_lf,
              coalesce(sum(square_footage) FILTER (WHERE thickness_in <= 8), 0)
                AS thin_sf,
              coalesce(sum(square_footage) FILTER (WHERE thickness_in > 8), 0)
                AS thick_sf,
              -- Brick ledge (sql/028): a 2x6 runs its length and ply faces its
              -- depth, so forming needs both the LF and the face area.
              coalesce((
                  SELECT sum(gb.length_lf)
                  FROM grade_beam_details gb
                  JOIN mono_slabs lm ON lm.id = gb.mono_slab_id
                  WHERE lm.section_id = :sid AND gb.kind = 'brick_ledge'
              ), 0) AS ledge_lf,
              coalesce((
                  SELECT sum(gb.length_lf * coalesce(gb.form_face_in, gb.height_in) / 12.0)
                  FROM grade_beam_details gb
                  JOIN mono_slabs lm ON lm.id = gb.mono_slab_id
                  WHERE lm.section_id = :sid AND gb.kind = 'brick_ledge'
              ), 0) AS ledge_face_sf
            FROM mono_slabs
            WHERE section_id = :sid
            """
        ),
        {"sid": str(section_id)},
    ).mappings().one()

    kind = section_kind(db, section_id)
    # Paving forms 100% of its curb; the slab sheet forms 50% of its perimeter.
    # That is an assembly fact, so it resolves like any other rate (sql/036).
    sys_form = _rate_numeric(db, kind, "form_percent", Decimal("0.50"))
    form_waste = _rate_numeric(db, kind, "form_waste", Decimal("0"))

    # Per-section override (Excel W65); NULL → the assembly / company default
    est_row = db.execute(
        text("SELECT form_percent FROM estimate_sections WHERE id = :sid"),
        {"sid": str(section_id)},
    ).mappings().first()
    est_form = est_row["form_percent"] if est_row else None
    form_pct = _d(est_form) if est_form is not None else sys_form

    joints = pv.joints_for(_d(row["total_sf"]))

    return {
        "section_id": section_id,
        "kind": kind,
        "pour_count": int(row["pour_count"] or 0),
        "total_sf": _d(row["total_sf"]),
        "perimeter_lf": _d(row["perimeter_lf"]),
        "curb_lf": _d(row["curb_lf"]),
        "thin_sf": _d(row["thin_sf"]),
        "thick_sf": _d(row["thick_sf"]),
        "drops_ff": _d(row["drops_ff"]),
        "total_rebar_lb": _d(row["total_rebar_lb"]),
        "support_rebar_lb": _d(row["support_rebar_lb"]),
        "mesh_sf": _d(row["mesh_sf"]),
        "ledge_lf": _d(row["ledge_lf"]),
        "ledge_face_sf": _d(row["ledge_face_sf"]),
        "construction_joint_lf": Decimal(joints.construction_lf),
        "control_joint_lf": Decimal(joints.control_lf),
        "form_percent": form_pct,
        "form_percent_is_override": est_form is not None,
        "form_percent_system_default": sys_form,
        "form_waste": form_waste,
    }


def _find_material(db: Session, *name_parts: str) -> dict[str, Any] | None:
    """
    Best-effort match on materials.name (case-insensitive contains all parts).

    ## Why the ordering has a word-boundary term

    `_find_material(db, "6p")` matched **"16p NAILS DUPLEX"** — `%6p%` is a
    substring, and "1" is just another character. It sorted ahead of the real
    "6p NAILS" on id, so every assembly in the app (slab, paving, piers, walls,
    columns — all five call this with "6p") put 16p nails on its 6p line.

    It cost nothing the day it was found, because all three nail boxes are
    $68.20, and that is exactly what made it invisible: the extension was right,
    the material name beside it was not. The day 6p and 16p diverge, five line
    sets quietly buy the wrong nail.

    The fix RANKS rather than filters, so nothing that resolves today stops
    resolving: a row whose name contains the part at a **word boundary** wins,
    and the old substring behaviour remains as the fallback. `6p` prefers
    "6p NAILS" (boundary: start of string) over "16p NAILS DUPLEX" (preceded by
    a digit), while "2 X 4" and "3/4" keep matching what they always did.

    This is the Yellow Guard's point (sql/030) restated: a price found by name
    search is a price nobody can see, so every resolved item is reported by
    name. That report is what made this visible — the columns forming card
    showed a 6p line labelled "16p NAILS DUPLEX".
    """
    clauses = " AND ".join(f"name ILIKE :p{i}" for i in range(len(name_parts)))
    params = {f"p{i}": f"%{p}%" for i, p in enumerate(name_parts)}
    # `[^0-9a-z]` either side, or a string edge. Postgres `~*` is
    # case-insensitive, and the parts are literals, never patterns.
    boundary = " + ".join(
        f"(CASE WHEN name ~* ('(^|[^0-9a-z])' || :b{i} || '([^0-9a-z]|$)') "
        f"THEN 1 ELSE 0 END)"
        for i in range(len(name_parts))
    )
    params.update({f"b{i}": _regex_quote(p) for i, p in enumerate(name_parts)})
    row = db.execute(
        text(
            f"""
            SELECT id, name, unit, unit_cost, category
            FROM materials
            WHERE coalesce(is_active, true) AND {clauses}
            ORDER BY ({boundary}) DESC, sort_order NULLS LAST, id
            LIMIT 1
            """
        ),
        params,
    ).mappings().first()
    # Priced as THIS JOB pays (sql/048): the name resolves against the catalog,
    # the price comes off the estimate's sheet. See services/price_book.py.
    return require_book(f"material {' '.join(name_parts)!r}").price_material_row(
        dict(row) if row else None
    )


def _regex_quote(s: str) -> str:
    """Escape a catalog fragment so it is matched literally inside a regex."""
    return re.sub(r"([\\^$.|?*+()\[\]{}])", r"\\\1", s)


def _assembly_unit_cost(db: Session, kind: str | None, code: str) -> Decimal | None:
    """
    `<code>_unit_cost` in assembly_rates: this assembly buys it for less.

    Paving accessories are $0.02/lb against the catalog's $0.04, and the paving
    sheet types that rate on the sheet rather than reaching for a second catalog
    item. Only an explicit row counts — there is no company-wide fallback here,
    because a missing row means "this assembly does not differ".
    """
    if not kind:
        return None
    row = db.execute(
        text("SELECT value FROM assembly_rates WHERE kind = :k AND key = :key"),
        {"k": kind, "key": f"{code}_unit_cost"},
    ).scalar()
    return Decimal(str(row)) if row is not None else None


def _line(
    *,
    db: Session,
    kind: str | None,
    code: str,
    label: str,
    qty: Decimal | float | int,
    unit: str,
    formula: str,
    material: dict[str, Any] | None,
    notes: str | None = None,
    form_waste: Decimal = Decimal("0"),
    taxable: bool = True,
    sheet_unit_cost: Decimal | str | float | None = None,
) -> dict[str, Any]:
    q = Decimal(qty) if isinstance(qty, int) else _d(qty).quantize(Decimal("0.001"))

    price_source: str | None = None
    unit_cost: Decimal | None = None

    override = _assembly_unit_cost(db, kind, code)
    if override is not None:
        unit_cost, price_source = override, "assembly"
    elif material:
        # The catalog has this item, so the catalog's answer is the answer —
        # even when that answer is "no price". On a sheeted estimate (sql/048)
        # a row the sheet holds nothing for is UNPRICED and reported as such
        # (decision 5, sql/047: never copied as zero, never silently priced).
        # Until 2026-09-04 this branch only claimed the item when it carried a
        # price, and an unpriced one fell through to the workbook literal
        # below with `price_source="sheet"` and `missing_price=False` — the
        # verdict turned back into a silent number (audit P2 #4).
        if material.get("unit_cost") is not None:
            unit_cost, price_source = _d(material["unit_cost"]), "catalog"
    elif sheet_unit_cost is not None:
        # Nothing in the catalog answers to this item AT ALL. Price it the way
        # the workbook does and say so, rather than quietly extending it at $0
        # — a zero on a real quantity is the kind of hole this project keeps
        # finding months later.
        unit_cost, price_source = Decimal(str(sheet_unit_cost)), "sheet"

    ext = None
    if unit_cost is not None:
        ext = (q * unit_cost * (Decimal("1") + form_waste)).quantize(Decimal("0.01"))

    return {
        "code": code,
        "label": label,
        "qty": q,
        "unit": unit,
        "formula": formula,
        "notes": notes,
        "material_id": material["id"] if material else None,
        "material_name": material["name"] if material else None,
        "unit_cost": unit_cost,
        "ext_cost": ext,
        "price_source": price_source,
        "missing_price": unit_cost is None and q > 0,
        "taxable": taxable,
        "group": "forming",
    }


# --------------------------------------------------------------------------
# mono slab
# --------------------------------------------------------------------------


def _mono_slab_lines(db: Session, d: dict[str, Any]) -> list[dict[str, Any]]:
    kind = d["kind"]
    p = float(d["perimeter_lf"])
    drops = float(d["drops_ff"])
    sf = float(d["total_sf"])
    form_pct = float(d["form_percent"])
    waste = d["form_waste"]
    rebar = float(d["total_rebar_lb"])
    mesh = float(d["mesh_sf"])
    ledge = float(d["ledge_lf"])
    ledge_face = float(d["ledge_face_sf"])

    qty_2x6 = p * form_pct
    qty_2x4 = (qty_2x6 * 3 + drops) * form_pct
    qty_2x10 = p * form_pct * 2
    qty_ply = (drops / 32.0) * form_pct * 1.1 if drops > 0 else 0.0
    qty_ledge_2x6 = ledge * form_pct
    qty_ledge_ply = (ledge_face / 32.0) * form_pct * 1.1 if ledge_face > 0 else 0.0
    qty_siding = _ceil(p * form_pct * 0.03 / 16.0) if p > 0 and form_pct > 0 else 0

    qty_brace = 3.0 * drops
    qty_stakes = _round0(qty_2x10 / 25.0) if qty_2x10 > 0 else 0
    qty_nails = _ceil(p * 1.25 / 500.0) if p > 0 else 0
    qty_anchors = p / 150.0 if p > 0 else 0.0
    qty_chairs = _ceil(sf / 15000.0) if sf > 0 else 0
    qty_tie = sf / 15000.0 if sf > 0 else 0.0
    qty_access = rebar + mesh * 0.75
    qty_cure = _ceil(sf / 300.0 / 55.0) if sf > 0 else 0

    m_2x4 = _find_material(db, "2 X 4")
    m_2x6 = _find_material(db, "2 X 6")
    m_2x10 = _find_material(db, "2 X 10")
    m_ply = _find_material(db, "FORMING PLY")
    m_siding = _find_material(db, "SIDING") or _find_material(db, "MASONITE")
    m_stakes = _find_material(db, "2 x 2", "Stake") or _find_material(db, "2 x 2")
    m_16p = _find_material(db, "16p")
    m_8p = _find_material(db, "8p")
    m_6p = _find_material(db, "6p")
    m_anchor = _find_material(db, "ANCHOR BOLTS 1/2") or _find_material(db, "ANCHOR BOLTS")
    m_keyway = _find_material(db, "KEYWAY")
    m_chamfer = _find_material(db, "CHAMFER")
    m_rw6 = _find_material(db, "1 X 6", "RED")
    m_rw8 = _find_material(db, "1 X 8", "RED")
    m_chairs = _find_material(db, "SLAB CHAIRS")
    m_tie = _find_material(db, "TIE WIRE")
    m_acc = _find_material(db, "ACCESSORIES")
    m_cure = _find_material(db, "SLAB CURE")
    m_release = _find_material(db, "FORM RELEASE")

    def L(**kw: Any) -> dict[str, Any]:
        return _line(db=db, kind=kind, form_waste=waste, **kw)

    return [
        L(code="2x6", label="2 X 6 X 16'", qty=qty_2x6, unit="LF",
          formula="perimeter_lf × form%", material=m_2x6,
          notes="Form lumber — uses form%"),
        L(code="2x4", label="2 X 4 X 16'", qty=qty_2x4, unit="LF",
          formula="(2x6_LF × 3 + drops_ff) × form%", material=m_2x4,
          notes="Form lumber — uses form%"),
        L(code="2x4_brace", label="2 x 4 BRACING", qty=qty_brace, unit="LF",
          formula="3 × drops_ff (not scaled by form%)", material=m_2x4,
          notes="Priced as 2x4; not multiplied by form%"),
        L(code="2x10", label="2 X 10 X 16'", qty=qty_2x10, unit="LF",
          formula="perimeter_lf × form% × 2", material=m_2x10,
          notes="Form lumber — uses form%"),
        L(code="siding", label='3/8" X 12" X 16\' SIDING (masonite)', qty=qty_siding,
          unit="SHEET", formula="ceil(perimeter_lf × form% × 0.03 / 16)",
          material=m_siding, notes="Form material — uses form%"),
        L(code="ply", label='3/4 " FORMING PLY', qty=qty_ply, unit="SHEET",
          formula="drops_ff / 32 × form% × 1.1", material=m_ply,
          notes="Form lumber — uses form%"),
        L(code="ledge_2x6", label="2 X 6 X 16' — brick ledge", qty=qty_ledge_2x6,
          unit="LF", formula="brick_ledge_lf × form%", material=m_2x6,
          notes="Ledge form lumber — uses form%"),
        L(code="ledge_ply", label='3/4 " FORMING PLY — brick ledge face',
          qty=qty_ledge_ply, unit="SHEET",
          formula="ledge face SF / 32 × form% × 1.1", material=m_ply,
          notes="Faces the ledge depth (form_face_in, else the section height)"),
        L(code="stakes", label="2 x 2 x 30 STAKES", qty=qty_stakes, unit="BUNDLE",
          formula="round(2x10_LF / 25) — follows 2x10 qty", material=m_stakes,
          notes="Derived from 2x10 (indirectly follows form%)"),
        L(code="16p", label="16p NAILS DUPLEX", qty=qty_nails, unit="BOX",
          formula="ceil(perimeter_lf × 1.25 / 500)", material=m_16p),
        L(code="8p", label="8p DUPLEX", qty=qty_nails, unit="BOX",
          formula="ceil(perimeter_lf × 1.25 / 500)", material=m_8p),
        L(code="20p", label="20p NAILS", qty=qty_nails, unit="BOX",
          formula="ceil(perimeter_lf × 1.25 / 500)", material=m_16p or m_6p,
          notes="No 20p in catalog — priced as 16p if available"),
        L(code="anchors", label="ANCHOR BOLTS", qty=qty_anchors, unit="BOX",
          formula="perimeter_lf / 150", material=m_anchor),
        L(code="keyway", label="KEYWAY", qty=0, unit="LF",
          formula="manual (Excel often blank)", material=m_keyway,
          notes="Enter job keyway LF when known"),
        L(code="chamfer", label="CHAMFER", qty=0, unit="LF", formula="manual",
          material=m_chamfer),
        L(code="rw6", label="1 X 6 RED WOOD", qty=0, unit="LF", formula="manual",
          material=m_rw6),
        L(code="rw8", label="1 X 8 RED WOOD", qty=0, unit="LF", formula="manual",
          material=m_rw8),
        L(code="chairs", label="SLAB CHAIRS", qty=qty_chairs, unit="BAG",
          formula="ceil(total_sf / 15000)", material=m_chairs),
        L(code="tie_wire", label="TIE WIRE", qty=qty_tie, unit="ROLL",
          formula="total_sf / 15000", material=m_tie),
        L(code="accessories", label="ACCESSORIES", qty=qty_access, unit="LB",
          formula="total_rebar_lb + mesh_sf × 0.75", material=m_acc),
        L(code="cure", label="SLAB CURE", qty=qty_cure, unit="DRUM",
          formula="ceil(total_sf / 300 / 55)", material=m_cure),
        L(code="form_release", label="FORM RELEASE", qty=0, unit="DRUM",
          formula="manual (usually 0 for SOG)", material=m_release),
    ]


# --------------------------------------------------------------------------
# paving
# --------------------------------------------------------------------------


def _paving_lines(db: Session, d: dict[str, Any]) -> list[dict[str, Any]]:
    """
    10-PAVING's lumber block. Every quantity here runs off curb LF, total SF or
    the joint layout — the pour perimeter does not appear in it at all.
    """
    kind = d["kind"]
    curb = float(d["curb_lf"])
    sf = float(d["total_sf"])
    form_pct = float(d["form_percent"])
    waste = d["form_waste"]
    rebar = float(d["total_rebar_lb"])

    # Sealant board splits on slab thickness (hidden columns AT / AU). The
    # sheet's own test is `<8` for the 1x6 and `>8` for the 1x8, which leaves
    # exactly 8" priced as neither; 8" is thin here.
    rw6_lf = pv.joints_for(d["thin_sf"]).construction_lf
    rw8_lf = pv.joints_for(d["thick_sf"]).construction_lf
    joint_lf = int(d["construction_joint_lf"])

    qty_2x4 = curb * form_pct
    qty_2x6 = curb * form_pct
    qty_2x10 = curb * form_pct
    # Siding is the one lumber line the paving sheet does NOT scale by form%:
    # R55 reads ROUNDUP(curb × 0.03 / 16) flat. Left as `× form%` it agreed
    # with the sheet only because this sheet forms 100%.
    qty_siding = _ceil(curb * 0.03 / 16.0) if curb > 0 else 0
    qty_stakes = _round0(qty_2x10 / 25.0) if qty_2x10 > 0 else 0
    qty_16p = _ceil(curb * 1.25 / float(pv.NAILS_16P_LF_PER_BOX)) if curb > 0 else 0
    qty_8p = _ceil(curb * 1.25 / float(pv.NAILS_8P_LF_PER_BOX)) if curb > 0 else 0
    qty_chairs = _ceil(sf / 15000.0) if sf > 0 else 0
    qty_tie = sf / 15000.0 if sf > 0 else 0.0
    qty_cure = pv.cure_drums(d["total_sf"])

    m_2x4 = _find_material(db, "2 X 4")
    m_2x6 = _find_material(db, "2 X 6")
    m_2x8 = _find_material(db, "2 X 8")
    m_2x10 = _find_material(db, "2 X 10")
    m_ply = _find_material(db, "FORMING PLY")
    m_siding = _find_material(db, "SIDING") or _find_material(db, "MASONITE")
    m_stakes = _find_material(db, "2 x 2", "Stake") or _find_material(db, "2 x 2")
    m_16p = _find_material(db, "16p")
    m_8p = _find_material(db, "8p")
    m_6p = _find_material(db, "6p")
    m_anchor = _find_material(db, "ANCHOR BOLTS 1/2") or _find_material(db, "ANCHOR BOLTS")
    m_keyway = _find_material(db, "KEYWAY")
    m_chamfer = _find_material(db, "CHAMFER")
    m_rw6 = _find_material(db, "1 X 6", "RED")
    m_rw8 = _find_material(db, "1 X 8", "RED")
    m_tack = _find_material(db, "TACK STRIP") or _find_material(db, "1 X 1")
    m_comb = _find_material(db, "TEXTURE COMB")
    m_haul = _find_material(db, "CONCRETE HAUL")
    # 3-1/4 by name: the catalog also has a 2-1/4 chair, and it sorts first.
    m_chairs = (
        _find_material(db, "3-1/4", "CHAIR")
        or _find_material(db, "PAVING CHAIR")
        or _find_material(db, "SLAB CHAIRS")
    )
    m_tie = _find_material(db, "TIE WIRE")
    m_acc = _find_material(db, "ACCESSORIES")
    m_baskets = _find_material(db, "DOWEL BASKET")
    # The sheet's line is 3/4" dowels. The catalog carries several diameters,
    # and a bare "smooth dowel" search lands on the 1/2" — so ask for the size.
    m_dowels = _find_material(db, "3/4", "smooth dowel") or _find_material(
        db, "SMOOTH DOWEL"
    )
    m_cure = _find_material(db, "SLAB CURE")
    m_release = _find_material(db, "FORM RELEASE")
    m_rock = _find_material(db, "ROCK")

    def L(**kw: Any) -> dict[str, Any]:
        return _line(db=db, kind=kind, form_waste=waste, **kw)

    return [
        L(code="2x4", label="2 X 4 X 16'", qty=qty_2x4, unit="LF",
          formula="curb_lf × form%", material=m_2x4, sheet_unit_cost="0.859375",
          notes="Paving forms off curb, not perimeter"),
        L(code="2x6", label="2 X 6 X 16'", qty=qty_2x6, unit="LF",
          formula="curb_lf × form%", material=m_2x6, sheet_unit_cost="1.4453125"),
        L(code="2x8", label="2 X 8 X 16'", qty=0, unit="LF",
          formula="manual", material=m_2x8, sheet_unit_cost="1.171875"),
        L(code="2x10", label="2 X 10 X 16'", qty=qty_2x10, unit="LF",
          formula="curb_lf × form%", material=m_2x10, sheet_unit_cost="1.09375"),
        L(code="siding", label='3/8" X 12" X 16\' SIDING', qty=qty_siding, unit="LNGTH",
          formula="ceil(curb_lf × form% × 0.03 / 16)", material=m_siding,
          sheet_unit_cost="20"),
        L(code="ply", label='3/4 " FORMING PLY', qty=0, unit="SHEET",
          formula="manual", material=m_ply, sheet_unit_cost="74.75"),
        L(code="stakes", label="2 x 2 x 30 STAKES", qty=qty_stakes, unit="BUNDLE",
          formula="round(2x10_LF / 25)", material=m_stakes, sheet_unit_cost="24"),
        L(code="16p", label="16p NAILS DUPLEX", qty=qty_16p, unit="BOX",
          formula="ceil(curb_lf × 1.25 / 1500)", material=m_16p,
          sheet_unit_cost="68.2",
          notes="Paving runs three times the curb per box the slab sheet does"),
        L(code="8p", label="8p DUPLEX", qty=qty_8p, unit="BOX",
          formula="ceil(curb_lf × 1.25 / 3000)", material=m_8p, sheet_unit_cost="68.2"),
        L(code="6p", label="6p NAILS", qty=qty_8p, unit="BOX",
          formula="= 8p boxes", material=m_6p, sheet_unit_cost="68.2"),
        L(code="anchors", label="ANCHOR BOLTS", qty=0, unit="BOX",
          formula="manual", material=m_anchor, sheet_unit_cost="45.24"),
        L(code="keyway", label="KEYWAY", qty=0, unit="LF", formula="manual",
          material=m_keyway, sheet_unit_cost="0.95"),
        L(code="chamfer", label="CHAMFER", qty=0, unit="LF", formula="manual",
          material=m_chamfer, sheet_unit_cost="0.25"),
        L(code="rw6", label="1 X 6 RED WOOD", qty=rw6_lf, unit="LF",
          formula='joint LF in areas 8" thick and under', material=m_rw6,
          sheet_unit_cost="1.063125"),
        L(code="rw8", label="1 X 8 RED WOOD", qty=rw8_lf, unit="LF",
          formula='joint LF in areas over 8" thick', material=m_rw8,
          sheet_unit_cost="1.494375",
          notes="The sheet hard-codes this to 0; the thickness split is honoured here"),
        L(code="tack_strip", label="1 X 1 TACK STRIPS", qty=rw6_lf + rw8_lf, unit="LF",
          formula="1x6 + 1x8 redwood", material=m_tack, sheet_unit_cost="0.70875"),
        L(code="texture_comb", label="TEXTURE COMB", qty=0, unit="UNITS",
          formula="manual", material=m_comb),
        L(code="haul_off", label="CONCRETE HAUL OFF", qty=0, unit="LOADS",
          formula="manual", material=m_haul, taxable=False,
          notes="Hauling is a service, not a purchase — not taxed"),
        L(code="chairs", label="3-1/4 PAVING CHAIRS", qty=qty_chairs, unit="BAG",
          formula="ceil(total_sf / 15000)", material=m_chairs, sheet_unit_cost="27"),
        L(code="tie_wire", label="TIE WIRE", qty=qty_tie, unit="ROLL",
          formula="total_sf / 15000", material=m_tie, sheet_unit_cost="37.8"),
        L(code="accessories", label="ACCESSORIES", qty=rebar, unit="LB",
          formula="total steel lb (no mesh term on paving)", material=m_acc,
          sheet_unit_cost="0.02"),
        L(code="dowel_baskets", label="DOWEL BASKETS", qty=0, unit="LF",
          formula="manual", material=m_baskets),
        L(code="smooth_dowels", label='3/4" SMOOTH DOWELS', qty=joint_lf, unit="PCS",
          formula="construction joint LF", material=m_dowels, sheet_unit_cost="1.9",
          notes="The sheet leaves this untaxed; it is a purchased material, so it is taxed here"),
        L(code="cure", label="SLAB CURE", qty=qty_cure, unit="DRUM",
          formula="ceil(total_sf / 350 / 55)", material=m_cure, sheet_unit_cost="567.5",
          notes="Paving cure covers 350 SF/gal against the slab sheet's 300. "
                "The sheet leaves it untaxed; it is taxed here"),
        L(code="form_release", label="FORM RELEASE", qty=0, unit="DRUM",
          formula="manual", material=m_release, sheet_unit_cost="542"),
        L(code="rock", label="ROCK", qty=0, unit="CY", formula="manual",
          material=m_rock, sheet_unit_cost="15"),
    ]


# --------------------------------------------------------------------------


def _pier_lines(db: Session, d: dict[str, Any]) -> list[dict[str, Any]]:
    """
    01-Piers' lumber block. Nothing here runs off a perimeter or an area — the
    drivers are the pier count, the drilled LF and the weight of steel.
    """
    kind = d["kind"]
    n = float(d["pier_count"])
    lf = float(d["total_lf"])
    cy = float(d["total_concrete_cy"])
    steel = float(d["total_rebar_lb"])
    waste = d["form_waste"]

    m_2x4 = _find_material(db, "2 X 4")
    m_2x6 = _find_material(db, "2 X 6")
    m_stakes = _find_material(db, "2 x 2", "Stake") or _find_material(db, "2 x 2")
    m_16p = _find_material(db, "16p")
    m_8p = _find_material(db, "8p")
    m_6p = _find_material(db, "6p")
    m_haul = _find_material(db, "CONCRETE HAUL")
    m_sleds = _find_material(db, "PIER SLED")
    m_boots = _find_material(db, "PIER BOOT")
    m_acc = _find_material(db, "ACCESSORIES")
    m_cure = _find_material(db, "SLAB CURE")
    m_release = _find_material(db, "FORM RELEASE")

    def L(**kw: Any) -> dict[str, Any]:
        return _line(db=db, kind=kind, form_waste=waste, **kw)

    return [
        L(code="2x4", label="2 X 4 X 16'", qty=n * 8, unit="LF",
          formula="piers × 8", material=m_2x4, sheet_unit_cost="0.859375"),
        L(code="2x6", label="2 X 6 X 16'", qty=n * 8, unit="LF",
          formula="= 2x4", material=m_2x6, sheet_unit_cost="1.4453125"),
        L(code="stakes", label="2 x 2 x 30 STAKES", qty=_ceil(n / 12.5), unit="BUNDLE",
          formula="ceil(piers / 12.5)", material=m_stakes, sheet_unit_cost="24"),
        L(code="16p", label="16p NAILS DUPLEX", qty=_ceil(steel / 15000.0), unit="BOX",
          formula="ceil(steel lb / 15000)", material=m_16p, sheet_unit_cost="68.2",
          notes="Driven by the weight of steel, not by any perimeter"),
        L(code="8p", label="8p DUPLEX", qty=_ceil(n / 1600.0), unit="BOX",
          formula="ceil(piers / 1600)", material=m_8p, sheet_unit_cost="68.2"),
        L(code="6p", label="6p NAILS", qty=_ceil(n / 1600.0), unit="BOX",
          formula="= 8p boxes", material=m_6p, sheet_unit_cost="68.2"),
        L(code="haul_off", label="CONCRETE HAUL OFF", qty=cy / 300.0 if cy > 0 else 0,
          unit="LOADS", formula="concrete CY / 300", material=m_haul,
          taxable=False,
          notes="Hauling is a service, not a purchase — not taxed. Separate from "
                "the spoil haul-off, which is priced per CY in contract services"),
        L(code="pier_sleds", label="PIER SLEDS", qty=lf / 8.0 * 3.0, unit="EA",
          formula="drilled LF / 8 × 3", material=m_sleds, sheet_unit_cost="2.75"),
        L(code="pier_boots", label="PIER BOOTS", qty=n * 4, unit="EA",
          formula="piers × 4", material=m_boots, sheet_unit_cost="3.25"),
        L(code="accessories", label="ACCESSORIES", qty=steel, unit="LB",
          formula="total steel lb", material=m_acc, sheet_unit_cost="0.04"),
        L(code="cure", label="SLAB CURE", qty=_ceil(n / 300.0 / 55.0), unit="DRUM",
          formula="ceil(piers / 300 / 55)", material=m_cure, sheet_unit_cost="567.5"),
        L(code="form_release", label="FORM RELEASE", qty=0, unit="DRUM",
          formula="manual", material=m_release, sheet_unit_cost="542"),
    ]


def _column_lines(db: Session, d: dict[str, Any]) -> list[dict[str, Any]]:
    """
    07-COLUMNS' lumber and accessory block (the sheet's hidden W column,
    $22,232.33 — 14% of the section, filed where nobody would look for it).

    Everything runs off FORM CONTACT AREA except the stakes, which run off the
    column count, and the chamfer, which runs off height.

    PLYWOOD is the big line here, and it is the reason columns is not just a
    small wall: 208 sheets against a wall job's handful, because you wrap four
    faces of every column and strip them again.

    CHAMFER counts the columns. The sheet's `S81 = SUM(F10:F53) * 4` sums the
    HEIGHT column across the four column TYPES and never multiplies by
    quantity — 240 LF on a 68-column job where the honest figure is 4,368.
    Same class as the paving bracing range that summed a section-number column
    into a length column. The quantity comes off the takeoff's stored
    calc_chamfer_lf rather than being re-derived here.
    """
    kind = d["kind"]
    sf = float(d["form_sf"])
    n = float(d["column_count"])
    steel = float(d["total_rebar_lb"])
    chamfer = float(d["chamfer_lf"])
    pct = float(d["form_percent"])
    waste = d["form_waste"]

    x4_rate = float(_rate_numeric(db, kind, "lumber_2x4_per_sf", Decimal("1")))
    ply_rate = float(_rate_numeric(db, kind, "lumber_ply_per_sf", Decimal("0.0625")))
    n16 = float(_rate_numeric(db, kind, "nails_16p_per_sf", Decimal("1800")))
    n8 = float(_rate_numeric(db, kind, "nails_8p_per_sf", Decimal("3000")))
    stake_n = float(_rate_numeric(db, kind, "stakes_per_column", Decimal("0.02")))
    rel_sf = float(_rate_numeric(db, kind, "form_release_sf_per_gal", Decimal("300")))
    chair_sf = float(_rate_numeric(db, kind, "chairs_sf_per_bag", Decimal("12000")))

    m_2x4 = _find_material(db, "2 X 4")
    m_ply = _find_material(db, "FORMING PLY") or _find_material(db, "PLY")
    m_stakes = _find_material(db, "2 x 2", "Stake") or _find_material(db, "2 x 2")
    m_16p = _find_material(db, "16p")
    m_8p = _find_material(db, "8p")
    m_6p = _find_material(db, "6p")
    m_chamfer = _find_material(db, "CHAMFER")
    # "SLAB CHAIRS" is the row the line is labelled with, and a real catalog
    # row at $27/bag. Asking for "CHAIRS" alone matched METAL CHAIRS 2.5" at
    # $45 by sort order — the mono slab has always asked for the right one
    # (audit 2026-09-02 #7).
    m_chairs = _find_material(db, "SLAB CHAIRS") or _find_material(db, "CHAIRS")
    m_acc = _find_material(db, "ACCESSORIES")
    m_release = _find_material(db, "FORM RELEASE")

    def L(**kw):
        return _line(db=db, kind=kind, form_waste=waste, **kw)

    return [
        L(code="2x4", label="2 X 4 X 16'", qty=sf * x4_rate * pct, unit="LF",
          formula="form SF × rate × form%", material=m_2x4,
          sheet_unit_cost="0.859375"),
        L(code="ply", label='3/4" FORMING PLY', qty=sf * ply_rate * pct, unit="SHEET",
          formula="form SF / 32 × 2 × form%", material=m_ply,
          sheet_unit_cost="74.75",
          notes="The biggest lumber line on this assembly — it rides the formed "
                "perimeter, so a pilaster's wall side is not in it"),
        L(code="stakes", label="2 x 2 x 30 STAKES", qty=_ceil(n * stake_n),
          unit="BUNDLE", formula="ceil(columns / 2 / 25)", material=m_stakes,
          sheet_unit_cost="24"),
        L(code="16p", label="16p NAILS DUPLEX", qty=_ceil(sf / n16) if n16 else 0,
          unit="BOX", formula="ceil(form SF / 1800)", material=m_16p,
          sheet_unit_cost="68.2"),
        L(code="8p", label="8p DUPLEX", qty=_ceil(sf / n8) if n8 else 0, unit="BOX",
          formula="ceil(form SF / 3000)", material=m_8p, sheet_unit_cost="68.2"),
        L(code="6p", label="6p NAILS", qty=_ceil(sf / n8) if n8 else 0, unit="BOX",
          formula="= 8p boxes", material=m_6p, sheet_unit_cost="68.2"),
        L(code="chamfer", label="CHAMFER", qty=chamfer, unit="LF",
          formula="4 corners × height × qty", material=m_chamfer,
          sheet_unit_cost="0.25",
          notes="The sheet's own formula forgets the column count — 240 LF "
                "against 4,368"),
        L(code="chairs", label="SLAB CHAIRS", qty=_ceil(sf / chair_sf) if chair_sf else 0,
          unit="BAG", formula="ceil(form SF / 12000)", material=m_chairs),
        L(code="accessories", label="ACCESSORIES", qty=steel, unit="LB",
          formula="total steel lb", material=m_acc, sheet_unit_cost="0.02"),
        L(code="form_release", label="FORM RELEASE",
          qty=_ceil(sf / rel_sf / 55.0) if rel_sf else 0, unit="DRUM",
          formula="ceil(form SF / 300 / 55)", material=m_release,
          sheet_unit_cost="542"),
    ]


def _rate_line(
    db: Session,
    *,
    kind: str | None,
    code: str,
    label: str,
    qty: Decimal | float | int,
    unit: str,
    formula: str,
    rate_key: str,
    notes: str | None = None,
    taxable: bool = True,
    multiplier: Decimal = Decimal("1"),
) -> dict[str, Any]:
    """
    A material priced by a RATE rather than by a catalog row.

    Post-tension, stud rails, carton forms, plywood forming and shoring are
    all bought by the square foot of deck; there is no catalog item to resolve
    and no unit cost to look up. The rate is still a PRICE — every key here is
    in MONETARY_KEYS, so it is frozen on the estimate's sheet like any other
    (sql/049) — and `_rate_optional` returns None when nobody has ever said
    what it costs, which is how the deck's blank reshoring rate becomes an
    unpriced line rather than a free one.
    """
    q = _d(qty).quantize(Decimal("0.001"))
    rate = _rate_optional(db, kind, rate_key)
    ext = None if rate is None else (q * rate * multiplier).quantize(Decimal("0.01"))
    return {
        "code": code,
        "label": label,
        "qty": q,
        "unit": unit,
        "formula": formula,
        "notes": notes,
        "material_id": None,
        "material_name": None,
        "unit_cost": rate,
        "ext_cost": ext,
        "price_source": None if rate is None else "rate",
        "missing_price": rate is None and q > 0,
        "taxable": taxable,
        "group": "forming",
    }


def _deck_lines(db: Session, d: dict[str, Any]) -> list[dict[str, Any]]:
    """
    08-CIP EL. DECK: the per-SF material lines (rows 79-84) and the lumber
    block (rows 73-118) that every other assembly also carries.

    Concrete and steel are NOT here — they sit on the level as direct cost,
    the way they sit on a pour, a pier group, a wall run and a column type.

    POST TENSION is NOT here. It is a material bought against the takeoff and
    quotable against it, so it sits on the LEVEL as direct cost the way
    concrete and steel do — see costing._deck_units. Putting it here as well
    would bill it twice, which is exactly what the first draft did.

    Five lines exist on no other assembly, and all five exist because the deck
    hangs in the air:

        STUD RAILS            lb x $1.65        shear reinforcement at columns
        CARTON FORMS          SF x $0.85
        PLYWOOD FORMING       SF x 50% coverage x $1.50
        RESHORING             SF x rate x 1.10  <- the rate is BLANK on the sheet
        FORM RENTAL SHORING   SF x $1.25 x 1.10

    The 1.10 on the last two is ONE CELL on the sheet (`J83`), labelled under
    reshoring and silently reused by form rental shoring — edit it for one
    reason and the other moves $4,300. Two rules here.

    Everything in the lumber block rides `perm edge LF + GB form FF`, not deck
    area. That is the figure the grade beam face count doubles.
    """
    kind = d["kind"]
    sf = float(d["total_sf"])
    edge = float(d["perm_edge_lf"])
    lumber_lf = float(d["lumber_driver_lf"])
    steel = float(d["total_rebar_lb"])
    stud = float(d["stud_rail_lb"])
    pct = float(d["form_percent"])
    waste = d["form_waste"]

    x4 = float(_rate_numeric(db, kind, "lumber_2x4_per_lf", Decimal("1")))
    x6 = float(_rate_numeric(db, kind, "lumber_2x6_per_lf", Decimal("1")))
    x10 = float(_rate_numeric(db, kind, "lumber_2x10_per_lf", Decimal("0.2")))
    ply = float(_rate_numeric(db, kind, "lumber_ply_per_lf", Decimal("0.015625")))
    stake_lf = float(_rate_numeric(db, kind, "stakes_2x10_lf_per_stake", Decimal("25")))
    per_bundle = float(_rate_numeric(db, kind, "stakes_per_bundle", Decimal("2")))
    nail_f = float(_rate_numeric(db, kind, "nails_edge_factor", Decimal("1.25")))
    n16 = float(_rate_numeric(db, kind, "nails_16p_per_sf", Decimal("1500")))
    n8 = float(_rate_numeric(db, kind, "nails_8p_per_sf", Decimal("3000")))
    pave_sf = float(_rate_numeric(db, kind, "pavecrete_sf_per_bag", Decimal("1200")))
    chair_sf = float(_rate_numeric(db, kind, "chairs_sf_per_bag", Decimal("15000")))
    cure_sf = float(_rate_numeric(db, kind, "cure_sf_per_gal", Decimal("300")))
    stud_f = float(
        _rate_numeric(db, kind, "accessories_stud_rail_factor", Decimal("0.75"))
    )
    reshore_m = _rate_numeric(db, kind, "reshoring_multiplier", Decimal("1"))
    rental_m = _rate_numeric(
        db, kind, "form_rental_shoring_multiplier", Decimal("1")
    )

    m_2x4 = _find_material(db, "2 X 4")
    m_2x6 = _find_material(db, "2 X 6")
    m_2x10 = _find_material(db, "2 X 10")
    m_ply = _find_material(db, "FORMING PLY") or _find_material(db, "PLY")
    m_stakes = _find_material(db, "2 x 2", "Stake") or _find_material(db, "2 x 2")
    m_16p = _find_material(db, "16p")
    m_8p = _find_material(db, "8p")
    m_6p = _find_material(db, "6p")
    m_pave = _find_material(db, "PAVECRETE")
    # "SLAB CHAIRS" by name, never "CHAIRS" — asking for the latter matched
    # METAL CHAIRS 2.5" at $45 by sort order on the columns sheet (audit #7).
    m_chairs = _find_material(db, "SLAB CHAIRS")
    m_acc = _find_material(db, "ACCESSORIES")
    m_cure = _find_material(db, "SLAB CURE")
    m_mesh = _find_material(db, "MESH")

    def L(**kw: Any) -> dict[str, Any]:
        return _line(db=db, kind=kind, form_waste=waste, **kw)

    def R(**kw: Any) -> dict[str, Any]:
        return _rate_line(db, kind=kind, **kw)

    return [
        # ------------------------------------------- what only a deck buys --
        R(code="stud_rails", label="STUD RAILS", qty=stud, unit="LB",
          formula="stud rail lb x $/lb", rate_key="stud_rails_lb",
          notes="Shear reinforcement where the deck lands on a column. Zero "
                "on LBJ; kept because Chad asked for it kept."),
        R(code="carton_forms", label="CARTON FORMS", qty=d["carton_form_sf"],
          unit="SF", formula="carton form SF x $/SF", rate_key="carton_forms_sf"),
        R(code="plywood_forming", label="PLYWOOD FORMING",
          qty=sf * pct, unit="SF",
          formula=f"deck SF x {pct:.0%} coverage x $/SF",
          rate_key="plywood_forming_sf"),
        R(code="reshoring", label="RESHORING", qty=sf, unit="SF",
          formula="deck SF x $/SF x multiplier", rate_key="reshoring_material_sf",
          multiplier=reshore_m,
          notes="Every level, not the sheet's hand-picked row list. The "
                "sheet's rate cell (F83) is BLANK, so this line is UNPRICED "
                "rather than free - its labor bills $11,235 on LBJ."),
        R(code="form_rental_shoring", label="FORM RENTAL SHORING", qty=sf,
          unit="SF", formula="deck SF x $/SF x multiplier",
          rate_key="form_rental_shoring_sf", multiplier=rental_m),

        # ---------------------------------------------- the lumber block --
        L(code="2x4", label="2 X 4 X 16'", qty=lumber_lf * x4, unit="LF",
          formula="(perm edge LF + GB form FF) x rate", material=m_2x4,
          sheet_unit_cost="0.859375"),
        L(code="2x6", label="2 X 6 X 16'", qty=lumber_lf * x6, unit="LF",
          formula="= 2x4 LF", material=m_2x6, sheet_unit_cost="1.4453125"),
        L(code="2x10", label="2 X 10 X 16'", qty=lumber_lf * x10, unit="LF",
          formula="(perm edge LF + GB form FF) x 0.2", material=m_2x10,
          sheet_unit_cost="1.09375"),
        L(code="ply", label='3/4" FORMING PLY', qty=lumber_lf * ply, unit="SHEET",
          formula="(perm edge LF + GB form FF) / 64", material=m_ply,
          sheet_unit_cost="74.75"),
        L(code="stakes", label="2 x 2 x 30 STAKES",
          qty=(_round0(lumber_lf * x10 / stake_lf) / per_bundle) if stake_lf and per_bundle else 0,
          unit="BUNDLE", formula="round(2x10 LF / 25) / 2", material=m_stakes,
          sheet_unit_cost="24"),
        L(code="16p", label="16p NAILS DUPLEX",
          qty=_ceil(edge * nail_f / n16) if n16 else 0, unit="BOX",
          formula="ceil(perm edge LF x 1.25 / 1500)", material=m_16p,
          sheet_unit_cost="68.2"),
        L(code="8p", label="8p DUPLEX",
          qty=_ceil(edge * nail_f / n8) if n8 else 0, unit="BOX",
          formula="ceil(perm edge LF x 1.25 / 3000)", material=m_8p,
          sheet_unit_cost="68.2"),
        L(code="6p", label="6p NAILS",
          qty=_ceil(edge * nail_f / n8) if n8 else 0, unit="BOX",
          formula="= 8p boxes", material=m_6p, sheet_unit_cost="68.2"),
        L(code="mesh", label="WIRE MESH", qty=d["mesh_sf"], unit="SF",
          formula="mesh SF entered on the levels", material=m_mesh,
          notes="Zero on LBJ - the mats are the steel here"),
        L(code="pavecrete", label="PAVECRETE",
          qty=(sf / pave_sf) if pave_sf else 0, unit="BAG",
          formula="deck SF / 1200", material=m_pave, sheet_unit_cost="15"),
        L(code="chairs", label="SLAB CHAIRS",
          qty=_ceil(sf / chair_sf) if chair_sf else 0, unit="BAG",
          formula="ceil(deck SF / 15000)", material=m_chairs),
        L(code="accessories", label="ACCESSORIES",
          qty=steel + stud * stud_f, unit="LB",
          formula="total steel lb + stud rail lb x 0.75", material=m_acc,
          sheet_unit_cost="0.02",
          notes="The sheet types $0.02 over a catalog that says $0.04 - the "
                "same cell sql/044 found on paving and columns"),
        L(code="cure", label="SLAB CURE",
          qty=_ceil(sf / cure_sf / 55.0) if cure_sf else 0, unit="DRUM",
          formula="ceil(deck SF / 300 / 55)", material=m_cure,
          sheet_unit_cost="567.5"),
    ]


def _wall_lines(db: Session, d: dict[str, Any]) -> list[dict[str, Any]]:
    """
    06-Walls & Footings' lumber and accessory block.

    Everything runs off FORM FEET or wall LENGTH. Two things here exist on no
    other assembly: wall ties and pipe bracing, which are what holds a formed
    wall together and plumb, and a french drain, which is both a material line
    here and a labor line in the labor set — you buy the pipe and you install
    it, and the sheet carries both.

    Form percent on this assembly is 40%, against the slab's 50%.
    """
    kind = d["kind"]
    ff = float(d["form_ff"])
    lf = float(d["wall_lf"])
    cy = float(d["total_concrete_cy"])
    steel = float(d["total_rebar_lb"])
    drain = float(d["drain_lf"])
    pct = float(d["form_percent"])
    waste = d["form_waste"]

    ply_rate = float(_rate_numeric(db, kind, "lumber_ply_per_ff", Decimal("0.0625")))
    x4_rate = float(_rate_numeric(db, kind, "lumber_2x4_per_ff", Decimal("3.6")))
    tie_ff = float(_rate_numeric(db, kind, "wall_ties_per_ff", Decimal("2.25")))
    cam_rate = float(_rate_numeric(db, kind, "camlocks_per_ff", Decimal("0.55")))
    brace_ff = float(_rate_numeric(db, kind, "pipe_brace_per_ff", Decimal("30")))
    patch_sf = float(_rate_numeric(db, kind, "patch_sf_per_bag", Decimal("350")))

    m_2x4 = _find_material(db, "2 X 4")
    m_2x6 = _find_material(db, "2 X 6")
    m_2x10 = _find_material(db, "2 X 10")
    m_ply = _find_material(db, "FORMING PLY") or _find_material(db, "PLY")
    m_stakes = _find_material(db, "2 x 2", "Stake") or _find_material(db, "2 x 2")
    m_16p = _find_material(db, "16p")
    m_8p = _find_material(db, "8p")
    m_6p = _find_material(db, "6p")
    m_chamfer = _find_material(db, "CHAMFER")
    m_ties = _find_material(db, "WALL TIE")
    m_stop = _find_material(db, "WATER STOP")
    m_drain = _find_material(db, "FRENCH DRAIN")
    m_cam = _find_material(db, "CAMLOCK")
    m_turn = _find_material(db, "TURNBUCKLE")
    m_patch = _find_material(db, "Patch Material") or _find_material(db, "PATCH")
    m_brace = _find_material(db, "PIPE BRACING")
    m_haul = _find_material(db, "CONCRETE HAUL")
    m_acc = _find_material(db, "ACCESSORIES")
    m_cure = _find_material(db, "SLAB CURE")

    def L(**kw: Any) -> dict[str, Any]:
        return _line(db=db, kind=kind, form_waste=waste, **kw)

    return [
        L(code="2x4", label="2 X 4 X 16'", qty=ff * x4_rate * pct, unit="LF",
          formula=f"form FF × {x4_rate} × form%", material=m_2x4,
          sheet_unit_cost="0.859375"),
        L(code="2x6", label="2 X 6 X 16'", qty=ff * x4_rate * pct * 0.2, unit="LF",
          formula="2x4 × 0.20", material=m_2x6, sheet_unit_cost="1.4453125"),
        L(code="2x10", label="2 X 10 X 16'", qty=lf * 2.0 * pct, unit="LF",
          formula="wall LF × 2 × form%", material=m_2x10, sheet_unit_cost="1.09375"),
        L(code="ply", label='3/4" FORMING PLY', qty=_ceil(ff * ply_rate * pct * 1.1),
          unit="SHT", formula="ceil(form FF × 2/32 × form% × 1.1)", material=m_ply,
          sheet_unit_cost="74.75",
          notes="The 1.1 is the sheet's own cutting allowance, on top of form%"),
        L(code="stakes", label="2 x 2 x 30 STAKES", qty=_ceil(lf * 2.0 / 25.0) * pct,
          unit="BUNDLE", formula="ceil(wall LF × 2 / 25) × form%", material=m_stakes,
          sheet_unit_cost="24",
          notes="Rounded up BEFORE form% is applied, which is the sheet's order"),
        L(code="16p", label="16p NAILS DUPLEX", qty=_ceil(ff / 1800.0), unit="BOX",
          formula="ceil(form FF / 1800)", material=m_16p, sheet_unit_cost="68.2"),
        L(code="8p", label="8p DUPLEX", qty=_ceil(ff / 1000.0), unit="BOX",
          formula="ceil(form FF / 1000)", material=m_8p, sheet_unit_cost="68.2"),
        L(code="6p", label="6p NAILS", qty=_ceil(ff / 1000.0), unit="BOX",
          formula="= 8p", material=m_6p, sheet_unit_cost="68.2"),
        L(code="chamfer", label="CHAMFER", qty=lf * 2.0, unit="LF",
          formula="wall LF × 2", material=m_chamfer, sheet_unit_cost="0.25",
          notes="Both top edges of the wall"),
        L(code="wall_ties", label="WALL TIES", qty=ff / tie_ff / 50.0, unit="BOX",
          formula=f"form FF / {tie_ff} / 50", material=m_ties, sheet_unit_cost="45",
          notes="50 to a box; not rounded up, matching the sheet"),
        L(code="water_stop", label="WATER STOP", qty=lf, unit="LF",
          formula="wall LF", material=m_stop, sheet_unit_cost="1.00"),
        L(code="french_drain", label="FRENCH DRAIN", qty=drain, unit="LF",
          formula="LF on runs that are backfilled", material=m_drain,
          sheet_unit_cost="8.50", taxable=False,
          notes="Material only — installing it is a labor line of its own"),
        L(code="camlocks", label="CAMLOCKS", qty=_ceil(ff * cam_rate * pct), unit="EA",
          formula=f"ceil(form FF × {cam_rate} × form%)", material=m_cam,
          sheet_unit_cost="0.45", taxable=False),
        L(code="turnbuckles", label="TURNBUCKLES", qty=lf / 4.0, unit="EA",
          formula="wall LF / 4", material=m_turn, sheet_unit_cost="0.75", taxable=False),
        L(code="patch", label="Patch Material", qty=ff / patch_sf, unit="BAGS",
          formula=f"form FF / {patch_sf}", material=m_patch, sheet_unit_cost="45",
          taxable=False),
        L(code="pipe_brace", label="Pipe Bracing", qty=ff / brace_ff, unit="EA",
          formula=f"form FF / {brace_ff}", material=m_brace,
          taxable=False),
        L(code="haul_off", label="CONCRETE HAUL OFF", qty=cy / 300.0 if cy > 0 else 0,
          unit="LOADS", formula="concrete CY / 300", material=m_haul,
          taxable=False,
          notes="Hauling is a service, not a purchase — not taxed"),
        L(code="accessories", label="ACCESSORIES", qty=steel, unit="LB",
          formula="total steel lb", material=m_acc, sheet_unit_cost="0.04",
          taxable=False),
        L(code="cure", label="SLAB CURE", qty=_ceil(ff / 300.0 / 55.0), unit="DRUM",
          formula="ceil(form FF / 300 / 55)", material=m_cure, sheet_unit_cost="567.5",
          taxable=False),
    ]


def calc_forming_materials(db: Session, section_id: UUID) -> dict[str, Any]:
    """One of the four price gates (sql/048): the whole takeoff prices from the
    estimate's sheet. See services/price_book.py."""
    with priced_as(db, _estimate_id_of(db, section_id)), for_section(section_id):
        return _calc_forming_materials(db, section_id)


def _estimate_id_of(db: Session, section_id: UUID):
    return db.execute(
        text("SELECT estimate_id FROM estimate_sections WHERE id = :i"), {"i": str(section_id)}
    ).scalar()


def _calc_forming_materials(db: Session, section_id: UUID) -> dict[str, Any]:
    """Drivers + material lines for a section, in that assembly's line set."""
    d = estimate_forming_drivers(db, section_id)
    if d["kind"] in PIER_KINDS:
        lines = _pier_lines(db, d)
    elif d["kind"] in WALL_KINDS:
        lines = _wall_lines(db, d)
    elif d["kind"] in COLUMN_KINDS:
        lines = _column_lines(db, d)
    elif d["kind"] in DECK_KINDS:
        lines = _deck_lines(db, d)
    elif d["kind"] in PAVING_KINDS:
        lines = _paving_lines(db, d)
    else:
        lines = _mono_slab_lines(db, d)
    total_ext = sum((ln["ext_cost"] or Decimal("0")) for ln in lines)

    return {
        "drivers": {
            "kind": d["kind"],
            "pour_count": d["pour_count"],
            "total_sf": d["total_sf"],
            "perimeter_lf": d["perimeter_lf"],
            "curb_lf": d["curb_lf"],
            "drops_ff": d["drops_ff"],
            "mesh_sf": d["mesh_sf"],
            "total_rebar_lb": d["total_rebar_lb"],
            "construction_joint_lf": d["construction_joint_lf"],
            "control_joint_lf": d["control_joint_lf"],
            "form_percent": d["form_percent"],
            "form_percent_is_override": d.get("form_percent_is_override", False),
            "form_percent_system_default": d.get("form_percent_system_default"),
            "form_waste": d["form_waste"],
        },
        "lines": lines,
        "total_ext_cost": total_ext.quantize(Decimal("0.01")),
        "missing_prices": [ln["code"] for ln in lines if ln.get("missing_price")],
        "stored": False,
        "refreshed_at": None,
    }


def refresh_and_store_forming(db: Session, section_id: UUID) -> dict[str, Any]:
    """
    Recalculate forming takeoff from pours and persist to
    estimate_forming_lines + estimate_forming_summary.
    Keeps rows marked is_manual (qty/notes) for those codes.

    Lines whose code is no longer in this assembly's set are deleted, so a
    section that changes kind does not keep a stale 20p nail line from the set
    it used to be in.
    """
    from datetime import datetime, timezone

    from sqlalchemy import delete, select

    from app.models.estimate_forming import EstimateFormingLine, EstimateFormingSummary

    data = calc_forming_materials(db, section_id)
    drivers = data["drivers"]
    lines = data["lines"]
    live_codes = {ln["code"] for ln in lines}

    # Preserve manual overrides
    existing = {
        r.code: r
        for r in db.scalars(
            select(EstimateFormingLine).where(
                EstimateFormingLine.section_id == section_id
            )
        ).all()
    }
    manuals = {c: r for c, r in existing.items() if r.is_manual and c in live_codes}
    # A refresh REWRITES quantities; it must not undo a decision (sql/056).
    # Same rule labor and equipment already follow: `enabled = prev.enabled if
    # prev is not None`. Read off the rows before the delete, since the delete
    # is what takes the flag with it.
    was_off = {c for c, r in existing.items() if not r.enabled}

    db.execute(
        delete(EstimateFormingLine).where(
            EstimateFormingLine.section_id == section_id,
            EstimateFormingLine.is_manual.is_(False),
        )
    )
    stale = [c for c in existing if c not in live_codes]
    if stale:
        db.execute(
            delete(EstimateFormingLine).where(
                EstimateFormingLine.section_id == section_id,
                EstimateFormingLine.code.in_(stale),
            )
        )
    db.flush()

    now = datetime.now(timezone.utc)
    stored_lines: list[EstimateFormingLine] = []
    order = 0
    for ln in lines:
        order += 10
        if ln["code"] in manuals:
            # keep manual qty; still refresh cost if unit_cost changed
            m = manuals[ln["code"]]
            if ln.get("unit_cost") is not None:
                m.unit_cost = ln["unit_cost"]
                m.ext_cost = (
                    Decimal("0.00")
                    if not m.enabled
                    else (
                        _d(m.qty)
                        * _d(ln["unit_cost"])
                        * (Decimal("1") + _d(drivers["form_waste"]))
                    ).quantize(Decimal("0.01"))
                )
            m.material_id = ln.get("material_id")
            m.material_name = ln.get("material_name")
            m.formula = ln.get("formula")
            m.label = ln.get("label") or m.label
            m.unit = ln.get("unit") or m.unit
            m.taxable = ln.get("taxable", True)
            m.sort_order = order
            m.updated_at = now
            stored_lines.append(m)
            continue

        on = ln["code"] not in was_off
        row = EstimateFormingLine(
            section_id=section_id,
            code=ln["code"],
            label=ln["label"],
            qty=_d(ln["qty"]),
            unit=ln["unit"],
            formula=ln.get("formula"),
            notes=ln.get("notes"),
            material_id=ln.get("material_id"),
            material_name=ln.get("material_name"),
            unit_cost=ln.get("unit_cost"),
            ext_cost=ln.get("ext_cost") if on else Decimal("0.00"),
            sort_order=order,
            is_manual=False,
            taxable=ln.get("taxable", True),
            enabled=on,
        )
        db.add(row)
        stored_lines.append(row)

    # Recompute total from all lines including manuals
    db.flush()
    all_rows = list(
        db.scalars(
            select(EstimateFormingLine)
            .where(EstimateFormingLine.section_id == section_id)
            .order_by(EstimateFormingLine.sort_order)
        ).all()
    )
    total_ext = sum((_d(r.ext_cost) for r in all_rows), Decimal("0")).quantize(
        Decimal("0.01")
    )

    summary = db.get(EstimateFormingSummary, section_id)
    if summary is None:
        summary = EstimateFormingSummary(section_id=section_id)
        db.add(summary)
    summary.pour_count = int(drivers["pour_count"])
    summary.total_sf = _d(drivers["total_sf"])
    summary.perimeter_lf = _d(drivers["perimeter_lf"])
    summary.drops_ff = _d(drivers["drops_ff"])
    summary.mesh_sf = _d(drivers["mesh_sf"])
    summary.total_rebar_lb = _d(drivers["total_rebar_lb"])
    summary.form_percent = _d(drivers["form_percent"])
    summary.form_waste = _d(drivers["form_waste"])
    summary.total_ext_cost = total_ext
    summary.refreshed_at = now

    from app.services.costing import refresh_pour_costs_for_id
    refresh_pour_costs_for_id(db, section_id)

    db.commit()
    return load_stored_forming(db, section_id)


def set_forming_line_enabled(
    db: Session, section_id: UUID, code: str, enabled: bool
) -> dict[str, Any]:
    """
    Switch one forming line on or off (sql/056).

    Off is a DECISION, and the line says so rather than disappearing: it keeps
    its quantity, its formula and its unit price, extends at $0.00, and stops
    appearing in the section's unpriced list. Deleting it would lose the
    takeoff and the next refresh would put it straight back.

    Chad, 2026-09-04: "that message should go away after I uncheck it as not
    used." This is the box to uncheck — forming was the one takeoff without
    one, which left `RESHORING — forming` asking a question nobody could
    answer.

    No refresh: rewriting the whole line set here would re-derive quantities
    the estimator may have edited, and a checkbox should not move a number it
    was not pointed at. The section's cost IS rebuilt, because the total just
    changed.
    """
    from sqlalchemy import select

    from app.models.estimate_forming import EstimateFormingLine, EstimateFormingSummary

    row = db.scalars(
        select(EstimateFormingLine).where(
            EstimateFormingLine.section_id == section_id,
            EstimateFormingLine.code == code,
        )
    ).first()
    if row is None:
        raise ValueError(f"no forming line {code!r} on this section")

    row.enabled = bool(enabled)
    if not row.enabled:
        row.ext_cost = Decimal("0.00")
    elif row.unit_cost is not None:
        summary = db.get(EstimateFormingSummary, section_id)
        waste = _d(summary.form_waste) if summary else Decimal("0")
        row.ext_cost = (
            _d(row.qty) * _d(row.unit_cost) * (Decimal("1") + waste)
        ).quantize(Decimal("0.01"))
    db.flush()

    summary = db.get(EstimateFormingSummary, section_id)
    if summary is not None:
        summary.total_ext_cost = sum(
            (
                _d(r.ext_cost)
                for r in db.scalars(
                    select(EstimateFormingLine).where(
                        EstimateFormingLine.section_id == section_id
                    )
                ).all()
            ),
            Decimal("0"),
        ).quantize(Decimal("0.01"))

    from app.services.costing import refresh_pour_costs_for_id

    refresh_pour_costs_for_id(db, section_id)
    db.commit()
    return load_stored_forming(db, section_id)


def set_form_percent_and_refresh(
    db: Session, section_id: UUID, form_percent: Decimal
) -> dict[str, Any]:
    """Save form% on the estimate (forms only) and rewrite forming lines."""
    from app.models.estimate_section import EstimateSection

    est = db.get(EstimateSection, section_id)
    if not est:
        raise ValueError("estimate not found")
    est.form_percent = _d(form_percent)
    db.flush()
    return refresh_and_store_forming(db, section_id)


def load_stored_forming(db: Session, section_id: UUID) -> dict[str, Any] | None:
    """Load persisted forming takeoff, or None if never refreshed."""
    from sqlalchemy import select

    from app.models.estimate_forming import EstimateFormingLine, EstimateFormingSummary

    summary = db.get(EstimateFormingSummary, section_id)
    if summary is None:
        return None

    rows = list(
        db.scalars(
            select(EstimateFormingLine)
            .where(EstimateFormingLine.section_id == section_id)
            .order_by(EstimateFormingLine.sort_order, EstimateFormingLine.code)
        ).all()
    )
    lines = [
        {
            "code": r.code,
            "label": r.label,
            "qty": r.qty,
            "unit": r.unit,
            "formula": r.formula or "",
            "notes": r.notes,
            "material_id": r.material_id,
            "material_name": r.material_name,
            "unit_cost": r.unit_cost,
            "ext_cost": r.ext_cost,
            "taxable": r.taxable,
            "group": "forming",
            "is_manual": r.is_manual,
            "enabled": r.enabled,
            # A switched-off line is not missing a price — somebody took it
            # out. Only a LIVE quantity with nothing behind it is a hole.
            "missing_price": r.enabled and r.unit_cost is None and _d(r.qty) > 0,
            "id": str(r.id),
        }
        for r in rows
    ]
    kind = section_kind(db, section_id)
    if kind in DECK_KINDS:
        # The summary table is shaped for pours; a deck's real drivers are
        # levels, deck area and the lumber figure. Serve the live geometry
        # (audit #9) rather than back-filling six summary columns.
        d = _deck_forming_drivers(db, section_id, kind)
        d["pour_count"] = summary.pour_count
        return {
            "drivers": d,
            "lines": lines,
            "total_ext_cost": summary.total_ext_cost,
            "missing_prices": [ln["code"] for ln in lines if ln.get("missing_price")],
            "stored": True,
            "refreshed_at": summary.refreshed_at.isoformat() if summary.refreshed_at else None,
        }
    if kind in COLUMN_KINDS:
        d = _column_forming_drivers(db, section_id, kind)
        d["pour_count"] = summary.pour_count
        return {
            "drivers": d,
            "lines": lines,
            "total_ext_cost": summary.total_ext_cost,
            "missing_prices": [ln["code"] for ln in lines if ln.get("missing_price")],
            "stored": True,
            "refreshed_at": summary.refreshed_at.isoformat() if summary.refreshed_at else None,
        }
    if kind in WALL_KINDS:
        # Same reasoning as piers below: the summary table is shaped for pours.
        d = _wall_forming_drivers(db, section_id, kind)
        d["pour_count"] = summary.pour_count
        return {
            "drivers": d,
            "lines": lines,
            "total_ext_cost": summary.total_ext_cost,
            "missing_prices": [ln["code"] for ln in lines if ln.get("missing_price")],
            "stored": True,
            "refreshed_at": summary.refreshed_at.isoformat() if summary.refreshed_at else None,
        }
    if kind in PIER_KINDS:
        # The summary table is shaped for pours, so the piers drivers are read
        # live. They are stored columns on pier_groups, not derived figures, so
        # they cannot go stale between a refresh and a read.
        d = _pier_forming_drivers(db, section_id, kind)
        d["pour_count"] = summary.pour_count
        return {
            "drivers": d,
            "lines": lines,
            "total_ext_cost": summary.total_ext_cost,
            "missing_prices": [ln["code"] for ln in lines if ln.get("missing_price")],
            "stored": True,
            "refreshed_at": summary.refreshed_at.isoformat() if summary.refreshed_at else None,
        }

    sys_form = _rate_numeric(db, kind, "form_percent", Decimal("0.50"))
    est_row = db.execute(
        text(
            "SELECT form_percent, "
            "  (SELECT coalesce(sum(curb_lf), 0) FROM mono_slabs WHERE section_id = :sid)"
            "    AS curb_lf "
            "FROM estimate_sections WHERE id = :sid"
        ),
        {"sid": str(section_id)},
    ).mappings().first()
    est_form = est_row["form_percent"] if est_row else None
    joints = pv.joints_for(summary.total_sf)

    return {
        "drivers": {
            "kind": kind,
            "pour_count": summary.pour_count,
            "total_sf": summary.total_sf,
            "perimeter_lf": summary.perimeter_lf,
            "curb_lf": _d(est_row["curb_lf"]) if est_row else Decimal("0"),
            "drops_ff": summary.drops_ff,
            "mesh_sf": summary.mesh_sf,
            "total_rebar_lb": summary.total_rebar_lb,
            "construction_joint_lf": Decimal(joints.construction_lf),
            "control_joint_lf": Decimal(joints.control_lf),
            "form_percent": summary.form_percent,
            "form_percent_is_override": est_form is not None,
            "form_percent_system_default": sys_form,
            "form_waste": summary.form_waste,
        },
        "lines": lines,
        "total_ext_cost": summary.total_ext_cost,
        "missing_prices": [ln["code"] for ln in lines if ln.get("missing_price")],
        "stored": True,
        "refreshed_at": summary.refreshed_at.isoformat() if summary.refreshed_at else None,
    }


def get_or_refresh_forming(db: Session, section_id: UUID) -> dict[str, Any]:
    """Return stored forming; if never saved, compute and store."""
    stored = load_stored_forming(db, section_id)
    if stored is not None:
        return stored
    return refresh_and_store_forming(db, section_id)
