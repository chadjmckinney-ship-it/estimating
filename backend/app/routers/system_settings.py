"""
Company defaults (waste factors, lb/SF rates, labor and equipment rates).

Changing one of these has to rewrite stored results, or estimates keep showing
figures derived from the old default. PATCH here does that automatically; for
edits made directly in psql there is POST /system-settings/recalc-all.
"""

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.system_setting import (
    RecalcReport,
    SystemSettingRead,
    SystemSettingUpdate,
)
from app.services.price_book import MONETARY_KEYS, RULE_KEYS
from app.services.recalc import recalc_all_estimates, settings_scope

router = APIRouter(prefix="/system-settings", tags=["system-settings"])


# Which card a key is filed under. Ordered, and the FIRST match wins — so
# `equip_fuel_maint_pct` lands in "Tax & uplifts" beside the tax rate it
# compounds with, rather than in "Equipment" with the day rates.
#
# This lives here and not in JavaScript for the same reason `is_price` does:
# one taxonomy, served, so the screen cannot hold a copy that drifts.
_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Tax & uplifts", ("sales_tax_pct", "equip_fuel_maint_pct")),
    (
        "Supervision",
        (
            "labor_super_day_rate", "labor_foreman_day_rate", "labor_pm_day_rate",
            "labor_expense_day_rate", "labor_super_sf_per_week",
            "labor_super_days_per_week", "columns_per_super_week",
        ),
    ),
    ("Mobilization", ("mobilization_ls",)),
    ("Waste & allowances", (
        "waste_", "support_rebar_lb_per_sf", "pt_lb_per_sf",
        "labor_tie_steel_free_lb_per_sf", "haul_off_swell", "backfill_swell",
    )),
    # After the allowances above, so `labor_tie_steel_free_lb_per_sf`
    # files as the allowance it is rather than as a rate.
    ("Labor rates", ("labor_",)),
    ("Equipment", ("equip_", "out_of_town_day_rate")),
    ("Contract services", (
        "concrete_pump_cy", "haul_off_cy", "cure_sf", "saw_cutting_lf",
        "joint_", "demo_lf", "stamping_sf", "slip_form_sf", "surveying_ea",
        "waterproofing_sf", "barricades_", "engineering_sf", "freight_load",
        "form_rental_", "rock_cy", "misc_contract_ls",
    )),
    ("Forming quantities", (
        "form_percent", "form_waste", "lumber_", "nails_", "stakes_",
        "chamfer_", "chairs_", "patch_", "camlocks_", "wall_ties_",
        "pipe_brace_", "horiz_lap_", "sand_in_under_form", "cure_sf_per_gal",
        "pavecrete_", "accessories_", "reshoring_multiplier",
    )),
    ("Vapor barrier", ("default_vapor_", "vapor_")),
    ("Pier geometry", ("pier_",)),
    ("Quotes", ("quote_",)),
)


def _group_for(key: str) -> tuple[str, int]:
    """The card this key is filed under, and where that card sits."""
    for i, (name, prefixes) in enumerate(_GROUPS):
        if any(key == p or key.startswith(p) for p in prefixes):
            return name, i
    return "Other", len(_GROUPS)


def _note(out: dict[str, Any]) -> str:
    n = len(out["recalculated"])
    skipped = len(out["skipped"])
    note = f"Rewrote {n} estimate(s)."
    if skipped:
        note += (
            f" Left {skipped} final/archived estimate(s) at their bid numbers — "
            "reprice one from its own Recalculate button if you need to."
        )
    return note


def _row_to_read(row: Any) -> SystemSettingRead:
    key = row["key"]
    label, unit = MONETARY_KEYS.get(key, (None, None))
    is_price = key in MONETARY_KEYS
    return SystemSettingRead(
        key=key,
        value=row["text_value"],
        description=row["description"],
        updated_at=row["updated_at"],
        is_price=is_price,
        label=label,
        unit=unit,
        group=_group_for(key)[0],
        group_order=_group_for(key)[1],
        # jsonb null reads back as SQL NULL. EXISTS but unpriced — not zero.
        is_set=row["text_value"] is not None,
        scope=settings_scope([key]),
        unclassified=not is_price and key not in RULE_KEYS,
    )


