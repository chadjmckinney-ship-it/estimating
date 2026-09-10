"""
The estimate Summary and the cost codes behind it (sql/088).

    /estimates/{id}/summary        the tab, as JSON
    /estimates/{id}/summary.xlsx   the tab, as the workbook
    /cost-codes                    the chart and where every line is filed
    /cost-codes/lines/{kind}/{code}   file a line (a senior estimator)
"""

from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.cost_code import LINE_KINDS, CostCode, CostCodeLine
from app.models.estimate import Estimate
from app.schemas.cost_summary import (
    CostCodeLineRead,
    CostCodeLineUpdate,
    CostCodesRead,
    CostSummaryRead,
)
from app.services.cost_summary import code_read, estimate_summary, lines_catalog, load_chart
from app.services.cost_summary_xlsx import build_workbook

router = APIRouter(tags=["cost-summary"])

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _estimate_or_404(db: Session, estimate_id: UUID) -> Estimate:
    row = db.get(Estimate, estimate_id)
    if not row:
        raise HTTPException(status_code=404, detail="Estimate not found")
    return row


@router.get("/estimates/{estimate_id}/summary", response_model=CostSummaryRead)
def get_summary(estimate_id: UUID, db: Session = Depends(get_db)) -> CostSummaryRead:
    """Every section's money by column and by cost code, the totals, the lower block."""
    return CostSummaryRead(**estimate_summary(db, _estimate_or_404(db, estimate_id)))


@router.get("/estimates/{estimate_id}/summary.xlsx")
def download_summary(estimate_id: UUID, db: Session = Depends(get_db)) -> Response:
    """The tab as a workbook, named `<Job> - Summary - <Job #> - <date>.xlsx`."""
    read = estimate_summary(db, _estimate_or_404(db, estimate_id))
    name = read["file_name"]
    ascii_name = name.encode("ascii", "ignore").decode() or "Summary.xlsx"
    return Response(
        content=build_workbook(read),
        media_type=XLSX,
        headers={
            "Content-Disposition": f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name)}",
            "X-Summary-File-Name": quote(name),
        },
    )


@router.get("/cost-codes", response_model=CostCodesRead)
def get_cost_codes(db: Session = Depends(get_db)) -> CostCodesRead:
    chart, _ = load_chart(db)
    return CostCodesRead(codes=[code_read(c) for c in chart], lines=lines_catalog(db))


def _code_or_400(db: Session, code: str | None, what: str) -> CostCode | None:
    if code is None or code == "":
        return None
    row = db.get(CostCode, code)
    if row is None:
        raise HTTPException(status_code=400, detail=f"No cost code {code!r} for the {what}")
    if row.is_subtotal:
        raise HTTPException(status_code=400, detail=f"{row.code} {row.name} is a subtotal of other codes; file the line under one of them")
    return row


@router.put("/cost-codes/lines/{kind}/{code}", response_model=CostCodeLineRead)
def file_line(kind: str, code: str, body: CostCodeLineUpdate, db: Session = Depends(get_db)) -> CostCodeLineRead:
    """Where a line goes from now on. The summary reads the table live, so every job follows."""
    if kind not in LINE_KINDS:
        raise HTTPException(status_code=404, detail=f"No such line kind {kind!r}; one of {', '.join(LINE_KINDS)}")
    _code_or_400(db, body.cost_code, "cost code")
    inhouse = body.inhouse_code or None
    if inhouse is not None and kind not in ("labor", "misc"):
        raise HTTPException(status_code=400, detail="Only a labor line takes an in-house code")
    _code_or_400(db, inhouse, "in-house code")
    row = db.get(CostCodeLine, (kind, code))
    if row is None:
        row = CostCodeLine(line_kind=kind, line_code=code, cost_code=body.cost_code, inhouse_code=inhouse)
        db.add(row)
    else:
        row.cost_code = body.cost_code
        row.inhouse_code = inhouse
    db.commit()
    match = next((ln for ln in lines_catalog(db) if ln["kind"] == kind and ln["code"] == code), None)
    return CostCodeLineRead(**match) if match else CostCodeLineRead(
        kind=kind, code=code, label=code, cost_code=body.cost_code, inhouse_code=inhouse, seen=False
    )
