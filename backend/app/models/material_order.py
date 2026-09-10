"""A material order (sql/087): rebar, post-tension or other for a job, beside the concrete orders."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.daily_report import FieldJob
from app.models.stamped import StampedBy

KINDS = ("rebar", "post_tension", "other")
KIND_LABELS = {"rebar": ("Rebar", "Varilla"), "post_tension": ("Post-tension", "Postensado"), "other": ("Other", "Otro")}
UNITS = ("LB", "TON", "EA", "LF", "SF", "BUNDLE", "PALLET", "ROLL", "BOX")
MATERIAL_STATUSES = ("ordered", "confirmed", "delivered", "canceled")


class MaterialOrder(StampedBy, Base):
    __tablename__ = "material_orders"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    ordered_on: Mapped[date] = mapped_column(Date, nullable=False, server_default=func.current_date())
    job_id: Mapped[int] = mapped_column(Integer, ForeignKey("field_jobs.id"), nullable=False)
    supplier: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    unit: Mapped[str | None] = mapped_column(Text)
    needed_by: Mapped[date | None] = mapped_column(Date)
    delivered_on: Mapped[date | None] = mapped_column(Date)
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
