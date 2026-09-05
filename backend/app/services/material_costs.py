"""
What each material on a section actually costs — the dollars behind the pounds.

The section screens have always shown quantities at the top: 2,205 CY, 21,945
lb, 158,109 SF of poly. Every one of those is a purchase, and until now the
only dollar figure anywhere near them was the section total. That is the wrong
grain for the question an estimator actually asks, which is "is the steel
number right?" — a question you answer by looking at $/lb and a total, not by
looking at a job total that moves for twenty reasons.

This module is deliberately a READER. It does not price anything new; it
re-walks the same stored quantities, the same catalog resolution and the same
quotes that `costing.py` used to write `calc_direct_cost`, and reports the
pieces. That is why every rate helper here is imported from costing rather than
reimplemented: a breakdown that disagrees with the total it breaks down is
worse than no breakdown at all.

The one thing it cannot promise is exact agreement to the cent.
`_direct_cost` quantizes ONCE PER ROW after summing that row's materials; this
sums each material across every row and quantizes once per material. Those two
roundings differ by a fraction of a cent per row. So the payload carries both
its own total and the stored direct total, and the difference is reported as
`rounding` rather than smeared into a line — a visible half-cent is honest,
and a line silently adjusted to make a sum work is how a real discrepancy hides.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.estimate_section import (
    COLUMN_KINDS,
    DECK_KINDS,
    PIER_KINDS,
    WALL_KINDS,
    EstimateSection,
)
from app.models.mix_design import MixDesign
from app.services import quotes as qt
from app.services.price_book import for_section, priced_as
from app.services.costing import (
    _d,
    _find_material,
    _mesh_unit_cost,
    _mix_unit_cost,
    _z,
    _poly_cost,
    _pt_sf_unit_cost,
    _rebar_unit_cost,
    _sand_unit_cost,
    _setting,
    _tape_cost,
    barrier_rolls,
    resolve_rebar,
    resolve_vapor_barrier,
    resolve_vapor_tape,
)

_Q2 = Decimal("0.01")
_Q4 = Decimal("0.0001")
_ZERO = Decimal("0")


@dataclass
class MaterialLine:
    """
    One purchase on a section, at the grain the stat cards are drawn at.

    `unit_cost` is BLENDED where the rows disagree — two mixes at $150 and $155
    report the weighted average, and `detail` says so. A single averaged rate
    that is labelled as an average beats a card that silently shows the first
    row's price.
    """

    key: str
    label: str
    qty: Decimal
    unit: str
    cost: Decimal
    source: str = "catalog"   # catalog | quote | quote (lump) | rate | unpriced
    detail: str | None = None
    # Items on this line that the catalog has no price for. Non-empty means
    # the cost shown is LIGHT by an unknown amount, the unit cost is withheld,
    # and `source` reads "unpriced" — a NULL price is not a free one.
    unpriced: list[str] = field(default_factory=list)

    @property
    def unit_cost(self) -> Decimal | None:
        if self.qty <= 0 or self.unpriced:
            return None
        return (self.cost / self.qty).quantize(_Q4)

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            # Rolls of tape come out of a division and arrive 25 places long.
            # Four decimals is the finest grain any stored quantity uses
            # (concrete CY), so this rounds the derived figures and leaves
            # every stored one exactly as the takeoff holds it.
            "qty": self.qty.quantize(_Q4),
            "unpriced": list(self.unpriced),
            "unit": self.unit,
            "unit_cost": self.unit_cost,
            "cost": self.cost.quantize(_Q2),
            "source": self.source,
            "detail": self.detail,
        }


@dataclass
class _Acc:
    """Exact accumulation. Quantizing happens once, at the end, per line."""

    qty: Decimal = _ZERO
    cost: Decimal = _ZERO
    names: set[str] = field(default_factory=set)
    # Items that reached this line with NO price. Money still accumulates at
    # zero for them — arithmetic has no other option — but the line says so.
    unpriced: set[str] = field(default_factory=set)

    def add(self, qty: Decimal, cost: Decimal, name: str | None = None) -> None:
        self.qty += qty
        self.cost += cost
        if name:
            self.names.add(name)

    def add_priced(self, qty: Decimal, price: Decimal | None, name: str | None) -> None:
        """
        Add `qty` at `price`, where `price` may be None — UNPRICED, not free.

        A NULL catalog price used to multiply through as zero and vanish into
        the total. Chad: "I dont like concrete prices starting @ $0." Now the
        item is named on the line and the section carries the list.
        """
        if price is None:
            self.unpriced.add(name or "unnamed item")
            self.add(qty, _ZERO, name)
        else:
            self.add(qty, qty * price, name)

    @property
    def live(self) -> bool:
        return self.qty > 0 or self.cost != 0


def _from(acc: "_Acc", key: str, label: str, unit: str, **kw: Any) -> MaterialLine:
    """A line from an accumulator, carrying its unpriced items and saying so."""
    if acc.unpriced:
        kw["source"] = "unpriced"
        names = ", ".join(sorted(acc.unpriced))
        kw["detail"] = f"UNPRICED — {names}"
    return MaterialLine(key, label, acc.qty, unit, acc.cost,
                        unpriced=sorted(acc.unpriced), **kw)


def _blend_note(acc: _Acc, singular: str | None = None) -> str | None:
    """Name the catalog item, or say plainly that the rate shown is a blend."""
    if not acc.names:
        return singular
    if len(acc.names) == 1:
        return next(iter(acc.names))
    return f"blended — {', '.join(sorted(acc.names))}"


def _quote_line(
    key: str, label: str, quote: qt.Quote, qty: Decimal, unit: str
) -> MaterialLine:
    """A LUMP quote, reported at its face value against the takeoff it covers."""
    return MaterialLine(
        key=key,
        label=label,
        qty=qty,
        unit=unit,
        cost=_d(quote.amount),
        source="quote (lump)",
        detail=quote.note or "supplier lump sum",
    )


# ------------------------------------------------------------------ slabs ----


def _slab_lines(db: Session, section: EstimateSection) -> list[MaterialLine]:
    from app.models.mono_slab import MonoSlab

    rows = list(
        db.scalars(
            select(MonoSlab)
            .where(MonoSlab.section_id == section.id)
            .order_by(MonoSlab.sort_order, MonoSlab.created_at)
        ).all()
    )
    barrier = resolve_vapor_barrier(db, section)
    tape = resolve_vapor_tape(db, section)
    tape_ratio = _setting(db, "vapor_tape_rolls_per_barrier_roll", Decimal("0"))
    quotes = qt.load_quotes(db, section.id)
    rebar_q = quotes.get(qt.REBAR)
    pt_q = quotes.get(qt.PT)
    quoted_lb = rebar_q.per_lb() if rebar_q else None
    quoted_sf = pt_q.per_sf() if pt_q else None

    concrete = _Acc()
    sand = _Acc()
    rebar = _Acc()
    pt = _Acc()
    poly = _Acc()
    tape_acc = _Acc()
    mesh = _Acc()

    for r in rows:
        sf = _d(r.square_footage)

        cy = _d(r.calc_concrete_cy)
        if cy > 0:
            mix = db.get(MixDesign, r.mix_design_id) if r.mix_design_id else None
            concrete.add_priced(
                cy,
                _mix_unit_cost(db, r.mix_design_id),
                getattr(mix, "name", None) or getattr(mix, "code", None) or "mix (none chosen)",
            )

        s = _d(r.calc_sand_cy)
        if s > 0:
            sand.add_priced(s, _sand_unit_cost(db), "SAND")

        lb = _d(r.calc_total_rebar_lb)
        if lb > 0 and not (rebar_q and rebar_q.is_lump):
            if quoted_lb is not None:
                rebar.add(lb, lb * quoted_lb)
            else:
                mat = resolve_rebar(db, bool(r.post_tension), section.kind) or {}
                rebar.add_priced(
                    lb,
                    _rebar_unit_cost(db, bool(r.post_tension), section.kind),
                    mat.get("name") or "rebar",
                )
        elif lb > 0:
            rebar.add(lb, _ZERO)   # quantity is real; the money is the lump below

        if r.post_tension and sf > 0:
            if pt_q and pt_q.is_lump:
                pt.add(sf, _ZERO)
            else:
                if quoted_sf is not None:
                    pt.add(sf, sf * quoted_sf)
                else:
                    pt.add_priced(sf, _pt_sf_unit_cost(db), "POST TENSION")

        poly_sf = _d(r.calc_poly_sf)
        if poly_sf > 0:
            poly.add(poly_sf, _poly_cost(db, poly_sf, barrier), (barrier or {}).get("name"))
            rolls = barrier_rolls(poly_sf, barrier) * tape_ratio
            tape_acc.add(rolls, _tape_cost(db, poly_sf, barrier, tape, tape_ratio),
                         (tape or {}).get("name"))

        if r.wire_mesh and sf > 0:
            mesh_mat = _find_material(db, "WIRE MESH", "10") or _find_material(db, "WIRE MESH")
            mesh.add_priced(sf, _mesh_unit_cost(db), (mesh_mat or {}).get("name") or "WIRE MESH")

    lines: list[MaterialLine] = []
    if concrete.live:
        lines.append(_from(concrete, "concrete", "Concrete", "CY", detail=_blend_note(concrete)))
    if sand.live:
        lines.append(_from(sand, "sand", "Sand", "CY",
                                  detail=_blend_note(sand)))
    if rebar.live:
        if rebar_q and rebar_q.is_lump:
            lines.append(_quote_line("rebar", "Rebar", rebar_q, rebar.qty, "LB"))
        else:
            lines.append(_from(rebar, "rebar", "Rebar", "LB",
                source="quote" if quoted_lb is not None else "catalog",
                detail=_blend_note(rebar, "quoted $/lb"),
            ))
    if pt.live:
        if pt_q and pt_q.is_lump:
            lines.append(_quote_line("pt", "Post-tension", pt_q, pt.qty, "SF"))
        else:
            lines.append(_from(pt, "pt", "Post-tension", "SF",
                source="quote" if quoted_sf is not None else "catalog",
                detail=_blend_note(pt, "quoted $/SF"),
            ))
    if poly.live:
        lines.append(_from(poly, "poly", "Vapor barrier", "SF",
                                  detail=_blend_note(poly)))
    if tape_acc.live:
        lines.append(_from(tape_acc, "tape", "Seam tape", "ROLL", detail=_blend_note(tape_acc)))
    if mesh.live:
        lines.append(_from(mesh, "mesh", "Wire mesh", "SF",
                                  detail=_blend_note(mesh)))
    return lines


# ------------------------------------------------------------------ piers ----


def _pier_lines(db: Session, section: EstimateSection) -> list[MaterialLine]:
    from app.models.pier_group import PierGroup

    rows = list(
        db.scalars(
            select(PierGroup)
            .where(PierGroup.section_id == section.id)
            .order_by(PierGroup.sort_order, PierGroup.created_at)
        ).all()
    )
    quotes = qt.load_quotes(db, section.id)
    rebar_q = quotes.get(qt.REBAR)
    drill_q = quotes.get(qt.DRILLING)
    quoted_lb = rebar_q.per_lb() if rebar_q else None

    concrete = _Acc()
    rebar = _Acc()
    drill = _Acc()

    for g in rows:
        cy = _d(g.calc_concrete_cy)
        if cy > 0:
            mix = db.get(MixDesign, g.mix_design_id) if g.mix_design_id else None
            concrete.add_priced(cy, _mix_unit_cost(db, g.mix_design_id),
                                getattr(mix, "name", None) or getattr(mix, "code", None) or "mix (none chosen)")

        lb = _d(g.calc_total_rebar_lb)
        if lb > 0 and not (rebar_q and rebar_q.is_lump):
            if quoted_lb is not None:
                rebar.add(lb, lb * quoted_lb)
            else:
                mat = resolve_rebar(db, False, section.kind) or {}
                rebar.add_priced(lb, _rebar_unit_cost(db, False, section.kind),
                                 mat.get("name") or "rebar")
        elif lb > 0:
            rebar.add(lb, _ZERO)

        drill.add(_d(g.calc_total_lf), _d(g.calc_drill_cost))

    lines: list[MaterialLine] = []
    if concrete.live:
        lines.append(_from(concrete, "concrete", "Concrete", "CY", detail=_blend_note(concrete)))
    if rebar.live:
        if rebar_q and rebar_q.is_lump:
            lines.append(_quote_line("rebar", "Rebar", rebar_q, rebar.qty, "LB"))
        else:
            lines.append(_from(rebar, "rebar", "Rebar", "LB",
                source="quote" if quoted_lb is not None else "catalog",
                detail=_blend_note(rebar, "quoted $/lb"),
            ))
    if drill.live:
        # Drilling is the one line here that is WORK, not a purchase — it is
        # never taxed. It belongs on this list anyway because it is the biggest
        # number on a piers section and the card above it says "Drilled LF".
        lines.append(_from(drill, "drilling", "Drilling", "LF",
            source="quote (lump)" if drill_q is not None else "rate",
            detail=(drill_q.note or "driller's lump sum") if drill_q is not None
            else "rate table, by shaft diameter",
        ))
    return lines


# ------------------------------------------------------------------ walls ----


def _wall_lines(db: Session, section: EstimateSection) -> list[MaterialLine]:
    from app.models.wall_run import WallRun
    from app.services.calc import _rate_numeric

    rows = list(
        db.scalars(
            select(WallRun)
            .where(WallRun.section_id == section.id)
            .order_by(WallRun.sort_order, WallRun.created_at)
        ).all()
    )
    quotes = qt.load_quotes(db, section.id)
    rebar_q = quotes.get(qt.REBAR)
    quoted_lb = rebar_q.per_lb() if rebar_q else None
    footing_mix = getattr(section, "footing_mix_design_id", None)
    sand_rate = _rate_numeric(db, section.kind, "sand_unit_cost", _z(_sand_unit_cost(db)))

    wall_c = _Acc()
    ftg_c = _Acc()
    rebar = _Acc()
    sand = _Acc()

    for r in rows:
        wall_cy = _d(r.calc_wall_concrete_cy)
        if wall_cy > 0:
            mix = db.get(MixDesign, r.mix_design_id) if r.mix_design_id else None
            wall_c.add_priced(wall_cy, _mix_unit_cost(db, r.mix_design_id),
                              getattr(mix, "name", None) or getattr(mix, "code", None) or "mix (none chosen)")

        ftg_cy = _d(r.calc_footing_concrete_cy)
        if ftg_cy > 0:
            mid = footing_mix or r.mix_design_id
            mix = db.get(MixDesign, mid) if mid else None
            ftg_c.add_priced(ftg_cy, _mix_unit_cost(db, mid),
                             getattr(mix, "name", None) or getattr(mix, "code", None) or "footing mix (none chosen)")

        lb = _d(r.calc_total_rebar_lb)
        if lb > 0 and not (rebar_q and rebar_q.is_lump):
            if quoted_lb is not None:
                rebar.add(lb, lb * quoted_lb)
            else:
                mat = resolve_rebar(db, False, section.kind) or {}
                rebar.add_priced(lb, _rebar_unit_cost(db, False, section.kind),
                                 mat.get("name") or "rebar")
        elif lb > 0:
            rebar.add(lb, _ZERO)

        s = _d(r.calc_sand_cy)
        if s > 0:
            sand.add(s, s * sand_rate, "SAND")

    lines: list[MaterialLine] = []
    if wall_c.live:
        lines.append(_from(wall_c, "wall_concrete", "Wall concrete", "CY", detail=_blend_note(wall_c)))
    if ftg_c.live:
        lines.append(_from(ftg_c, "footing_concrete", "Footing concrete", "CY", detail=_blend_note(ftg_c)))
    if rebar.live:
        if rebar_q and rebar_q.is_lump:
            lines.append(_quote_line("rebar", "Rebar", rebar_q, rebar.qty, "LB"))
        else:
            lines.append(_from(rebar, "rebar", "Rebar", "LB",
                source="quote" if quoted_lb is not None else "catalog",
                detail=_blend_note(rebar, "quoted $/lb"),
            ))
    if sand.live:
        lines.append(_from(sand, "sand", "Sand", "CY",
                                  detail=_blend_note(sand)))
    return lines


# ---------------------------------------------------------------- columns ---


def _column_lines(db: Session, section: EstimateSection) -> list[MaterialLine]:
    from app.models.column_type import ColumnType

    rows = list(
        db.scalars(
            select(ColumnType)
            .where(ColumnType.section_id == section.id)
            .order_by(ColumnType.sort_order, ColumnType.created_at)
        ).all()
    )
    quotes = qt.load_quotes(db, section.id)
    rebar_q = quotes.get(qt.REBAR)
    quoted_lb = rebar_q.per_lb() if rebar_q else None

    concrete = _Acc()
    rebar = _Acc()

    for r in rows:
        cy = _d(r.calc_concrete_cy)
        if cy > 0:
            mix = db.get(MixDesign, r.mix_design_id) if r.mix_design_id else None
            concrete.add_priced(
                cy,
                _mix_unit_cost(db, r.mix_design_id),
                getattr(mix, "name", None) or getattr(mix, "code", None) or "mix (none chosen)",
            )

        lb = _d(r.calc_total_rebar_lb)
        if lb > 0 and not (rebar_q and rebar_q.is_lump):
            if quoted_lb is not None:
                rebar.add(lb, lb * quoted_lb)
            else:
                mat = resolve_rebar(db, False, section.kind) or {}
                rebar.add_priced(
                    lb, _rebar_unit_cost(db, False, section.kind), mat.get("name") or "rebar"
                )
        elif lb > 0:
            rebar.add(lb, _ZERO)

    lines: list[MaterialLine] = []
    if concrete.live:
        lines.append(_from(concrete, "concrete", "Concrete", "CY", detail=_blend_note(concrete)))
    if rebar.live:
        if rebar_q and rebar_q.is_lump:
            lines.append(_quote_line("rebar", "Rebar", rebar_q, rebar.qty, "LB"))
        else:
            lines.append(_from(rebar, "rebar", "Rebar", "LB",
                source="quote" if quoted_lb is not None else "catalog",
                detail=_blend_note(rebar, "quoted $/lb"),
            ))
    return lines


# ------------------------------------------------------------------- deck ----


def _deck_lines(db: Session, section: EstimateSection) -> list[MaterialLine]:
    """
    The sixth assembly's purchases: concrete, the bar, and the cable.

    Mirrors `costing._deck_units` line for line — concrete by the level's mix,
    every pound of mat and beam steel at the PT-slab bar price (an elevated PT
    deck is a PT slab, and `resolve_rebar(post_tension=True)` says so), and
    post-tension per square foot of the levels that carry cable, priced through
    the `pt_cable_sf` rate or a PT quote. Mesh, stud rails and carton forms are
    forming and labor lines, not purchases on the level, so they are not here —
    the same rule that keeps plywood off the columns list.

    Shipped without this branch in sql/052: a deck section fell through to the
    slab reader, found no pours, and reported no money under any of its cards
    with `rounding` equal to the whole direct cost (audit 2026-09-04, P2 #3).
    """
    from app.models.deck_level import DeckLevel
    from app.services.calc import _rate_optional

    rows = list(
        db.scalars(
            select(DeckLevel)
            .where(DeckLevel.section_id == section.id)
            .order_by(DeckLevel.sort_order, DeckLevel.created_at)
        ).all()
    )
    quotes = qt.load_quotes(db, section.id)
    rebar_q = quotes.get(qt.REBAR)
    pt_q = quotes.get(qt.PT)
    quoted_lb = rebar_q.per_lb() if rebar_q else None
    quoted_sf = pt_q.per_sf() if pt_q else None
    # The rate the level was costed at. `_rate_optional` is the one rung on the
    # ladder with no code default: None here is UNPRICED, and the line says so.
    pt_rate = _rate_optional(db, section.kind, "pt_cable_sf")

    concrete = _Acc()
    rebar = _Acc()
    pt = _Acc()

    for r in rows:
        cy = _d(r.calc_concrete_cy)
        if cy > 0:
            mix = db.get(MixDesign, r.mix_design_id) if r.mix_design_id else None
            concrete.add_priced(
                cy,
                _mix_unit_cost(db, r.mix_design_id),
                getattr(mix, "name", None) or getattr(mix, "code", None) or "mix (none chosen)",
            )

        lb = _d(r.calc_total_rebar_lb)
        if lb > 0 and not (rebar_q and rebar_q.is_lump):
            if quoted_lb is not None:
                rebar.add(lb, lb * quoted_lb)
            else:
                mat = resolve_rebar(db, True, section.kind) or {}
                rebar.add_priced(
                    lb, _rebar_unit_cost(db, True, section.kind), mat.get("name") or "rebar"
                )
        elif lb > 0:
            rebar.add(lb, _ZERO)

        pt_sf = _d(r.calc_pt_sf)
        if pt_sf > 0:
            if pt_q and pt_q.is_lump:
                pt.add(pt_sf, _ZERO)
            elif quoted_sf is not None:
                pt.add(pt_sf, pt_sf * quoted_sf)
            else:
                pt.add_priced(pt_sf, pt_rate, "PT cable (pt_cable_sf)")

    lines: list[MaterialLine] = []
    if concrete.live:
        lines.append(_from(concrete, "concrete", "Concrete", "CY", detail=_blend_note(concrete)))
    if rebar.live:
        if rebar_q and rebar_q.is_lump:
            lines.append(_quote_line("rebar", "Rebar", rebar_q, rebar.qty, "LB"))
        else:
            lines.append(_from(rebar, "rebar", "Rebar", "LB",
                source="quote" if quoted_lb is not None else "catalog",
                detail=_blend_note(rebar, "quoted $/lb"),
            ))
    if pt.live:
        if pt_q and pt_q.is_lump:
            lines.append(_quote_line("pt", "Post-tension", pt_q, pt.qty, "SF"))
        else:
            lines.append(_from(pt, "pt", "Post-tension", "SF",
                source="quote" if quoted_sf is not None else "rate",
                detail="quoted $/SF" if quoted_sf is not None
                else "pt_cable_sf — this section's rate, per SF of level with cable",
            ))
    return lines


# ----------------------------------------------------------------- public ----


def _stored_direct_total(db: Session, section: EstimateSection) -> Decimal:
    """What costing.py actually wrote — the number this breakdown answers to."""
    from app.services.costing import cost_units

    return sum((u.direct for u in cost_units(db, section)), Decimal("0")).quantize(_Q2)


def section_material_costs(db: Session, section: EstimateSection) -> dict[str, Any]:
    """A reader, priced the way the section was costed: through its sheet (sql/048)."""
    with priced_as(db, section.estimate_id), for_section(section.id):
        return _section_material_costs(db, section)


def _section_material_costs(db: Session, section: EstimateSection) -> dict[str, Any]:
    """
    Every material on a section, with its quantity, its rate and its dollars.

    Materials only — the forming package, labor, supervision and equipment are
    allocated costs, not purchases, and they are already reported as
    `total_allocated_cost` on the section's totals. Adding them here would make
    the list add up to something no card is measured in.
    """
    if section.kind in PIER_KINDS:
        lines = _pier_lines(db, section)
    elif section.kind in WALL_KINDS:
        lines = _wall_lines(db, section)
    elif section.kind in COLUMN_KINDS:
        lines = _column_lines(db, section)
    elif section.kind in DECK_KINDS:
        lines = _deck_lines(db, section)
    else:
        lines = _slab_lines(db, section)

    total = sum((ln.cost for ln in lines), Decimal("0")).quantize(_Q2)
    direct = _stored_direct_total(db, section)
    return {
        "section_id": str(section.id),
        "kind": section.kind,
        "lines": [ln.as_dict() for ln in lines],
        "total_material_cost": total,
        "direct_cost": direct,
        # Per-row vs per-material rounding. Cents, or something is wrong.
        "rounding": (direct - total).quantize(_Q2),
    }
