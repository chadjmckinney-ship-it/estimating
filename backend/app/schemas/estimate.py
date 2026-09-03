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
    pass


class EstimateUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    status: EstimateStatus | None = None
    estimator_id: UUID | None = None
    version: int | None = Field(None, ge=1)
    # Bounds must match EstimateBase/EstimateRead — a value that passes here but
    # fails on read is persisted first, then 500s every GET of this estimate.
    waste_concrete: Decimal | None = Field(None, ge=0, le=1)
    form_percent: Decimal | None = Field(None, ge=0, le=2)
    notes: str | None = None
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
