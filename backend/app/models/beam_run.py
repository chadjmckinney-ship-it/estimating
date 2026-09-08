"""
Beam runs — one separately poured beam type, or one continuous footing type,
on a grade-beams section (sql/073).

The workbook's 02-Gd Beams row: mix, length, width, height, top, bottom and
mid bars, stirrups at a spacing, L bars at a spacing with a length each, and
pilasters. Not the mono slab's beams: those are monolithic, live on
estimate_beam_types, and are a different cost model (vault, 2026-08-02).
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, SmallInteger, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.stamped import StampedBy


class BeamRun(StampedBy, Base):
    __tablename__ = "beam_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    section_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("estimate_sections.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    mix_design_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("mix_designs.id", ondelete="SET NULL")
    )

    length_ft: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False, server_default=text("0"))
    width_in: Mapped[Decimal] = mapped_column(Numeric(8, 3), nullable=False, server_default=text("0"))
    height_in: Mapped[Decimal] = mapped_column(Numeric(8, 3), nullable=False, server_default=text("0"))

    top_bars_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    top_bars_size: Mapped[int | None] = mapped_column(SmallInteger)
    bottom_bars_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    bottom_bars_size: Mapped[int | None] = mapped_column(SmallInteger)
    mid_bars_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    mid_bars_size: Mapped[int | None] = mapped_column(SmallInteger)
    stirrup_size: Mapped[int | None] = mapped_column(SmallInteger)
    stirrup_spacing_in: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    l_bars_size: Mapped[int | None] = mapped_column(SmallInteger)
    l_bars_spacing_in: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    l_bars_length_ft: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))

    pilaster_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    pilaster_length_in: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    pilaster_width_in: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))

    notes: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    calc_total_rebar_lb: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    calc_concrete_cy: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    calc_contact_ff: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    calc_face_ff: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    calc_pilaster_ff: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    calc_excavate_cy: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    calc_backfill_cy: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))

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
