from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class FormingDrivers(BaseModel):
    # Which line set produced these — mono_slab forms off perimeter, paving
    # off curb LF (sql/036).
    kind: str | None = None
    pour_count: int
    total_sf: Decimal
    perimeter_lf: Decimal
    curb_lf: Decimal = Decimal("0")
    # Piers: counts and drilled feet, since not one lumber line there runs off
    # a perimeter or an area.
    pier_count: int = 0
    total_lf: Decimal = Decimal("0")
    # Walls form off FORM FEET — one face — and the footing under the run has
    # its own plan area. Neither is a perimeter and neither is `total_sf`.
    wall_lf: Decimal = Decimal("0")
    form_ff: Decimal = Decimal("0")
    footing_sf: Decimal = Decimal("0")
    drain_lf: Decimal = Decimal("0")
    # Columns form off CONTACT AREA — all four faces, since a column is wrapped
    # — and a count. `form_sf` is also mirrored into `total_sf` so anything
    # generic that divides by an area still gets a real number.
    #
    # These four were computed by the service and then dropped on the way out,
    # because a driver the schema does not name does not reach the screen. The
    # forming card read `d.column_count` and rendered a dash. tests/
    # test_columns_ui_contract.py is the guard.
    column_count: int = 0
    form_sf: Decimal = Decimal("0")
    chamfer_lf: Decimal = Decimal("0")
    drops_ff: Decimal
    mesh_sf: Decimal
    total_rebar_lb: Decimal
    construction_joint_lf: Decimal = Decimal("0")
    control_joint_lf: Decimal = Decimal("0")
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


class FormingLineToggle(BaseModel):
    """Switch one forming line on or off (sql/056)."""

    enabled: bool = Field(
        ...,
        description=(
            "False = not used on this job. Keeps the quantity and formula, "
            "extends at $0.00, and stops asking to be priced."
        ),
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
    # False only for a genuine service filed with the lumber (haul-off).
    taxable: bool = True
    # Unchecked = not used on this job (sql/056). Keeps qty and formula,
    # extends at $0.00, and goes quiet in the unpriced list.
    enabled: bool = True
    # A real quantity with no price behind it. Surfaced rather than left to
    # extend at $0 — a silent zero on a live line is how a hole stays hidden.
    # A DISABLED line is never missing_price: nobody left it out, somebody
    # took it out.
    missing_price: bool = False


class FormingMaterialsRead(BaseModel):
    section_id: UUID
    drivers: FormingDrivers
    lines: list[FormingLine] = Field(default_factory=list)
    total_ext_cost: Decimal = Decimal("0")
    missing_prices: list[str] = Field(default_factory=list)
    stored: bool = False
    refreshed_at: datetime | str | None = None
