from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CostCodeRead(BaseModel):
    code: str
    name: str
    category: str
    category_label: str
    summary_column: str | None = None
    is_subtotal: bool = False
    sort_order: int


class SummaryLine(BaseModel):
    """One priced line of a section, with where the summary filed it."""

    kind: str            # purchase | material | labor | equipment | misc | uplift
    code: str
    label: str
    qty: Decimal | None = None
    unit: str | None = None
    cost: Decimal
    group: str | None = None
    inhouse: bool = False
    cost_code: str | None = None
    column: str


class SummaryColumn(BaseModel):
    key: str
    label: str


class SummarySection(BaseModel):
    id: UUID
    name: str
    kind: str
    unit: str
    quantity: Decimal | None = None
    sale: Decimal
    cost: Decimal
    tax: Decimal
    sale_per_unit: Decimal | None = None
    cost_per_unit: Decimal | None = None
    margin_pct: Decimal
    contingency_pct: Decimal
    labor_subcontracted: bool
    columns: dict[str, Decimal]
    per_unit: dict[str, Decimal]
    codes: dict[str, Decimal]
    contingency: Decimal
    profit: Decimal
    # The stored section cost less what the lines add to: cents of per-row
    # rounding, or a line set that was never built.
    difference: Decimal
    missing_line_sets: list[str] = []
    unassigned: list[SummaryLine] = []
    lines: list[SummaryLine] = []


class SummaryLower(BaseModel):
    """The block under the job-cost table: what the office reads first."""

    total_material: Decimal
    total_labor: Decimal
    total_sub_labor: Decimal
    total_other: Decimal
    sales_tax: Decimal
    unassigned: Decimal
    margin_contingency: Decimal
    estimated_profit: Decimal
    labor_insurance: Decimal
    labor_insurance_pct: Decimal
    contract_price: Decimal
    cost: Decimal
    difference: Decimal


class SummaryTotals(BaseModel):
    columns: dict[str, Decimal]
    codes: dict[str, Decimal]


class CostSummaryRead(BaseModel):
    estimate_id: UUID
    estimate_name: str
    estimate_status: str
    project_id: UUID
    project_name: str | None = None
    job_number: str | None = None
    gc: str | None = None
    location: str | None = None
    estimator_name: str | None = None
    generated_at: datetime
    file_name: str
    columns: list[SummaryColumn]
    sections: list[SummarySection]
    totals: SummaryTotals
    shares: dict[str, Decimal]
    lower: SummaryLower
    codes: list[CostCodeRead]


class CostCodeLineRead(BaseModel):
    kind: str
    code: str
    label: str
    cost_code: str | None = None
    inhouse_code: str | None = None
    # Whether a section on some estimate carries this line today.
    seen: bool = False


class CostCodesRead(BaseModel):
    codes: list[CostCodeRead]
    lines: list[CostCodeLineRead]


class CostCodeLineUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cost_code: str = Field(..., min_length=1, max_length=12)
    inhouse_code: str | None = Field(None, max_length=12)
