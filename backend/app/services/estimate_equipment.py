"""
Equipment takeoff for mono-slab estimates (Excel 04 EQUIPMENT).

Days ladder (from superintendent days E91):
  bands add: ≤3 → d; else base 7; +7 if 5–10; +14 if 10–15; +23 if 15–20;
  +53 if 20–40; +83 if 40–60; …  (e.g. 27 days → 7+53 = 60)

Rental tier billing (Excel O15 style, no markup):
  1–3 days: days × rate
  4–7: 3 × rate
  8–20: (days/7) × 3 × rate
  21–29: 9 × rate
  30+: (days/30) × 9 × rate

Pumping: concrete CY × $/CY (catalog).
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from app.services import paving as pv
from app.models.estimate_section import (
    COLUMN_KINDS,
    DECK_KINDS,
    PAVING_KINDS,
    PIER_KINDS,
    WALL_KINDS,
)
from app.services.calc import _rate_numeric, _setting_numeric, section_kind
from app.services.price_book import for_section, priced_as, require_book



def _d(x: Any) -> Decimal:
    return Decimal(str(x or 0))


def equip_days_from_super(super_days: float | Decimal) -> Decimal:
    """Excel additive band ladder on superintendent days."""
    d = float(super_days or 0)
    if d <= 0:
        return Decimal("0")
    total = 0.0
    # IF(E>0, IF(E<=3, E, 7), 0)
    total += d if d <= 3 else 7
    if 5 < d <= 10:
        total += 7
    if 10 < d <= 15:
        total += 14
    if 15 < d <= 20:
        total += 23
    if 20 < d <= 40:
        total += 53
    if 40 < d <= 60:
        total += 83
    if 60 < d <= 80:
        total += 113
    if 80 < d <= 100:
        total += 143
    if 100 < d <= 120:
        total += 163
    if d > 120:
        # extend roughly: +20 per 20 days past 120
        total += 163 + ((d - 120) // 20) * 20
    return Decimal(str(total)).quantize(Decimal("0.0001"))


def _use_rental_tiers(db: Session, kind: str | None) -> bool:
    """
    The company's rental-tier switch, read through the ladder like every
    other rate — job rule, then assembly, then the setting. Until 2026-09-06
    a raw read of system_settings overrode the ladder here (the ladder could
    not read the jsonb `true` the key is seeded with; since batch 2 it can),
    so a rule on a job was written, shown on the rules screen, and ignored
    (audit P3).
    """
    return _rate_numeric(db, kind, "equip_use_rental_tiers", Decimal("1")) > 0


def rental_billable_units(days: float | Decimal, use_tiers: bool = True) -> Decimal:
    """
    Convert calendar days to billable day-equivalents (Excel tier).
    Returns units such that cost = units × day_rate.
    """
    d = float(days or 0)
    if d <= 0:
        return Decimal("0")
    if not use_tiers:
        return Decimal(str(d)).quantize(Decimal("0.0001"))
    if d < 4:
        units = d
    elif d < 8:
        units = 3.0
    elif d < 21:
        units = (d / 7.0) * 3.0
    elif d < 30:
        units = 9.0
    else:
        units = (d / 30.0) * 9.0
    return Decimal(str(units)).quantize(Decimal("0.0001"))


def _super_days(db: Session, section_id: UUID) -> Decimal:
    """
    How many superintendent days this section carries — the number the whole
    rental ladder rides.

    ## The flush is load-bearing

    This reads `estimate_labor_summary` in raw SQL, and its most important
    caller arrives mid-write: `update_labor_line` sets `summary.super_days`
    through the ORM and then rewrites the equipment takeoff, which lands here.
    The app's session is `autoflush=False` (app/db.py), so without this flush
    the SELECT below returns the days as they were BEFORE the edit.

    On piers that is not a rounding error. Supervision days are TYPED there —
    there is no area to derive them from — so a stale zero gives a zero-day
    ladder, and every rental line prices at $0.00 with nothing on screen
    saying why. The section came out **$7,263.67 light**, and the totals still
    looked plausible.

    Second instance of the same bug; `refresh_estimate_totals` was the first.
    The rule both follow: **a reader that reads in raw SQL must flush first.**
    Do not move this to the call sites.
    """
    db.flush()

    # Prefer labor summary if present
    row = db.execute(
        text(
            """
            SELECT super_days FROM estimate_labor_summary
            WHERE section_id = :sid
            """
        ),
        {"sid": str(section_id)},
    ).scalar()
    if row is not None:
        return _d(row)
    # Fallback: SF / 16000 * 7
    sf = db.execute(
        text(
            "SELECT coalesce(sum(square_footage),0) FROM mono_slabs WHERE section_id = :sid"
        ),
        {"sid": str(section_id)},
    ).scalar()
    sf_per_week = _setting_numeric(db, "labor_super_sf_per_week", Decimal("16000"))
    days_per_week = _setting_numeric(db, "labor_super_days_per_week", Decimal("7"))
    sf = _d(sf)
    if sf_per_week <= 0 or sf <= 0:
        return Decimal("0")
    return (sf / sf_per_week * days_per_week).quantize(Decimal("0.0001"))


def equipment_drivers(db: Session, section_id: UUID) -> dict[str, Any]:
    kind = section_kind(db, section_id)
    if kind in PIER_KINDS:
        # Piers keeps its quantities in pier_groups, and its CY is what pumping
        # and haul-off ride on.
        prow = db.execute(
            text(
                "SELECT count(*)::int AS n, coalesce(sum(qty), 0)::int AS piers, "
                "       coalesce(sum(calc_concrete_cy), 0) AS cy, "
                "       coalesce(sum(calc_total_lf), 0) AS lf "
                "FROM pier_groups WHERE section_id = :sid"
            ),
            {"sid": str(section_id)},
        ).mappings().one()
        super_days = _super_days(db, section_id)
        return {
            "kind": kind,
            "pour_count": int(prow["n"] or 0),
            "pier_count": int(prow["piers"] or 0),
            "total_sf": Decimal("0"),
            "total_lf": _d(prow["lf"]),
            "super_days": super_days,
            "equip_days": equip_days_from_super(super_days),
            "total_concrete_cy": _d(prow["cy"]),
            "curb_lf": Decimal("0"),
            "demo_lf": Decimal("0"),
            "slip_form_sf": Decimal("0"),
            "traffic_control_sf": Decimal("0"),
            "construction_joint_lf": Decimal("0"),
            "control_joint_lf": Decimal("0"),
        }

    if kind in DECK_KINDS:
        # Deck levels, and a TYPED duration. The rental ladder rides the
        # superintendent's days exactly as it does on piers and walls, which
        # is why an untyped deck section prices every machine at $0.00 beside
        # a correct rate (audit #5).
        drow = db.execute(
            text(
                "SELECT count(*)::int AS n, "
                "       coalesce(sum(area_sf), 0) AS sf, "
                "       coalesce(sum(perm_edge_lf), 0) AS edge, "
                "       coalesce(sum(calc_concrete_cy), 0) AS cy, "
                "       coalesce(sum(calc_pt_sf), 0) AS pt_sf "
                "FROM deck_levels WHERE section_id = :sid"
            ),
            {"sid": str(section_id)},
        ).mappings().one()
        sd = _super_days(db, section_id)
        return {
            "kind": kind,
            "pour_count": int(drow["n"] or 0),
            "level_count": int(drow["n"] or 0),
            "pier_count": 0,
            "column_count": 0,
            "total_sf": _d(drow["sf"]),
            "total_lf": _d(drow["edge"]),
            "pt_sf": _d(drow["pt_sf"]),
            "super_days": sd,
            "equip_days": equip_days_from_super(sd),
            "total_concrete_cy": _d(drow["cy"]),
            "curb_lf": Decimal("0"),
            "demo_lf": Decimal("0"),
            "slip_form_sf": Decimal("0"),
            "traffic_control_sf": Decimal("0"),
            "construction_joint_lf": Decimal("0"),
            "control_joint_lf": Decimal("0"),
        }

    if kind in COLUMN_KINDS:
        # Column types, not pours. Supervision here is DERIVED from a count on
        # a five-day week (sql/045), so the rental ladder rides a duration
        # nothing else in the system produces.
        from app.services.columns import super_days as _column_super_days

        crow = db.execute(
            text(
                "SELECT count(*)::int AS n, "
                "       coalesce(sum(qty), 0)::int AS columns_n, "
                "       coalesce(sum(calc_form_sf), 0) AS sf, "
                "       coalesce(sum(calc_concrete_cy), 0) AS cy "
                "FROM column_types WHERE section_id = :sid"
            ),
            {"sid": str(section_id)},
        ).mappings().one()
        sd = _column_super_days(db, section_id, kind)
        return {
            "kind": kind,
            "pour_count": int(crow["n"] or 0),
            "pier_count": 0,
            "column_count": int(crow["columns_n"] or 0),
            "total_sf": _d(crow["sf"]),
            "total_lf": Decimal("0"),
            "super_days": sd,
            "equip_days": equip_days_from_super(sd),
            "total_concrete_cy": _d(crow["cy"]),
            "curb_lf": Decimal("0"),
            "demo_lf": Decimal("0"),
            "slip_form_sf": Decimal("0"),
            "traffic_control_sf": Decimal("0"),
            "construction_joint_lf": Decimal("0"),
            "control_joint_lf": Decimal("0"),
        }

    if kind in WALL_KINDS:
        # Wall runs, not pours — the CY that pumping rides lives in wall_runs.
        # Without this branch the pour query returns nothing and the pump line
        # silently prices at zero, which is exactly the class of quiet hole
        # this codebase keeps producing.
        wrow = db.execute(
            text(
                "SELECT count(*)::int AS n, "
                "       coalesce(sum(calc_concrete_cy), 0) AS cy, "
                "       coalesce(sum(calc_form_ff), 0) AS ff, "
                "       coalesce(sum(length_ft), 0) AS lf "
                "FROM wall_runs WHERE section_id = :sid"
            ),
            {"sid": str(section_id)},
        ).mappings().one()
        super_days = _super_days(db, section_id)
        return {
            "kind": kind,
            "pour_count": int(wrow["n"] or 0),
            "pier_count": 0,
            "total_sf": _d(wrow["ff"]),
            "total_lf": _d(wrow["lf"]),
            "super_days": super_days,
            "equip_days": equip_days_from_super(super_days),
            "total_concrete_cy": _d(wrow["cy"]),
            "curb_lf": Decimal("0"),
            "demo_lf": Decimal("0"),
            "slip_form_sf": Decimal("0"),
            "traffic_control_sf": Decimal("0"),
            "construction_joint_lf": Decimal("0"),
            "control_joint_lf": Decimal("0"),
        }

    row = db.execute(
        text(
            """
            SELECT
              count(*)::int AS pour_count,
              coalesce(sum(square_footage), 0) AS total_sf,
              coalesce(sum(calc_concrete_cy), 0) AS total_concrete_cy,
              -- Paving contract-service drivers (sql/036)
              coalesce(sum(curb_lf), 0) AS curb_lf,
              coalesce(sum(demo_lf), 0) AS demo_lf,
              coalesce(sum(square_footage) FILTER (WHERE slip_form), 0) AS slip_form_sf,
              coalesce(sum(square_footage) FILTER (WHERE traffic_control), 0)
                AS traffic_control_sf
            FROM mono_slabs
            WHERE section_id = :sid
            """
        ),
        {"sid": str(section_id)},
    ).mappings().one()
    super_days = _super_days(db, section_id)
    equip_days = equip_days_from_super(super_days)
    joints = pv.joints_for(_d(row["total_sf"]))
    return {
        "kind": section_kind(db, section_id),
        "pour_count": int(row["pour_count"] or 0),
        "total_sf": _d(row["total_sf"]),
        "super_days": super_days,
        "equip_days": equip_days,
        "total_concrete_cy": _d(row["total_concrete_cy"]),
        "curb_lf": _d(row["curb_lf"]),
        "demo_lf": _d(row["demo_lf"]),
        "slip_form_sf": _d(row["slip_form_sf"]),
        "traffic_control_sf": _d(row["traffic_control_sf"]),
        "construction_joint_lf": Decimal(joints.construction_lf),
        "control_joint_lf": Decimal(joints.control_lf),
    }


def _find_equip(db: Session, *parts: str) -> dict[str, Any] | None:
    clauses = " AND ".join(f"name ILIKE :p{i}" for i in range(len(parts)))
    params = {f"p{i}": f"%{p}%" for i, p in enumerate(parts)}
    row = db.execute(
        text(
            f"""
            SELECT id, code, name, unit, unit_cost
            FROM equipment
            WHERE is_active AND {clauses}
            ORDER BY sort_order, id
            LIMIT 1
            """
        ),
        params,
    ).mappings().first()
    # Resolved by name against the catalog, PRICED off this job's sheet
    # (sql/049) — the same split as costing._find_material.
    return require_book(f"equipment {' '.join(parts)!r}").price_equipment_row(
        dict(row) if row else None
    )


def _equip_rate(
    db: Session,
    kind: str | None,
    item: dict[str, Any] | None,
    rate_key: str,
    fallback: float,
) -> float:
    """
    What a day of this machine costs: the CATALOG, then an assembly rate, then
    a code default.

    Catalog first is the whole point (sql/044). A rate copied into
    `assembly_rates` out of a workbook cell is a second home for a price, and
    the second home is the one nobody updates — that is how piers billed steel
    at $0.75/lb for weeks after the sheet cell it came from turned out to be a
    typed-over lookup. An assembly rate still wins over the code default,
    because "this assembly rents at a different number" is a real thing to be
    able to say; it just should not outrank the price list.
    """
    return _equip_price(db, kind, item, rate_key, fallback)[0]


def _equip_price(
    db: Session,
    kind: str | None,
    item: dict[str, Any] | None,
    rate_key: str,
    fallback: float,
) -> tuple[float, str]:
    """
    `_equip_rate` plus WHERE the number came from: "catalog", "rate" or
    "default".

    Two things changed here on 2026-09-02 (price-sheet stage 0e):

      * a catalog price of ZERO no longer wins. `is not None` let a $0.00 row
        price a machine at nothing — zeroing MINI EXCAVATOR took the columns
        hoisting line to $0.00 while the same machine on walls fell back to
        $475, because that branch used a truthy check. A zero is not a price.
      * the source is reported, so a line that reached the code default —
        no catalog price, no assembly rate — can be marked `missing_price` and
        surfaced on the section, the way forming has always done. Chad: "I dont
        like concrete prices starting @ $0"; a rental priced from a literal in
        this file is the same failure wearing a different number.
    """
    if item and item.get("unit_cost") is not None and float(item["unit_cost"]) > 0:
        return float(item["unit_cost"]), item.get("price_source") or "catalog"
    rated = _rate_numeric(db, kind, rate_key, Decimal("NaN"))
    if not rated.is_nan():
        return float(rated), "rate"
    return float(fallback), "default"


def _priced(
    db: Session, kind: str | None, item: dict[str, Any] | None, rate_key: str, fallback: float
) -> dict[str, Any]:
    """`rate=` and `price_source=` for a day_line, from one lookup."""
    rate, source = _equip_price(db, kind, item, rate_key, fallback)
    return {"rate": rate, "price_source": source}


def calc_estimate_equipment(db: Session, section_id: UUID) -> dict[str, Any]:
    """A price gate (sql/049): every machine and rate below prices from the
    estimate's sheet. See services/price_book.py."""
    with priced_as(db, _estimate_id_of(db, section_id)), for_section(section_id):
        return _calc_estimate_equipment(db, section_id)


