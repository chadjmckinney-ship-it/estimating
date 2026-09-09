from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.daily_report import MAINTENANCE, SUB_TRADES, TRADES

TEXT_FIELDS = ("work_accomplished", "delays", "plan_tomorrow", "safety_concerns", "comments", "supplier", "what_poured")


def _blank_none(v):
    if isinstance(v, str) and not v.strip():
        return None
    return v


def _blank_zero(v):
    if v is None or (isinstance(v, str) and not v.strip()):
        return 0
    return v


def _names(v) -> list[str]:
    """Trimmed, non-empty, first occurrence wins."""
    out: list[str] = []
    for item in v or []:
        s = str(item or "").strip()
        if s and s.lower() not in {o.lower() for o in out}:
            out.append(s)
    return out


class CrewRow(BaseModel):
    """One trade on the man-power grid: workers, and the hours EACH worked."""

    model_config = ConfigDict(extra="forbid")

    trade: str
    workers: int = Field(0, ge=0, le=999)
    hours: Decimal = Field(Decimal(0), ge=0, le=24)

    @field_validator("trade")
    @classmethod
    def _known_trade(cls, v):
        if v not in TRADES:
            raise ValueError(f"trade must be one of {', '.join(TRADES)}")
        return v

    @field_validator("workers", "hours", mode="before")
    @classmethod
    def _blank_is_zero(cls, v):
        return _blank_zero(v)


class SubRow(BaseModel):
    """A subcontractor's crew on the job that day."""

    model_config = ConfigDict(extra="forbid")

    trade: str
    sub_name: str = Field(..., min_length=1, max_length=200)
    workers: int = Field(0, ge=0, le=999)
    hours: Decimal = Field(Decimal(0), ge=0, le=24)

    @field_validator("trade")
    @classmethod
    def _known_trade(cls, v):
        if v not in SUB_TRADES:
            raise ValueError(f"trade must be one of {', '.join(SUB_TRADES)}")
        return v

    @field_validator("workers", "hours", mode="before")
    @classmethod
    def _blank_is_zero(cls, v):
        return _blank_zero(v)

    @field_validator("sub_name", mode="before")
    @classmethod
    def _trim(cls, v):
        return v.strip() if isinstance(v, str) else v


class DailyReportBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_date: date
    job_id: int
    foremen: list[str] = Field(default_factory=list)
    work_accomplished: str | None = None
    delays: str | None = None
    plan_tomorrow: str | None = None
    safety_concerns: str | None = None
    comments: str | None = None
    concrete_poured: bool = False
    yards_poured: Decimal | None = Field(None, ge=0, le=99999)
    supplier: str | None = Field(None, max_length=200)
    what_poured: str | None = None
    tax_exempt: bool | None = None
    maintenance: list[str] = Field(default_factory=list)
    crew: list[CrewRow] = Field(default_factory=list)
    subs: list[SubRow] = Field(default_factory=list)

    @field_validator(*TEXT_FIELDS, "yards_poured", "tax_exempt", mode="before")
    @classmethod
    def _blank_is_none(cls, v):
        return _blank_none(v)

    @field_validator("foremen", mode="before")
    @classmethod
    def _foremen_names(cls, v):
        return _names(v)

    @field_validator("maintenance")
    @classmethod
    def _known_checks(cls, v):
        bad = [k for k in v if k not in MAINTENANCE]
        if bad:
            raise ValueError(f"maintenance keys must be among {', '.join(MAINTENANCE)}; got {bad}")
        return list(dict.fromkeys(v))

    @field_validator("crew")
    @classmethod
    def _one_row_per_trade(cls, v):
        seen = [r.trade for r in v]
        if len(seen) != len(set(seen)):
            raise ValueError("one crew row per trade")
        return v


class DailyReportCreate(DailyReportBase):
    pass


class DailyReportUpdate(BaseModel):
    """Every field optional; a grid given replaces the grid, a grid left out stays."""

    model_config = ConfigDict(extra="forbid")

    report_date: date | None = None
    job_id: int | None = None
    foremen: list[str] | None = None
    work_accomplished: str | None = None
    delays: str | None = None
    plan_tomorrow: str | None = None
    safety_concerns: str | None = None
    comments: str | None = None
    concrete_poured: bool | None = None
    yards_poured: Decimal | None = Field(None, ge=0, le=99999)
    supplier: str | None = Field(None, max_length=200)
    what_poured: str | None = None
    tax_exempt: bool | None = None
    maintenance: list[str] | None = None
    crew: list[CrewRow] | None = None
    subs: list[SubRow] | None = None

    @field_validator(*TEXT_FIELDS, "yards_poured", "tax_exempt", mode="before")
    @classmethod
    def _blank_is_none(cls, v):
        return _blank_none(v)

    @field_validator("foremen", mode="before")
    @classmethod
    def _foremen_names(cls, v):
        return None if v is None else _names(v)

    @field_validator("maintenance")
    @classmethod
    def _known_checks(cls, v):
        if v is None:
            return v
        bad = [k for k in v if k not in MAINTENANCE]
        if bad:
            raise ValueError(f"maintenance keys must be among {', '.join(MAINTENANCE)}; got {bad}")
        return list(dict.fromkeys(v))

    @field_validator("crew")
    @classmethod
    def _one_row_per_trade(cls, v):
        if v is None:
            return v
        seen = [r.trade for r in v]
        if len(seen) != len(set(seen)):
            raise ValueError("one crew row per trade")
        return v


