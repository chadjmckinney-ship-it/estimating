from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class MaterialRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str | None
    name: str
    category: str
    unit: str
    unit_cost: Decimal | None
    unit_note: str | None
    description: str | None
    supplier_ref: str | None
    price_as_of: date | None
    is_active: bool
    sort_order: int
    source_sheet: str | None = None
    created_at: datetime
    updated_at: datetime


class MaterialCreate(BaseModel):
    name: str = Field(..., min_length=1)
    category: str = Field(..., min_length=1)
    unit: str = Field(..., min_length=1, examples=["EA", "LF", "SF", "CY", "TON"])
    code: str | None = None
    unit_cost: Decimal | None = Field(None, ge=0)
    unit_note: str | None = None
    description: str | None = None
    supplier_ref: str | None = None
    price_as_of: date | None = None
    sort_order: int = 0


class MaterialUpdate(BaseModel):
    name: str | None = Field(None, min_length=1)
    category: str | None = Field(None, min_length=1)
    unit: str | None = Field(None, min_length=1)
    code: str | None = None
    unit_cost: Decimal | None = Field(None, ge=0)
    unit_note: str | None = None
    is_active: bool | None = None
    description: str | None = None
    supplier_ref: str | None = None
    price_as_of: date | None = None
    sort_order: int | None = None
