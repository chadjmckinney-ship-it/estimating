"""
Daily reports from the field (sql/084).

    /daily-reports                 list (job, foreman, dates, poured, search), file one
    /daily-reports/meta            what the form offers: jobs, foremen, suppliers, the grids' rows, the checks
    /daily-reports/summary         reports, pours, yards and man-hours by job and month
    /daily-reports/jobs            the job pick-list: list, add, edit, delete (its reports moved first)
    /daily-reports/foremen         the foreman pick-list: list, add, edit, delete (its reports moved, or not)
    /daily-reports/import          raw Jotform submissions, upserted by submission id
    /daily-reports/{id}            read, edit, delete

A foreman (app/policy.py) may read under here and file a report; the rest
is the office's.
"""

from datetime import date, datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import current_user
from app.db import get_db
from app.models.daily_report import DailyReport, FieldForeman, FieldJob
from app.models.estimator import Estimator
from app.schemas.daily_report import (
    DailyReportCreate,
    DailyReportMeta,
    DailyReportRead,
    DailyReportUpdate,
    FieldForemanCreate,
    FieldForemanRead,
    FieldForemanUpdate,
    FieldJobCreate,
    FieldJobRead,
    FieldJobUpdate,
    ImportBody,
    ImportResult,
    MoveResult,
    SummaryRow,
)
from app.services.daily_reports import (
    foreman_reads,
    import_submissions,
    job_reads,
    meta,
    reads,
    set_grids,
    summary,
    to_read,
)

router = APIRouter(prefix="/daily-reports", tags=["daily-reports"])

GRID_KEYS = ("crew", "subs")


def _or_404(db: Session, report_id: UUID) -> DailyReport:
    row = db.get(DailyReport, report_id)
    if not row:
        raise HTTPException(status_code=404, detail="Daily report not found")
    return row


def _job_or_400(db: Session, job_id: int) -> FieldJob:
    job = db.get(FieldJob, job_id)
    if job is None:
        raise HTTPException(status_code=400, detail="Unknown job")
    return job


def _name_conflict(what: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"A {what} with that name is already on the list")


# ------------------------------------------------------------ the lists --


@router.get("/meta", response_model=DailyReportMeta)
def daily_report_meta(db: Session = Depends(get_db)) -> DailyReportMeta:
    return DailyReportMeta(**meta(db))


@router.get("/summary", response_model=list[SummaryRow])
def daily_report_summary(
    job_id: int | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    db: Session = Depends(get_db),
) -> list[SummaryRow]:
    return [SummaryRow(**r) for r in summary(db, job_id, date_from, date_to)]


@router.get("/jobs", response_model=list[FieldJobRead])
def list_field_jobs(db: Session = Depends(get_db)) -> list[FieldJobRead]:
    return [FieldJobRead(**j) for j in job_reads(db)]


@router.post("/jobs", response_model=FieldJobRead, status_code=status.HTTP_201_CREATED)
def create_field_job(body: FieldJobCreate, db: Session = Depends(get_db)) -> FieldJobRead:
    row = FieldJob(**body.model_dump())
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise _name_conflict("job") from exc
    return next(FieldJobRead(**j) for j in job_reads(db) if j["id"] == row.id)


