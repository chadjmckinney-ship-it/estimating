from datetime import datetime
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
    # extra="forbid" (audit 2026-09-04, P2 #8): a misspelled field on the
    # single largest material price in the app is a 422, not a silent 200.
    model_config = ConfigDict(extra="forbid")


class MixDesignUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

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


class MixDesignRead(MixDesignBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


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
