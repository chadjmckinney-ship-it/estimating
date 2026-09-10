from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.material_order import KINDS

TEXT_FIELDS = ("supplier", "description", "unit", "order_number", "ordered_by", "notes")


class MaterialKind(str, Enum):
    rebar = "rebar"
    post_tension = "post_tension"
    other = "other"


class MaterialStatus(str, Enum):
    ordered = "ordered"
    confirmed = "confirmed"
    delivered = "delivered"
    canceled = "canceled"


def _blank_none(v):
    if isinstance(v, str) and not v.strip():
        return None
    return v.strip() if isinstance(v, str) else v


class MaterialOrderBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: MaterialKind
    ordered_on: date | None = None  # today when left blank
    job_id: int
    supplier: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=1, max_length=2000)
    quantity: Decimal | None = Field(None, ge=0, le=99999999)
    unit: str | None = Field(None, max_length=20)
    needed_by: date | None = None
    delivered_on: date | None = None
    order_number: str | None = Field(None, max_length=100)
    ordered_by: str | None = Field(None, max_length=200)  # the signed-in person when left blank
    notes: str | None = None
    status: MaterialStatus = MaterialStatus.ordered

    @field_validator(*TEXT_FIELDS, "quantity", "needed_by", "delivered_on", "ordered_on", mode="before")
    @classmethod
    def _blank_is_none(cls, v):
        return _blank_none(v)

    @field_validator("unit")
    @classmethod
    def _upper(cls, v):
        return v.upper() if isinstance(v, str) else v


class MaterialOrderCreate(MaterialOrderBase):
    pass


class MaterialOrderUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: MaterialKind | None = None
    ordered_on: date | None = None
    job_id: int | None = None
    supplier: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, min_length=1, max_length=2000)
    quantity: Decimal | None = Field(None, ge=0, le=99999999)
    unit: str | None = Field(None, max_length=20)
    needed_by: date | None = None
    delivered_on: date | None = None
    order_number: str | None = Field(None, max_length=100)
    ordered_by: str | None = Field(None, max_length=200)
    notes: str | None = None
    status: MaterialStatus | None = None

    @field_validator(*TEXT_FIELDS, "quantity", "needed_by", "delivered_on", "ordered_on", mode="before")
    @classmethod
    def _blank_is_none(cls, v):
        return _blank_none(v)

    @field_validator("unit")
    @classmethod
    def _upper(cls, v):
        return v.upper() if isinstance(v, str) else v


class MaterialOrderRead(BaseModel):
    id: UUID
    kind: str
    ordered_on: date
    job_id: int
    job_name: str
    supplier: str
    description: str
    quantity: Decimal | None
    unit: str | None
    needed_by: date | None
    delivered_on: date | None
    order_number: str | None
    ordered_by: str | None
    notes: str | None
    status: str
    created_by: UUID | None
    created_by_name: str | None
    created_at: datetime
    updated_at: datetime


class LabelMeta(BaseModel):
    key: str
    en: str
    es: str


class MaterialOrderMeta(BaseModel):
    kinds: list[LabelMeta]
    units: list[str]
    statuses: list[str]
    suppliers: list[str]  # the ones used before, most recent first


class MaterialSummaryRow(BaseModel):
    """What a job has ordered of a kind, in one unit."""

    job_id: int
    job_name: str
    kind: str
    unit: str | None
    orders: int
    quantity: Decimal


assert set(k.value for k in MaterialKind) == set(KINDS)
