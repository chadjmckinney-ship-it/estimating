from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class FormingDrivers(BaseModel):
    pour_count: int
    total_sf: Decimal
    perimeter_lf: Decimal
    drops_ff: Decimal
    mesh_sf: Decimal
    total_rebar_lb: Decimal
    form_percent: Decimal
    form_percent_is_override: bool = False
    form_percent_system_default: Decimal | None = None
    form_waste: Decimal


class FormPercentUpdate(BaseModel):
    """Set estimate form% and recalculate form lumber lines."""

    form_percent: Decimal = Field(
        ...,
        ge=0,
        le=2,
        examples=[0.50, 0.70, 1.0],
        description="% of forming (e.g. 0.5 = 50%). Applies to 2x4, 2x6, 2x10, ply, masonite only.",
    )


class FormingLine(BaseModel):
    id: str | None = None
    code: str
    label: str
    qty: Decimal
    unit: str
    formula: str = ""
    notes: str | None = None
    material_id: int | None = None
    material_name: str | None = None
    unit_cost: Decimal | None = None
    ext_cost: Decimal | None = None
    group: str = "forming"
    is_manual: bool = False


class FormingMaterialsRead(BaseModel):
    estimate_id: UUID
    drivers: FormingDrivers
    lines: list[FormingLine] = Field(default_factory=list)
    total_ext_cost: Decimal = Decimal("0")
    stored: bool = False
    refreshed_at: datetime | str | None = None
