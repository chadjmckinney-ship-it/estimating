"""
Per-pour cost and sale from stored quantities + catalog + ON takeoff lines.

Locked rule: engines show cost; margin + contingency live on the bid.

  SALE = cost × (1 + estimate.margin_pct + estimate.contingency_pct)

Pour COST = direct materials on that pour (mix CY, sand, rebar, PT, poly,
mesh — stored qty × catalog unit cost) PLUS this pour's share of ON forming /
labor / supervision / equipment lines, PLUS two uplifts. Default share is SF;
CY-driven lines (pumping, haul-off, excavation) share by CY. Off/manual flags
are respected: an off sky track stays $0 because its stored ext_cost is already 0.

The two uplifts, both from sql/027:

  fuel & maintenance   rental day lines × equip_fuel_maint_pct
  sales tax            (materials + rental days) × sales_tax_pct

Catalog prices are pre-tax, so the material list stays a real material list and
the tax is a visible number of its own. Labor, supervision and services such as
pumping are neither taxed nor uplifted. Exemption is a project fact
(projects.tax_exempt) — ROW paving is always exempt.

Missing slab mat / PT spacing: price what is stored. Do not invent PT LF —
the PT catalog is $/SF, so a PT pour is priced SF × catalog, and a 0 PT LF
stays 0 rather than being back-filled.

Numbers are stored on the pour (and rolled up on the estimate), not computed
on read. Recalc rewrites them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.estimate_section import (
    COLUMN_KINDS,
    DECK_KINDS,
    PIER_KINDS,
    WALL_KINDS,
    EstimateSection,
)
from app.models.estimate_equipment import EstimateEquipmentLine
from app.models.estimate_forming import EstimateFormingLine
from app.models.estimate_labor import EstimateLaborLine
from app.models.mix_design import MixDesign
from app.models.mono_slab import MonoSlab
from app.services import quotes as qt
from app.services.price_book import for_section, priced_as, require_book

_Q2 = Decimal("0.01")
_Q4 = Decimal("0.0001")
_ZERO = Decimal("0.00")

# "14' x 210" / "20 x 100" / "14'x140'" on vapor-barrier roll names.
_ROLL_DIM = re.compile(
    r"(\d+(?:\.\d+)?)\s*['\"]?\s*[x×]\s*(\d+(?:\.\d+)?)",
    re.IGNORECASE,
)


def _d(x: Any) -> Decimal:
    if x is None or x == "":
        return Decimal("0")
    return Decimal(str(x))


def sf_per_cy(sf: Decimal | None, cy: Decimal | None) -> Decimal | None:
    """Pour SF / total concrete CY. Zero CY → None (blank, not div0)."""
    c = _d(cy)
    if c <= 0:
        return None
    return (_d(sf) / c).quantize(_Q4)


def sale_from_cost(
    cost: Decimal,
    margin_pct: Decimal | None,
    contingency_pct: Decimal | None,
) -> Decimal:
    """SALE = cost × (1 + margin + contingency). No tax."""
    factor = Decimal("1") + _d(margin_pct) + _d(contingency_pct)
    return (_d(cost) * factor).quantize(_Q2)


def is_cy_driven(unit: str | None) -> bool:
    """Pumping / haul-off / excavation — allocate by CY, not SF."""
    u = (unit or "").upper().replace(" ", "")
    return u in {"CY", "/CY"} or u.endswith("CY")


def allocate_amount(amount: Decimal, weights: list[Decimal]) -> list[Decimal]:
    """
    Split `amount` across pours by weight. Last pour takes the remainder so
    the pieces always sum to the original (no silent leftover cents).

    Every weight zero: split EVENLY. Until 2026-09-06 the whole amount landed
    on the last row — right for leftover cents, wrong for a CY-driven line on
    a section whose rows all carry 0 CY, the trap the EA allocation basis
    fixed for SF one axis over (audit 2026-09-04, P3). When the driver says
    nothing, no row is more that line's than another. Lump quotes never
    reach this branch: _apply_lump_quotes leaves an all-zero lump alone.
    """
    amount = _d(amount).quantize(_Q2)
    n = len(weights)
    if n == 0:
        return []
    if amount == 0:
        return [_ZERO] * n
    total_w = sum((_d(w) for w in weights), Decimal("0"))
    if total_w <= 0:
        weights = [Decimal("1")] * n
        total_w = Decimal(n)
    out: list[Decimal] = []
    remaining = amount
    for i, w in enumerate(weights):
        if i == n - 1:
            out.append(remaining)
        else:
            share = (amount * _d(w) / total_w).quantize(_Q2)
            out.append(share)
            remaining -= share
    return out


def per_sf(amount: Decimal | None, sf: Decimal | None) -> Decimal | None:
    s = _d(sf)
    if s <= 0 or amount is None:
        return None
    return (_d(amount) / s).quantize(_Q4)


def roll_coverage_sf(name: str | None) -> Decimal | None:
    """Parse roll coverage from a catalog name like '10 mil 20 x 100'."""
    if not name:
        return None
    m = _ROLL_DIM.search(name)
    if not m:
        return None
    a = Decimal(m.group(1))
    b = Decimal(m.group(2))
    if a <= 0 or b <= 0:
        return None
    return a * b


def _find_material(
    db: Session, *name_parts: str, category: str | None = None
) -> dict[str, Any] | None:
    """
    A catalog row by name — priced as THIS JOB pays for it (sql/048).

    Name resolution is against the catalog, which is the list of what exists.
    The price is then swapped for the estimate's sheet value by the book in
    the current `priced_as` context. On a sheeted estimate an item absent from
    the sheet comes back UNPRICED, not at today's catalog — see
    services/price_book.py, "Once a sheet exists, it is the only source".

    `category` narrows the search to one catalog category. A name search that
    can land in ANY category is how "10 mil" + "20" found a black site-poly
    roll and priced a vapor barrier at a third of what the job was bid on
    (sql/030; audit 2026-09-02 #8).
    """
    clauses = " AND ".join(f"name ILIKE :p{i}" for i in range(len(name_parts)))
    params: dict[str, Any] = {f"p{i}": f"%{p}%" for i, p in enumerate(name_parts)}
    if category:
        clauses += " AND category = :category"
        params["category"] = category
    row = db.execute(
        text(
            f"""
            SELECT id, name, unit, unit_cost, category
            FROM materials
            WHERE coalesce(is_active, true) AND {clauses}
            ORDER BY sort_order NULLS LAST, id
            LIMIT 1
            """
        ),
        params,
    ).mappings().first()
    return require_book(f"material {' '.join(name_parts)!r}").price_material_row(
        dict(row) if row else None
    )


def _material_by_id(db: Session, material_id: int) -> dict[str, Any] | None:
    """A catalog row by id, priced through the book like `_find_material`."""
    row = db.execute(
        text("SELECT id, name, unit, unit_cost, category FROM materials WHERE id = :i"),
        {"i": int(material_id)},
    ).mappings().first()
    return require_book(f"material #{material_id}").price_material_row(
        dict(row) if row else None
    )


# ---------------------------------------------------------------------------
# Unit prices: None means UNPRICED, and the arithmetic says so out loud
#
# Until 2026-09-02 every helper below returned Decimal("0") when the catalog
# had no price — a NULL mix, a missing material, a row nobody had costed. That
# is the single most expensive habit this codebase had: a fresh install priced
# $324k of LBJ concrete at nothing and 425 tests stayed green, because zero is
# a perfectly plausible number to multiply by.
#
# Chad, on the price-sheet design: "I dont like concrete prices starting @ $0."
#
# So these return None. The arithmetic sites wrap them in _z(), which still
# multiplies by zero — there is nothing else arithmetic can do — but the None
# is visible at every call site, and `section_unpriced()` walks the same
# lookups and NAMES what is missing, so the section, the breakdown and the
# screen can all say "5000-ASH is unpriced" instead of quietly bidding it free.
# ---------------------------------------------------------------------------


def _z(price: Decimal | None) -> Decimal:
    """Zero for arithmetic. Only ever paired with a section_unpriced() report."""
    return price if price is not None else _ZERO


def _mix_unit_cost(db: Session, mix_id: int | None) -> Decimal | None:
    """
    The master-list price for a mix, or None if it has none.

    `mix_designs.unit_cost` IS the master list — one price per mix, kept current
    as supplier numbers come in. The per-supplier `mix_prices` history this used
    to fall back on (taking the MINIMUM across every supplier and every date,
    so a 2019 quote would have won) was dropped in sql/047.
    """
    if not mix_id:
        return None
    book = require_book(f"mix #{mix_id}")
    if book.has_sheet:
        # The sheet is the only source once it exists. A mix that is not on
        # it — added to the master list after the pull — is unpriced on this
        # job until the next pull, and the drift check says so.
        return book.mix_price(mix_id)
    mix = db.get(MixDesign, mix_id)
    if mix is None or mix.unit_cost is None:
        return None
    return _d(mix.unit_cost)


def resolve_rebar(
    db: Session, post_tension: bool, kind: str | None = None
) -> dict[str, Any] | None:
    """
    Which catalog item this pour's steel is priced from.

    Paving buys different bar from a building slab, and the catalog already
    says so — there is a REBAR PAVING line in it. Reaching for that on a paving
    section is the whole change; an assembly with no item of its own falls
    through to exactly what it used before.

    An `rebar_cost_per_lb` row in assembly_rates overrides the catalog outright,
    for an assembly that buys at a price no catalog item carries. Nothing seeds
    one — it exists so a rate CAN be stated rather than typed into a sheet.
    """
    if kind:
        row = db.execute(
            text(
                "SELECT value FROM assembly_rates "
                "WHERE kind = :k AND key = 'rebar_cost_per_lb'"
            ),
            {"k": kind},
        ).scalar()
        if row is not None:
            return {"name": f"{kind} assembly rate", "unit_cost": _d(row)}
        if kind in ("paving", "sidewalk"):
            mat = _find_material(db, "REBAR PAVING")
            if mat is not None:
                return mat
        if kind in PIER_KINDS:
            # Piers and PT slabs buy the same bar, and the catalog says so in
            # the item's own name: "REBAR PIERS / PT slabs". Until sql/043 this
            # went through an assembly_rates override at $0.75, copied from
            # `01-Piers!G53` — a cell whose Pricing lookup had been typed over
            # with a constant. Reading the catalog means the price follows it,
            # the way paving follows REBAR PAVING.
            mat = _find_material(db, "REBAR PIERS")
            if mat is not None:
                return mat
        if kind in DECK_KINDS:
            # Chad, 2026-09-05: "use rebar GB." The deck sheet points F78 at
            # REBAR GRADE BEAM ($0.65). Until today the app bought PT-slab bar
            # for an elevated PT deck ($0.60) on the sql/043 rule, which read
            # $3,513.21 light on LBJ. A deck buys grade-beam bar whether or
            # not it is post-tensioned.
            mat = _find_material(db, "REBAR GRADE BEAM")
            if mat is not None:
                return mat

    mat = None
    if post_tension:
        mat = _find_material(db, "REBAR", "PT") or _find_material(db, "PT slabs")
    if mat is None:
        mat = _find_material(db, "REBAR GRADE BEAM")
    if mat is None:
        mat = _find_material(db, "REBAR")
    return mat


def _priced(mat: dict[str, Any] | None) -> Decimal | None:
    """A catalog row's price, or None when the row is missing or unpriced."""
    if mat is None or mat.get("unit_cost") is None:
        return None
    return _d(mat["unit_cost"])


def _rebar_unit_cost(
    db: Session, post_tension: bool, kind: str | None = None
) -> Decimal | None:
    return _priced(resolve_rebar(db, post_tension, kind))


def _pt_sf_unit_cost(db: Session) -> Decimal | None:
    return _priced(_find_material(db, "POST TENSION"))


def _sand_unit_cost(db: Session) -> Decimal | None:
    return _priced(_find_material(db, "SAND"))


def _mesh_unit_cost(db: Session) -> Decimal | None:
    return _priced(_find_material(db, "WIRE MESH", "10") or _find_material(db, "WIRE MESH"))


def resolve_vapor_barrier(db: Session, section: EstimateSection) -> dict[str, Any] | None:
    """Gated (sql/048): the section's roll, at this job's price."""
    with priced_as(db, section.estimate_id), for_section(section.id):
        return _resolve_vapor_barrier(db, section)


def _resolve_vapor_barrier(db: Session, section: EstimateSection) -> dict[str, Any] | None:
    """
    Which roll this section is priced with: the section's choice, else the
    company default, else — for sections nobody has set — the old name search.

    That search is why this function exists. It matched "10 mil" and "20" and
    found a black poly roll filed under site_accessories, half the price of the
    Yellow Guard the job was bid on, which no search of that shape could ever
    have found (sql/030).
    """
    mid = getattr(section, "vapor_barrier_material_id", None)
    if not mid:
        setting = _setting(db, "default_vapor_barrier_material_id", Decimal("0"))
        mid = int(setting) if setting > 0 else None
    if mid:
        row = _material_by_id(db, int(mid))
        if row:
            return row
    return vapor_barrier_fallback(db)


def vapor_barrier_fallback(db: Session) -> dict[str, Any] | None:
    """
    The roll a section gets when nobody chose one and the company has no
    default — the OLD name search, now confined to the `vapor_barrier`
    category. On 2026-09-02 the unconfined search still resolved to
    `POLY 10 mil 20 x 100 Black` ($105, site_accessories) whenever
    `default_vapor_barrier_material_id` was 0 — which it is. A section that
    reaches this is told so (`section_pour_totals.vapor_barrier_source`), and
    one that finds nothing here is unpriced rather than wrapped in site poly.
    """
    return (
        _find_material(db, "10 mil", "20", category="vapor_barrier")
        or _find_material(db, "STEGO", category="vapor_barrier")
        or _find_material(db, "10 mil", category="vapor_barrier")
    )


def vapor_barrier_source(section: EstimateSection, db: Session) -> str:
    """Where this section's barrier came from: section / default / fallback."""
    if getattr(section, "vapor_barrier_material_id", None):
        return "section"
    if _setting(db, "default_vapor_barrier_material_id", Decimal("0")) > 0:
        return "default"
    return "fallback"


def resolve_vapor_tape(db: Session, section: EstimateSection) -> dict[str, Any] | None:
    """Gated (sql/048): the section's roll, at this job's price."""
    with priced_as(db, section.estimate_id), for_section(section.id):
        return _resolve_vapor_tape(db, section)


def _resolve_vapor_tape(db: Session, section: EstimateSection) -> dict[str, Any] | None:
    """Seam tape for the barrier: the section's choice, else the company default."""
    mid = getattr(section, "vapor_tape_material_id", None)
    if not mid:
        setting = _setting(db, "default_vapor_tape_material_id", Decimal("0"))
        mid = int(setting) if setting > 0 else None
    if not mid:
        return None
    return _material_by_id(db, int(mid))


def barrier_rolls(poly_sf: Decimal, mat: dict[str, Any] | None) -> Decimal:
    """
    How many rolls of wrap the poly area takes. A barrier priced per SF has no
    roll count — and therefore carries no tape.
    """
    if poly_sf <= 0 or mat is None:
        return _ZERO
    if (mat.get("unit") or "").upper() == "SF":
        return _ZERO
    coverage = roll_coverage_sf(mat.get("name"))
    if not coverage:
        return _ZERO
    return poly_sf / coverage


def _tape_cost(
    db: Session,
    poly_sf: Decimal,
    barrier: dict[str, Any] | None,
    tape: dict[str, Any] | None,
    rolls_per_roll: Decimal,
) -> Decimal:
    """Tape scales with the barrier, not the slab: rolls of wrap x the ratio."""
    if tape is None or tape.get("unit_cost") is None:
        return _ZERO
    rolls = barrier_rolls(poly_sf, barrier)
    if rolls <= 0 or rolls_per_roll <= 0:
        return _ZERO
    return (rolls * rolls_per_roll * _d(tape["unit_cost"])).quantize(_Q2)


def _poly_cost(db: Session, poly_sf: Decimal, mat: dict[str, Any] | None) -> Decimal:
    """Price stored poly SF from the chosen vapor barrier (roll → $/SF)."""
    if poly_sf <= 0:
        return _ZERO
    if mat is None or mat.get("unit_cost") is None:
        return _ZERO
    unit = (mat.get("unit") or "").upper()
    rate = _d(mat["unit_cost"])
    if unit == "SF":
        return (poly_sf * rate).quantize(_Q2)
    coverage = roll_coverage_sf(mat.get("name"))
    if not coverage:
        return _ZERO
    return (poly_sf / coverage * rate).quantize(_Q2)


def _direct_cost(
    db: Session,
    slab: MonoSlab,
    vapor_barrier: dict[str, Any] | None = None,
    vapor_tape: dict[str, Any] | None = None,
    tape_ratio: Decimal = Decimal("0"),
    kind: str | None = None,
    quotes: "qt.QuoteSet | None" = None,
) -> Decimal:
    """
    Materials sitting on this pour. Price stored qty; don't invent PT LF.

    A quote (sql/039) intervenes in one of two ways. A UNIT-priced one replaces
    the catalog rate right here — $/lb for steel, $/SF for PT. A LUMP
    contributes nothing at this point and is added afterwards as this pour's
    share, because apportioning a lump needs every pour's weight at once and a
    per-pour function cannot know its own share.
    """
    sf = _d(slab.square_footage)
    total = Decimal("0")

    mix_cy = _d(slab.calc_concrete_cy)
    if mix_cy > 0:
        total += mix_cy * _z(_mix_unit_cost(db, slab.mix_design_id))

    sand_cy = _d(slab.calc_sand_cy)
    if sand_cy > 0:
        total += sand_cy * _z(_sand_unit_cost(db))

    q = quotes or qt.EMPTY
    rebar_q = q.get(qt.REBAR)
    pt_q = q.get(qt.PT)

    rebar_lb = _d(slab.calc_total_rebar_lb)
    if rebar_lb > 0 and not (rebar_q and rebar_q.is_lump):
        # A quoted $/lb beats the catalog; a lump is added later as a share.
        quoted = rebar_q.per_lb() if rebar_q else None
        rate = quoted if quoted is not None else _z(_rebar_unit_cost(
            db, bool(slab.post_tension), kind
        ))
        total += rebar_lb * rate

    # PT catalog is $/SF. Zero stored PT LF is left at 0, not back-filled.
    if slab.post_tension and sf > 0 and not (pt_q and pt_q.is_lump):
        quoted_sf = pt_q.per_sf() if pt_q else None
        total += sf * (quoted_sf if quoted_sf is not None else _z(_pt_sf_unit_cost(db)))

    poly_sf = _d(slab.calc_poly_sf)
    total += _poly_cost(db, poly_sf, vapor_barrier)
    total += _tape_cost(db, poly_sf, vapor_barrier, vapor_tape, tape_ratio)

    if slab.wire_mesh and sf > 0:
        total += sf * _z(_mesh_unit_cost(db))

    return total.quantize(_Q2)


def _setting(db: Session, key: str, default: Decimal) -> Decimal:
    row = db.execute(
        text("SELECT value #>> '{}' FROM system_settings WHERE key = :k"), {"k": key}
    ).scalar()
    if row is None or str(row).strip() == "":
        return default
    try:
        return Decimal(str(row).strip().strip('"'))
    except Exception:
        return default


def _money_setting(db: Session, key: str, default: Decimal) -> Decimal:
    """
    A company setting that is a PRICE — the tax rate, the fuel percentage —
    read the way every other price is read (sql/049): from this job's sheet
    when it has one. `_setting` stays for rules and pointers.
    """
    from app.services.calc import _rate_numeric

    return _rate_numeric(db, None, key, default)


def tax_rate_for(db: Session, section: EstimateSection) -> Decimal:
    """Sales tax rate for this section — see `_tax_rate_for`. Self-gating,
    because callers have the section in hand and nothing else to thread."""
    with priced_as(db, section.estimate_id), for_section(section.id):
        return _tax_rate_for(db, section)


def _tax_rate_for(db: Session, section: EstimateSection) -> Decimal:
    """
    Sales tax rate for this section.

    Exemption is a PROJECT fact with a SECTION exception: ROW paving and
    sidewalks are exempt inside jobs that are otherwise taxable, so the section
    wins when it says anything at all. `section.tax_exempt` is deliberately
    tri-state — NULL inherits the project, true/false override it — and is never
    defaulted from `kind`, because plenty of paving is not ROW and a silently
    exempt section is a wrong number with nothing on screen to notice.
    """
    if section.tax_exempt is not None:
        return Decimal("0") if section.tax_exempt else _money_setting(
            db, "sales_tax_pct", Decimal("0")
        )

    exempt = db.execute(
        text(
            "SELECT coalesce(p.tax_exempt, false) FROM projects p "
            "JOIN estimates e ON e.project_id = p.id "
            "JOIN estimate_sections s ON s.estimate_id = e.id WHERE s.id = :sid"
        ),
        {"sid": str(section.id)},
    ).scalar()
    if exempt:
        return Decimal("0")
    return _money_setting(db, "sales_tax_pct", Decimal("0"))


def is_rental(unit: str | None) -> bool:
    """A rental day line — what fuel & maintenance rides on."""
    return (unit or "").strip().upper() in {"DAY", "/DAY", "DAYS"}


def _on_takeoff_lines(db: Session, section_id: UUID) -> list[dict[str, Any]]:
    """
    ON takeoff lines with a stored ext_cost to allocate. Off → $0, skipped.

    Each line carries what it is, because the uplifts differ: materials are
    taxed, rental days are taxed and carry fuel & maintenance, and labor,
    supervision and services (pumping) get neither.
    """
    lines: list[dict[str, Any]] = []

    for r in db.scalars(
        select(EstimateFormingLine).where(
            EstimateFormingLine.section_id == section_id
        )
    ).all():
        if not r.enabled:
            continue
        ext = _d(r.ext_cost)
        if ext == 0:
            continue
        # Nearly every line in this block is a purchase. The exception is a
        # service that happens to be filed with the lumber — concrete haul-off
        # is hauling, and hauling is not taxed (sql/036).
        lines.append(
            {
                "unit": r.unit,
                "ext_cost": ext,
                "kind": "material" if getattr(r, "taxable", True) else "service",
            }
        )

    for r in db.scalars(
        select(EstimateLaborLine).where(EstimateLaborLine.section_id == section_id)
    ).all():
        if not r.enabled:
            continue
        ext = _d(r.ext_cost)
        if ext == 0:
            continue
        lines.append({"unit": r.unit, "ext_cost": ext, "kind": "labor"})

    for r in db.scalars(
        select(EstimateEquipmentLine).where(
            EstimateEquipmentLine.section_id == section_id
        )
    ).all():
        if not r.enabled:
            continue
        ext = _d(r.ext_cost)
        if ext == 0:
            continue
        # Only the rental group carries fuel & maintenance. A contract service
        # priced by the day — out-of-town expense, a crew day rate — is work,
        # not a machine, and burns no diesel.
        rental = is_rental(r.unit) and (r.group_name or "equipment") == "equipment"
        lines.append(
            {
                "unit": r.unit,
                "ext_cost": ext,
                "kind": "rental" if rental else "service",
            }
        )

    return lines


@dataclass
class _Unit:
    """
    One thing a section's shared cost is spread across.

    A pour on a slab or paving section; a pier group on a piers section. The
    allocator does not care which — it needs a weight, a CY figure for the
    CY-driven lines, and somewhere to write the answer.
    """

    row: Any
    weight: Decimal          # SF on a pour, pier count on a group
    cy: Decimal
    quantity: Decimal        # what the per-unit figures divide by
    direct_taxable: Decimal  # materials bought for this unit
    direct_untaxed: Decimal  # services sitting on it — drilling a shaft
    per_unit_fields: tuple[str, str]

    @property
    def direct(self) -> Decimal:
        return (self.direct_taxable + self.direct_untaxed).quantize(_Q2)


def allocation_basis(kind: str | None) -> str:
    """
    What a section's shared cost is spread in proportion to.

    SF for anything shaped like a slab. EA for piers, which have no square
    footage at all — and that is not a detail. `allocate_amount` falls back to
    "the last row takes the remainder" when every weight is zero, so a piers
    section run on the SF basis would put the entire forming, labor and
    equipment cost on whichever group sorted last, with no error and nothing on
    screen to notice (sql/037).
    """
    if kind in PIER_KINDS:
        return "EA"
    if kind in WALL_KINDS:
        # Form feet — contact area on one face (sql/040). A walls section has
        # no square footage either, so the same zero-weight trap applies.
        return "FF"
    if kind in DECK_KINDS:
        # Deck AREA. The sheet's own allocation columns (BU:BY) all divide by
        # the total square footage, and the section is measured and sold in
        # SF, so weight and quantity are the same field here — the first
        # assembly since the mono slab where they are.
        return "SF"
    if kind in COLUMN_KINDS:
        # Form CONTACT area, all four faces (sql/045). Columns are measured and
        # sold in EA, but forming is what the money goes on, and a 24-foot
        # column is not the same share of a supervisor as a 12-foot one. Same
        # split as walls: the weight and the unit are different columns.
        return "SF"
    return "SF"


def _pier_units(db: Session, section: EstimateSection) -> list[_Unit]:
    from app.models.pier_group import PierGroup

    kind = section.kind
    groups = list(
        db.scalars(
            select(PierGroup)
            .where(PierGroup.section_id == section.id)
            .order_by(PierGroup.sort_order, PierGroup.created_at)
        ).all()
    )
    quotes = qt.load_quotes(db, section.id)
    rebar_q = quotes.get(qt.REBAR)
    quoted_lb = rebar_q.per_lb() if rebar_q else None

    units: list[_Unit] = []
    for g in groups:
        qty = _d(g.qty)
        cy = _d(g.calc_concrete_cy)
        materials = Decimal("0")
        if cy > 0:
            materials += cy * _z(_mix_unit_cost(db, g.mix_design_id))
        steel = _d(g.calc_total_rebar_lb)
        if steel > 0 and not (rebar_q and rebar_q.is_lump):
            rate = quoted_lb if quoted_lb is not None else _z(_rebar_unit_cost(db, False, kind))
            materials += steel * rate
        units.append(
            _Unit(
                row=g,
                weight=qty,
                cy=cy,
                quantity=qty,
                direct_taxable=materials.quantize(_Q2),
                # Drilling the hole is work, not a purchase. It rides the group
                # because the rate is per diameter, but it is never taxed.
                direct_untaxed=_d(g.calc_drill_cost).quantize(_Q2),
                per_unit_fields=("calc_cost_per_unit", "calc_sale_per_unit"),
            )
        )
    _apply_lump_quotes(db, section, units, quotes)
    return units


def _column_units(db: Session, section: EstimateSection) -> list[_Unit]:
    """
    One column TYPE, weighted by FORM CONTACT AREA and counted in COLUMNS.

    The two are deliberately different fields. Shared cost — supervision, the
    rental ladder, pumping — is spent on surface to form and strip, so a
    24-foot column carries twice the share of a 12-foot one of the same
    section. But the assembly is measured, quoted and compared in EA, so the
    per-unit figures divide by the count.

    Piers make the opposite call (weight and quantity are both the pier count)
    because a pier's shared cost really does track the hole, not its depth.
    """
    from app.models.column_type import ColumnType

    kind = section.kind
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

    units: list[_Unit] = []
    for r in rows:
        qty = Decimal(int(r.qty or 0))
        cy = _d(r.calc_concrete_cy)
        materials = Decimal("0")
        if cy > 0:
            materials += cy * _z(_mix_unit_cost(db, r.mix_design_id))
        steel = _d(r.calc_total_rebar_lb)
        if steel > 0 and not (rebar_q and rebar_q.is_lump):
            rate = quoted_lb if quoted_lb is not None else _z(_rebar_unit_cost(db, False, kind))
            materials += steel * rate
        units.append(
            _Unit(
                row=r,
                weight=_d(r.calc_form_sf),
                cy=cy,
                quantity=qty,
                direct_taxable=materials.quantize(_Q2),
                direct_untaxed=Decimal("0"),
                per_unit_fields=("calc_cost_per_unit", "calc_sale_per_unit"),
            )
        )
    _apply_lump_quotes(db, section, units, quotes)
    return units


def _deck_units(db: Session, section: EstimateSection) -> list[_Unit]:
    """
    One deck LEVEL, weighted by area and counted in square feet.

    The concrete, the mats, the beam steel and the POST-TENSION all sit here
    as direct cost, the way concrete and steel sit on a pour or a column type.
    PT is the new one: it is priced per square foot of the levels that carry
    cable (`calc_pt_sf`, zero where they do not), and a PT quote replaces the
    computed figure — which is exactly the slot the sheet already has at
    `N80 = IF(I80 = 0, SF x 1.45, I80)`.
    """
    from app.models.deck_level import DeckLevel

    kind = section.kind
    rows = list(
        db.scalars(
            select(DeckLevel)
            .where(DeckLevel.section_id == section.id)
            .order_by(DeckLevel.sort_order, DeckLevel.created_at)
        ).all()
    )
    quotes = qt.load_quotes(db, section.id)
    rebar_q = quotes.get(qt.REBAR)
    quoted_lb = rebar_q.per_lb() if rebar_q else None
    pt_q = quotes.get(qt.PT)
    quoted_pt_sf = pt_q.per_sf() if pt_q else None

    units: list[_Unit] = []
    for r in rows:
        sf = _d(r.area_sf)
        cy = _d(r.calc_concrete_cy)
        materials = Decimal("0")
        if cy > 0:
            materials += cy * _z(_mix_unit_cost(db, r.mix_design_id))
        steel = _d(r.calc_total_rebar_lb)
        if steel > 0 and not (rebar_q and rebar_q.is_lump):
            rate = quoted_lb if quoted_lb is not None else _z(
                _rebar_unit_cost(db, True, kind)
            )
            materials += steel * rate
        pt_sf = _d(r.calc_pt_sf)
        if pt_sf > 0 and not (pt_q and pt_q.is_lump):
            rate = quoted_pt_sf
            if rate is None:
                from app.services.calc import _rate_optional

                rate = _z(_rate_optional(db, kind, "pt_cable_sf"))
            materials += pt_sf * rate
        units.append(
            _Unit(
                row=r,
                weight=sf,
                cy=cy,
                quantity=sf,
                direct_taxable=materials.quantize(_Q2),
                direct_untaxed=Decimal("0"),
                per_unit_fields=("calc_cost_per_unit", "calc_sale_per_unit"),
            )
        )
    _apply_lump_quotes(db, section, units, quotes)
    return units


def _slab_units(db: Session, section: EstimateSection) -> list[_Unit]:
    slabs = list(
        db.scalars(
            select(MonoSlab)
            .where(MonoSlab.section_id == section.id)
            .order_by(MonoSlab.sort_order, MonoSlab.created_at)
        ).all()
    )
    vapor_barrier = resolve_vapor_barrier(db, section)
    vapor_tape = resolve_vapor_tape(db, section)
    tape_ratio = _setting(db, "vapor_tape_rolls_per_barrier_roll", Decimal("0"))
    quotes = qt.load_quotes(db, section.id)
    units = [
        _Unit(
            row=s,
            weight=_d(s.square_footage),
            cy=_d(s.calc_concrete_cy),
            quantity=_d(s.square_footage),
            direct_taxable=_direct_cost(
                db, s, vapor_barrier, vapor_tape, tape_ratio, section.kind, quotes
            ),
            direct_untaxed=Decimal("0"),
            per_unit_fields=("calc_cost_per_sf", "calc_sale_per_sf"),
        )
        for s in slabs
    ]
    _apply_lump_quotes(db, section, units, quotes)
    return units


def _apply_lump_quotes(
    db: Session,
    section: EstimateSection,
    units: list[_Unit],
    quotes: "qt.QuoteSet",
) -> None:
    """
    Add each lump quote to the units as their share of it.

    The weight is the driver the quote was priced on — rebar lb for steel, PT SF
    for PT — never the section's default allocation basis. Two consequences
    worth being explicit about:

      * a PT lump lands ONLY on pours that are actually post-tensioned. Spread
        by plain SF it would charge PT to slabs that have none, which reads as
        a plausible per-SF number and is wrong on every row.
      * a row with no steel takes no part of a rebar quote, rather than an
        equal share of it.

    A lump whose every weight is zero is left alone rather than dumped on the
    last row: allocate_amount's remainder rule is right for pennies and wrong
    for a whole quote, and that fallback is exactly the bug the EA allocation
    basis was introduced to prevent.
    """
    if not quotes or not units:
        return

    # One definition, shared with `quotes.section_driver_qty`, which stamps and
    # checks the baseline. These were two implementations until 2026-09-02 and
    # they disagreed for walls and columns — the spread was right and the
    # baseline was zero, which silently disabled the staleness badge. Spreading
    # a lump and deciding whether that lump is still valid must read the same
    # driver or the check means nothing.
    for kind in (qt.REBAR, qt.PT):
        weight_of = qt.LUMP_DRIVERS[kind]
        quote = quotes.get(kind)
        if quote is None or not quote.is_lump:
            continue
        weights = [weight_of(u.row) for u in units]
        if sum(weights, Decimal("0")) <= 0:
            continue
        for unit, share in zip(units, qt.spread(quote.amount, weights)):
            unit.direct_taxable = (unit.direct_taxable + share).quantize(_Q2)


def _wall_units(db: Session, section: EstimateSection) -> list[_Unit]:
    """
    One wall run, weighted by FORM FEET.

    The only assembly so far where concrete comes from two mixes: the wall
    takes the row's mix, the footing its own `footing_mix_design_id` (sql/062),
    else the section's, else the row's — cheaper concrete in the ground, better
    concrete in the wall, and a footing never priced at nothing. The ladder is
    `WallRun.footing_mix_for`, the one rule every costing path uses.

    Sand is a direct material here (it goes under the form line), where on a
    slab it is part of the pour. Excavation and backfill are labor, not
    material, and live in the labor set.
    """
    from app.models.wall_run import WallRun

    kind = section.kind
    runs = list(
        db.scalars(
            select(WallRun)
            .where(WallRun.section_id == section.id)
            .order_by(WallRun.sort_order, WallRun.created_at)
        ).all()
    )
    quotes = qt.load_quotes(db, section.id)
    rebar_q = quotes.get(qt.REBAR)
    quoted_lb = rebar_q.per_lb() if rebar_q else None

    from app.services.calc import _rate_numeric

    sand_rate = _rate_numeric(db, kind, "sand_unit_cost", _z(_sand_unit_cost(db)))

    units: list[_Unit] = []
    for r in runs:
        ff = _d(r.calc_form_ff)
        materials = Decimal("0")

        wall_cy = _d(r.calc_wall_concrete_cy)
        ftg_cy = _d(r.calc_footing_concrete_cy)
        if wall_cy > 0:
            materials += wall_cy * _z(_mix_unit_cost(db, r.mix_design_id))
        if ftg_cy > 0:
            materials += ftg_cy * _z(_mix_unit_cost(db, r.footing_mix_for(section)))

        steel = _d(r.calc_total_rebar_lb)
        if steel > 0 and not (rebar_q and rebar_q.is_lump):
            rate = quoted_lb if quoted_lb is not None else _z(_rebar_unit_cost(db, False, kind))
            materials += steel * rate

        sand = _d(r.calc_sand_cy)
        if sand > 0:
            materials += sand * sand_rate

        # Allocate on FORM FEET + FOOTING SF, the sheet's own basis (BF36 +
        # BG36), but keep FORM FEET as the unit the section is measured in.
        #
        # Weighting by form feet alone under-serves a long, low wall on a wide
        # footing: 135 ft of 3 ft wall is 405 form feet sitting on 787 SF of
        # footing, and supervision and equipment are spent on both. Getting
        # this wrong does not move the section total — it moves money between
        # rows, and it showed up as the wall/footing split producing rates that
        # swung 2:1 across sixteen identically-built walls.
        units.append(
            _Unit(
                row=r,
                weight=ff + _d(r.calc_footing_sf),
                cy=_d(r.calc_concrete_cy),
                quantity=ff,
                direct_taxable=materials.quantize(_Q2),
                direct_untaxed=Decimal("0"),
                per_unit_fields=("calc_cost_per_unit", "calc_sale_per_unit"),
            )
        )
    _apply_lump_quotes(db, section, units, quotes)
    return units


def cost_units(db: Session, section: EstimateSection) -> list[_Unit]:
    """
    The rows this section's cost is spread across, whatever shape they are.

    Builds each row's direct material cost, so it is a price gate in its own
    right (sql/048): reached from `refresh_pour_costs` (already inside the
    book) and from `quotes.section_driver_qty` via the quotes router (not).
    Re-entrant, so the nested case costs nothing.
    """
    with priced_as(db, section.estimate_id), for_section(section.id):
        if section.kind in PIER_KINDS:
            return _pier_units(db, section)
        if section.kind in WALL_KINDS:
            return _wall_units(db, section)
        if section.kind in COLUMN_KINDS:
            return _column_units(db, section)
        if section.kind in DECK_KINDS:
            return _deck_units(db, section)
        return _slab_units(db, section)


def refresh_pour_costs(db: Session, section: EstimateSection) -> dict[str, Any]:
    """
    Rewrite the stored cost/sale fields on a section and everything under it.
    Does not commit.

    Sum of the units' calc_cost equals section.calc_total_cost from the same
    rules. The job total is the sum of its sections — see
    refresh_estimate_totals.

    One of the four gates every price passes through (sql/048): the whole pass
    runs inside the estimate's price book, so every lookup below — and in
    split_wall_and_footing, section_unpriced and the quote spread — reads the
    same sheet.
    """
    with priced_as(db, section.estimate_id), for_section(section.id):
        return _refresh_pour_costs(db, section)


def _refresh_pour_costs(db: Session, section: EstimateSection) -> dict[str, Any]:
    units = cost_units(db, section)

    # Markup is priced on the section (sql/033). The estimate's figures are only
    # the default a new section is created with.
    margin = (
        _d(section.margin_pct) if section.margin_pct is not None else Decimal("0.20")
    )
    conting = (
        _d(section.contingency_pct)
        if section.contingency_pct is not None
        else Decimal("0.00")
    )

    tax_rate = tax_rate_for(db, section)
    fuel_rate = _money_setting(db, "equip_fuel_maint_pct", Decimal("0"))

    weights = [u.weight for u in units]
    cy_weights = [u.cy for u in units]
    allocated = [_ZERO] * len(units)
    taxable_alloc = [_ZERO] * len(units)   # materials + rentals
    rental_alloc = [_ZERO] * len(units)    # rentals only

    for ln in _on_takeoff_lines(db, section.id):
        w = cy_weights if is_cy_driven(ln["unit"]) else weights
        shares = allocate_amount(ln["ext_cost"], w)
        for i, share in enumerate(shares):
            allocated[i] += share
            if ln["kind"] in ("material", "rental"):
                taxable_alloc[i] += share
            if ln["kind"] == "rental":
                rental_alloc[i] += share

    total_cost = _ZERO
    total_sale = _ZERO
    total_tax = _ZERO
    total_qty = Decimal("0")

    for i, unit in enumerate(units):
        row = unit.row
        direct = unit.direct
        alloc = allocated[i].quantize(_Q2)

        # Fuel & maintenance and tax both ride on the pre-uplift base, the way
        # the workbook applies them (× (1 + tax + fuel)), so neither compounds
        # on the other. Only the taxable half of direct is taxed: drilling a
        # shaft is work, not a purchase.
        fuel = (rental_alloc[i] * fuel_rate).quantize(_Q2)
        tax = ((unit.direct_taxable + taxable_alloc[i]) * tax_rate).quantize(_Q2)

        cost = (direct + alloc + fuel + tax).quantize(_Q2)
        sale = sale_from_cost(cost, margin, conting)

        if hasattr(row, "calc_sf_per_cy"):
            row.calc_sf_per_cy = sf_per_cy(unit.quantity, unit.cy)
        row.calc_direct_cost = direct
        row.calc_allocated_cost = alloc
        row.calc_equip_fuel = fuel
        row.calc_tax = tax
        row.calc_cost = cost
        row.calc_sale = sale
        cost_field, sale_field = unit.per_unit_fields
        setattr(row, cost_field, per_sf(cost, unit.quantity))
        setattr(row, sale_field, per_sf(sale, unit.quantity))

        total_cost += cost
        total_sale += sale
        total_tax += tax
        total_qty += unit.quantity

    # Walls carry a second breakdown: what the wall costs and what the footing
    # under it costs, each on its own driver (sql/042). Done here, after every
    # row's calc_cost is final, because the wall side is the remainder.
    if section.kind in WALL_KINDS:
        from app.services.walls import split_wall_and_footing

        split_wall_and_footing(db, section)

    section.calc_total_cost = total_cost.quantize(_Q2)
    section.calc_total_sale = total_sale.quantize(_Q2)
    section.calc_total_tax = total_tax.quantize(_Q2)
    section.calc_quantity = total_qty.quantize(Decimal("0.001"))
    section.calc_cost_per_unit = per_sf(total_cost, total_qty)
    section.calc_sale_per_unit = per_sf(total_sale, total_qty)
    # What the total above is missing. Written in the same breath as the total
    # so the two can never disagree about which refresh they belong to.
    section.calc_unpriced = section_unpriced(db, section)

    # These six lines are the ONLY place a section total is written, which is
    # why the job roll-up happens here and nowhere else — see _roll_up_parent.
    _roll_up_parent(db, section)

    is_pt = any(bool(getattr(u.row, "post_tension", False)) for u in units)
    out = {
        "section_id": str(section.id),
        "pours": len(units),
        "units": len(units),
        "basis": allocation_basis(section.kind),
        "total_cost": section.calc_total_cost,
        "total_sale": section.calc_total_sale,
        "total_tax": section.calc_total_tax,
        "tax_rate": tax_rate,
        "margin_pct": margin,
        "contingency_pct": conting,
        # Named on purpose. The Yellow Guard lesson (sql/030) was that a price
        # resolved by a name search is a price nobody can see; every resolved
        # item now says what it landed on.
        "rebar_material": (resolve_rebar(db, is_pt, section.kind) or {}).get("name"),
    }
    if section.kind not in PIER_KINDS:
        out["vapor_barrier"] = (resolve_vapor_barrier(db, section) or {}).get("name")
        out["vapor_barrier_source"] = vapor_barrier_source(section, db)
        out["vapor_tape"] = (resolve_vapor_tape(db, section) or {}).get("name")
    return out


def section_unpriced(db: Session, section: EstimateSection) -> list[str]:
    """
    Every item this section reaches for that the master list has NO price for.

    This is the other half of `_z()`. The arithmetic multiplies an unpriced item
    by zero because it has no alternative; this walks the same lookups and
    NAMES what came back None, so the section total can carry the list and the
    screen can say "5000-ASH is unpriced — this bid is light by an unknown
    amount" instead of quietly bidding the concrete free.

    Stored on `estimate_sections.calc_unpriced` by `refresh_pour_costs`, next to
    the totals it qualifies. Empty means every price this section used was a
    real one. Ordered and de-duplicated so the same list reads the same way on
    every refresh.

    Covers the direct-material lookups — mixes (including a walls section's
    footing mix), the resolved rebar item, PT, sand, mesh. Forming already
    reports its own `missing_prices`; equipment gets the same treatment in
    stage 0e of the price-sheet work.
    """
    out: set[str] = set()
    kind = section.kind

    def mix_name(mix_id: int | None) -> str:
        if not mix_id:
            return "mix (none chosen)"
        mix = db.get(MixDesign, mix_id)
        if mix is None:
            return f"mix #{mix_id} (not in the catalog)"
        return mix.code or mix.name

    def need_mix(mix_id: int | None, cy: Any) -> None:
        if _d(cy) > 0 and _mix_unit_cost(db, mix_id) is None:
            out.add(f"{mix_name(mix_id)} — mix")

    def need(label: str, price: Decimal | None, qty: Any) -> None:
        if _d(qty) > 0 and price is None:
            out.add(label)

    quotes = qt.load_quotes(db, section.id)
    rebar_q = quotes.get(qt.REBAR)
    pt_q = quotes.get(qt.PT)
    rebar_quoted = rebar_q is not None          # any quote prices the steel
    pt_quoted = pt_q is not None

    def rebar_label(post_tension: bool) -> str:
        mat = resolve_rebar(db, post_tension, kind)
        return f"{mat['name']} — rebar" if mat else "rebar (no catalog item)"

    if kind in PIER_KINDS:
        from app.models.pier_group import PierGroup

        for g in db.scalars(select(PierGroup).where(PierGroup.section_id == section.id)):
            need_mix(g.mix_design_id, g.calc_concrete_cy)
            if not rebar_quoted:
                need(rebar_label(False), _rebar_unit_cost(db, False, kind), g.calc_total_rebar_lb)

    elif kind in WALL_KINDS:
        from app.models.wall_run import WallRun

        for r in db.scalars(select(WallRun).where(WallRun.section_id == section.id)):
            need_mix(r.mix_design_id, r.calc_wall_concrete_cy)
            need_mix(r.footing_mix_for(section), r.calc_footing_concrete_cy)
            if not rebar_quoted:
                need(rebar_label(False), _rebar_unit_cost(db, False, kind), r.calc_total_rebar_lb)
            need("SAND", _sand_unit_cost(db), getattr(r, "calc_sand_cy", 0))

    elif kind in DECK_KINDS:
        from app.models.deck_level import DeckLevel
        from app.services.calc import _rate_optional

        for r in db.scalars(select(DeckLevel).where(DeckLevel.section_id == section.id)):
            need_mix(r.mix_design_id, r.calc_concrete_cy)
            if not rebar_quoted:
                # A deck is post-tensioned steel: the catalog says so in the
                # item's own name, "REBAR PIERS / PT slabs" (sql/043).
                need(rebar_label(True), _rebar_unit_cost(db, True, kind), r.calc_total_rebar_lb)
            if not pt_quoted:
                # Priced per SF of the levels that carry cable, by RATE rather
                # than by a catalog row — the sheet's F80.
                need(
                    "POST TENSION — cables",
                    _rate_optional(db, kind, "pt_cable_sf"),
                    r.calc_pt_sf,
                )
            need("WIRE MESH", _mesh_unit_cost(db), r.mesh_sf)

    elif kind in COLUMN_KINDS:
        from app.models.column_type import ColumnType

        for r in db.scalars(select(ColumnType).where(ColumnType.section_id == section.id)):
            need_mix(r.mix_design_id, r.calc_concrete_cy)
            if not rebar_quoted:
                need(rebar_label(False), _rebar_unit_cost(db, False, kind), r.calc_total_rebar_lb)

    else:
        from app.models.mono_slab import MonoSlab

        for r in db.scalars(select(MonoSlab).where(MonoSlab.section_id == section.id)):
            need_mix(r.mix_design_id, r.calc_concrete_cy)
            need("SAND", _sand_unit_cost(db), r.calc_sand_cy)
            if not rebar_quoted:
                need(
                    rebar_label(bool(r.post_tension)),
                    _rebar_unit_cost(db, bool(r.post_tension), kind),
                    r.calc_total_rebar_lb,
                )
            if r.post_tension and not pt_quoted:
                need("POST TENSION — cables", _pt_sf_unit_cost(db), r.square_footage)
            if getattr(r, "wire_mesh", False):
                need("WIRE MESH", _mesh_unit_cost(db), r.square_footage)
            if _d(getattr(r, "calc_poly_sf", 0)) > 0:
                barrier = _resolve_vapor_barrier(db, section)
                need(
                    "vapor barrier — none chosen and no company default"
                    if barrier is None
                    else f"{barrier['name']} — vapor barrier",
                    _priced(barrier),
                    r.calc_poly_sf,
                )

    # Piers and walls TYPE their supervision (the workbook does), and the
    # rental ladder rides those days. A section nobody has typed yet has
    # super_days = 0 → every rental at $0.00 with a correct-looking rate
    # beside it, and supervision itself at $0 — proven −$19,638.67 on piers,
    # −$14,403.10 on walls (audit 2026-09-02 #5). Not an unpriced ITEM, but
    # the same lie in the total, so it goes on the same list.
    if kind in PIER_KINDS or kind in WALL_KINDS or kind in DECK_KINDS:
        table = (
            "pier_groups" if kind in PIER_KINDS
            else "wall_runs" if kind in WALL_KINDS
            else "deck_levels"
        )
        has_work = db.execute(
            text(f"SELECT count(*) FROM {table} WHERE section_id = :sid"),
            {"sid": str(section.id)},
        ).scalar()
        sup = db.execute(
            text("SELECT qty, enabled FROM estimate_labor_lines "
                 "WHERE section_id = :sid AND code = 'superintendent'"),
            {"sid": str(section.id)},
        ).first()
        typed = _d(sup[0]) if sup else Decimal("0")
        # An UNCHECKED superintendent is a decision, not an omission — Chad,
        # 2026-09-04: "that message should go away after I uncheck it as not
        # used". Nothing is riding on the days in that state either: on all
        # three typed assemblies the rental ladder derives from super days, so
        # zero days means the machines are already at zero and the warning has
        # nothing left to protect.
        typed_off = bool(sup) and not sup[1]
        if has_work and typed <= 0 and not typed_off:
            out.add("superintendent days — not typed (supervision and rentals are at 0 days)")

    # The two stored takeoffs keep their own lists. Fold them in so the section
    # carries ONE answer to "what on this bid has no price behind it".
    from app.models.estimate_forming import EstimateFormingLine

    equip_lines = list(
        db.scalars(
            select(EstimateEquipmentLine).where(
                EstimateEquipmentLine.section_id == section.id
            )
        )
    )
    for r in equip_lines:
        if r.price_source == "default" and r.enabled and _d(r.billable_units) > 0:
            out.add(f"{r.label} — equipment (placeholder rate)")

    # MOBILIZATION (sql/053). The workbook prices it nowhere, so every bid in
    # the system is currently missing the cost of getting the iron to the job
    # — which on a section renting a $3,200/day crane is not a rounding error.
    #
    # Flagged only where there is something to mobilize: a section billing
    # rental days and carrying $0 of mobilization has left it out. A section
    # with no machines on it has nothing to move and says nothing.
    #
    # A WARNING, not a refusal — Chad, on validation: "Skip it." Equipment
    # already on site from the last phase is a real zero. It should just never
    # be a silent one.
    #
    # And UNCHECKING the line is how you say so. Chad, 2026-09-04: "you have it
    # set to that when something shows an error if nothing is entered, I like
    # that so I can check it.. but that message should go away after I uncheck
    # it as not used."
    #
    # He is right, and the version I shipped had it exactly backwards: it fired
    # BECAUSE the box was unchecked, so the one gesture that means "considered,
    # not needed" was the one gesture that could not clear it. A warning you
    # cannot answer is a warning people learn to scroll past, which costs the
    # rest of the list its credibility too.
    #
    # So: no line at all, or a line that is ON and carrying nothing, warns —
    # that is the case where somebody has not looked. A line switched OFF is
    # somebody having looked.
    renting = any(
        r.enabled
        and (r.group_name or "equipment") == "equipment"
        and is_rental(r.unit)
        and _d(r.billable_units) > 0
        for r in equip_lines
    )
    mobil = next((r for r in equip_lines if r.code == "mobilization"), None)
    if renting and (mobil is None or (mobil.enabled and _d(mobil.ext_cost) <= 0)):
        out.add(
            "mobilization — not entered (this section rents equipment and "
            "carries nothing for getting it there)"
        )
    # Forming lines carry the same switch as of sql/056, for the same reason:
    # RESHORING on a deck has no rate anywhere, and until now there was no box
    # to uncheck and no way to make the line stop asking.
    for r in db.scalars(
        select(EstimateFormingLine).where(EstimateFormingLine.section_id == section.id)
    ):
        if r.enabled and r.unit_cost is None and _d(r.qty) > 0:
            out.add(f"{r.label} — forming")

    return sorted(out)


def catalog_cost_for_quote(
    db: Session, section: EstimateSection, quote_kind: str
) -> Decimal | None:
    """
    What this section's catalog would charge for the thing a quote replaces.

    The comparison shown beside every quote. Returns None when the figure cannot
    be built honestly — no takeoff yet, or no price behind it — because a
    PARTIAL total is worse than none: it invites subtracting it from the quote
    and calling the difference a saving. That rule is `rate_table_drill_cost`'s,
    generalised; drilling has had this comparison since piers were built and it
    is the only quote kind that ever had one.

    Rebar rates are resolved PER ROW, not once for the section. A post-tensioned
    pour and a plain one resolve to different catalog bar, and a slab section
    can hold both — blending them into one rate would produce a comparison that
    disagrees with the material breakdown on the same screen.

    Priced through the estimate's book (sql/048): "what would we have charged"
    means at THIS JOB's prices, or a negotiated mix rate makes every quote on
    the job read as off-band.
    """
    with priced_as(db, section.estimate_id), for_section(section.id):
        return _catalog_cost_for_quote(db, section, quote_kind)


def _catalog_cost_for_quote(
    db: Session, section: EstimateSection, quote_kind: str
) -> Decimal | None:
    from app.models.pier_group import PierGroup
    from app.services import quotes as qt
    from app.services.piers import rate_table_drill_cost

    if quote_kind == qt.DRILLING:
        groups = list(
            db.scalars(select(PierGroup).where(PierGroup.section_id == section.id)).all()
        )
        return rate_table_drill_cost(db, groups) if groups else None

    units = cost_units(db, section)
    if not units:
        return None

    total = _ZERO
    priced = False

    if quote_kind == qt.REBAR:
        for u in units:
            lb = _d(getattr(u.row, "calc_total_rebar_lb", 0))
            if lb <= 0:
                continue
            rate = _rebar_unit_cost(db, bool(getattr(u.row, "post_tension", False)), section.kind)
            if rate is None or rate <= 0:
                # A catalog with no price for this bar cannot say what the
                # quote should have been. Say nothing rather than say zero.
                return None
            total += lb * rate
            priced = True

    elif quote_kind == qt.PT:
        rate = _pt_sf_unit_cost(db)
        if rate is None or rate <= 0:
            return None
        for u in units:
            if not getattr(u.row, "post_tension", False):
                continue
            sf = _d(getattr(u.row, "square_footage", 0))
            if sf <= 0:
                continue
            total += sf * rate
            priced = True

    else:
        return None

    return total.quantize(_Q2) if priced else None


def _roll_up_parent(db: Session, section: EstimateSection) -> None:
    """
    Re-add the job from its sections, immediately after one of them changed.

    ## Why this lives here and not in the eleven callers

    The audit of 2026-09-02 found that **no takeoff endpoint rolled the job up**.
    `refresh_estimate_totals` had five callers, all section-level, while every
    grid save and row edit called `refresh_pour_costs` and stopped. One
    `PUT /api/wall-runs/bulk` moved its section from $162,920.41 to $237,719.77
    and left the estimate on $162,920.41. Measured elsewhere: a mono-slab PATCH
    $1,278,678.90 adrift, piers $287,256.13, columns $228,276.08.

    The obvious repair — add the call to each router — is the repair that
    created the bug. Eleven call sites across five routers each had to remember,
    and a twelfth arrives with every new assembly. Columns was that twelfth, and
    it forgot too, three days after the same class of bug cost $15,440.35.

    So the invariant is enforced structurally instead. The six assignments above
    are the **only** place `section.calc_total_cost` is written anywhere in the
    app — verified across services and routers — so a roll-up attached to them
    cannot be forgotten by code that does not exist yet. A new assembly gets it
    for free, which is the whole point.

    Cost of doing it here: `recalc_estimate` re-aggregates once per section
    rather than once at the end. That is one small SUM per section on a table
    with a section index, against a class of bug that has now produced four
    separate wrong totals. Correct and slightly redundant beats fast and
    silently wrong.

    `refresh_estimate_totals` flushes before it reads — it reads in raw SQL, and
    we have just written this section through the ORM under autoflush=False.
    That flush is the 2026-09-01 fix and this call depends on it.
    """
    from app.models.estimate import Estimate

    estimate = db.get(Estimate, section.estimate_id)
    if estimate is not None:
        refresh_estimate_totals(db, estimate)


def refresh_pour_costs_for_id(db: Session, section_id: UUID) -> dict[str, Any] | None:
    section = db.get(EstimateSection, section_id)
    if section is None:
        return None
    return refresh_pour_costs(db, section)


def refresh_estimate_totals(db: Session, estimate: Any) -> dict[str, Any]:
    """
    Roll the sections up onto the job. Does not commit.

    The estimate no longer computes anything of its own — it adds up what its
    sections priced, each at its own markup and its own tax treatment. Cost per
    unit is deliberately absent here: sections are measured in EA, SF, FF and
    LS, and a job-level "per SF" would be adding unlike units together.

    ## The flush is load-bearing

    This reads `estimate_sections` in raw SQL, and every caller reaches here
    having just written `section.calc_total_cost` on an ORM object. The app's
    session is built `autoflush=False` (app/db.py), so without this flush the
    SELECT below runs against the row as it was BEFORE the edit and the job
    total comes out one edit behind — silently, and only in production, since
    a plain Session autoflushes and the test harness therefore cannot see it.

    That was live for real: a mono slab moved $15,440.35, the section said so,
    and the estimate above it kept the old number until an unrelated recalc
    happened to roll it up again. Do not remove this line, and do not "fix" a
    stale total by adding a flush at the call site — there are five of them.
    """
    db.flush()

    rows = db.execute(
        text(
            "SELECT coalesce(sum(calc_total_cost), 0) AS cost, "
            "       coalesce(sum(calc_total_sale), 0) AS sale, "
            "       coalesce(sum(calc_total_tax), 0)  AS tax, "
            "       count(*)::int AS sections "
            "FROM estimate_sections WHERE estimate_id = :eid"
        ),
        {"eid": str(estimate.id)},
    ).mappings().one()

    estimate.calc_total_cost = _d(rows["cost"]).quantize(_Q2)
    estimate.calc_total_sale = _d(rows["sale"]).quantize(_Q2)
    estimate.calc_total_tax = _d(rows["tax"]).quantize(_Q2)
    estimate.calc_cost_per_sf = None
    estimate.calc_sale_per_sf = None

    return {
        "estimate_id": str(estimate.id),
        "sections": rows["sections"],
        "total_cost": estimate.calc_total_cost,
        "total_sale": estimate.calc_total_sale,
        "total_tax": estimate.calc_total_tax,
    }