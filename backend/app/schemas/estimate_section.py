from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.estimate_section import SECTION_KINDS
from app.schemas.section_quote import SectionQuoteRead


class EstimateSectionBase(BaseModel):
    kind: str = Field(..., examples=["mono_slab"])
    name: str = Field(..., min_length=1, max_length=200)
    unit: str | None = Field(
        None,
        max_length=8,
        description="EA, SF, FF, LF, LS. Defaults from the kind when omitted.",
    )
    sort_order: int = 0
    margin_pct: Decimal | None = Field(None, ge=0, le=2)
    contingency_pct: Decimal | None = Field(None, ge=0, le=2)
    # Tri-state. NULL inherits projects.tax_exempt; true/false override it for
    # this section — ROW paving and sidewalks inside a taxable job.
    tax_exempt: bool | None = None
    # One switch per section (sql/052). The CIP deck sheet decides it per
    # labor line; Chad, 2026-09-04, asked whether that is real: one switch.
    # Supervision is never subbed.
    labor_subcontracted: bool = False
    form_percent: Decimal | None = Field(None, ge=0, le=2)
    waste_concrete: Decimal | None = Field(None, ge=0, le=1)
    waste_sand: Decimal | None = Field(None, ge=0, le=1)
    waste_rebar: Decimal | None = Field(None, ge=0, le=1)
    vapor_barrier_material_id: int | None = None
    vapor_tape_material_id: int | None = None
    # Walls only (sql/040). The mix every FOOTING in this section is poured
    # from, where the wall above takes its mix per row. Without this on the
    # schema the column existed, costing read it, and nothing could write it —
    # the same shape as the sql/037 drilling quote.
    footing_mix_design_id: int | None = None
    notes: str | None = None


class EstimateSectionCreate(EstimateSectionBase):
    pass


class EstimateSectionUpdate(BaseModel):
    # A PATCH that silently ignored an unknown field is how footing_mix_design_id
    # went a whole build without anyone being able to set it — the write
    # returned 200 and changed nothing. A typo here is now a 422.
    model_config = ConfigDict(extra="forbid")

    kind: str | None = None
    name: str | None = Field(None, min_length=1, max_length=200)
    unit: str | None = Field(None, max_length=8)
    sort_order: int | None = None
    # Bounds must match the read model — a value that passes here but fails on
    # read is persisted first, then 500s every GET of this section.
    margin_pct: Decimal | None = Field(None, ge=0, le=2)
    contingency_pct: Decimal | None = Field(None, ge=0, le=2)
    tax_exempt: bool | None = None
    labor_subcontracted: bool | None = None
    form_percent: Decimal | None = Field(None, ge=0, le=2)
    waste_concrete: Decimal | None = Field(None, ge=0, le=1)
    waste_sand: Decimal | None = Field(None, ge=0, le=1)
    waste_rebar: Decimal | None = Field(None, ge=0, le=1)
    vapor_barrier_material_id: int | None = None
    vapor_tape_material_id: int | None = None
    footing_mix_design_id: int | None = None
    notes: str | None = None


class EstimateSectionRead(EstimateSectionBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    estimate_id: UUID
    unit: str
    margin_pct: Decimal
    contingency_pct: Decimal
    calc_total_cost: Decimal | None = None
    calc_total_tax: Decimal | None = None
    calc_total_sale: Decimal | None = None
    calc_quantity: Decimal | None = None
    calc_cost_per_unit: Decimal | None = None
    calc_sale_per_unit: Decimal | None = None
    # Resolved from the section, else the project — what tax actually applied.
    effective_tax_exempt: bool | None = None
    # Resolved from the section, else the assembly, else the company. Since
    # sql/036 an unset waste factor is not necessarily the company's: paving
    # carries its own, and the screen used to read "sys" for all three.
    effective_waste_concrete: Decimal | None = None
    effective_waste_sand: Decimal | None = None
    effective_waste_rebar: Decimal | None = None
    effective_form_percent: Decimal | None = None
    # Quotes live in their own table since sql/039. `quote_kinds` is what this
    # assembly CAN carry — the screen draws its cards from this rather than
    # keeping a second copy of the mapping in JavaScript.
    # Items the master list had no price for when this section was costed
    # (sql/047). Non-empty means calc_total_cost is light by an unknown amount
    # — the screen turns this into a banner, not a footnote.
    calc_unpriced: list[str] = Field(default_factory=list)
    quote_kinds: list[str] = Field(default_factory=list)
    quotes: list[SectionQuoteRead] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


KINDS = list(SECTION_KINDS)
