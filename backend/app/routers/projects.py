from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.estimator import Estimator
from app.models.project import Project, ProjectEstimator
from app.schemas.project import PROJECT_TYPE_OPTIONS, ProjectCreate, ProjectRead, ProjectUpdate

router = APIRouter(prefix="/projects", tags=["projects"])


def _to_read(row: Project) -> ProjectRead:
    return ProjectRead(
        id=row.id,
        name=row.name,
        job_number=row.job_number,
        location=row.location,
        gc=row.gc,
        project_types=list(row.project_types or []),
        status=row.status,
        bid_due=row.bid_due,
        bid_date=row.bid_date,
        plans_url=row.plans_url,
        bid_price=row.bid_price,
        rev_date=row.rev_date,
        rev_price=row.rev_price,
        notes=row.notes,
        notion_message_id=row.notion_message_id,
        notion_page_id=row.notion_page_id,
        created_by=row.created_by,
        estimator_ids=[link.estimator_id for link in (row.estimator_links or [])],
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _set_estimators(db: Session, project: Project, estimator_ids: list[UUID]) -> None:
    ids = list(dict.fromkeys(estimator_ids))
    if ids:
        found = set(db.scalars(select(Estimator.id).where(Estimator.id.in_(ids))).all())
        missing = [str(i) for i in ids if i not in found]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown estimator_ids: {missing}",
            )
    project.estimator_links.clear()
    db.flush()
    for eid in ids:
        project.estimator_links.append(
            ProjectEstimator(project_id=project.id, estimator_id=eid)
        )


@router.get("/meta/project-types", response_model=list[str])
def list_project_types(db: Session = Depends(get_db)) -> list[str]:
    """Notion Project Type options."""
    result = db.execute(
        text("SELECT name FROM project_type_options ORDER BY sort_order, name")
    )
    names = [r[0] for r in result]
    return names or list(PROJECT_TYPE_OPTIONS)


@router.get("/meta/statuses", response_model=list[str])
def list_statuses() -> list[str]:
    return [
        "not_started",
        "in_progress",
        "submitted",
        "awarded",
        "lost",
        "no_bid",
        "archived",
    ]


@router.get("", response_model=list[ProjectRead])
def list_projects(
    status_filter: str | None = Query(None, alias="status"),
    gc: str | None = Query(None, description="Substring match on GC"),
    q: str | None = Query(None, description="Search name / location / job_number"),
    db: Session = Depends(get_db),
) -> list[ProjectRead]:
    stmt = select(Project).order_by(Project.bid_due.nulls_last(), Project.name)
    if status_filter:
        stmt = stmt.where(Project.status == status_filter)
    if gc:
        stmt = stmt.where(Project.gc.ilike(f"%{gc}%"))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(
                Project.name.ilike(like),
                Project.location.ilike(like),
                Project.job_number.ilike(like),
            )
        )
    rows = list(db.scalars(stmt).unique().all())
    return [_to_read(r) for r in rows]


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(project_id: UUID, db: Session = Depends(get_db)) -> ProjectRead:
    row = db.get(Project, project_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return _to_read(row)


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(body: ProjectCreate, db: Session = Depends(get_db)) -> ProjectRead:
    if body.created_by and not db.get(Estimator, body.created_by):
        raise HTTPException(status_code=400, detail="created_by estimator not found")

    row = Project(
        name=body.name.strip(),
        job_number=body.job_number,
        location=body.location,
        notes=body.notes,
        created_by=body.created_by,
        gc=body.gc,
        project_types=body.project_types or [],
        status=body.status.value,
        bid_due=body.bid_due,
        bid_date=body.bid_date,
        plans_url=body.plans_url,
        bid_price=body.bid_price,
        rev_date=body.rev_date,
        rev_price=body.rev_price,
        notion_message_id=body.notion_message_id,
        notion_page_id=body.notion_page_id,
    )
    db.add(row)
    try:
        db.flush()
        _set_estimators(db, row, body.estimator_ids)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Conflict (duplicate notion_message_id?)",
        ) from exc
    db.refresh(row)
    return _to_read(row)


@router.patch("/{project_id}", response_model=ProjectRead)
def update_project(
    project_id: UUID,
    body: ProjectUpdate,
    db: Session = Depends(get_db),
) -> ProjectRead:
    row = db.get(Project, project_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    data = body.model_dump(exclude_unset=True)
    estimator_ids = data.pop("estimator_ids", None)
    if "status" in data and data["status"] is not None:
        data["status"] = (
            data["status"].value if hasattr(data["status"], "value") else data["status"]
        )
    if "name" in data and data["name"] is not None:
        data["name"] = data["name"].strip()
    if "created_by" in data and data["created_by"] is not None:
        if not db.get(Estimator, data["created_by"]):
            raise HTTPException(status_code=400, detail="created_by estimator not found")

    for key, value in data.items():
        setattr(row, key, value)
    row.updated_at = datetime.now(timezone.utc)

    try:
        if estimator_ids is not None:
            _set_estimators(db, row, estimator_ids)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Conflict updating project") from exc
    db.refresh(row)
    return _to_read(row)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_project(project_id: UUID, db: Session = Depends(get_db)) -> None:
    """Soft archive (status=archived)."""
    row = db.get(Project, project_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    row.status = "archived"
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
