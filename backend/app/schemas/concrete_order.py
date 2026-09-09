from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

TEXT_FIELDS = ("supplier", "mix", "order_number", "ordered_by", "notes")


class OrderStatus(str, Enum):
    ordered = "ordered"
    confirmed = "confirmed"
    poured = "poured"
    canceled = "canceled"


def _blank_none(v):
    if isinstance(v, str) and not v.strip():
        return None
    return v.strip() if isinstance(v, str) else v


class ConcreteOrderBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ordered_on: date | None = None  # today when left blank
    job_id: int
    supplier: str = Field(..., min_length=1, max_length=200)
    pour_date: date
    pour_time: time | None = None
    yards: Decimal = Field(..., gt=0, le=99999)
    mix: str | None = Field(None, max_length=200)
    order_number: str | None = Field(None, max_length=100)
    ordered_by: str | None = Field(None, max_length=200)  # the signed-in person when left blank
    notes: str | None = None
    status: OrderStatus = OrderStatus.ordered

    @field_validator(*TEXT_FIELDS, "pour_time", "ordered_on", mode="before")
    @classmethod
    def _blank_is_none(cls, v):
        return _blank_none(v)


class ConcreteOrderCreate(ConcreteOrderBase):
    pass


class ConcreteOrderUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ordered_on: date | None = None
    job_id: int | None = None
    supplier: str | None = Field(None, min_length=1, max_length=200)
    pour_date: date | None = None
    pour_time: time | None = None
    yards: Decimal | None = Field(None, gt=0, le=99999)
    mix: str | None = Field(None, max_length=200)
    order_number: str | None = Field(None, max_length=100)
    ordered_by: str | None = Field(None, max_length=200)
    notes: str | None = None
    status: OrderStatus | None = None

    @field_validator(*TEXT_FIELDS, "pour_time", "ordered_on", mode="before")
    @classmethod
    def _blank_is_none(cls, v):
        return _blank_none(v)


class ConcreteOrderRead(BaseModel):
    id: UUID
    ordered_on: date
    job_id: int
    job_name: str
    supplier: str
    pour_date: date
    pour_time: time | None
    yards: Decimal
    mix: str | None
    order_number: str | None
    ordered_by: str | None
    notes: str | None
    status: str
    created_by: UUID | None
    created_by_name: str | None
    created_at: datetime
    updated_at: datetime