def _estimate_id_of(db: Session, section_id: UUID):
    return db.execute(
        text("SELECT estimate_id FROM estimate_sections WHERE id = :i"), {"i": str(section_id)}
    ).scalar()


def _calc_estimate_equipment(db: Session, section_id: UUID) -> dict[str, Any]:
    d = equipment_drivers(db, section_id)
    # Rates follow the assembly (sql/035); the company setting is the fallback.
    kind = section_kind(db, section_id)
    days = float(d["equip_days"])
    cy = float(d["total_concrete_cy"])
    use_tiers = _use_rental_tiers(db, kind)

    vault_rate = float(_rate_numeric(db, kind, "equip_vault_day_rate", Decimal("25")))
    misc_rate = float(_rate_numeric(db, kind, "equip_misc_day_rate", Decimal("55")))

    def day_line(
        *,
        code: str,
        label: str,
        rate: float,
        equipment_id: int | None,
        order: int,
        enabled: bool = True,
        notes: str | None = None,
        default_days: float | None = None,
        price_source: str | None = None,
    ) -> dict[str, Any]:
        dq = default_days if default_days is not None else days
        bill = rental_billable_units(dq, use_tiers=use_tiers)
        rt = _d(rate)
        ext = (bill * rt).quantize(Decimal("0.01")) if enabled else Decimal("0.00")
        return {
            "group_name": "equipment",
            "code": code,
            "label": label,
            "enabled": enabled,
            # Where the rate came from, and whether it is a real price. A line
            # priced from the code default on real days is UNPRICED — the
            # number beside it is a placeholder, not a quote.
            "price_source": price_source,
            "missing_price": price_source == "default" and enabled and bill > 0,
            "equipment_id": equipment_id,
            "days_qty": _d(dq).quantize(Decimal("0.0001")),
            "rate": rt.quantize(Decimal("0.0001")),
            "unit": "DAY",
            "billable_units": bill,
            "ext_cost": ext,
            "formula": (
                f"days from super ladder ({d['equip_days']}); "
                f"billable={bill} × rate"
                + (" (rental tiers)" if use_tiers else " (days×rate)")
            ),
            "notes": notes,
            "sort_order": order,
            "is_manual": False,
        }

    def qty_line(
        *,
        code: str,
        label: str,
        rate: float | Decimal,
        qty: float | Decimal,
        unit: str,
        formula: str,
        order: int,
        equipment_id: int | None = None,
        enabled: bool = True,
        notes: str | None = None,
    ) -> dict[str, Any]:
        """
        A contract service: billed on its own quantity, not on rental days.

        These never carry fuel & maintenance and are never taxed — saw cutting,
        pumping and demolition are work done, not things bought. Costing tells
        them apart by group, so they stay in "contract" even when priced by day.
        """
        q = _d(qty).quantize(Decimal("0.0001"))
        rt = _d(rate).quantize(Decimal("0.0001"))
        return {
            "group_name": "contract",
            "code": code,
            "label": label,
            "enabled": enabled,
            "equipment_id": equipment_id,
            "days_qty": q,
            "rate": rt,
            "unit": unit,
            "billable_units": q,
            "ext_cost": (q * rt).quantize(Decimal("0.01")) if enabled else Decimal("0.00"),
            "formula": formula,
            "notes": notes,
            "sort_order": order,
            "is_manual": False,
        }

    pump = _find_equip(db, "Pump") or _find_equip(db, "PUMP")
    tower = _find_equip(db, "TOWER LIGHT") or _find_equip(db, "LIGHT TOWER")

    # MOBILIZATION — every assembly, because every assembly brings iron to a
    # site (sql/053). Chad, 2026-09-04: "we need to add a price for
    # mobilization."
    #
    # The workbook prices it NOWHERE — every tab was searched, and the only
    # hits are the word "Mobile" beside supplier phone numbers. So this is not
    # a formula being reproduced; it is a cost the sheets have been leaving
    # out, on jobs that rent a $3,200/day crane.
    #
    # `rate` is one ROUND TRIP — there and home, not two figures. `days_qty`
    # is HOW MANY MOVES, so a job that mobilizes twice for two phases says 2
    # instead of somebody doubling a number in their head.
    #
    # Built here rather than six times below, because "every assembly
    # mobilizes" is the whole point and six copies is how one of them quietly
    # stops having it.
    mobilization = qty_line(
        code="mobilization", label="MOBILIZATION",
        rate=_rate_numeric(db, kind, "mobilization_ls", Decimal("0")),
        qty=0, unit="LS", formula="moves x round-trip cost (manual)", order=180,
        # Short on purpose: the reasoning is in the comment above, and the
        # screen only needs to say what to type. Every other note in this
        # block is one line.
        notes="There and back, once. Enter how many moves the job needs — "
              "not taxed, no fuel.",
    )

    if kind in PIER_KINDS:
        # 01-Piers rows 71–83. The ladder rides TYPED superintendent days
        # rather than an area, so a fresh piers section shows zero rental days
        # until somebody says how long the job is.
        sky = _find_equip(db, "SkyTrack") or _find_equip(db, "SKY")
        mini = _find_equip(db, "MINI EXCAVATOR") or _find_equip(db, "MINI")
        skid = _find_equip(db, "SKID STEER") or _find_equip(db, "SKID")
        piers_n = float(d.get("pier_count") or 0)

        lines = [
            day_line(
                code="skytrack", label="SKY TRACK",
                **_priced(db, kind, sky, "equip_skytrack_day_rate", 425),
                equipment_id=sky["id"] if sky else None, order=10,
                enabled=False, default_days=0,
                notes="Off by default — enable when used",
            ),
            day_line(
                code="mini_excavator", label="MINI EXCAVATOR",
                **_priced(db, kind, mini, "equip_mini_excavator_day_rate", 475),
                equipment_id=mini["id"] if mini else None, order=20,
                enabled=False, default_days=0,
                notes="Off by default — enable when used",
            ),
            day_line(
                code="skid_steer", label="SKID STEER",
                **_priced(db, kind, skid, "equip_skid_steer_day_rate", 325),
                equipment_id=skid["id"] if skid else None, order=30,
            ),
            day_line(
                code="light_tower", label="LIGHT TOWER",
                # Catalog first, the way skid_steer above already does it
                # (sql/044). This used to read an assembly_rates row while
                # attaching the catalog item's id — so the line LOOKED
                # catalog-linked on screen and ignored the catalog's price.
                **_priced(db, kind, tower, "equip_light_tower_day_rate", 100),
                equipment_id=tower["id"] if tower else None, order=40,
            ),
            day_line(code="vault", label="VAULT", rate=vault_rate,
                     equipment_id=None, order=50,
                     notes="The sheet exempts this one from fuel and tax; it is "
                           "billed as an ordinary rental here"),
            day_line(code="misc_equip", label="MISCELLANEOUS", rate=misc_rate,
                     equipment_id=None, order=60,
                     notes="The sheet bills this flat days × rate; the rental "
                           "tier is applied here as it is everywhere else"),
            qty_line(
                code="surveying", label="SURVEYING",
                rate=_rate_numeric(db, kind, "surveying_ea", Decimal("25")),
                qty=piers_n, unit="/EA", formula="piers × rate", order=100,
            ),
            qty_line(
                code="demo", label="DEMO",
                rate=_rate_numeric(db, kind, "demo_lf", Decimal("0")),
                qty=0, unit="/LF", formula="demo LF (manual)", order=110,
            ),
            qty_line(
                code="concrete_pump", label="CONCRETE PUMPING",
                rate=_rate_numeric(db, kind, "concrete_pump_cy", Decimal("20")),
                qty=cy, unit="CY", formula="concrete CY × $/CY", order=120,
                equipment_id=pump["id"] if pump else None,
            ),
            qty_line(
                code="haul_off", label="OFF SITE HAUL OFF",
                rate=_rate_numeric(db, kind, "haul_off_cy", Decimal("4")),
                qty=float(_d(cy) * _rate_numeric(db, kind, "haul_off_swell", Decimal("1.3"))),
                unit="CY", formula="concrete CY × 1.3 swell × $/CY", order=130,
            ),
            qty_line(
                code="out_of_town", label="OUT OF TOWN EXPENSE",
                rate=_rate_numeric(db, kind, "out_of_town_day_rate", Decimal("250")),
                qty=0, unit="MAN-DAY", formula="man-days away (manual)", order=140,
            ),
            qty_line(
                code="misc_contract", label="MISCELLANEOUS",
                rate=float(_rate_numeric(db, kind, "misc_contract_ls", Decimal("1000"))),
                qty=0, unit="LS", formula="lump sum (manual)", order=150,
            ),
        ]
        lines.append(mobilization)
        return _totals(d, lines, use_tiers)

    if kind in DECK_KINDS:
        # 08-CIP EL. DECK rows 105-118. The ladder is the one every assembly
        # uses; what is different is what is on it.
        #
        # THE CRANE. $3,200/day x 27 billable = $136,728 with fuel and tax —
        # 14% of the section on one line, and by far the largest single
        # equipment figure anywhere in the app. It is here because the deck
        # hangs in the air and everything that goes into it has to be lifted.
        #
        # MISCELLANEOUS is the fifth sighting of the fuel-and-tax quirk: the
        # sheet's formula for that ONE line ends without `x (1 + tax + fuel)`
        # where the five above it carry it. Slab, piers, walls, columns and
        # now deck. The app taxes it like any other rental and says so.
        lift = _find_equip(db, "20 TON") or _find_equip(db, "TON LIFT")
        crane = _find_equip(db, "CRANE")
        skid = _find_equip(db, "SKID STEER") or _find_equip(db, "SKID")
        tower = _find_equip(db, "TOWER LIGHT") or _find_equip(db, "LIGHT")
        sky = _find_equip(db, "SKY LIFT")

        lines = [
            day_line(
                code="lift_20_ton", label="20 TON LIFT",
                **_priced(db, kind, lift, "equip_20_ton_lift_day_rate", 850),
                equipment_id=lift["id"] if lift else None, order=10,
                default_days=0,
                notes="The sheet types 0 days on this job — set days if a "
                      "deck needs one",
            ),
            day_line(
                code="crane", label="CRANE & OPERATOR",
                **_priced(db, kind, crane, "equip_crane_day_rate", 3200),
                equipment_id=crane["id"] if crane else None, order=20,
                notes="The largest single equipment line in the app. Nothing "
                      "reaches an elevated deck without it.",
            ),
            day_line(
                code="skid_steer", label="SKID STEER",
                **_priced(db, kind, skid, "equip_skid_steer_day_rate", 325),
                equipment_id=skid["id"] if skid else None, order=30,
            ),
            day_line(
                code="light_tower", label="LIGHT TOWER",
                **_priced(db, kind, tower, "equip_light_tower_day_rate", 100),
                equipment_id=tower["id"] if tower else None, order=40,
            ),
            day_line(
                code="sky_lift", label="SKY LIFT",
                **_priced(db, kind, sky, "equip_skytrack_day_rate", 380),
                equipment_id=sky["id"] if sky else None, order=50,
                notes="The sheet files this under cost code 80061 SkyTrack. "
                      "It is the SKY LIFT — read the rate, not the label.",
            ),
            day_line(code="misc_equip", label="MISCELLANEOUS", rate=misc_rate,
                     equipment_id=None, order=60,
                     notes="The sheet exempts this one line from fuel and "
                           "tax. Fifth sheet it has done that on; the app "
                           "treats it as the rental it is."),

            # -------------------------------------------- contract services --
            qty_line(
                code="engineering", label="ENGINEERING",
                rate=_rate_numeric(db, kind, "engineering_sf", Decimal("1.05")),
                qty=0, unit="/SF", formula="SF engineered (manual)", order=110,
            ),
            qty_line(
                code="saw_cutting", label="SAW CUTTING",
                rate=_rate_numeric(db, kind, "saw_cutting_lf", Decimal("2.5")),
                qty=0, unit="/LF", formula="LF cut (manual)", order=120,
            ),
            qty_line(
                code="concrete_pump", label="CONCRETE PUMPING",
                rate=_rate_numeric(db, kind, "concrete_pump_cy", Decimal("10")),
                qty=cy, unit="CY", formula="concrete CY x $/CY", order=130,
                equipment_id=pump["id"] if pump else None,
                notes="Half the columns rate — a deck pump is a placing boom "
                      "on a full day, not a call-out",
            ),
            qty_line(
                code="freight", label="FREIGHT",
                rate=_rate_numeric(db, kind, "freight_load", Decimal("1100")),
                qty=0, unit="/LOAD", formula="loads (manual)", order=140,
            ),
            qty_line(
                code="waterproofing", label="WATERPROOFING",
                rate=_rate_numeric(db, kind, "waterproofing_sf", Decimal("2.25")),
                qty=0, unit="/SF", formula="SF waterproofed (manual)", order=150,
            ),
            qty_line(
                code="out_of_town", label="OUT OF TOWN EXPENSE",
                rate=_rate_numeric(db, kind, "out_of_town_day_rate", Decimal("225")),
                qty=0, unit="/DAY", formula="days away (manual)", order=160,
            ),
            qty_line(
                code="barricades", label="SUB CONTRACT BARRICADES",
                rate=_rate_numeric(db, kind, "barricades_lf", Decimal("1.45")),
                qty=0, unit="/LF", formula="LF barricaded (manual)", order=170,
            ),
        ]
        lines.append(mobilization)
        return _totals(d, lines, use_tiers)

    if kind in COLUMN_KINDS:
        # 07-COLUMNS rows 97-109. Two machines no other assembly bills:
        # HOISTING, which is how a cage and a form box reach the top of a
        # 24-foot column, and STORAGE, which is the gang-form yard.
        #
        # The sheet points HOISTING at Pricing!D33 — the MINI EXCAVATOR row.
        # That is the sheet's filing, not a claim that a column crew digs: the
        # rate is what a hoist costs and D33 is where the money came from.
        # Resolved to that catalog item so the price still tracks, and labelled
        # for what it is.
        sky = _find_equip(db, "SkyTrack") or _find_equip(db, "SKY")
        hoist = _find_equip(db, "MINI EXCAVATOR") or _find_equip(db, "MINI")
        skid = _find_equip(db, "SKID STEER") or _find_equip(db, "SKID")

        lines = [
            day_line(
                code="skytrack", label="SKY TRACK",
                # Its own key. Until 2026-09-06 this read the FORK TRUCK's
                # rate (audit P3) — dormant while the catalog priced the
                # machine, wrong the day it did not.
                **_priced(db, kind, sky, "equip_skytrack_day_rate", 425),
                equipment_id=sky["id"] if sky else None, order=10,
            ),
            day_line(
                code="hoisting", label="HOISTING",
                **_priced(db, kind, hoist, "equip_hoisting_day_rate", 475),
                equipment_id=hoist["id"] if hoist else None, order=20,
                notes="Priced off the sheet's Pricing!D33 row — a hoist, not an "
                      "excavator, whatever row it is filed under",
            ),
            day_line(
                code="skid_steer", label="SKID STEER",
                **_priced(db, kind, skid, "equip_skid_day_rate", 325),
                equipment_id=skid["id"] if skid else None, order=30,
            ),
            day_line(
                code="storage", label="STORAGE",
                rate=float(
                    _rate_numeric(db, kind, "equip_storage_day_rate", Decimal("105"))
                ),
                equipment_id=None, order=40,
                notes="The gang-form yard — no catalog item carries it",
            ),
            day_line(code="misc_equip", label="MISCELLANEOUS", rate=misc_rate,
                     equipment_id=None, order=50),
            qty_line(
                code="concrete_pump", label="CONCRETE PUMPING",
                rate=_rate_numeric(db, kind, "concrete_pump_cy", Decimal("20")),
                qty=cy, unit="CY", formula="concrete CY × $/CY", order=120,
                equipment_id=pump["id"] if pump else None,
            ),
            # Both OFF by default, with haul-off below. Chad, 2026-09-02, asked
            # whether these were real for columns or more workbook rows:
            # "furniture..". You do not cure or saw-cut a column — the rows are
            # on the 07 sheet because the sheet was built from a slab sheet.
            # Same treatment as haul-off: kept and disabled, so a job that
            # genuinely needs one is a checkbox rather than a missing line.
            qty_line(
                code="cure", label="DIAMOND HARD CURE",
                rate=_rate_numeric(db, kind, "cure_sf", Decimal("0.5")),
                qty=0, unit="/SF", formula="manual", order=130,
                enabled=False,
                notes="Not part of a columns bid — a column is rubbed and "
                      "patched, not cured. Turn it on if a job calls for it.",
            ),
            qty_line(
                code="saw_cutting", label="SAW CUTTING",
                rate=_rate_numeric(db, kind, "saw_cutting_lf", Decimal("2.5")),
                qty=0, unit="/LF", formula="manual", order=140,
                enabled=False,
                notes="Not part of a columns bid — nothing to saw. Turn it on "
                      "if a job calls for it.",
            ),
            qty_line(
                code="haul_off", label="OFF SITE HAUL OFF",
                rate=_rate_numeric(db, kind, "haul_off_cy", Decimal("6")),
                qty=0, unit="CY", formula="spoil CY (manual)", order=150,
                # OFF by default. Chad, 2026-09-02: "I think columns having
                # hauloff is an artifact from building the workbook.. there
                # shouldnt be hauloff.. and if there is, thats on us for a
                # mistake or a CO.. but we will need it for pilasters."
                #
                # A column is formed off a footing somebody else dug; there is
                # no spoil to haul. The line exists because the 07 sheet has
                # the row, which is how a workbook column becomes a feature.
                #
                # It is disabled rather than deleted because a PILASTER is a
                # columns section — sql/041, "I just use column sheet for it
                # since it is basically a short column" — and a pilaster does
                # dig. Tick it on there, or when a CO pays for hauling that a
                # mistake created. Off, the rate still shows, so turning it on
                # is one click and not a hunt for $/CY.
                enabled=False,
                notes="Not part of a columns bid — a column has no spoil. Turn "
                      "it on for a pilaster section, or for a change order.",
            ),
            qty_line(
                code="out_of_town", label="OUT OF TOWN EXPENSE",
                rate=_rate_numeric(db, kind, "out_of_town_day_rate", Decimal("200")),
                qty=0, unit="/DAY", formula="days away (manual)", order=160,
            ),
        ]
        lines.append(mobilization)
        return _totals(d, lines, use_tiers)

    if kind in WALL_KINDS:
        # 06-Walls & Footings rows 83–95. Same ladder as piers — it rides TYPED
        # superintendent days, because a wall job's duration comes from pour
        # sequence and cure, not from area.
        #
        # No trencher and no bobcat: a wall crew digs its footing trench with
        # the mini excavator, which is what the sheet bills. The lines that are
        # here and zero (sky track, vault) are lines the sheet HAS and types a
        # zero into — different from a line the sheet does not have at all,
        # which is simply absent.
        sky = _find_equip(db, "SkyTrack") or _find_equip(db, "SKY")
        mini = _find_equip(db, "MINI EXCAVATOR") or _find_equip(db, "MINI")
        skid = _find_equip(db, "SKID STEER") or _find_equip(db, "SKID")
        tower = _find_equip(db, "TOWER LIGHT") or _find_equip(db, "LIGHT")

        lines = [
            day_line(
                code="skytrack", label="SKY TRACK",
                **_priced(db, kind, sky, "equip_skytrack_day_rate", 425),
                equipment_id=sky["id"] if sky else None, order=10, default_days=0,
                notes="The sheet types 0 days on this job — set days if a wall "
                      "needs one",
            ),
            day_line(
                code="mini_excavator", label="MINI EXCAVATOR",
                **_priced(db, kind, mini, "equip_mini_excavator_day_rate", 475),
                equipment_id=mini["id"] if mini else None, order=20,
                notes="Digs the footing trench — there is no separate trencher "
                      "on a wall job",
            ),
            day_line(
                code="skid_steer", label="SKID STEER",
                **_priced(db, kind, skid, "equip_skid_steer_day_rate", 275),
                equipment_id=skid["id"] if skid else None, order=30,
            ),
            day_line(
                code="light_tower", label="LIGHT TOWER",
                **_priced(db, kind, tower, "equip_light_tower_day_rate", 100),
                equipment_id=tower["id"] if tower else None, order=40,
            ),
            day_line(code="vault", label="VAULT", rate=vault_rate,
                     equipment_id=None, order=50, default_days=0,
                     notes="The sheet types 0 days on this job"),
            day_line(code="misc_equip", label="MISCELLANEOUS", rate=misc_rate,
                     equipment_id=None, order=60),
            qty_line(
                code="concrete_pump", label="CONCRETE PUMPING",
                rate=_rate_numeric(db, kind, "concrete_pump_cy", Decimal("10")),
                qty=cy, unit="CY", formula="concrete CY × $/CY", order=120,
                equipment_id=pump["id"] if pump else None,
            ),
            qty_line(
                code="waterproofing", label="WATERPROOFING",
                rate=_rate_numeric(db, kind, "waterproofing_sf", Decimal("5.25")),
                qty=0, unit="/SF", formula="wall face SF (manual)", order=130,
                notes="Priced per SF of wall face when the job calls for it — "
                      "the sheet leaves it at zero here",
            ),
            qty_line(
                code="haul_off", label="OFF SITE HAUL OFF",
                rate=_rate_numeric(db, kind, "haul_off_cy", Decimal("6")),
                qty=0, unit="CY", formula="spoil CY (manual)", order=140,
            ),
            qty_line(
                code="out_of_town", label="OUT OF TOWN EXPENSE",
                rate=_rate_numeric(db, kind, "out_of_town_day_rate", Decimal("200")),
                qty=0, unit="MAN-DAY", formula="man-days away (manual)", order=150,
            ),
            qty_line(
                code="misc_contract", label="MISCELLANEOUS",
                rate=float(_rate_numeric(db, kind, "misc_contract_ls", Decimal("1000"))),
                qty=0, unit="LS", formula="lump sum (manual)", order=160,
            ),
        ]
        lines.append(mobilization)
        return _totals(d, lines, use_tiers)

    if kind in PAVING_KINDS:
        # 10-PAVING runs a Bob Cat, a light tower and a vault, all on the same
        # ladder off superintendent days, and prices its joints, demolition and
        # slip forming as contract services (sheet rows 75–88).
        bobcat = _find_equip(db, "BOB CAT") or _find_equip(db, "BOBCAT") or _find_equip(db, "SKID")
        tower = _find_equip(db, "TOWER LIGHT") or _find_equip(db, "LIGHT TOWER")
        fork = _find_equip(db, "FORK TRUCK") or _find_equip(db, "SkyTrack")
        drill = _find_equip(db, "EASY DRILL") or _find_equip(db, "DRILL")

        lines = [
            day_line(
                code="fork_truck", label="FORK TRUCK",
                rate=float(_rate_numeric(db, kind, "equip_fork_truck_day_rate", Decimal("425"))),
                equipment_id=fork["id"] if fork else None, order=10,
                enabled=False, default_days=0,
                notes="Off by default — enable when used",
            ),
            day_line(
                code="bobcat", label="BOB CAT",
                # The paving sheet calls it a Bob Cat; `equip_bobcat_day_rate`
                # was seeded from `10-PAVING!F76`, whose own comment points at
                # Pricing!D35 — the SKID STEER row. Same machine, so it reads
                # the same catalog item every other assembly reads (sql/044).
                **_priced(db, kind, bobcat, "equip_bobcat_day_rate", 325),
                equipment_id=bobcat["id"] if bobcat else None, order=20,
            ),
            day_line(
                code="easy_drill", label="EASY DRILL",
                rate=float(_rate_numeric(db, kind, "equip_easy_drill_day_rate", Decimal("350"))),
                equipment_id=drill["id"] if drill else None, order=30,
                enabled=False, default_days=0,
                notes="Off by default — enable when used",
            ),
            day_line(
                code="light_tower", label="LIGHT TOWER",
                **_priced(db, kind, tower, "equip_light_tower_day_rate", 100),
                equipment_id=tower["id"] if tower else None, order=40,
            ),
            day_line(code="vault", label="VAULT", rate=vault_rate,
                     equipment_id=None, order=50),
            # Barricades bill by the month and carry no fuel — they sit still.
            qty_line(
                code="barricades", label="BARRICADES",
                rate=_rate_numeric(db, kind, "barricades_month", Decimal("3500")),
                qty=0, unit="MONTH", formula="months on site (manual)", order=60,
                notes=(
                    f"{d['traffic_control_sf']:,.0f} SF marked for traffic control"
                    if d["traffic_control_sf"] else "Enter months when traffic control is needed"
                ),
            ),
            qty_line(
                code="joint_construction", label="HOT POUR JOINT SEALANT",
                rate=_rate_numeric(db, kind, "joint_construction_lf", Decimal("1.60")),
                qty=d["construction_joint_lf"], unit="LF",
                formula="ROUNDUP(total_sf / 60)", order=100,
            ),
            qty_line(
                code="joint_control", label="HOT POUR CTRL JOINT SEALANT",
                rate=_rate_numeric(db, kind, "joint_control_lf", Decimal("0.65")),
                qty=d["control_joint_lf"], unit="LF",
                formula="ROUNDUP(total_sf / 15 × 2 − construction joints)", order=110,
            ),
            qty_line(
                code="soft_cut", label="SOFT CUT",
                rate=_rate_numeric(db, kind, "joint_soft_cut_lf", Decimal("0.45")),
                qty=d["control_joint_lf"], unit="LF",
                formula="= control joint LF", order=120,
            ),
            qty_line(
                code="concrete_pump", label="CONCRETE PUMPING",
                rate=_rate_numeric(db, kind, "concrete_pump_cy", Decimal("0")),
                qty=cy, unit="CY", formula="total_concrete_cy × $/CY", order=130,
                equipment_id=pump["id"] if pump else None,
                notes="Paving is placed off the truck — rate 0 until a job needs a pump",
            ),
            qty_line(
                code="stamping", label="STAMPING",
                rate=_rate_numeric(db, kind, "stamping_sf", Decimal("2.50")),
                qty=0, unit="/SF", formula="stamped SF (manual)", order=140,
            ),
            qty_line(
                code="demo", label="DEMO",
                rate=_rate_numeric(db, kind, "demo_lf", Decimal("6")),
                qty=d["demo_lf"], unit="/LF", formula="Σ area demo LF × rate", order=150,
            ),
            qty_line(
                code="slip_forming", label="SLIP FORMING",
                rate=_rate_numeric(db, kind, "slip_form_sf", Decimal("5")),
                qty=d["slip_form_sf"], unit="/SF",
                formula="Σ SF of areas marked slip formed × rate", order=160,
            ),
            qty_line(
                code="form_rental", label="FORM RENTAL",
                rate=_rate_numeric(db, kind, "form_rental_contact_ft", Decimal("0.65")),
                qty=_d(d["curb_lf"])
                * _rate_numeric(db, kind, "form_rental_percent", Decimal("0")),
                unit="LF", formula="curb_lf × form rental % × $/contact ft", order=170,
                notes="Set form_rental_percent on the assembly to rent forms",
            ),
            qty_line(
                code="out_of_town", label="OUT OF TOWN EXPENSE",
                rate=_rate_numeric(db, kind, "out_of_town_day_rate", Decimal("200")),
                qty=0, unit="MAN-DAY", formula="man-days away (manual)", order=180,
            ),
        ]
        lines.append(mobilization)
        return _totals(d, lines, use_tiers)

    sky = _find_equip(db, "SkyTrack") or _find_equip(db, "SKY")
    mini = _find_equip(db, "MINI EXCAVATOR") or _find_equip(db, "MINI")
    trench = _find_equip(db, "TRENCHER")
    skid = _find_equip(db, "SKID STEER") or _find_equip(db, "SKID")

    lines: list[dict[str, Any]] = [
        day_line(
            code="skytrack",
            label="SKY TRACK",
            **_priced(db, kind, sky, "equip_skytrack_day_rate", 425),
            equipment_id=sky["id"] if sky else None,
            order=10,
            enabled=False,  # often 0 on SOG
            notes="Off by default — enable when used",
            default_days=0,
        ),
        day_line(
            code="mini_excavator",
            label="MINI EXCAVATOR",
            **_priced(db, kind, mini, "equip_mini_excavator_day_rate", 475),
            equipment_id=mini["id"] if mini else None,
            order=20,
        ),
        day_line(
            code="trencher",
            label="TRENCHER",
            **_priced(db, kind, trench, "equip_trencher_day_rate", 325),
            equipment_id=trench["id"] if trench else None,
            order=30,
        ),
        day_line(
            code="skid_steer",
            label="SKID STEER",
            **_priced(db, kind, skid, "equip_skid_steer_day_rate", 325),
            equipment_id=skid["id"] if skid else None,
            order=40,
        ),
        day_line(
            code="vault",
            label="VAULT",
            rate=vault_rate,
            equipment_id=None,
            order=50,
        ),
        day_line(
            code="misc_equip",
            label="MISCELLANEOUS",
            rate=misc_rate,
            equipment_id=None,
            order=60,
        ),
    ]

    # Contract / related
    pump_rate, pump_source = _equip_price(db, kind, pump, "concrete_pump_cy", 16)
    lines.append(
        qty_line(
            code="concrete_pump",
            label="CONCRETE PUMPING",
            rate=pump_rate,
            qty=cy,
            unit="CY",
            formula="total_concrete_cy × $/CY",
            order=100,
            equipment_id=pump["id"] if pump else None,
        )
    )
    lines.append(
        qty_line(
            code="haul_off",
            label="HAUL OFF",
            # A rate since 2026-09-06 (sql/065, audit P3): piers and columns
            # already read haul_off_cy at their own rates; the slab typed $12.50.
            rate=_rate_numeric(db, kind, "haul_off_cy", Decimal("12.5")),
            qty=0,
            unit="CY",
            formula="dirt CY (manual / later)",
            order=110,
            notes="Qty starts at 0",
        )
    )
    lines.append(
        qty_line(
            code="engineering",
            label="ENGINEERING",
            rate=_rate_numeric(db, kind, "engineering_sf", Decimal("0.20")),
            qty=d["total_sf"],
            unit="/SF",
            formula="total_sf × rate (off by default)",
            order=120,
            enabled=False,
        )
    )
    lines.append(mobilization)
    return _totals(d, lines, use_tiers)


