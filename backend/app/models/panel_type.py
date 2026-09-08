import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.stamped import StampedBy


class PanelType(StampedBy, Base):
    """
    One tilt-wall panel type and how many of it there are (sql/077).

    The seventh takeoff shape — the 12-PANELS tab's row. Closest to a column
    type: a quantity of identical things. Measured and sold in SF, GROSS of
    openings (the tab's W column), and shared cost allocates by that SF.

    Four opening slots per type where the tab has one. Chad, 2026-09-08:
    "right now we have to figure total opening size if more than 1 opening so
    it is actually short on rebar and lumber for the openings". Each opening
    comes off the concrete, adds a set of the panel's edge bars, and puts its
    perimeter on the lumber and the chamfer.

    The bar-size columns are foreign keys to `bar_weights` in SQL only, the
    way beam_runs carries them (sql/073) — the ORM never joins them.
    """

    __tablename__ = "panel_types"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    section_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("estimate_sections.id", ondelete="CASCADE"),
        nullable=False,
    )

    label: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)

    qty: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    mix_design_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("mix_designs.id", ondelete="SET NULL")
    )

    length_ft: Mapped[Decimal] = mapped_column(
        Numeric(12, 3), nullable=False, server_default=text("0")
    )
    thickness_in: Mapped[Decimal] = mapped_column(
        Numeric(8, 3), nullable=False, server_default=text("0")
    )
    top_el_ft: Mapped[Decimal] = mapped_column(
        Numeric(12, 3), nullable=False, server_default=text("0")
    )
    bot_el_ft: Mapped[Decimal] = mapped_column(
        Numeric(12, 3), nullable=False, server_default=text("0")
    )

    open1_len_ft: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    open1_wide_ft: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    open2_len_ft: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    open2_wide_ft: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    open3_len_ft: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    open3_wide_ft: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    open4_len_ft: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    open4_wide_ft: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))

    horiz_spacing_in: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    horiz_size: Mapped[int | None] = mapped_column(Integer)
    horiz_mats: Mapped[int | None] = mapped_column(Integer)
    vert_spacing_in: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    vert_size: Mapped[int | None] = mapped_column(Integer)
    vert_mats: Mapped[int | None] = mapped_column(Integer)
    edge_bar_count: Mapped[int | None] = mapped_column(Integer)
    edge_bar_size: Mapped[int | None] = mapped_column(Integer)
    corner_bar_count: Mapped[int | None] = mapped_column(Integer)
    corner_bar_size: Mapped[int | None] = mapped_column(Integer)

    notes: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )

    calc_height_ft: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    calc_sf_each: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    calc_sf: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    calc_opening_sf: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    calc_opening_lf: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    calc_perimeter_lf: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    calc_bottom_lf: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    calc_concrete_cy: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    calc_steel_each_lb: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    calc_total_rebar_lb: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))

    calc_direct_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    calc_allocated_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    calc_equip_fuel: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    calc_tax: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    calc_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    calc_sale: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    calc_cost_per_unit: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    calc_sale_per_unit: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
