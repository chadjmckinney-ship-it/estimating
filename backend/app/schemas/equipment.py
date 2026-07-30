from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class EquipmentCategory(str, Enum):
    earthwork = "earthwork"
    lifting = "lifting"
    power = "power"
    hauling = "hauling"
    pumping = "pumping"
    other = "other"


class EquipmentBase(BaseModel):
    code: str | None = Field(None, max_length=64, examples=["MINI-EXCAVATOR"])
    name: str = Field(..., min_length=1, max_length=200, examples=["MINI EXCAVATOR"])
    category: EquipmentCategory = EquipmentCategory.other
    unit: str = Field("DAY", max_length=20, examples=["DAY", "YD", "HOUR"])
    unit_cost: Decimal | None = Field(None, examples=[475.00])
    unit_note: str | None = None
    description: str | None = None
    is_owned: bool = False
    is_active: bool = True
    sort_order: int = 0
    price_as_of: date | None = None


class EquipmentCreate(EquipmentBase):
    pass


class EquipmentUpdate(BaseModel):
    code: str | None = Field(None, max_length=64)
    name: str | None = Field(None, min_length=1, max_length=200)
    category: EquipmentCategory | None = None
    unit: str | None = Field(None, max_length=20)
    unit_cost: Decimal | None = None
    unit_note: str | None = None
    description: str | None = None
    is_owned: bool | None = None
    is_active: bool | None = None
    sort_order: int | None = None
    price_as_of: date | None = None


class EquipmentRead(EquipmentBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_sheet: str | None = None
    source_row: int | None = None
    created_at: datetime
    updated_at: datetime
