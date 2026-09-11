"""
The eTakeoff template coder (docs/specs/etakeoff-bid-codes.md).

Chad, 2026-09-10: "we can build a bidcode file that I can import and them
assign to each item... then there is no way to screw it up". Pinned on the
office's own `Rev Template 2026-09-10.itt`, the whole tree saved from the top
node: the coded file differs from the original in nothing but BidCode
values; every measurable item gets a code and no two items share one; the
families already in use are kept; every changed code has one of the named
reasons; the slips are named for a person; the layers and descriptions to
straighten are listed; the code list is two columns with no header; a
synthetic template round-trips its bytes, its escapes and its CRLF.
"""

from __future__ import annotations

import csv
import io
import re
from collections import Counter
from pathlib import Path

import pytest

from app.services.etakeoff_template import (
    Item,
    assign,
    expected_layer,
    items,
    mask_bid_codes,
    measurable,
    norm,
    parse,
    recode,
)

FIXTURE = Path(__file__).parent / "fixtures" / "etakeoff" / "Rev Template 2026-09-10.itt"


@pytest.fixture(scope="module")
def template() -> str:
    return FIXTURE.read_text(encoding="utf-8", newline="")


@pytest.fixture(scope="module")
def coded(template):
    return recode(template)


def _find(result, where: str, desc: str | None = None) -> Item:
    """The first item at a path (a description tells twins apart)."""
    for it in result.items:
        if it.where == where and (desc is None or it.desc == desc):
            return it
    raise KeyError(where)


def test_the_template_reads_as_the_tree_chad_keeps(template):
    root = parse(template)
    its = items(root)
    assert len(its) == 891
    tops = [it.label for it in its if len(it.path) == 1]
    assert len(tops) == 18 and "05 MonoSlab Wrap Bld 1" in tops and "07 PAVING" in tops and "MISC" in tops
    assert sum(1 for it in its if it.trace) == 691
    assert sum(1 for it in its if it.old_code) == 590


def test_only_bid_code_values_change(template, coded):
    assert coded.text != template
    assert mask_bid_codes(coded.text) == mask_bid_codes(template)
    assert coded.text.count("\r\n") == template.count("\r\n")     # CRLF kept
    # and what was written reads back as what was decided, item for item
    again = items(parse(coded.text))
    assert len(again) == len(coded.items)
    for before, after in zip(coded.items, again):
        assert (after.where, after.old_code) == (before.where, before.new_code)


def test_every_measurable_item_is_coded_once(coded):
    for it in coded.items:
        assert bool(it.new_code) == measurable(it), it.where
    codes = Counter(it.new_code for it in coded.items if it.new_code)
    assert len(codes) == 725 and max(codes.values()) == 1
    bad = [c for c in codes if not re.fullmatch(r"[A-Za-z0-9\-]+", c)]
    assert not bad, bad
    # headers, formulas, groups and typeless leftovers carry nothing
    assert _find(coded, "07 PAVING").status == "skipped"
    assert _find(coded, "05 MonoSlab Wrap Bld 1 > Bld 01 Pour 01 > Perimeter").new_code == ""
    assert _find(coded, "05 Mono Slab Garden Style > Clubhouse > Exposed GB's").status == "skipped"
    assert _find(coded, "09 GARAGE SOG > PIERS").status == "skipped"       # a group, not a defect
    assert coded.counts == {"kept": 340, "added": 135, "changed": 250, "skipped": 166}


def test_the_families_already_in_use_are_kept(coded):
    for where, code in (
        ("05 MonoSlab Wrap Bld 1 > Bld 01 Pour 01", "MonoSlabBld1Pour01"),
        ("05 MonoSlab Wrap Bld 1 > Bld 01 Pour 01 > Drops", "MonoSlabDropBld1Pour01"),
        ("05 MonoSlab Wrap Bld 1 > Bld 01 Pour 01 > Exposed GB", "MonoSlabEXPBld1Pour01"),
        ("05 MonoSlab Wrap Bld 1 > Bld 01 Pour 01 > INT RB", "MonoSlabIntRBBld1Pour01"),
        ("05 MonoSlab Wrap Bld 1 > Bld 01 Pour 01 > INT TKND", "MonoSlabTKNDBld1Pour01"),
        ("05 Mono Slab Garden Style > Bld Type 04", "MonoSlabType04"),
        ("05 Mono Slab Garden Style > Bld Type 04 >  INT GB", "MonoSlabIntGBType04"),
        ("06 Footings > F01 Footings", "Footings-F01"),
        ("09 Garage Footings > GarageFooting-F16", "GarageFooting-F16"),
        ("06 Walls > Wall Sec 24", "WallSec24"),
        ("09 Garage Walls > Garage Wall Sec 25", "GarageWallSec25"),
        ("07 PAVING > Heavy Duty/Firelane", "PavingHeavyDuty"),
        ("07 PAVING > Light Duty Paver Base", "PavingLightDutyPavers"),
        ("07 PAVING > Medium Duty Stamped", "PavingMediumDutyStamped"),
    ):
        it = _find(coded, where)
        assert (it.new_code, it.status) == (code, "kept"), where
    # the depth-coded drops and exposed beams keep their family too
    assert _find(coded, '05 MonoSlab Wrap Bld 2 > Bld 02 Pour 1 > Drops > 06" Drop').new_code == "MonoSlab06DropBld2Pour01"
    assert _find(coded, '05 MonoSlab Wrap Bld 2 > Bld 02 Pour 1 > Exposed GB\'s > 24" Exposed GB').new_code == "MonoSlab24EXPBld2Pour01"


