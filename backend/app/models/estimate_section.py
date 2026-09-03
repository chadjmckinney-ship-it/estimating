import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

# The workbook's per-sheet level. One job (estimate) has many.
SECTION_KINDS = (
    "mono_slab",
    "paving",
    "sidewalk",
    "piers",
    "grade_beams",
    "walls_footings",
    "columns",
    "slabs",
    "cip_deck",
    "slab_on_deck",
    "panels",
    "miscellaneous",
)

# Assemblies that share a line set or a takeoff shape. Defined here, next to
# the kinds themselves, because the same grouping is needed by forming, labor,
# equipment and costing — and four private copies of a frozenset is how they
# quietly stop agreeing.
PAVING_KINDS = frozenset({"paving", "sidewalk"})
PIER_KINDS = frozenset({"piers"})
# Walls take off as a wall-plus-footing run and are measured in FORM FEET —
# the third takeoff shape, after the pour and the group (sql/040).
WALL_KINDS = frozenset({"walls_footings"})
# Columns take off as a TYPE and a count — the fourth shape (sql/045). Measured
# in EA like piers, but shared cost allocates by form contact area, because
# forming is what a column job spends its money on.
#
# Pilasters live here too, and deliberately: Chad takes them off on the column
# sheet because a pilaster is a short column and the wall sheet has nowhere to
# put a full schedule. Two sections, the second named "Pilasters" — which is
# why sql/041 dropped the pilaster fields from wall_runs.
COLUMN_KINDS = frozenset({"columns"})

# What each assembly is measured in — a property of the assembly, not the job.
DEFAULT_UNIT_BY_KIND = {
    "mono_slab": "SF",
    "paving": "SF",
    "sidewalk": "SF",
    "piers": "EA",
    "grade_beams": "LF",
    "walls_footings": "FF",
    "columns": "EA",
    "slabs": "SF",
    "cip_deck": "SF",
    "slab_on_deck": "SF",
    "panels": "SF",
    "miscellaneous": "LS",
}


class EstimateSection(Base):
    """
    One assembly of a job (sql/033–034).

    Owns the work — pours, beam types, forming, labor and equipment lines all
    hang off a section — plus the settings that describe the assembly and the
    markup it is priced at. The estimate above it owns tax treatment, markup
    defaults, and the rollup.
    """

    __tablename__ = "estimate_sections"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    estimate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("estimates.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    unit: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'SF'"))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    # Priced markup for this section. Default 20%; a new section inherits the
    # estimate's figures, and existing work kept whatever it was bid at.
    margin_pct: Mapped[Decimal] = mapped_column(
        Numeric(6, 4), nullable=False, server_default=text("0.20")
    )
    contingency_pct: Mapped[Decimal] = mapped_column(
        Numeric(6, 4), nullable=False, server_default=text("0.00")
    )

    # NULL = inherit projects.tax_exempt. Set only where the section differs —
    # ROW paving and sidewalks inside an otherwise taxable job. Never defaulted
    # from `kind`: plenty of paving is not ROW, and a silently exempt section is
    # a wrong number with nothing on screen to notice.
    tax_exempt: Mapped[bool | None] = mapped_column(nullable=True)

    form_percent: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))
    waste_concrete: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))
    waste_sand: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))
    waste_rebar: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))
    vapor_barrier_material_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("materials.id", ondelete="SET NULL")
    )
    vapor_tape_material_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("materials.id", ondelete="SET NULL")
    )

    # Walls only (sql/040). The mix every FOOTING in this section is poured
    # from, where the wall above takes its mix per row — cheaper concrete in
    # the ground, better concrete in the wall. NULL falls back to the row's
    # wall mix rather than to nothing.
    footing_mix_design_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("mix_designs.id", ondelete="SET NULL")
    )

    # Quotes are rows, not columns (sql/039). The drilling quote lived here
    # briefly as three columns; adding PT and rebar the same way would have
    # meant nine, plus three copies of the stamping and staleness logic. See
    # models/section_quote.py and services/quotes.py.

    calc_total_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    calc_total_tax: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    calc_total_sale: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    calc_quantity: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    calc_cost_per_unit: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    calc_sale_per_unit: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    # What this section reached for that had no master price (sql/047). A
    # non-empty list means calc_total_cost is LIGHT by an unknown amount.
    calc_unpriced: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb"), default=list
    )

    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
