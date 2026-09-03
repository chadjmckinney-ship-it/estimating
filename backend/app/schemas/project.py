from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class ProjectStatus(str, Enum):
    not_started = "not_started"
    in_progress = "in_progress"
    submitted = "submitted"
    awarded = "awarded"
    lost = "lost"
    no_bid = "no_bid"
    archived = "archived"


# Notion Project Type options
PROJECT_TYPE_OPTIONS = [
    "Multifamily",
    "Retail",
    "Commercial",
    "Warehouse",
    "Parking Lot",
    "Elevated Deck",
    "Retaining Wall",
    "Other",
]


class ProjectBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=500, examples=["Crunch Fitness- Waxahachie"])
    job_number: str | None = Field(None, max_length=64)
    location: str | None = Field(None, max_length=300, examples=["Waxahachie, TX"])
    gc: str | None = Field(None, max_length=300, examples=["MEC General Contractors"])
    project_types: list[str] = Field(default_factory=list, examples=[["Retail"]])
    status: ProjectStatus = ProjectStatus.not_started
    bid_due: date | None = None
    bid_date: date | None = None
    plans_url: str | None = Field(None, examples=["https://app.buildingconnected.com/..."])
    bid_price: Decimal | None = None
    rev_date: date | None = None
    rev_price: Decimal | None = None
    notes: str | None = None
    tax_exempt: bool = False
    notion_message_id: str | None = None
    notion_page_id: str | None = None
    created_by: UUID | None = None
    estimator_ids: list[UUID] = Field(
        default_factory=list,
        description="Assigned estimators (Notion multi-select)",
    )


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=500)
    job_number: str | None = None
    location: str | None = None
    gc: str | None = None
    project_types: list[str] | None = None
    status: ProjectStatus | None = None
    bid_due: date | None = None
    bid_date: date | None = None
    plans_url: str | None = None
    bid_price: Decimal | None = None
    rev_date: date | None = None
    rev_price: Decimal | None = None
    notes: str | None = None
    tax_exempt: bool | None = None
    notion_message_id: str | None = None
    notion_page_id: str | None = None
    created_by: UUID | None = None
    estimator_ids: list[UUID] | None = None


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    job_number: str | None
    location: str | None
    gc: str | None
    project_types: list[str]
    status: str
    bid_due: date | None
    bid_date: date | None
    plans_url: str | None
    bid_price: Decimal | None
    rev_date: date | None
    rev_price: Decimal | None
    notes: str | None
    tax_exempt: bool
    notion_message_id: str | None
    notion_page_id: str | None
    created_by: UUID | None
    estimator_ids: list[UUID] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