def test_the_gaps_are_filled_in_the_same_style(coded):
    for where, code in (
        ("07 PAVING > Firelane", "PavingFirelane"),
        ("07 PAVING > Mono Curb", "PavingMonoCurb"),
        ("07 PAVING > Curb & Gutter", "PavingCurbGutter"),
        ("07 PAVING > Turn Lane/Decel Lane > Median Area", "PavingTurnLaneMedian"),
        ("07 ROW PAVING > Approach", "ROWPavingApproach"),
        ("07 ROW PAVING > Approach > CURB", "ROWPavingApproachCurb"),
        ("08 SIDEWALK > ADA Ramps City", "SidewalkADARampsCity"),
        ("08 SIDEWALK > Standard Broom Finish", "SidewalkBroom"),
        ("08 Courtyard Hardscape > Stamped and Stained Sidewalk", "CourtyardStampedStained"),
        ("02 COL > TYPE A", "ColumnTypeA"),
        ("01 PIERS > P1", "PierP01"),
        ("03 SLAB ON METAL DECK > AREA 4", "DeckArea04"),
        ("03 SLAB ON METAL DECK > PAN STAIRS > LANDINGS", "DeckPanStairsLandings"),
        ("04 CIP DECK > Level  3 > GB2", "CIPDeckLevel03GB02"),
        ("09 GARAGE SOG > COLUMNS > C1", "GarageSOGColC01"),
        ("09 GARAGE SOG > COLUMNS > C10", "GarageSOGColC10"),
        ("09 GARAGE SOG > GRADE BEAMS > CMU", "GarageSOGGBCMU"),
        ("09 GARAGE SOG > GRADE BEAMS > GB 3", "GarageSOGGB03"),
        ("09 GARAGE SOG > GRADE BEAMS > S1", "GarageSOGGBS01"),
        ("09 GARAGE SOG > GRADE BEAMS > Thickened", "GarageSOGGBThickened"),
        ("09 GARAGE SOG > PIER CAPS > PC1", "GarageSOGPierCapPC01"),
        ("MISC > Light Pole Bases", "MiscLightPoleBases"),
        ("MISC > MISC AREA", "MiscArea"),
        ("MISC > ELEV PIT", "MiscElevPit"),
        ("05 Mono Slab Garden Style > Bld Type 02 > Brickledge", "MonoSlabBrickType02"),
        ("05 Mono Slab Garden Style > KEYWAY", "MonoSlabKeywayGarden"),
        ("05 MonoSlab Wrap Bld 2 > KEYWAY", "MonoSlabKeywayBld2"),
    ):
        it = _find(coded, where)
        assert (it.new_code, it.status) == (code, "added"), (where, it.new_code, it.status)
    # a building type with a name instead of a number keeps the family, the name as the type
    it = _find(coded, "05 Mono Slab Garden Style > Clubhouse")
    assert (it.old_code, it.new_code, it.status) == ("MonoSlabType01", "MonoSlabTypeClubhouse", "changed")
    assert "a named building type" in "; ".join(it.notes)
    assert _find(coded, "05 Mono Slab Garden Style > Trash Enclosure > Drops").new_code == "MonoSlabDropTypeTrashEnclosure"


def _reason(it: Item) -> str | None:
    """The one reason a code was allowed to change."""
    o, n = it.old_code, it.new_code
    if n.endswith(tuple(f"-DUP{i}" for i in range(2, 9))):
        return "duplicate item"
    if it.top.endswith("Bld 2") and "Bld1" in o and "Bld2" in n:
        return "building 2 item coded for building 1"
    if re.fullmatch(r"P\d+", o) and n.startswith("GarageSOGPierP"):
        return "garage pier bare P##"
    if "Pour18" in o and "PourLO" in n:
        return "leave-outs coded as pour 18"
    if "Garden" in it.top and re.sub(r"Type\w+$", "Type*", o) == re.sub(r"Type\w+$", "Type*", n):
        return "named building type" if re.search(r"Type[A-Za-z]", n) else "type coded as the neighbouring type"
    if re.sub(r"Pour\d+", "Pour#", o) == re.sub(r"Pour\d+", "Pour#", n):
        return "child coded for the neighbouring pour"
    return None


