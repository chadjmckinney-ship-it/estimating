import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class SectionQuote(Base):
    """
    A real quote that replaces a computed cost on a section (sql/039).

    One row per (section, kind). See services/quotes.py for what each kind
    replaces and how a lump is spread; the rule that matters most is that a
    lump can go stale and a unit price cannot.
    """

    __tablename__ = "section_quotes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    section_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("estimate_sections.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    unit: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'LS'"))

    # Stamped on write, never on recalc. LS only.
    baseline_qty: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    baseline_unit: Mapped[str | None] = mapped_column(Text)

    note: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
