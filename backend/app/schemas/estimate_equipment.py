from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class EquipmentDrivers(BaseModel):
    kind: str | None = None
    pour_count: int
    total_sf: Decimal
    super_days: Decimal
    equip_days: Decimal
    total_concrete_cy: Decimal
    # Paving contract services (sql/036)
    curb_lf: Decimal = Decimal("0")
    demo_lf: Decimal = Decimal("0")
    slip_form_sf: Decimal = Decimal("0")
    traffic_control_sf: Decimal = Decimal("0")
    construction_joint_lf: Decimal = Decimal("0")
    control_joint_lf: Decimal = Decimal("0")
    # The other assemblies' geometry — produced by equipment_drivers since
    # piers / columns / walls were built and DROPPED here until 2026-09-02
    # (audit #9). A key this model does not name never reaches the screen.
    pier_count: int = 0
    column_count: int = 0
    total_lf: Decimal = Decimal("0")


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
    # Which half was typed (sql/058): `is_manual` is the days and the switch,
    # this is the rate. Typed days keep following the price sheet.
    rate_is_manual: bool = False
    # Where the rate came from — catalog | rate | default — and whether the
    # line is a placeholder standing where a price belongs (sql/047). A schema
    # that does not name a field drops it; see docs/specs/frontend-parse-and-drivers.md.
    price_source: str | None = None
    missing_price: bool = False


class EstimateEquipmentRead(BaseModel):
    section_id: UUID
    drivers: EquipmentDrivers
    lines: list[EstimateEquipmentLineRead] = Field(default_factory=list)
    total_equipment_cost: Decimal = Decimal("0")
    total_contract_cost: Decimal = Decimal("0")
    total_cost: Decimal = Decimal("0")
    cost_per_sf: Decimal | None = None
    # Labels of lines priced from a code default on real days (sql/047).
    missing_prices: list[str] = Field(default_factory=list)
    stored: bool = False
    refreshed_at: datetime | str | None = None


class EstimateEquipmentLineUpdate(BaseModel):
    enabled: bool | None = None
    rate: Decimal | None = Field(None, ge=0)
    days_qty: Decimal | None = Field(None, ge=0)
    mark_manual: bool = True
