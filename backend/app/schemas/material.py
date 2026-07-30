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


class MaterialUpdate(BaseModel):
    unit_cost: Decimal | None = None
    unit_note: str | None = None
    is_active: bool | None = None
    description: str | None = None
    supplier_ref: str | None = None
    price_as_of: date | None = None
