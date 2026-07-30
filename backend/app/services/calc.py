"""Refresh mono_slab calculated quantities using locked Postgres functions."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.estimate import Estimate
from app.models.grade_beam import GradeBeam
from app.models.mono_slab import MonoSlab


def _setting_numeric(db: Session, key: str, default: Decimal) -> Decimal:
    row = db.execute(
        text("SELECT value #>> '{}' FROM system_settings WHERE key = :k"),
        {"k": key},
    ).scalar()
    if row is None or row == "":
        return default
    try:
        return Decimal(str(row).strip().strip('"'))
    except Exception:
        return default


def _waste(estimate: Estimate, db: Session, field: str, setting_key: str) -> Decimal:
    val = getattr(estimate, field, None)
    if val is not None:
        return Decimal(str(val))
    return _setting_numeric(db, setting_key, Decimal("0"))


def _apply_beam_rebar_and_cy(
    db: Session,
    beam: Any,
    waste_concrete: Decimal | None = None,
    *,
    include_pt_cables: bool = False,
) -> Any:
    """Shared rebar + concrete CY for mono-slab grade beams / exposed / drops."""
    total = Decimal("0")

    for count, size in (
        (beam.top_bars_count, beam.top_bars_size),
        (beam.bottom_bars_count, beam.bottom_bars_size),
        (beam.mid_bars_count, beam.mid_bars_size),
    ):
        if count and size:
            lb = db.execute(
                text(
                    "SELECT calc_long_bar_lb(CAST(:n AS integer), CAST(:sz AS smallint), CAST(:lf AS numeric))"
                ),
                {"n": int(count), "sz": int(size), "lf": beam.length_lf},
            ).scalar()
            total += Decimal(str(lb or 0))

    if beam.stirrup_size and beam.stirrup_spacing_in:
        lb = db.execute(
            text(
                "SELECT calc_stirrup_lb(CAST(:w AS numeric), CAST(:h AS numeric), "
                "CAST(:lf AS numeric), CAST(:sz AS smallint), CAST(:sp AS numeric))"
            ),
            {
                "w": beam.width_in,
                "h": beam.height_in,
                "lf": beam.length_lf,
                "sz": int(beam.stirrup_size),
                "sp": beam.stirrup_spacing_in,
            },
        ).scalar()
        total += Decimal(str(lb or 0))

    if beam.l_bars_count and beam.l_bars_size:
        lb = db.execute(
            text(
                "SELECT calc_long_bar_lb(CAST(:n AS integer), CAST(:sz AS smallint), CAST(:lf AS numeric))"
            ),
            {
                "n": int(beam.l_bars_count),
                "sz": int(beam.l_bars_size),
                "lf": beam.length_lf,
            },
        ).scalar()
        total += Decimal(str(lb or 0))

    beam.calc_rebar_lb = total.quantize(Decimal("0.001"))

    if include_pt_cables:
        pt_count = getattr(beam, "pt_cables_count", None)
        if pt_count and beam.length_lf is not None:
            beam.calc_pt_cable_lf = (
                Decimal(str(pt_count)) * Decimal(str(beam.length_lf))
            ).quantize(Decimal("0.001"))
        else:
            beam.calc_pt_cable_lf = Decimal("0")

    if waste_concrete is None:
        waste_concrete = Decimal("0")
    w = Decimal(str(beam.width_in))
    h = Decimal(str(beam.height_in))
    lf = Decimal(str(beam.length_lf))
    raw_cy = (w * h * lf) / (Decimal("144") * Decimal("27"))
    beam.calc_concrete_cy = (
        raw_cy * (Decimal("1") + Decimal(str(waste_concrete)))
    ).quantize(Decimal("0.0001"))

    # Poly / Stego wrap (Excel): two sides only = (2 × H / 12) × L
    poly = db.execute(
        text(
            "SELECT calc_poly_beam_sf(CAST(:w AS numeric), CAST(:h AS numeric), CAST(:lf AS numeric))"
        ),
        {"w": beam.width_in, "h": beam.height_in, "lf": beam.length_lf},
    ).scalar()
    if hasattr(beam, "calc_poly_sf"):
        beam.calc_poly_sf = (
            Decimal(str(poly)).quantize(Decimal("0.001")) if poly is not None else None
        )

    return beam


def refresh_grade_beam_calcs(
    db: Session,
    beam: GradeBeam,
    waste_concrete: Decimal | None = None,
) -> GradeBeam:
    """
    Rebar lb, concrete CY, and (grade_beam only) PT LF.
    Exposed GBs and drops use the same bar schedule; no PT cables.
    """
    kind = getattr(beam, "kind", None) or "grade_beam"
    include_pt = kind == "grade_beam"
    if not include_pt:
        # clear any leftover PT if kind changed
        if hasattr(beam, "pt_cables_count"):
            beam.pt_cables_count = None
    return _apply_beam_rebar_and_cy(
        db, beam, waste_concrete, include_pt_cables=include_pt
    )


def refresh_mono_slab_calcs(db: Session, slab: MonoSlab, estimate: Estimate | None = None) -> MonoSlab:
    """Populate slab.calc_* from locked SQL helpers + grade beam sum."""
    if estimate is None:
        estimate = db.get(Estimate, slab.estimate_id)
    if estimate is None:
        raise ValueError("estimate not found for mono slab")

    waste_c = _waste(estimate, db, "waste_concrete", "waste_concrete")
    waste_s = _waste(estimate, db, "waste_sand", "waste_sand")
    waste_poly = _setting_numeric(db, "waste_poly", Decimal("0.10"))
    # Per-pour rate overrides for SOG rebar / PT (lb/SF); else system defaults
    sys_support = _setting_numeric(db, "support_rebar_lb_per_sf", Decimal("0.1"))
    sys_pt = _setting_numeric(db, "pt_lb_per_sf", Decimal("1.0"))
    support_rate = (
        Decimal(str(slab.support_rebar_lb_per_sf))
        if slab.support_rebar_lb_per_sf is not None
        else sys_support
    )
    pt_rate = (
        Decimal(str(slab.pt_lb_per_sf)) if slab.pt_lb_per_sf is not None else sys_pt
    )

    sf = slab.square_footage
    thk = slab.thickness_in
    sand_thk = slab.sand_thickness_in

    # SOG slab concrete only
    slab.calc_slab_concrete_cy = db.execute(
        text("SELECT calc_concrete_cy(:sf, :thk, :w)"),
        {"sf": sf, "thk": thk, "w": waste_c},
    ).scalar()

    if sand_thk is not None:
        slab.calc_sand_cy = db.execute(
            text("SELECT calc_sand_cy(:sf, :sand, :w)"),
            {"sf": sf, "sand": sand_thk, "w": waste_s},
        ).scalar()
    else:
        slab.calc_sand_cy = None

    # Slab mat from bar size + spacing (each way). waste_rebar carries the lap
    # allowance; applied to the mat only, not to support or beam steel.
    waste_r = _waste(estimate, db, "waste_rebar", "waste_rebar")
    if slab.slab_bar_size and slab.slab_bar_spacing_in:
        slab.calc_slab_bar_lf = db.execute(
            text(
                "SELECT calc_slab_mat_rebar_lf(CAST(:sf AS numeric), CAST(:sp AS numeric))"
            ),
            {"sf": sf, "sp": slab.slab_bar_spacing_in},
        ).scalar()
        slab.calc_slab_bar_lb = db.execute(
            text(
                "SELECT calc_slab_mat_rebar_lb(CAST(:sf AS numeric), CAST(:sz AS smallint), "
                "CAST(:sp AS numeric), CAST(:w AS numeric))"
            ),
            {
                "sf": sf,
                "sz": int(slab.slab_bar_size),
                "sp": slab.slab_bar_spacing_in,
                "w": waste_r,
            },
        ).scalar()
    else:
        slab.calc_slab_bar_lf = Decimal("0")
        slab.calc_slab_bar_lb = Decimal("0")

    slab.calc_support_rebar_lb = db.execute(
        text(
            "SELECT calc_support_rebar_lb(CAST(:sf AS numeric), CAST(:rate AS numeric))"
        ),
        {"sf": sf, "rate": support_rate},
    ).scalar()

    # Legacy PT weight method (lb): SF × lb/SF when PT
    slab.calc_pt_cable_lb = db.execute(
        text(
            "SELECT calc_pt_cable_lb(CAST(:sf AS numeric), CAST(:pt AS boolean), CAST(:rate AS numeric))"
        ),
        {"sf": sf, "pt": bool(slab.post_tension), "rate": pt_rate},
    ).scalar()

    # PT cable LF — primary quantity method
    # Slab (one-way): SF / (spacing_ft) = SF × 12 / spacing_in
    if slab.post_tension and slab.pt_spacing_in and Decimal(str(slab.pt_spacing_in)) > 0:
        spacing = Decimal(str(slab.pt_spacing_in))
        slab.calc_pt_slab_lf = (
            Decimal(str(sf)) * Decimal("12") / spacing
        ).quantize(Decimal("0.001"))
    else:
        slab.calc_pt_slab_lf = Decimal("0") if slab.post_tension else Decimal("0")

    # Refresh each GB with current waste so CY stays in sync
    from sqlalchemy import select

    beams = list(
        db.scalars(select(GradeBeam).where(GradeBeam.mono_slab_id == slab.id)).all()
    )
    for beam in beams:
        refresh_grade_beam_calcs(db, beam, waste_concrete=waste_c)
    if beams:
        db.flush()

    # All kinds (grade_beam + exposed + drop) share the same CY/rebar/poly rules and
    # roll into the pour. Forming/labor for Exp & Drops is separate (cost sheet).
    gb = db.execute(
        text(
            """
            SELECT
              coalesce(sum(calc_rebar_lb), 0) AS rebar_lb,
              coalesce(sum(calc_pt_cable_lf), 0) AS pt_lf,
              coalesce(sum(calc_concrete_cy), 0) AS concrete_cy,
              coalesce(sum(calc_poly_sf), 0) AS poly_sf,
              coalesce(sum(calc_rebar_lb) FILTER (WHERE kind = 'grade_beam'), 0) AS gb_rebar_lb,
              coalesce(sum(calc_rebar_lb) FILTER (WHERE kind = 'exposed'), 0) AS exposed_rebar_lb,
              coalesce(sum(calc_rebar_lb) FILTER (WHERE kind = 'drop'), 0) AS drop_rebar_lb,
              coalesce(sum(calc_concrete_cy) FILTER (WHERE kind = 'grade_beam'), 0) AS gb_cy,
              coalesce(sum(calc_concrete_cy) FILTER (WHERE kind = 'exposed'), 0) AS exposed_cy,
              coalesce(sum(calc_concrete_cy) FILTER (WHERE kind = 'drop'), 0) AS drop_cy,
              coalesce(sum(calc_poly_sf) FILTER (WHERE kind = 'grade_beam'), 0) AS gb_poly,
              coalesce(sum(calc_poly_sf) FILTER (WHERE kind = 'exposed'), 0) AS exposed_poly,
              coalesce(sum(calc_poly_sf) FILTER (WHERE kind = 'drop'), 0) AS drop_poly,
              coalesce(sum(length_lf) FILTER (WHERE kind = 'grade_beam'), 0) AS gb_lf,
              coalesce(sum(length_lf) FILTER (WHERE kind = 'exposed'), 0) AS exposed_lf,
              coalesce(sum(length_lf) FILTER (WHERE kind = 'drop'), 0) AS drop_lf
            FROM grade_beams
            WHERE mono_slab_id = :id
            """
        ),
        {"id": str(slab.id)},
    ).mappings().one()
    # Stored rollups = GBs + exposed + drops (names kept for schema stability)
    slab.calc_grade_beam_rebar_lb = Decimal(str(gb["rebar_lb"] or 0))
    slab.calc_gb_concrete_cy = Decimal(str(gb["concrete_cy"] or 0)).quantize(
        Decimal("0.0001")
    )
    # Only count GB PT when pour is PT (exposed/drops have no PT cables)
    if slab.post_tension:
        slab.calc_pt_gb_lf = Decimal(str(gb["pt_lf"] or 0))
    else:
        slab.calc_pt_gb_lf = Decimal("0")

    slab.calc_pt_cable_lf = (
        Decimal(str(slab.calc_pt_slab_lf or 0)) + Decimal(str(slab.calc_pt_gb_lf or 0))
    ).quantize(Decimal("0.001"))

    # Total pour concrete = SOG slab + all beam kinds (GB + Exp + Drop)
    slab.calc_concrete_cy = (
        Decimal(str(slab.calc_slab_concrete_cy or 0))
        + Decimal(str(slab.calc_gb_concrete_cy or 0))
    ).quantize(Decimal("0.0001"))

    # Slab steel = mat + support; total also picks up GB + Exp + Drop
    support = Decimal(str(slab.calc_support_rebar_lb or 0))
    mat = Decimal(str(slab.calc_slab_bar_lb or 0))
    slab.calc_total_rebar_lb = mat + support + slab.calc_grade_beam_rebar_lb

    # Poly / Stego: pour SF + beam wrap ((2×H)/12 × L), then waste
    slab.calc_poly_slab_sf = Decimal(str(sf)).quantize(Decimal("0.001"))
    slab.calc_poly_gb_sf = Decimal(str(gb["poly_sf"] or 0)).quantize(Decimal("0.001"))
    raw_poly = slab.calc_poly_slab_sf + slab.calc_poly_gb_sf
    slab.calc_poly_sf = (
        raw_poly * (Decimal("1") + waste_poly)
    ).quantize(Decimal("0.001"))

    # Transient breakdown for API (not persisted columns)
    slab._beam_breakdown = {  # type: ignore[attr-defined]
        "grade_beam": {
            "count": None,
            "length_lf": Decimal(str(gb["gb_lf"] or 0)),
            "concrete_cy": Decimal(str(gb["gb_cy"] or 0)).quantize(Decimal("0.0001")),
            "rebar_lb": Decimal(str(gb["gb_rebar_lb"] or 0)),
            "poly_sf": Decimal(str(gb["gb_poly"] or 0)).quantize(Decimal("0.001")),
        },
        "exposed": {
            "length_lf": Decimal(str(gb["exposed_lf"] or 0)),
            "concrete_cy": Decimal(str(gb["exposed_cy"] or 0)).quantize(Decimal("0.0001")),
            "rebar_lb": Decimal(str(gb["exposed_rebar_lb"] or 0)),
            "poly_sf": Decimal(str(gb["exposed_poly"] or 0)).quantize(Decimal("0.001")),
        },
        "drop": {
            "length_lf": Decimal(str(gb["drop_lf"] or 0)),
            "concrete_cy": Decimal(str(gb["drop_cy"] or 0)).quantize(Decimal("0.0001")),
            "rebar_lb": Decimal(str(gb["drop_rebar_lb"] or 0)),
            "poly_sf": Decimal(str(gb["drop_poly"] or 0)).quantize(Decimal("0.001")),
        },
    }

    return slab


def refresh_estimate_slab_calcs(db: Session, estimate: Estimate) -> int:
    """
    Re-run pour calcs for every mono slab on an estimate; returns the count.

    Needed because the calc_* columns are stored, not derived on read: changing
    an estimate-level input (waste_concrete / waste_sand) leaves every pour at
    the factors in force when it was last saved. Caller commits.
    """
    from sqlalchemy import select

    slabs = list(
        db.scalars(select(MonoSlab).where(MonoSlab.estimate_id == estimate.id)).all()
    )
    for slab in slabs:
        refresh_mono_slab_calcs(db, slab, estimate)
    return len(slabs)


def beam_kind_breakdown(db: Session, mono_slab_id: Any) -> dict[str, dict[str, Any]]:
    """Per-kind CY/rebar/LF/poly for a pour (all kinds sum into calc_gb_* totals)."""
    rows = db.execute(
        text(
            """
            SELECT
              kind,
              count(*)::int AS n,
              coalesce(sum(length_lf), 0) AS length_lf,
              coalesce(sum(calc_rebar_lb), 0) AS rebar_lb,
              coalesce(sum(calc_concrete_cy), 0) AS concrete_cy,
              coalesce(sum(calc_poly_sf), 0) AS poly_sf
            FROM grade_beams
            WHERE mono_slab_id = :id
            GROUP BY kind
            """
        ),
        {"id": str(mono_slab_id)},
    ).mappings().all()
    empty = {
        "count": 0,
        "length_lf": Decimal("0"),
        "rebar_lb": Decimal("0"),
        "concrete_cy": Decimal("0"),
        "poly_sf": Decimal("0"),
    }
    out: dict[str, dict[str, Any]] = {
        "grade_beam": dict(empty),
        "exposed": dict(empty),
        "drop": dict(empty),
    }
    for r in rows:
        k = r["kind"] or "grade_beam"
        if k not in out:
            out[k] = dict(empty)
        out[k] = {
            "count": int(r["n"] or 0),
            "length_lf": Decimal(str(r["length_lf"] or 0)),
            "rebar_lb": Decimal(str(r["rebar_lb"] or 0)),
            "concrete_cy": Decimal(str(r["concrete_cy"] or 0)).quantize(
                Decimal("0.0001")
            ),
            "poly_sf": Decimal(str(r["poly_sf"] or 0)).quantize(Decimal("0.001")),
        }
    return out


def estimate_mono_totals(db: Session, estimate_id: Any) -> dict[str, Any]:
    row = db.execute(
        text(
            """
            SELECT
              count(*)::int AS slab_count,
              coalesce(sum(square_footage), 0) AS total_sf,
              coalesce(sum(calc_concrete_cy), 0) AS total_concrete_cy,
              coalesce(sum(calc_slab_concrete_cy), 0) AS total_slab_concrete_cy,
              coalesce(sum(calc_gb_concrete_cy), 0) AS total_gb_concrete_cy,
              coalesce(sum(calc_sand_cy), 0) AS total_sand_cy,
              coalesce(sum(calc_slab_bar_lf), 0) AS total_slab_bar_lf,
              coalesce(sum(calc_slab_bar_lb), 0) AS total_slab_bar_lb,
              coalesce(sum(calc_support_rebar_lb), 0) AS total_support_rebar_lb,
              coalesce(sum(calc_pt_cable_lb), 0) AS total_pt_cable_lb,
              coalesce(sum(calc_pt_cable_lf), 0) AS total_pt_cable_lf,
              coalesce(sum(calc_grade_beam_rebar_lb), 0) AS total_grade_beam_rebar_lb,
              coalesce(sum(calc_total_rebar_lb), 0) AS total_rebar_lb,
              coalesce(sum(calc_poly_slab_sf), 0) AS total_poly_slab_sf,
              coalesce(sum(calc_poly_gb_sf), 0) AS total_poly_gb_sf,
              coalesce(sum(calc_poly_sf), 0) AS total_poly_sf
            FROM mono_slabs
            WHERE estimate_id = :eid
            """
        ),
        {"eid": str(estimate_id)},
    ).mappings().one()
    return dict(row)
