import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class EstimateBeamType(Base):
    """
    One grade beam / exposed GB / drop section on an estimate.

    The section and bar schedule live here once; pours reference it and supply
    only a length (see GradeBeam). Introduced by sql/025.
    """

    __tablename__ = "estimate_beam_types"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    estimate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("estimates.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'grade_beam'")
    )
    width_in: Mapped[Decimal] = mapped_column(Numeric(8, 3), nullable=False)
    height_in: Mapped[Decimal] = mapped_column(Numeric(8, 3), nullable=False)

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
    # PT cables running through this section; LF = count × length used
    pt_cables_count: Mapped[int | None] = mapped_column(Integer)

    notes: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    usages: Mapped[list["GradeBeam"]] = relationship(  # noqa: F821
        back_populates="beam_type", cascade="all, delete-orphan"
    )
