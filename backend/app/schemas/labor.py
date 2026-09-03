from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class LaborDrivers(BaseModel):
    kind: str | None = None
    pour_count: int
    total_sf: Decimal
    drops_ff: Decimal
    # Paving (sql/036): curb LF carries its own labor line, and the per-area
    # $/SF adder lands on LABOR ADJUSTMENT.
    curb_lf: Decimal = Decimal("0")
    paving_add: Decimal = Decimal("0")
    # Piers: a count and drilled feet, and days nobody can derive.
    pier_count: int = 0
    total_lf: Decimal = Decimal("0")
    super_days_are_typed: bool = False
    # Walls: form feet on one face, plus the footing's plan area under it.
    wall_lf: Decimal = Decimal("0")
    form_ff: Decimal = Decimal("0")
    footing_sf: Decimal = Decimal("0")
    # Columns: the only assembly whose duration comes from a COUNT rather than
    # an area or a typed number of days — 20 a week on a five-day week. The
    # screen spells the derivation out, so it needs the two divisors and not
    # just the answer.
    #
    # A driver the schema does not name does not reach the screen: these were
    # computed and then dropped, and the labor card rendered a dash where the
    # column count belonged. tests/test_columns_ui_contract.py is the guard.
    column_count: int = 0
    form_sf: Decimal = Decimal("0")
    chamfer_lf: Decimal = Decimal("0")
    sf_per_week: Decimal = Decimal("0")
    days_per_week: Decimal = Decimal("0")
    foreman_days: Decimal = Decimal("0")
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
    section_id: UUID
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
    mark_manual: bool | None = Field(
        True,
        description="True pins the line against recalc; false hands it back to the "
        "company default; null leaves the flag alone.",
    )
