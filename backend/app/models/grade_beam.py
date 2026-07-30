import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, SmallInteger, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class GradeBeam(Base):
    __tablename__ = "grade_beams"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    mono_slab_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mono_slabs.id", ondelete="CASCADE"), nullable=False
    )
    # Excel 04: grade_beam | exposed (EXP GB) | drop — same schedule shape
    kind: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'grade_beam'"))
    label: Mapped[str | None] = mapped_column(Text)
    width_in: Mapped[Decimal] = mapped_column(Numeric(8, 3), nullable=False)
    height_in: Mapped[Decimal] = mapped_column(Numeric(8, 3), nullable=False)
    length_lf: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    top_bars_count: Mapped[int | None] = mapped_column(Integer)
    top_bars_size: Mapped[int | None] = mapped_column(SmallInteger)
    bottom_bars_count: Mapped[int | None] = mapped_column(Integer)
    bottom_bars_size: Mapped[int | None] = mapped_column(SmallInteger)
    mid_bars_count: Mapped[int | None] = mapped_column(Integer)
    mid_bars_size: Mapped[int | None] = mapped_column(SmallInteger)
    stirrup_size: Mapped[int | None] = mapped_column(SmallInteger)
    stirrup_spacing_in: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    l_bars_count: Mapped[int | None] = mapped_column(Integer)
    l_bars_size: Mapped[int | None] = mapped_column(SmallInteger)
    l_bars_spacing_in: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    pt_cables_count: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    calc_rebar_lb: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    calc_pt_cable_lf: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    calc_concrete_cy: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    # Poly wrap SF (Excel): (2 × H″ / 12) × L ft — sides only; bottom in pour SF
    calc_poly_sf: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