def test_every_changed_code_has_a_reason(coded):
    changed = [it for it in coded.items if it.status == "changed"]
    reasons = Counter(_reason(it) for it in changed)
    assert None not in reasons, [(it.where, it.old_code, it.new_code) for it in changed if _reason(it) is None]
    assert reasons == Counter({
        "building 2 item coded for building 1": 146, "duplicate item": 36, "garage pier bare P##": 22,
        "type coded as the neighbouring type": 14, "named building type": 13,
        "child coded for the neighbouring pour": 12, "leave-outs coded as pour 18": 7,
    })


def test_the_slips_are_fixed_and_named(coded):
    # Building 2's pours were coded as building 1
    it = next(x for x in coded.items if x.top.endswith("Bld 2") and "Bld1" in x.old_code and x.label.strip() == "INT RB")
    assert it.new_code == it.old_code.replace("Bld1", "Bld2") and it.status == "changed"
    # a child coded for the pour next door
    it = _find(coded, "05 MonoSlab Wrap Bld 1 > Bld 01 Pour 02 > INT RB")
    assert (it.old_code, it.new_code) == ("MonoSlabIntRBBld1Pour01", "MonoSlabIntRBBld1Pour02")
    # garden types 01 and 02 re-created as copies of type 03, codes and all
    for n in ("01", "02"):
        it = _find(coded, f"05 Mono Slab Garden Style > Bld Type {n}")
        assert (it.old_code, it.new_code, it.status) == ("MonoSlabType03", f"MonoSlabType{n}", "changed")
    # a stem wall coded with no building number
    stems = [x for x in coded.items if x.old_code == "MonoSlabStemBldPour01"]
    assert stems and stems[0].new_code.startswith("MonoSlabStemBld2Pour01")
    # the leave-outs coded as pour 18
    it = _find(coded, "05 MonoSlab Wrap Bld 1 > Bld 01 Pour Leaveouts")
    assert (it.old_code, it.new_code) == ("MonoSlabBld1Pour18", "MonoSlabBld1PourLO")
    assert _find(coded, "05 MonoSlab Wrap Bld 1 > Bld 01 Pour Leavout").new_code == "MonoSlabBld1PourLO-DUP2"
    # the twin garage-wall breakdowns: 09 keeps the clean codes, 06 is the one to delete
    assert _find(coded, "09 Garage Walls > Garage Wall Sec 02").new_code == "GarageWallSec02"
    it = _find(coded, "06 Garage Walls > Garage Wall Sec 02")
    assert (it.old_code, it.new_code) == ("WallSec02", "GarageWallSec02-DUP2") and any("duplicate" in n for n in it.notes)
    # the garage piers lose their bare P## so they cannot be mistaken for the piers tab
    it = _find(coded, "09 GARAGE SOG > PIERS > P01")
    assert (it.old_code, it.new_code, it.status) == ("P01", "GarageSOGPierP01", "changed")
    # named for a person: traces pointing at a numbered sibling, duplicates, typeless leftovers, traced headers
    notes = {it.where: "; ".join(it.notes) for it in coded.defects()}
    assert "the trace is 'F15 Footings'" in notes["06 Footings > F16 Footings"]
    assert "the trace is 'P14'" in notes["09 GARAGE SOG > PIERS > P15"]
    assert "the trace is 'Bld 01 Pour 1'" in notes["05 MonoSlab Wrap Bld 2 > Bld 02 Pour 1"]
    assert "05 MonoSlab Wrap Bld 1 > Bld 01 Pour 07" not in notes            # "Pour 07" on the "Pour 7" trace is the same pour
    assert "duplicate of '05 MonoSlab Wrap Bld 2 > Bld 02 Pour 01'" in notes["05 MonoSlab Wrap Bld 2 > Bld 02 Pour 1"]
    assert "no type and no trace" in notes["05 Mono Slab Garden Style > Clubhouse > Drops"]
    assert "a breakdown header carrying the trace 'WALL'" in notes["06 Walls"]
    review = coded.review()
    assert "Two breakdowns carry the same codes: '06 Garage Walls' and '09 Garage Walls'. Keep one." in review
    assert "| 06 Garage Walls > Garage Wall Sec 02 | `WallSec02` | `GarageWallSec02-DUP2` |" in review