def _totals(
    d: dict[str, Any], lines: list[dict[str, Any]], use_tiers: bool
) -> dict[str, Any]:

    equip_cost = sum(
        (_d(ln["ext_cost"]) for ln in lines if ln["group_name"] == "equipment"),
        Decimal("0"),
    ).quantize(Decimal("0.01"))
    contract_cost = sum(
        (_d(ln["ext_cost"]) for ln in lines if ln["group_name"] == "contract"),
        Decimal("0"),
    ).quantize(Decimal("0.01"))
    total = (equip_cost + contract_cost).quantize(Decimal("0.01"))
    cpsf = (total / d["total_sf"]).quantize(Decimal("0.0001")) if d["total_sf"] > 0 else None

    return {
        "drivers": d,
        "lines": lines,
        "total_equipment_cost": equip_cost,
        "total_contract_cost": contract_cost,
        "total_cost": total,
        "cost_per_sf": cpsf,
        "use_rental_tiers": use_tiers,
        # Lines whose rate is a code default on real days — a placeholder
        # standing where a price belongs. Forming has had this since sql/030.
        "missing_prices": [ln["label"] for ln in lines if ln.get("missing_price")],
        "stored": False,
        "refreshed_at": None,
    }


def refresh_and_store_equipment(db: Session, section_id: UUID) -> dict[str, Any]:
    from app.models.estimate_equipment import EstimateEquipmentLine, EstimateEquipmentSummary

    data = calc_estimate_equipment(db, section_id)
    drivers = data["drivers"]
    lines = data["lines"]

    existing = {
        r.code: r
        for r in db.scalars(
            select(EstimateEquipmentLine).where(
                EstimateEquipmentLine.section_id == section_id
            )
        ).all()
    }
    live_codes = {ln["code"] for ln in lines}
    manuals = {c: r for c, r in existing.items() if r.is_manual and c in live_codes}

    db.execute(
        delete(EstimateEquipmentLine).where(
            EstimateEquipmentLine.section_id == section_id,
            EstimateEquipmentLine.is_manual.is_(False),
        )
    )
    # A section that changes kind changes line set; a trencher does not follow
    # it into paving.
    stale = [c for c in existing if c not in live_codes]
    if stale:
        db.execute(
            delete(EstimateEquipmentLine).where(
                EstimateEquipmentLine.section_id == section_id,
                EstimateEquipmentLine.code.in_(stale),
            )
        )
    db.flush()
    now = datetime.now(timezone.utc)
    use_tiers = data.get("use_rental_tiers", True)

    for ln in lines:
        if ln["code"] in manuals:
            m = manuals[ln["code"]]
            m.formula = ln.get("formula")
            m.label = ln.get("label") or m.label
            m.unit = ln.get("unit") or m.unit
            m.group_name = ln["group_name"]
            m.sort_order = ln["sort_order"]
            m.equipment_id = ln.get("equipment_id")
            if m.rate_is_manual:
                m.price_source = "manual"
            else:
                # Typed days, live rate (sql/058): the ladder's answer today,
                # and where it came from — so a placeholder rate on a machine
                # somebody gave days still reads as the placeholder it is.
                m.rate = _d(ln["rate"])
                m.price_source = ln.get("price_source")
            # recompute cost from stored days/rate
            if m.unit == "DAY":
                m.billable_units = rental_billable_units(m.days_qty, use_tiers=use_tiers)
            else:
                m.billable_units = _d(m.days_qty)
            m.ext_cost = (
                (_d(m.billable_units) * _d(m.rate)).quantize(Decimal("0.01"))
                if m.enabled
                else Decimal("0.00")
            )
            m.updated_at = now
            continue

        # Rate comes from the equipment catalog / settings; only the on/off
        # toggle is preserved. Manual lines are handled above and keep theirs.
        prev = existing.get(ln["code"])
        enabled = prev.enabled if prev is not None else ln["enabled"]
        rate = ln["rate"]
        days_qty = ln["days_qty"]
        # SKYTRACK had the same special case the foreman line had in labor.py,
        # with the same comment ("if they set without is_manual") and the same
        # actual behaviour: it fired whenever `prev.days_qty > 0`, which is
        # true after the first refresh, so the line stopped tracking the
        # supervision ladder for good. `update_equipment_line` defaults
        # mark_manual=True, so days an estimator types are preserved by the
        # `manuals` branch above — which is the mechanism, and this was
        # quietly overriding it.
        #
        # Found alongside the foreman one, 2026-09-04: 14 days kept from a
        # takeoff that had since grown to 30. Both removed together.

        if ln["unit"] == "DAY":
            bill = rental_billable_units(days_qty, use_tiers=use_tiers)
        else:
            bill = _d(days_qty)
        ext = (_d(bill) * _d(rate)).quantize(Decimal("0.01")) if enabled else Decimal("0.00")

        db.add(
            EstimateEquipmentLine(
                section_id=section_id,
                group_name=ln["group_name"],
                code=ln["code"],
                label=ln["label"],
                enabled=enabled,
                equipment_id=ln.get("equipment_id"),
                days_qty=_d(days_qty),
                rate=_d(rate),
                unit=ln["unit"],
                billable_units=_d(bill),
                ext_cost=ext,
                formula=ln.get("formula"),
                notes=ln.get("notes"),
                sort_order=ln["sort_order"],
                is_manual=False,
                price_source=ln.get("price_source"),
            )
        )

    db.flush()
    all_rows = list(
        db.scalars(
            select(EstimateEquipmentLine)
            .where(EstimateEquipmentLine.section_id == section_id)
            .order_by(EstimateEquipmentLine.sort_order)
        ).all()
    )
    equip_cost = sum(
        (_d(r.ext_cost) for r in all_rows if r.group_name == "equipment"), Decimal("0")
    ).quantize(Decimal("0.01"))
    contract_cost = sum(
        (_d(r.ext_cost) for r in all_rows if r.group_name == "contract"), Decimal("0")
    ).quantize(Decimal("0.01"))
    total = (equip_cost + contract_cost).quantize(Decimal("0.01"))
    cpsf = (
        (total / drivers["total_sf"]).quantize(Decimal("0.0001"))
        if drivers["total_sf"] > 0
        else None
    )

    summary = db.get(EstimateEquipmentSummary, section_id)
    if summary is None:
        summary = EstimateEquipmentSummary(section_id=section_id)
        db.add(summary)
    summary.pour_count = drivers["pour_count"]
    summary.total_sf = drivers["total_sf"]
    summary.super_days = drivers["super_days"]
    summary.equip_days = drivers["equip_days"]
    summary.total_concrete_cy = drivers["total_concrete_cy"]
    summary.total_equipment_cost = equip_cost
    summary.total_contract_cost = contract_cost
    summary.total_cost = total
    summary.cost_per_sf = cpsf
    summary.refreshed_at = now
    from app.services.costing import refresh_pour_costs_for_id
    refresh_pour_costs_for_id(db, section_id)
    db.commit()
    return load_stored_equipment(db, section_id)


