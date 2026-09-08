from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

Block = Literal["alternates", "equipment_rates", "labor_rates", "qualifications", "exclusions", "terms"]
Status = Literal["INCLUDED", "EXCLUDED"]


class Drawing(BaseModel):
    """One of the four drawing rows: the discipline, who drew it, the plan date."""

    model_config = ConfigDict(extra="forbid")

    discipline: str = Field(..., max_length=40)
    firm: str | None = None
    plan_date: date | None = None

    @field_validator("firm", "plan_date", mode="before")
    @classmethod
    def _blank_is_none(cls, v):
        return None if v == "" else v


class ProposalCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    estimate_id: UUID


class ProposalUpdate(BaseModel):
    """The header and the two sentences; everything the estimator types over."""

    model_config = ConfigDict(extra="forbid")

    rev: int | None = Field(None, ge=1)
    proposal_date: date | None = None
    submitted_to: str | None = None
    attn: str | None = None
    email: str | None = None
    phone: str | None = None
    job_label: str | None = None
    location: str | None = None
    intro: str | None = None
    payment_terms: str | None = None
    drawings: list[Drawing] | None = Field(None, max_length=8)
    notes: str | None = None

    @field_validator("rev", "proposal_date", "intro", "payment_terms", mode="before")
    @classmethod
    def _blank_keeps(cls, v):
        # A cleared box on a field that cannot be empty means "leave it".
        return None if v == "" else v


class ProposalSectionRow(BaseModel):
    """One row of the sections grid. `id` present = that section, absent = a new one."""

    model_config = ConfigDict(extra="forbid")

    id: UUID | None = None
    title: str | None = None
    sort_order: int | None = None


class ProposalSectionsBulk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rows: list[ProposalSectionRow] = Field(default_factory=list, max_length=100)
    delete_missing: bool = False


class ProposalLineRow(BaseModel):
    """One row of a section's lines grid."""

    model_config = ConfigDict(extra="forbid")

    id: UUID | None = None
    description: str | None = None
    qty: Decimal | None = Field(None, ge=0)
    unit: str | None = Field(None, max_length=10)
    status: Status | None = None
    unit_price: Decimal | None = None
    sort_order: int | None = None
    notes: str | None = None

    @field_validator("status", mode="before")
    @classmethod
    def _blank_status_is_included(cls, v):
        return "INCLUDED" if v in (None, "") else v


class ProposalLinesBulk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rows: list[ProposalLineRow] = Field(default_factory=list, max_length=500)
    delete_missing: bool = False


class ItemsUpdate(BaseModel):
    """A whole block, in order: one string per bullet or numbered paragraph."""

    model_config = ConfigDict(extra="forbid")

    items: list[str] = Field(default_factory=list, max_length=200)


# --------------------------------------------------------------- reads ----


class ProposalLineRead(BaseModel):
    id: UUID
    sort_order: int
    description: str
    qty: Decimal | None
    unit: str | None
    status: str
    unit_price: Decimal | None
    extended: Decimal
    source_table: str | None
    source_id: UUID | None
    source_label: str | None = None
    source_missing: bool
    notes: str | None


class ProposalSectionRead(BaseModel):
    id: UUID
    title: str
    sort_order: int
    section_id: UUID | None
    estimate_section_name: str | None = None
    estimate_section_kind: str | None = None
    estimate_sale: Decimal | None = None
    total: Decimal
    difference: Decimal | None = None
    line_count: int
    lines: list[ProposalLineRead]


class ProposalItemRead(BaseModel):
    id: UUID
    sort_order: int
    text: str


class ProposalRead(BaseModel):
    id: UUID
    estimate_id: UUID
    estimate_name: str | None = None
    project_name: str | None = None
    rev: int
    proposal_date: date
    submitted_to: str | None
    attn: str | None
    email: str | None
    phone: str | None
    job_label: str | None
    location: str | None
    intro: str
    payment_terms: str
    drawings: list[Drawing]
    notes: str | None
    sections: list[ProposalSectionRead]
    items: dict[str, list[ProposalItemRead]]
    total: Decimal
    estimate_sale: Decimal | None = None
    difference: Decimal | None = None
    file_name: str
    created_at: datetime
    updated_at: datetime


class RefreshResult(BaseModel):
    """What a refresh from the estimate did, and the proposal after it."""

    updated: int
    added_lines: int
    added_sections: int
    missing: int
    proposal: ProposalRead


class LibraryItemRead(BaseModel):
    id: int
    sort_order: int
    text: str


class LibraryRead(BaseModel):
    """Every block of the standing text, in order."""

    blocks: dict[str, list[LibraryItemRead]]
