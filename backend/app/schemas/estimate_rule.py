from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RuleSectionUse(BaseModel):
    """
    One section that does NOT end up using the job's answer for this rule.

    The card's whole job is saying whether a job rule is actually REACHING the
    work. Two ways it does not:

      * the section set its own value in `section_rates` (sql/055), which beats
        the job outright;
      * the rule is one of the four that live as a COLUMN on the section —
        waste concrete/sand/rebar and form % — and that column is checked
        before the ladder runs at all, so it beats even a section rate.

    Either way the number on the job row is not what that section is pricing
    at, and a screen that did not say so would be lying by omission.
    """

    section_id: UUID
    name: str
    kind: str
    value: Decimal | None = None
    # "section" (a section_rates row) or "column" (waste / form % on the section)
    source: str = "section"


class EstimateRuleRead(BaseModel):
    """
    One RULE, as this job resolves it, and the whole ladder behind it.

    Prices are not here. A price is frozen on the price sheet at the pull, and
    that screen already edits it per job; a rule is read LIVE, deliberately, so
    that a correction to how the work is computed reaches the jobs it was made
    for. Putting a rule on the sheet would freeze it and break that.
    """

    key: str
    label: str
    unit: str | None = None
    description: str | None = None
    group: str = "Other"
    group_order: int = 99

    # What this job says, and which rung it came from.
    value: Decimal | None = None
    source: str = "default"          # job | assembly | company | default
    job_value: Decimal | None = None
    note: str | None = None

    # `assembly_rates` is per KIND, so on a job with paving AND a deck the same
    # key can have two different assembly answers. Reported per kind rather
    # than flattened to one number that would be wrong for one of them.
    assembly_values: dict[str, Decimal] = Field(default_factory=dict)
    company_value: Decimal | None = None
    default_value: Decimal | None = None

    # True for waste_concrete / waste_sand / waste_rebar / form_percent — the
    # four that are columns on `estimate_sections` and are checked before the
    # ladder. Setting those here works only on sections that left the column
    # blank, and the row says so.
    is_section_column: bool = False

    # Which sections read this key on their last build, and which of them
    # answer it themselves anyway.
    read_by: list[str] = Field(default_factory=list)
    overridden_by: list[RuleSectionUse] = Field(default_factory=list)


class EstimateRulesRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    estimate_id: UUID
    name: str
    rows: list[EstimateRuleRead] = Field(default_factory=list)
    set_here: int = 0
    section_count: int = 0


class EstimateRuleWrite(BaseModel):
    # extra="forbid" (audit 2026-09-04, P2 #8): a misspelled field is a 422,
    # not a silent 200.
    model_config = ConfigDict(extra="forbid")

    # Never negative, never absurd here; the key's own range (a waste is 0-1)
    # is checked in the router against price_book.RULE_BOUNDS.
    value: Decimal = Field(..., ge=0, le=1_000_000)
    note: str | None = Field(
        None,
        max_length=200,
        description="Who said so. A rule set on a job is a decision somebody made.",
    )
