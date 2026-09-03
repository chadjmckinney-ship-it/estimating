"""
One price on one estimate's sheet (sql/048).

The sheet is what an estimate is priced FROM. `catalog_value` is what the
master list said when this row was pulled; `value` is what this job pays;
`is_edited` says a person changed it, which a re-pull must never undo.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

PRICE_KINDS = ("mix", "material", "equipment", "setting", "assembly_rate", "drill_rate")


class EstimatePrice(Base):
    __tablename__ = "estimate_prices"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    estimate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("estimates.id", ondelete="CASCADE"), nullable=False
    )

    kind: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[str | None] = mapped_column(Text)
    ref_id: Mapped[int | None] = mapped_column(Integer)
    ref_key: Mapped[str | None] = mapped_column(Text)

    label: Mapped[str] = mapped_column(Text, nullable=False)
    unit: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(Text)

    catalog_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    value: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    is_edited: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"), default=False
    )
    note: Mapped[str | None] = mapped_column(Text)

    pulled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
