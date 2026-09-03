from decimal import Decimal

from pydantic import BaseModel


class MaterialCostLine(BaseModel):
    key: str
    label: str
    qty: Decimal
    unit: str
    unit_cost: Decimal | None = None
    cost: Decimal
    source: str          # catalog | quote | quote (lump) | rate | unpriced
    detail: str | None = None
    # Items on this line the master list has no price for (sql/047). Non-empty
    # means `cost` is light by an unknown amount and `unit_cost` is withheld.
    #
    # This field was computed, serialised by MaterialLine.as_dict, and then
    # dropped RIGHT HERE for the first hour of its life — the concrete card
    # rendered "$0" beside 2,205 CY of unpriced concrete. Third instance of the
    # schema-drop class in two days; see claude/frontend-parse-and-drivers.md.
    unpriced: list[str] = []


class SectionMaterialCosts(BaseModel):
    """
    The purchase side of a section, line by line.

    `direct_cost` is what costing.py stored; `total_material_cost` is what these
    lines add to. They differ by per-row rounding and nothing else, which is
    what `rounding` reports — a figure worth watching rather than hiding.
    """

    section_id: str
    kind: str | None = None
    lines: list[MaterialCostLine] = []
    total_material_cost: Decimal = Decimal("0")
    direct_cost: Decimal = Decimal("0")
    rounding: Decimal = Decimal("0")
