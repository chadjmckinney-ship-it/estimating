from datetime import datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EstimateStatus(str, Enum):
    draft = "draft"
    in_review = "in_review"
    final = "final"
    archived = "archived"


class EstimateBase(BaseModel):
    project_id: UUID
    name: str = Field(..., min_length=1, max_length=200, examples=["Mono Slab base"])
    status: EstimateStatus = EstimateStatus.draft
    estimator_id: UUID | None = None
    version: int = Field(1, ge=1)
    notes: str | None = None
    margin_pct: Decimal = Field(
        Decimal("0.20"),
        ge=0,
        le=2,
        examples=[0.20],
        description="Default margin for new sections (0.20 = 20%). The priced figure lives on each section.",
    )
    contingency_pct: Decimal = Field(
        Decimal("0.03"),
        ge=0,
        le=2,
        examples=[0.03],
        description="Default contingency for new sections. The priced figure lives on each section.",
    )


class EstimateCreate(EstimateBase):
    # extra="forbid": a misspelled field is a 422, not a silent 200 (audit
    # 2026-09-04, P2 #8). The estimate modal sent three waste fields here for
    # a week after the columns left the table; nothing said so.
    model_config = ConfigDict(extra="forbid")


class EstimateUpdate(BaseModel):
    # Waste factors and form % are SECTION fields (sql/033–034) and rules on the
    # ladder (sql/055); the estimate has carried neither since sql/034. This
    # schema still declared `waste_concrete` and `form_percent`, and the router
    # setattr'd them onto an ORM row with no such column — a plain Python
    # attribute, dropped on commit — so the modal's waste inputs were accepted
    # and silently discarded (audit 2026-09-04, P2 #6). Gone, and forbidden.
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(None, min_length=1, max_length=200)
    status: EstimateStatus | None = None
    estimator_id: UUID | None = None
    version: int | None = Field(None, ge=1)
    notes: str | None = None
    # Bounds must match EstimateBase/EstimateRead — a value that passes here but
    # fails on read is persisted first, then 500s every GET of this estimate.
    margin_pct: Decimal | None = Field(None, ge=0, le=2)
    contingency_pct: Decimal | None = Field(None, ge=0, le=2)


class EstimateRead(EstimateBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime
    project_name: str | None = None
    estimator_name: str | None = None
    calc_total_cost: Decimal | None = None
    calc_total_sale: Decimal | None = None
    calc_cost_per_sf: Decimal | None = None
    calc_sale_per_sf: Decimal | None = None