def load_stored_equipment(db: Session, section_id: UUID) -> dict[str, Any] | None:
    from app.models.estimate_equipment import EstimateEquipmentLine, EstimateEquipmentSummary

    summary = db.get(EstimateEquipmentSummary, section_id)
    if summary is None:
        return None
    rows = list(
        db.scalars(
            select(EstimateEquipmentLine)
            .where(EstimateEquipmentLine.section_id == section_id)
            .order_by(EstimateEquipmentLine.sort_order, EstimateEquipmentLine.code)
        ).all()
    )
    lines = [
        {
            "id": str(r.id),
            "group_name": r.group_name,
            "code": r.code,
            "label": r.label,
            "enabled": r.enabled,
            "equipment_id": r.equipment_id,
            "days_qty": r.days_qty,
            "rate": r.rate,
            "unit": r.unit,
            "billable_units": r.billable_units,
            "ext_cost": r.ext_cost,
            "formula": r.formula or "",
            "notes": r.notes,
            "sort_order": r.sort_order,
            "is_manual": r.is_manual,
            "rate_is_manual": bool(getattr(r, "rate_is_manual", False)),
            "price_source": r.price_source,
            "missing_price": (
                r.price_source == "default" and r.enabled and _d(r.billable_units) > 0
            ),
        }
        for r in rows
    ]
    # The geometry comes LIVE from equipment_drivers — pour columns and group
    # sums that cannot go stale between a refresh and a read — and the four
    # figures the lines were actually PRICED with come from the summary, so
    # the page explains the stored rows rather than a fresher ladder. Until
    # 2026-09-02 this dict was hand-built from six summary columns and served
    # a confident "0" for paving's 9,537 LF of curb and 36,361 LF of joints
    # (audit #9), the `load_stored_labor` bug over again.
    drivers = dict(equipment_drivers(db, section_id))
    drivers.update(
        pour_count=summary.pour_count,
        total_sf=summary.total_sf,
        super_days=summary.super_days,
        equip_days=summary.equip_days,
        total_concrete_cy=summary.total_concrete_cy,
    )
    return {
        "drivers": drivers,
        "lines": lines,
        "total_equipment_cost": summary.total_equipment_cost,
        "total_contract_cost": summary.total_contract_cost,
        "total_cost": summary.total_cost,
        "cost_per_sf": summary.cost_per_sf,
        # Derived from the stored rows, not a summary column: a line PATCH
        # (enable a placeholder-priced machine, give it days) must change this
        # without a full refresh, and the row is the only thing that knows.
        "missing_prices": [ln["label"] for ln in lines if ln.get("missing_price")],
        "stored": True,
        "refreshed_at": summary.refreshed_at.isoformat() if summary.refreshed_at else None,
    }


