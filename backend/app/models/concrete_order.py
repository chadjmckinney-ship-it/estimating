"""A concrete order (sql/086): the pour planned, beside the daily report of the pour."""

import uuid
from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, Text, Time, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.daily_report import FieldJob
from app.models.stamped import StampedBy

ORDER_STATUSES = ("ordered", "confirmed", "poured", "canceled")


class ConcreteOrder(StampedBy, Base):
    __tablename__ = "concrete_orders"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    ordered_on: Mapped[date] = mapped_column(Date, nullable=False, server_default=func.current_date())
    job_id: Mapped[int] = mapped_column(Integer, ForeignKey("field_jobs.id"), nullable=False)
    supplier: Mapped[str] = mapped_column(Text, nullable=False)
    pour_date: Mapped[date] = mapped_column(Date, nullable=False)
    pour_time: Mapped[time | None] = mapped_column(Time)
    yards: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    mix: Mapped[str | None] = mapped_column(Text)  # the supplier's own mix number, as typed
    order_number: Mapped[str | None] = mapped_column(Text)
    ordered_by: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="ordered", server_default=text("'ordered'"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("estimators.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    job: Mapped[FieldJob] = relationship("FieldJob", lazy="joined")
