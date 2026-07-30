from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class EquipmentDrivers(BaseModel):
    pour_count: int
    total_sf: Decimal
    super_days: Decimal
    equip_days: Decimal
    total_concrete_cy: Decimal


class EstimateEquipmentLineRead(BaseModel):
    id: str | None = None
    group_name: str
    code: str
    label: str
    enabled: bool = True
    equipment_id: int | None = None
    days_qty: Decimal
    rate: Decimal
    unit: str
    billable_units: Decimal
    ext_cost: Decimal
    formula: str = ""
    notes: str | None = None
    sort_order: int = 0
    is_manual: bool = False


class EstimateEquipmentRead(BaseModel):
    estimate_id: UUID
    drivers: EquipmentDrivers
    lines: list[EstimateEquipmentLineRead] = Field(default_factory=list)
    total_equipment_cost: Decimal = Decimal("0")
    total_contract_cost: Decimal = Decimal("0")
    total_cost: Decimal = Decimal("0")
    cost_per_sf: Decimal | None = None
    stored: bool = False
    refreshed_at: datetime | str | None = None


class EstimateEquipmentLineUpdate(BaseModel):
    enabled: bool | None = None
    rate: Decimal | None = Field(None, ge=0)
    days_qty: Decimal | None = Field(None, ge=0)
    mark_manual: bool = True