@router.patch("/jobs/{job_id}", response_model=FieldJobRead)
def update_field_job(job_id: int, body: FieldJobUpdate, db: Session = Depends(get_db)) -> FieldJobRead:
    row = db.get(FieldJob, job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Job not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        if k == "name" and v is None:
            continue
        setattr(row, k, v)
    row.updated_at = datetime.now(timezone.utc)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise _name_conflict("job") from exc
    return next(FieldJobRead(**j) for j in job_reads(db) if j["id"] == row.id)


@router.get("/foremen", response_model=list[FieldForemanRead])
def list_field_foremen(db: Session = Depends(get_db)) -> list[FieldForemanRead]:
    return [FieldForemanRead(**f) for f in foreman_reads(db)]


@router.post("/foremen", response_model=FieldForemanRead, status_code=status.HTTP_201_CREATED)
def create_field_foreman(body: FieldForemanCreate, db: Session = Depends(get_db)) -> FieldForemanRead:
    row = FieldForeman(**body.model_dump())
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise _name_conflict("foreman") from exc
    return next(FieldForemanRead(**f) for f in foreman_reads(db) if f["id"] == row.id)


@router.patch("/foremen/{foreman_id}", response_model=FieldForemanRead)
def update_field_foreman(foreman_id: int, body: FieldForemanUpdate, db: Session = Depends(get_db)) -> FieldForemanRead:
    row = db.get(FieldForeman, foreman_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Foreman not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        if k == "name" and v is None:
            continue
        setattr(row, k, v)
    row.updated_at = datetime.now(timezone.utc)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise _name_conflict("foreman") from exc
    return next(FieldForemanRead(**f) for f in foreman_reads(db) if f["id"] == row.id)


@router.delete("/jobs/{job_id}", response_model=MoveResult)
def delete_field_job(
    job_id: int,
    move_to: int | None = Query(None, description="The job its reports move to first"),
    db: Session = Depends(get_db),
) -> MoveResult:
    """A job with reports is refused until told where they go; nothing is left pointing at a job that is gone."""
    row = db.get(FieldJob, job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Job not found")
    db.flush()
    n = db.scalar(select(func.count()).select_from(DailyReport).where(DailyReport.job_id == job_id)) or 0
    if n and move_to is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{row.name} has {n} report{'' if n == 1 else 's'}; choose the job to move them to first",
        )
    moved = 0
    if n:
        if move_to == job_id or db.get(FieldJob, move_to) is None:
            raise HTTPException(status_code=400, detail="Unknown job to move the reports to")
        moved = db.execute(
            update(DailyReport)
            .where(DailyReport.job_id == job_id)
            .values(job_id=move_to, updated_at=datetime.now(timezone.utc))
        ).rowcount
    db.delete(row)
    db.commit()
    return MoveResult(moved=moved)


@router.delete("/foremen/{foreman_id}", response_model=MoveResult)
def delete_field_foreman(
    foreman_id: int,
    move_to: int | None = Query(None, description="The foreman whose name replaces this one on the reports; blank keeps the name as typed"),
    db: Session = Depends(get_db),
) -> MoveResult:
    """The reports name their foremen in text, so the list entry can go and the name stay; or the name moves."""
    row = db.get(FieldForeman, foreman_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Foreman not found")
    moved = 0
    if move_to is not None:
        target = db.get(FieldForeman, move_to)
        if target is None or move_to == foreman_id:
            raise HTTPException(status_code=400, detail="Unknown foreman to move the reports to")
        db.flush()
        gone = row.name.lower()
        for report in db.scalars(select(DailyReport)).all():
            names = list(report.foremen or [])
            if not any(n.lower() == gone for n in names):
                continue
            kept: list[str] = []
            for n in names:
                new = target.name if n.lower() == gone else n
                if new.lower() not in {k.lower() for k in kept}:
                    kept.append(new)
            report.foremen = kept
            report.updated_at = datetime.now(timezone.utc)
            moved += 1
    db.delete(row)
    db.commit()
    return MoveResult(moved=moved)


@router.post("/import", response_model=ImportResult)
def import_daily_reports(body: ImportBody, db: Session = Depends(get_db)) -> ImportResult:
    """Raw Jotform submissions of one form, upserted by submission id (backend/import_daily_reports.py)."""
    result = import_submissions(db, body.form_id, body.submissions)
    db.commit()
    return ImportResult(**result)


# ----------------------------------------------------------- the reports --


@router.get("", response_model=list[DailyReportRead])
def list_daily_reports(
    job_id: int | None = Query(None),
    foreman: str | None = Query(None, description="A foreman named on the report (case-insensitive)"),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    poured: bool | None = Query(None, description="true: pours only"),
    q: str | None = Query(None, description="Search the texts, the job and the foremen"),
    limit: int = Query(500, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> list[DailyReportRead]:
    stmt = select(DailyReport).order_by(DailyReport.report_date.desc(), DailyReport.submitted_at.desc())
    if job_id is not None:
        stmt = stmt.where(DailyReport.job_id == job_id)
    if date_from is not None:
        stmt = stmt.where(DailyReport.report_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(DailyReport.report_date <= date_to)
    if poured:
        stmt = stmt.where(DailyReport.concrete_poured.is_(True))
    rows = db.scalars(stmt).unique().all()
    if foreman:
        want = foreman.strip().lower()
        rows = [r for r in rows if any(n.lower() == want for n in (r.foremen or []))]
    if q:
        needle = q.strip().lower()

        def hay(r: DailyReport) -> str:
            return " ".join(
                str(x or "") for x in (
                    r.job.name if r.job else "", " ".join(r.foremen or []), r.work_accomplished, r.delays,
                    r.plan_tomorrow, r.safety_concerns, r.comments, r.what_poured, r.supplier,
                )
            ).lower()

        rows = [r for r in rows if needle in hay(r)]
    return [DailyReportRead(**r) for r in reads(db, rows[offset:offset + limit])]


@router.post("", response_model=DailyReportRead, status_code=status.HTTP_201_CREATED)
def create_daily_report(
    body: DailyReportCreate, db: Session = Depends(get_db), user: Estimator = Depends(current_user)
) -> DailyReportRead:
    _job_or_400(db, body.job_id)
    data = body.model_dump(exclude=set(GRID_KEYS))
    row = DailyReport(source="app", submitted_by=user.id, submitted_at=datetime.now(timezone.utc), **data)
    db.add(row)
    db.flush()
    set_grids(row, [c.model_dump() for c in body.crew], [s.model_dump() for s in body.subs])
    db.commit()
    db.refresh(row)
    return DailyReportRead(**to_read(db, row))


@router.get("/{report_id}", response_model=DailyReportRead)
def get_daily_report(report_id: UUID, db: Session = Depends(get_db)) -> DailyReportRead:
    return DailyReportRead(**to_read(db, _or_404(db, report_id)))


@router.patch("/{report_id}", response_model=DailyReportRead)
def update_daily_report(report_id: UUID, body: DailyReportUpdate, db: Session = Depends(get_db)) -> DailyReportRead:
    row = _or_404(db, report_id)
    data = body.model_dump(exclude_unset=True)
    crew = data.pop("crew", None)
    subs = data.pop("subs", None)
    if "job_id" in data:
        if data["job_id"] is None:
            data.pop("job_id")
        else:
            _job_or_400(db, data["job_id"])
    if "report_date" in data and data["report_date"] is None:
        data.pop("report_date")
    for k, v in data.items():
        setattr(row, k, v)
    set_grids(row, crew, subs)
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return DailyReportRead(**to_read(db, row))


@router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_daily_report(report_id: UUID, db: Session = Depends(get_db)) -> None:
    row = _or_404(db, report_id)
    db.delete(row)
    db.commit()
