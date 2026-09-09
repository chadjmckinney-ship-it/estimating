from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.project import PlansUrl


class BidStatus(str, Enum):
    not_started = "not_started"
    in_progress = "in_progress"
    submitted = "submitted"
    awarded = "awarded"
    canceled = "canceled"


def _blank_none(v):
    return None if v == "" else v


class BidRequestBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=500, examples=["EOS Fitness"])
    gc: str | None = Field(None, max_length=300, examples=["MYCON General Contractors"])
    location: str | None = Field(None, max_length=300)
    project_types: list[str] = Field(default_factory=list)
    status: BidStatus = BidStatus.not_started
    bid_due: date | None = None
    bid_due_time: time | None = None
    bid_date: date | None = None
    plans_url: PlansUrl = None
    bid_price: Decimal | None = None
    rev_date: date | None = None
    rev_price: Decimal | None = None
    notes: str | None = None
    message_id: str | None = None
    notion_page_id: str | None = None
    estimator_ids: list[UUID] = Field(default_factory=list)

    @field_validator(
        "gc", "location", "bid_due", "bid_due_time", "bid_date", "bid_price", "rev_date", "rev_price",
        "notes", "message_id", "notion_page_id", mode="before",
    )
    @classmethod
    def _blank_is_none(cls, v):
        return _blank_none(v)


class BidRequestCreate(BidRequestBase):
    pass


class BidRequestUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(None, min_length=1, max_length=500)
    gc: str | None = None
    location: str | None = None
    project_types: list[str] | None = None
    status: BidStatus | None = None
    bid_due: date | None = None
    bid_due_time: time | None = None
    bid_date: date | None = None
    plans_url: PlansUrl = None
    bid_price: Decimal | None = None
    rev_date: date | None = None
    rev_price: Decimal | None = None
    notes: str | None = None
    message_id: str | None = None
    notion_page_id: str | None = None
    estimator_ids: list[UUID] | None = None

    @field_validator(
        "gc", "location", "bid_due", "bid_due_time", "bid_date", "bid_price", "rev_date", "rev_price",
        "notes", "message_id", "notion_page_id", mode="before",
    )
    @classmethod
    def _blank_is_none(cls, v):
        return _blank_none(v)


class BidRequestRead(BaseModel):
    id: UUID
    name: str
    gc: str | None
    location: str | None
    project_types: list[str]
    status: str
    bid_due: date | None
    bid_due_time: time | None
    bid_date: date | None
    plans_url: str | None
    bid_price: Decimal | None
    rev_date: date | None
    rev_price: Decimal | None
    notes: str | None
    message_id: str | None
    notion_page_id: str | None
    project_id: UUID | None
    project_name: str | None = None
    estimator_ids: list[UUID]
    estimator_names: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class EstimateThisResult(BaseModel):
    """What "Estimate this" made: the bid as it now stands, and the project."""

    bid: BidRequestRead
    project_id: UUID


class ImportRow(BaseModel):
    """One row of a Notion export, as the MCP's rows mode hands it over."""

    model_config = ConfigDict(extra="allow")


class ImportResult(BaseModel):
    created: int
    updated: int
    unchanged: int
    skipped: int
    duplicates: list[str] = Field(default_factory=list)
    unknown_estimators: list[str] = Field(default_factory=list)
