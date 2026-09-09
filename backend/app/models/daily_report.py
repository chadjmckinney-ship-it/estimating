"""
Daily reports from the field (sql/084): the job pick-list, the foreman
pick-list, the report, its man-power grid and its sub-labor grid.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, Text, func, text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.stamped import StampedBy

# The man-power grid's rows, in the form's order, and the sub-labor grid's.
TRADES = ("foreman", "assistants", "rod_busters", "form_setters", "finishers", "laborers")
SUB_TRADES = ("finishers", "form_setters", "rod_busters", "laborers")
TRADE_LABELS = {
    "foreman": ("Foreman", "Mayordomo"),
    "assistants": ("Assistants", "Asistentes"),
    "rod_busters": ("Rod busters", "Fierreros"),
    "form_setters": ("Form setters", "Carpinteros"),
    "finishers": ("Finishers", "Acabadores"),
    "laborers": ("Laborers", "Ayudantes"),
}
# The maintenance checks, as keys, with the form's English and Spanish.
MAINTENANCE = ("fuel", "grease", "oil", "hydraulic", "tires")
MAINTENANCE_LABELS = {
    "fuel": ("Checked fuel level", "Revisó el combustible"),
    "grease": ("Grease machine", "Engrasado"),
    "oil": ("Check oil level", "Nivel de aceite"),
    "hydraulic": ("Check hydraulic fluid level", "Nivel hidráulico"),
    "tires": ("Tire pressure", "Presión de llantas"),
}
# The concrete suppliers the Jotform form offered; the catalog's join them on the form.
FORM_SUPPLIERS = ("Cowtown", "Martin Marietta", "Sunrise", "SRM", "Chisholm Trail", "Quikrete")
SOURCES = ("app", "jotform")


class FieldJob(StampedBy, Base):
    __tablename__ = "field_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class FieldForeman(StampedBy, Base):
    __tablename__ = "field_foremen"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    estimator_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("estimators.id", ondelete="SET NULL")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class DailyReport(StampedBy, Base):
    __tablename__ = "daily_reports"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    report_date: Mapped[date] = mapped_column(Date, nullable=False)
    job_id: Mapped[int] = mapped_column(Integer, ForeignKey("field_jobs.id"), nullable=False)
    foremen: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list, server_default=text("'{}'"))
    work_accomplished: Mapped[str | None] = mapped_column(Text)
    delays: Mapped[str | None] = mapped_column(Text)
    plan_tomorrow: Mapped[str | None] = mapped_column(Text)
    safety_concerns: Mapped[str | None] = mapped_column(Text)
    comments: Mapped[str | None] = mapped_column(Text)
    concrete_poured: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    yards_poured: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    supplier: Mapped[str | None] = mapped_column(Text)
    what_poured: Mapped[str | None] = mapped_column(Text)
    tax_exempt: Mapped[bool | None] = mapped_column(Boolean)
    # Seniors, management and admins only (sql/085); the API blanks it for the rest.
    management_notes: Mapped[str | None] = mapped_column(Text)
    maintenance: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list, server_default=text("'{}'")
    )
    source: Mapped[str] = mapped_column(Text, nullable=False, default="app", server_default=text("'app'"))
    jotform_form_id: Mapped[str | None] = mapped_column(Text)
    jotform_submission_id: Mapped[str | None] = mapped_column(Text)
    signature_url: Mapped[str | None] = mapped_column(Text)
    import_fingerprint: Mapped[str | None] = mapped_column(Text)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    submitted_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("estimators.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    job: Mapped[FieldJob] = relationship("FieldJob", lazy="joined")
    crew: Mapped[list["DailyReportCrew"]] = relationship(
        "DailyReportCrew", cascade="all, delete-orphan", lazy="selectin", order_by="DailyReportCrew.id"
    )
    subs: Mapped[list["DailyReportSub"]] = relationship(
        "DailyReportSub", cascade="all, delete-orphan", lazy="selectin", order_by="DailyReportSub.sort_order"
    )


class DailyReportCrew(Base):
    __tablename__ = "daily_report_crew"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("daily_reports.id", ondelete="CASCADE"), nullable=False
    )
    trade: Mapped[str] = mapped_column(Text, nullable=False)
    workers: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    hours: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False, default=0, server_default=text("0"))
    man_hours: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=0, server_default=text("0"))


class DailyReportSub(Base):
    __tablename__ = "daily_report_subs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("daily_reports.id", ondelete="CASCADE"), nullable=False
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    trade: Mapped[str] = mapped_column(Text, nullable=False)
    sub_name: Mapped[str] = mapped_column(Text, nullable=False)
    workers: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    hours: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False, default=0, server_default=text("0"))
    man_hours: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=0, server_default=text("0"))
