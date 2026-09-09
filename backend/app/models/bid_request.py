"""
The bid list (sql/082): every invite as it came in, apart from the projects
that were chosen. "Estimate this" copies a bid into a project and links them.
"""

import uuid
from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, Text, Time, func, text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.stamped import StampedBy

BID_STATUSES = ("not_started", "in_progress", "submitted", "awarded", "canceled")


class BidRequest(StampedBy, Base):
    __tablename__ = "bid_requests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    gc: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(Text)
    project_types: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list, server_default=text("'{}'")
    )
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="not_started", server_default=text("'not_started'")
    )
    bid_due: Mapped[date | None] = mapped_column(Date)
    bid_due_time: Mapped[time | None] = mapped_column(Time)
    bid_date: Mapped[date | None] = mapped_column(Date)
    plans_url: Mapped[str | None] = mapped_column(Text)
    bid_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    rev_date: Mapped[date | None] = mapped_column(Date)
    rev_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    notes: Mapped[str | None] = mapped_column(Text)
    message_id: Mapped[str | None] = mapped_column(Text)
    notion_page_id: Mapped[str | None] = mapped_column(Text)
    import_fingerprint: Mapped[str | None] = mapped_column(Text)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    estimator_links: Mapped[list["BidRequestEstimator"]] = relationship(
        "BidRequestEstimator", cascade="all, delete-orphan", lazy="selectin"
    )


class BidRequestEstimator(Base):
    __tablename__ = "bid_request_estimators"

    bid_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bid_requests.id", ondelete="CASCADE"), primary_key=True
    )
    estimator_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("estimators.id", ondelete="CASCADE"), primary_key=True
    )
