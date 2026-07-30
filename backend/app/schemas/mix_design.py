from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class MixDesignBase(BaseModel):
    code: str = Field(..., min_length=1, max_length=64, examples=["3000-ASH-SOG"])
    name: str = Field(..., min_length=1, max_length=300, examples=["3000 PSI W/ ASH PIERS, SOG"])
    description: str | None = None
    strength_psi: int | None = Field(None, ge=1000, le=12000, examples=[3000])
    has_ash: bool = False
    has_air: bool = False
    sack_count: Decimal | None = Field(None, examples=[5.0])
    typical_use: str | None = Field(None, examples=["Piers, grade beams, SOG"])
    unit: str = "CY"
    unit_cost: Decimal | None = Field(None, examples=[155.00])
    sort_order: int = 0
    notes: str | None = None
    is_active: bool = True


class MixDesignCreate(MixDesignBase):
    pass


class MixDesignUpdate(BaseModel):
    code: str | None = Field(None, min_length=1, max_length=64)
    name: str | None = Field(None, min_length=1, max_length=300)
    description: str | None = None
    strength_psi: int | None = Field(None, ge=1000, le=12000)
    has_ash: bool | None = None
    has_air: bool | None = None
    sack_count: Decimal | None = None
    typical_use: str | None = None
    unit: str | None = None
    unit_cost: Decimal | None = None
    sort_order: int | None = None
    notes: str | None = None
    is_active: bool | None = None


class MixPriceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    mix_design_id: int
    supplier_id: int
    supplier_name: str | None = None
    unit_cost: Decimal
    price_as_of: date | None
    notes: str | None


class MixDesignRead(MixDesignBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
    prices: list[MixPriceRead] = Field(default_factory=list)


class ConcreteSupplierBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    contact_name: str | None = None
    phone: str | None = None
    notes: str | None = None
    is_active: bool = True


class ConcreteSupplierCreate(ConcreteSupplierBase):
    pass


class ConcreteSupplierUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    contact_name: str | None = None
    phone: str | None = None
    notes: str | None = None
    is_active: bool | None = None


class ConcreteSupplierRead(ConcreteSupplierBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class MixPriceCreate(BaseModel):
    mix_design_id: int
    supplier_id: int
    unit_cost: Decimal = Field(..., gt=0)
    price_as_of: date | None = None
    notes: str | None = None


class MixPriceUpdate(BaseModel):
    unit_cost: Decimal | None = Field(None, gt=0)
    price_as_of: date | None = None
    notes: str | None = None