def get_or_refresh_equipment(db: Session, section_id: UUID) -> dict[str, Any]:
    stored = load_stored_equipment(db, section_id)
    if stored is not None:
        return stored
    return refresh_and_store_equipment(db, section_id)


def update_equipment_line(
    db: Session,
    section_id: UUID,
    code: str,
    *,
    enabled: bool | None = None,
    rate: Decimal | None = None,
    days_qty: Decimal | None = None,
    mark_manual: bool = False,
) -> dict[str, Any]:
    from app.models.estimate_equipment import EstimateEquipmentLine, EstimateEquipmentSummary

    row = db.scalars(
        select(EstimateEquipmentLine).where(
            EstimateEquipmentLine.section_id == section_id,
            EstimateEquipmentLine.code == code,
        )
    ).first()
    if not row:
        get_or_refresh_equipment(db, section_id)
        row = db.scalars(
            select(EstimateEquipmentLine).where(
                EstimateEquipmentLine.section_id == section_id,
                EstimateEquipmentLine.code == code,
            )
        ).first()
    if not row:
        raise ValueError(f"equipment line {code} not found")

    if enabled is not None:
        row.enabled = enabled
    if rate is not None:
        row.rate = _d(rate)
        if mark_manual:
            row.is_manual = True
            # Only a typed RATE pins the rate (sql/058).
            row.rate_is_manual = True
    if days_qty is not None:
        row.days_qty = _d(days_qty)
        if mark_manual:
            row.is_manual = True

    # As one section of its job, so a rule reaches this path too.
    with priced_as(db, _estimate_id_of(db, section_id)), for_section(section_id):
        use_tiers = _use_rental_tiers(db, section_kind(db, section_id))

    if row.unit == "DAY":
        row.billable_units = rental_billable_units(row.days_qty, use_tiers=use_tiers)
    else:
        row.billable_units = _d(row.days_qty)
    row.ext_cost = (
        (_d(row.billable_units) * _d(row.rate)).quantize(Decimal("0.01"))
        if row.enabled
        else Decimal("0.00")
    )
    row.updated_at = datetime.now(timezone.utc)
    db.flush()

    all_rows = list(
        db.scalars(
            select(EstimateEquipmentLine).where(
                EstimateEquipmentLine.section_id == section_id
            )
        ).all()
    )
    equip_cost = sum(
        (_d(r.ext_cost) for r in all_rows if r.group_name == "equipment"), Decimal("0")
    ).quantize(Decimal("0.01"))
    contract_cost = sum(
        (_d(r.ext_cost) for r in all_rows if r.group_name == "contract"), Decimal("0")
    ).quantize(Decimal("0.01"))
    total = (equip_cost + contract_cost).quantize(Decimal("0.01"))

    summary = db.get(EstimateEquipmentSummary, section_id)
    if summary:
        summary.total_equipment_cost = equip_cost
        summary.total_contract_cost = contract_cost
        summary.total_cost = total
        summary.cost_per_sf = (
            (total / summary.total_sf).quantize(Decimal("0.0001"))
            if summary.total_sf and summary.total_sf > 0
            else None
        )
        summary.refreshed_at = datetime.now(timezone.utc)
    from app.services.costing import refresh_pour_costs_for_id
    refresh_pour_costs_for_id(db, section_id)
    db.commit()
    return load_stored_equipment(db, section_id)  # type: ignore[return-value]