class CrewRead(BaseModel):
    trade: str
    workers: int
    hours: Decimal
    man_hours: Decimal


class SubRead(BaseModel):
    trade: str
    sub_name: str
    workers: int
    hours: Decimal
    man_hours: Decimal


class DailyReportRead(BaseModel):
    id: UUID
    report_date: date
    job_id: int
    job_name: str
    foremen: list[str]
    work_accomplished: str | None
    delays: str | None
    plan_tomorrow: str | None
    safety_concerns: str | None
    comments: str | None
    concrete_poured: bool
    yards_poured: Decimal | None
    supplier: str | None
    what_poured: str | None
    tax_exempt: bool | None
    maintenance: list[str]
    source: str
    jotform_submission_id: str | None
    signature_url: str | None
    submitted_at: datetime
    submitted_by: UUID | None
    submitted_by_name: str | None
    crew: list[CrewRead]
    subs: list[SubRead]
    workers: int
    man_hours: Decimal
    sub_workers: int
    sub_man_hours: Decimal
    created_at: datetime
    updated_at: datetime


class FieldJobCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=200)
    project_id: UUID | None = None
    is_active: bool = True
    sort_order: int = 0

    @field_validator("name", mode="before")
    @classmethod
    def _trim(cls, v):
        return v.strip() if isinstance(v, str) else v

    @field_validator("project_id", mode="before")
    @classmethod
    def _blank_is_none(cls, v):
        return _blank_none(v)


class FieldJobUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(None, min_length=1, max_length=200)
    project_id: UUID | None = None
    is_active: bool | None = None
    sort_order: int | None = None

    @field_validator("name", mode="before")
    @classmethod
    def _trim(cls, v):
        return v.strip() if isinstance(v, str) else v

    @field_validator("project_id", mode="before")
    @classmethod
    def _blank_is_none(cls, v):
        return _blank_none(v)


class FieldJobRead(BaseModel):
    id: int
    name: str
    project_id: UUID | None
    project_name: str | None
    is_active: bool
    sort_order: int
    reports: int
    last_report: date | None


class FieldForemanCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=200)
    estimator_id: UUID | None = None
    is_active: bool = True
    sort_order: int = 0

    @field_validator("name", mode="before")
    @classmethod
    def _trim(cls, v):
        return v.strip() if isinstance(v, str) else v

    @field_validator("estimator_id", mode="before")
    @classmethod
    def _blank_is_none(cls, v):
        return _blank_none(v)


class FieldForemanUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(None, min_length=1, max_length=200)
    estimator_id: UUID | None = None
    is_active: bool | None = None
    sort_order: int | None = None

    @field_validator("name", mode="before")
    @classmethod
    def _trim(cls, v):
        return v.strip() if isinstance(v, str) else v

    @field_validator("estimator_id", mode="before")
    @classmethod
    def _blank_is_none(cls, v):
        return _blank_none(v)


class FieldForemanRead(BaseModel):
    id: int
    name: str
    estimator_id: UUID | None
    is_active: bool
    sort_order: int
    reports: int
    last_report: date | None


class LabelMeta(BaseModel):
    key: str
    en: str
    es: str


class DailyReportMeta(BaseModel):
    """What the form offers: the two pick-lists, the suppliers, the grids' rows and the checks."""

    jobs: list[FieldJobRead]
    foremen: list[FieldForemanRead]
    suppliers: list[str]
    trades: list[LabelMeta]
    sub_trades: list[str]
    maintenance: list[LabelMeta]


class SummaryRow(BaseModel):
    job_id: int
    job_name: str
    month: str
    reports: int
    pours: int
    yards: Decimal
    man_hours: Decimal
    sub_man_hours: Decimal


class ImportBody(BaseModel):
    """Raw Jotform submissions, as the API hands them over, with the form they came from."""

    model_config = ConfigDict(extra="forbid")

    form_id: str = Field(..., min_length=1, max_length=40)
    submissions: list[dict] = Field(..., max_length=2000)


class ImportResult(BaseModel):
    created: int
    updated: int
    unchanged: int
    skipped: int
    jobs_added: list[str] = Field(default_factory=list)
    foremen_added: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
