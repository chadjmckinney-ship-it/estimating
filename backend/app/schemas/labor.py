from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class LaborDrivers(BaseModel):
    pour_count: int
    total_sf: Decimal
    drops_ff: Decimal
    total_rebar_lb: Decimal
    total_rebar_tons: Decimal
    super_weeks: Decimal
    super_days: Decimal


class LaborLine(BaseModel):
    id: str | None = None
    group_name: str
    code: str
    label: str
    enabled: bool = True
    rate: Decimal
    unit: str
    qty: Decimal
    ext_cost: Decimal
    formula: str = ""
    notes: str | None = None
    sort_order: int = 0
    is_manual: bool = False


class LaborMaterialsRead(BaseModel):
    estimate_id: UUID
    drivers: LaborDrivers
    lines: list[LaborLine] = Field(default_factory=list)
    total_labor_cost: Decimal = Decimal("0")
    total_supervision_cost: Decimal = Decimal("0")
    total_cost: Decimal = Decimal("0")
    cost_per_sf: Decimal | None = None
    stored: bool = False
    refreshed_at: datetime | str | None = None


class LaborLineUpdate(BaseModel):
    enabled: bool | None = None
    rate: Decimal | None = Field(None, ge=0)
    qty: Decimal | None = Field(None, ge=0)
    mark_manual: bool = True