@router.get("", response_model=list[SystemSettingRead])
def list_settings(
    prefix: str | None = Query(None, description="Filter by key prefix, e.g. labor_"),
    db: Session = Depends(get_db),
) -> list[SystemSettingRead]:
    # No str.format here: the jsonb operator `#>> '{}'` is itself a format
    # field, so formatting this string raises IndexError before it ever
    # reaches the database. That is why this endpoint has never returned.
    where = "WHERE key LIKE :p" if prefix else ""
    sql = (
        "SELECT key, value #>> '{}' AS text_value, description, updated_at "
        "FROM system_settings "
        f"{where} "
        "ORDER BY key"
    )
    params = {"p": f"{prefix}%"} if prefix else {}
    rows = db.execute(text(sql), params).mappings().all()
    return [_row_to_read(r) for r in rows]


@router.get("/{key}", response_model=SystemSettingRead)
def get_setting(key: str, db: Session = Depends(get_db)) -> SystemSettingRead:
    row = db.execute(
        text(
            "SELECT key, value #>> '{}' AS text_value, description, updated_at "
            "FROM system_settings WHERE key = :k"
        ),
        {"k": key},
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail=f"Unknown setting '{key}'")
    return _row_to_read(row)


@router.patch("/{key}", response_model=RecalcReport)
def update_setting(
    key: str,
    body: SystemSettingUpdate,
    recalc: bool = Query(
        True,
        description="Rewrite affected estimates. Only turn off to batch several "
        "edits, then call recalc-all.",
    ),
    db: Session = Depends(get_db),
) -> RecalcReport:
    exists = db.execute(
        text("SELECT 1 FROM system_settings WHERE key = :k"), {"k": key}
    ).scalar()
    if not exists:
        # Settings are seeded by migration; inventing keys here would create
        # values nothing reads.
        raise HTTPException(status_code=404, detail=f"Unknown setting '{key}'")

    db.execute(
        text(
            "UPDATE system_settings SET value = CAST(:v AS jsonb), updated_at = :t "
            "WHERE key = :k"
        ),
        {"k": key, "v": body.as_jsonb(), "t": datetime.now(timezone.utc)},
    )
    db.commit()

    scope = settings_scope([key])

    if not recalc:
        return RecalcReport(
            changed_keys=[key],
            scope=scope,
            recalculated=[],
            note="Saved without recalculating — stored estimates are now stale. "
            "Run POST /system-settings/recalc-all when your edits are done.",
        )
    if not any(scope.values()):
        return RecalcReport(
            changed_keys=[key],
            scope=scope,
            recalculated=[],
            note="Saved. This key feeds no stored calculation, so nothing needed rewriting.",
        )

    out = recalc_all_estimates(db, **scope)
    return RecalcReport(
        changed_keys=[key],
        scope=scope,
        recalculated=out["recalculated"],
        skipped=out["skipped"],
        note=_note(out),
    )


@router.post("/recalc-all", response_model=RecalcReport, status_code=status.HTTP_200_OK)
def recalc_all(
    pours: bool = Query(True),
    forming: bool = Query(True),
    labor: bool = Query(True),
    equipment: bool = Query(True),
    include_frozen: bool = Query(
        False,
        description="Also reprice final / archived estimates. Off by default — a "
        "bid that has gone out keeps the numbers it was bid with.",
    ),
    db: Session = Depends(get_db),
) -> RecalcReport:
    """
    Rewrite the open estimates from current inputs.

    Run this after editing catalog prices or system_settings — a direct UPDATE,
    and a catalog PATCH, cannot trigger anything on their own.
    """
    scope = {"pours": pours, "forming": forming, "labor": labor, "equipment": equipment}
    out = recalc_all_estimates(db, include_frozen=include_frozen, **scope)
    return RecalcReport(
        changed_keys=[],
        scope=scope,
        recalculated=out["recalculated"],
        skipped=out["skipped"],
        note=_note(out),
    )