def test_the_layers_and_descriptions_to_straighten_are_listed(coded):
    """Chad, 2026-09-10: "there is a lot I need to straighten up in it.. like the layers... some items have bad descriptions"."""
    it = _find(coded, "05 MonoSlab Wrap Bld 1 > Bld 01 Pour 02 > INT RB")
    assert it.layer == "Sidewalks" and expected_layer(it) == "04 GradeBeams"
    assert expected_layer(_find(coded, "05 MonoSlab Wrap Bld 1 > Bld 01 Pour 02")) == "04 Slab"
    assert expected_layer(_find(coded, "02 COL > TYPE A")) == "03 Columns"
    assert expected_layer(_find(coded, "09 GARAGE SOG > COLUMNS > C1")) == "03 Columns"
    assert expected_layer(_find(coded, "MISC > Mow Strip")) is None
    rows = coded.layer_rows()
    assert len(rows) == 229 and all(it.layer and it.layer != expected_layer(it) for it in rows)
    review = coded.review()
    assert "77 items under '05 MonoSlab Wrap Bld 1' default to the 'Sidewalks' layer; the family uses '04 GradeBeams'" in review
    assert "| 02 COL > TYPE A | 01 piers | 03 Columns |" in review
    assert "## Layers to straighten" in review and "## Descriptions" in review
    assert "| MISC > ELEV PIT | ELEVATOR PITS |" in review
    assert len(coded.described()) == 152


def test_the_code_list_is_two_columns_without_a_header(coded):
    rows = list(csv.reader(io.StringIO(coded.bid_code_csv())))
    assert len(rows) == 725 and rows[0][0] != "Bid Code"
    assert len({r[0] for r in rows}) == len(rows)
    by_code = {r[0]: r[1] for r in rows}
    assert by_code["MonoSlabIntRBBld2Pour03"] == "05 MonoSlab Wrap Bld 2 > Bld 02 Pour 03 > INT RB (interior rebar beam)"
    assert by_code["Footings-F01"] == "06 Footings > F01 Footings"
    assert by_code["MonoSlabTKNDType02"].endswith('INT TKND — 24" X 12" GB (thickened beam)')


# ----------------------------------------------------------- the small cases


def test_norm_makes_code_fragments():
    assert norm("Wall 1") == "Wall01" and norm("C1") == "C01" and norm("C10") == "C10"
    assert norm("18 x 36") == "18x36" and norm("60/24/20") == "60-24-20"
    assert norm("Curb & Gutter") == "CurbGutter" and norm("ADA Ramps Bldg") == "ADARampsBldg"
    assert norm("STANDARD BROOM FINISH") == "StandardBroomFinish" and norm("Level  1") == "Level01"


SMALL = (
    'INodeLink {\r\n ItemNode {\r\n  BrkdnCode("07 PAVING")\r\n  Desc("")\r\n  DataType("A")\r\n  Level(0)\r\n'
    '  Trace("")\r\n  BidCode("Stray")\r\n }\r\n INodeLink {\r\n  ItemNode {\r\n   BrkdnCode("Mono Curb")\r\n'
    '   Desc("say \\"hi\\" \\\\ back")\r\n   DataType("L")\r\n   Level(1)\r\n'
    '   Trace("3,0,0xff0000,,0,3,0xffff,0,0,W_,0xffe0e0,PAVING,,0,,,,1,2,3,100,100")\r\n   BidCode("")\r\n  }\r\n }\r\n}\r\n'
)


def test_a_small_template_round_trips_bytes_escapes_and_crlf():
    result = recode(SMALL)
    head, curb = result.items
    assert (head.old_code, head.new_code, head.status) == ("Stray", "", "cleared")
    assert (curb.new_code, curb.status) == ("PavingMonoCurb", "added")
    assert curb.desc == 'say "hi" \\ back'
    assert mask_bid_codes(result.text) == mask_bid_codes(SMALL)
    assert 'BidCode("PavingMonoCurb")' in result.text and 'BidCode("")\r\n }' in result.text
    assert result.text.count("\r\n") == SMALL.count("\r\n")
    # written back and read again, the description's escapes are intact
    again = items(parse(result.text))
    assert again[1].desc == 'say "hi" \\ back' and again[1].old_code == "PavingMonoCurb"


def test_assign_flags_a_duplicate_code():
    its = items(parse(SMALL))
    twin = Item(node=its[1].node, path=("07 PAVING", "Mono Curb"), label="Mono Curb", desc="", trace="PAVING",
                dtype="L", fmla="", layer="", has_children=False, old_code="")
    assign(its + [twin])
    assert twin.new_code == "PavingMonoCurb-DUP2" and any("duplicate" in n for n in twin.notes)
