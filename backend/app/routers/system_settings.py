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
from app.services.recalc import recalc_all_estimates, settings_scope

router = APIRouter(prefix="/system-settings", tags=["system-settings"])


def _row_to_read(row: Any) -> SystemSettingRead:
    return SystemSettingRead(
        key=row["key"],
        value=row["text_value"],
        description=row["description"],
        updated_at=row["updated_at"],
    )


@router.get("", response_model=list[SystemSettingRead])
def list_settings(
    prefix: str | None = Query(None, description="Filter by key prefix, e.g. labor_"),
    db: Session = Depends(get_db),
) -> list[SystemSettingRead]:
    sql = """
        SELECT key, value #>> '{}' AS text_value, description, updated_at
        FROM system_settings
        {where}
        ORDER BY key
    """.format(where="WHERE key LIKE :p" if prefix else "")
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

    results = recalc_all_estimates(db, **scope)
    return RecalcReport(
        changed_keys=[key],
        scope=scope,
        recalculated=results,
        note=f"Saved and rewrote {len(results)} estimate(s).",
    )


@router.post("/recalc-all", response_model=RecalcReport, status_code=status.HTTP_200_OK)
def recalc_all(
    pours: bool = Query(True),
    forming: bool = Query(True),
    labor: bool = Query(True),
    equipment: bool = Query(True),
    db: Session = Depends(get_db),
) -> RecalcReport:
    """
    Rewrite every estimate from current inputs.

    Run this after editing system_settings in psql — a direct UPDATE cannot
    trigger anything on its own.
    """
    scope = {"pours": pours, "forming": forming, "labor": labor, "equipment": equipment}
    results = recalc_all_estimates(db, **scope)
    return RecalcReport(changed_keys=[], scope=scope, recalculated=results)
