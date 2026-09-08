import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.stamped import StampedBy


class MiscItemLibrary(Base):
    """
    The 13-Miscellaneous tab's 22 named items with their defaults (sql/078).

    Read at section creation and copied onto the section at no quantity —
    Chad, 2026-09-08: "have the 4 sections with the ones shown as defaults,
    minus the quantities". Never priced from directly.
    """

    __tablename__ = "misc_item_library"

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    shape: Mapped[str] = mapped_column(Text, nullable=False)
    unit: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'EA'"))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    pours_concrete: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    structural_mix: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    unit_sale: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    labor_per_unit: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, server_default=text("0"))
    subcontracted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    dim_a: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    dim_b: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    dim_c: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    concrete_waste: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, server_default=text("0"))
    steel_lb_per_cy: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False, server_default=text("0"))
    steel_lb_per_in_ft: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False, server_default=text("0"))
    steel_lb_per_unit: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False, server_default=text("0"))
    forms_pct_of_sale: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, server_default=text("0"))
    forms_per_unit: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, server_default=text("0"))
    forms_per_face_sf: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False, server_default=text("0"))
    forms_pct_of_concrete: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, server_default=text("0"))
    super_pct_of_labor: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, server_default=text("0"))
    equip_per_unit: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, server_default=text("0"))
    equip_pct_of_labor: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, server_default=text("0"))
    equip_min: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, server_default=text("0"))
    notes: Mapped[str | None] = mapped_column(Text)


# The columns a section row copies from the library, verbatim.
LIBRARY_FIELDS = (
    "code", "description", "shape", "unit", "sort_order", "pours_concrete",
    "unit_sale", "labor_per_unit", "subcontracted", "dim_a", "dim_b", "dim_c", "concrete_waste",
    "steel_lb_per_cy", "steel_lb_per_in_ft", "steel_lb_per_unit",
    "forms_pct_of_sale", "forms_per_unit", "forms_per_face_sf", "forms_pct_of_concrete",
    "super_pct_of_labor", "equip_per_unit", "equip_pct_of_labor", "equip_min", "notes",
)


class MiscItem(StampedBy, Base):
    """
    One priced site item on a miscellaneous section (sql/078).

    The eighth takeoff shape, and the first where the SALE is typed: the
    tab's H column is what a light pole base sells for, and the margin is
    what falls out once the cost is built. Concrete and steel come from the
    shape and price from the catalog; forms, supervision and equipment are
    typed allowances with the tab's formulas as their defaults.
    """

    __tablename__ = "misc_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    section_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("estimate_sections.id", ondelete="CASCADE"),
        nullable=False,
    )

    code: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    shape: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'round'"))
    unit: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'EA'"))
    qty: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False, server_default=text("0"))

    unit_sale: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    labor_per_unit: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, server_default=text("0"))
    subcontracted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    pours_concrete: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    mix_design_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("mix_designs.id", ondelete="SET NULL")
    )
    dim_a: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    dim_b: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    dim_c: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    concrete_waste: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, server_default=text("0"))

    steel_lb_per_cy: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False, server_default=text("0"))
    steel_lb_per_in_ft: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False, server_default=text("0"))
    steel_lb_per_unit: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False, server_default=text("0"))

    forms_pct_of_sale: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, server_default=text("0"))
    forms_per_unit: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, server_default=text("0"))
    forms_per_face_sf: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False, server_default=text("0"))
    forms_pct_of_concrete: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, server_default=text("0"))
    super_pct_of_labor: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, server_default=text("0"))
    equip_per_unit: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, server_default=text("0"))
    equip_pct_of_labor: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, server_default=text("0"))
    equip_min: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, server_default=text("0"))

    notes: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    calc_concrete_cy: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    calc_steel_lb: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    calc_face_sf: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    calc_sale: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    calc_concrete_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    calc_steel_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    calc_forms_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    calc_labor_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    calc_super_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    calc_equip_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    calc_margin: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))

    calc_direct_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    calc_allocated_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    calc_equip_fuel: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    calc_tax: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    calc_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    calc_cost_per_unit: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    calc_sale_per_unit: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
