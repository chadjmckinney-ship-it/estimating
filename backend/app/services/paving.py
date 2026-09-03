"""
Paving quantities that more than one takeoff needs.

The joint LF is the clearest case. Three contract-service lines are priced off
it — hot pour joint sealant, control joint sealant, soft cut — and so are three
lumber lines, because the redwood, the tack strip and the smooth dowels all run
in the joints. Computing it twice from two copies of `ROUNDUP(SF / 60)` is how
those six lines quietly stop agreeing, so it is computed once, here.

Source: 10-PAVING rows 82–84 and the hidden AT / AU columns. Every formula is
re-derived in claude/paving-spec.md.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

# Construction joints go in at 60 ft. Control joints go in at 15 ft BOTH ways,
# less the construction joints already cut — which is what the `× 2 −` does.
CONSTRUCTION_JOINT_SPACING_FT = Decimal("60")
CONSTRUCTION_JOINT_PASSES = Decimal("1")
CONTROL_JOINT_SPACING_FT = Decimal("15")
CONTROL_JOINT_PASSES = Decimal("2")

# The sheet splits sealant board by slab thickness: a 1x6 in anything under 8",
# a 1x8 over it (hidden columns AT and AU). The lumber block then reads the 1x6
# off the joint total and hard-codes the 1x8 to zero, which is fine while every
# area is thin and wrong the first time one is not. The split is honoured here.
REDWOOD_THICKNESS_BREAK_IN = Decimal("8")

# Nails run a long way on paving: one box of 16p per 1,500 LF of curb against
# the slab sheet's 500, and 8p at half that again.
NAILS_16P_LF_PER_BOX = Decimal("1500")
NAILS_8P_LF_PER_BOX = Decimal("3000")

# Cure covers more ground outdoors: 350 SF/gal against the slab sheet's 300.
CURE_COVERAGE_SF_PER_GAL = Decimal("350")
CURE_GAL_PER_DRUM = Decimal("55")

# Curb concrete: 0.25 CF per LF, i.e. LF / 108 CY. Thickened edge: 18" deep by
# 1.5 ft wide, i.e. LF × 1.5 × 0.18 / 27 CY.
CURB_LF_PER_CY = Decimal("108")
THICK_EDGE_CY_PER_LF = Decimal("1.5") * Decimal("0.18") / Decimal("27")


def _d(x: Any) -> Decimal:
    if x is None or x == "":
        return Decimal("0")
    return Decimal(str(x))


def roundup(x: Decimal) -> int:
    """Excel ROUNDUP(x, 0). Zero and below stay zero rather than going to 1."""
    if x <= 0:
        return 0
    return int(math.ceil(float(x) - 1e-9))


@dataclass(frozen=True)
class Joints:
    """One paving section's joint layout, in linear feet."""

    construction_lf: int
    control_lf: int

    @property
    def sealed_lf(self) -> int:
        """The joints that take board, tack strip and dowels — the wide ones."""
        return self.construction_lf


def joints_for(
    total_sf: Decimal | float | int,
    *,
    construction_spacing_ft: Decimal = CONSTRUCTION_JOINT_SPACING_FT,
    construction_passes: Decimal = CONSTRUCTION_JOINT_PASSES,
    control_spacing_ft: Decimal = CONTROL_JOINT_SPACING_FT,
    control_passes: Decimal = CONTROL_JOINT_PASSES,
) -> Joints:
    """
    Joint LF for a paving section.

        construction = ROUNDUP(SF / 60 × 1)
        control      = ROUNDUP(SF / 15 × 2 − construction)

    Control joints are cut at 15 ft in both directions; the construction joints
    are already cut, so they come off. On 272,703 SF that is 4,546 and 31,815 LF.
    """
    sf = _d(total_sf)
    if sf <= 0 or construction_spacing_ft <= 0 or control_spacing_ft <= 0:
        return Joints(0, 0)

    construction = roundup(sf / construction_spacing_ft * construction_passes)
    control = roundup(sf / control_spacing_ft * control_passes - Decimal(construction))
    return Joints(construction, max(control, 0))


def edge_concrete_cy(
    curb_lf: Decimal | float | int | None,
    thick_edge_lf: Decimal | float | int | None,
    waste: Decimal | float | int | None = 0,
) -> Decimal:
    """
    Curb + thickened-edge concrete, wasted like the rest of the pour.

        (curb_lf / 108 + thick_edge_lf × 1.5 × 0.18 / 27) × (1 + waste)
    """
    curb = _d(curb_lf)
    edge = _d(thick_edge_lf)
    if curb <= 0 and edge <= 0:
        return Decimal("0.0000")
    raw = curb / CURB_LF_PER_CY + edge * THICK_EDGE_CY_PER_LF
    return (raw * (Decimal("1") + _d(waste))).quantize(Decimal("0.0001"))


def cure_drums(total_sf: Decimal | float | int) -> int:
    """ROUNDUP(SF / 350 / 55). 15 drums on 272,703 SF."""
    sf = _d(total_sf)
    if sf <= 0:
        return 0
    return roundup(sf / CURE_COVERAGE_SF_PER_GAL / CURE_GAL_PER_DRUM)
