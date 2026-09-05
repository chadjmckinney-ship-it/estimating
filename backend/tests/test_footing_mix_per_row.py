"""
A footing can name its own mix (sql/062).

Chad, 2026-09-05, ~7:30 AM, right after the section-level "Footing mix" select
went onto the walls page: "there is no option for me to set the mix if I
price walls manually" — "per row footing mix, on the footing line."

The ladder lives in one place, WallRun.footing_mix_for: the row's footing
mix, else the section's (the sheet's R8, one for every footing), else the
wall's, so a footing never prices at nothing. Every path that prices footing
concrete — the wall/footing split, the pour costing, the materials breakdown
and the unpriced check — asks that one method. Existing rows are NULL and
price exactly as before; test_walls.py's golden numbers are the proof.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import get_db
from app.main import app
from app.models.mix_design import MixDesign
from app.models.wall_run import WallRun
from app.services.price_book import pull_prices
from tests import walls_fixture as wf

D = Decimal


class _Section:
    def __init__(self, footing_mix_design_id=None):
        self.footing_mix_design_id = footing_mix_design_id


def test_the_footing_mix_ladder():
    run = WallRun(mix_design_id=5, footing_mix_design_id=None)
    assert run.footing_mix_for(_Section(None)) == 5  # nothing named: the wall's
    assert run.footing_mix_for(_Section(3)) == 3  # the section's R8
    run.footing_mix_design_id = 9
    assert run.footing_mix_for(_Section(3)) == 9  # the row wins
    assert run.footing_mix_for(None) == 9  # and needs no section to


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


ROW_FIELDS = (
    "length_ft", "wall_thick_in", "wall_height_in", "backfill", "mix_design_id",
    "horiz_spacing_in", "horiz_size", "horiz_mats", "vert_spacing_in", "vert_size", "vert_mats",
    "ftg_width_in", "ftg_thick_in", "ftg_bot_spacing_in", "ftg_bot_size",
    "ftg_top_spacing_in", "ftg_top_size",
)


def _twins(client, db, section, dear):
    """Two runs identical in every way, except one names a dear mix for its footing."""
    first = client.get(f"/api/wall-runs?section_id={section.id}").json()[0]
    common = {k: first[k] for k in ROW_FIELDS}
    r = client.put("/api/wall-runs/bulk", json={
        "section_id": str(section.id),
        "rows": [
            {**common, "label": "twin-default", "footing_mix_design_id": None},
            {**common, "label": "twin-dear", "footing_mix_design_id": dear},
        ],
    })
    assert r.status_code == 200, r.text
    return {x["label"]: x for x in r.json()["rows"]}


def _dear_mix(db, estimate) -> int:
    """
    A third mix at $400/CY. The fixture's estimate carries a price sheet
    (every fixture pulls one), and once a sheet exists it is the only source
    — a catalog price nobody pulled is invisible to the job. So the master
    list moves and the job pulls it, exactly as the office would.
    """
    mix = db.scalar(select(MixDesign).where(MixDesign.code == "3000-SC"))
    assert mix is not None
    mix.unit_cost = D("400")
    db.flush()
    pull_prices(db, estimate.id)
    return int(mix.id)


def test_a_row_can_pour_its_footing_from_its_own_mix(client, db, estimate):
    """
    Only the footing side moves — by that footing's CY at the price difference,
    plus tax, which is under 10% on the fixture — and the wall side does not
    move a cent.
    """
    section = wf.build(db, estimate)
    dear = _dear_mix(db, estimate)
    by = _twins(client, db, section, dear)
    assert by["twin-dear"]["footing_mix_design_id"] == dear
    assert by["twin-default"]["footing_mix_design_id"] is None

    default_ftg = D(by["twin-default"]["calc_footing_cost"])
    dear_ftg = D(by["twin-dear"]["calc_footing_cost"])
    assert dear_ftg > default_ftg > 0
    assert D(by["twin-dear"]["calc_wall_cost"]) == D(by["twin-default"]["calc_wall_cost"])
    cy = D(by["twin-dear"]["calc_footing_concrete_cy"])
    bare = cy * (D("400") - wf.FOOTING_MIX_COST)
    assert bare <= dear_ftg - default_ftg <= bare * D("1.10")


def test_a_blank_footing_mix_follows_the_section_then_the_wall(client, db, estimate):
    """
    Clearing the section's footing mix moves every blank footing onto its
    wall's mix ($140 -> $145 on the fixture); a row that named its own mix does
    not move, because the section's default is not its business.
    """
    section = wf.build(db, estimate)
    dear = _dear_mix(db, estimate)
    before = {k: D(v["calc_footing_cost"]) for k, v in _twins(client, db, section, dear).items()}

    p = client.patch(f"/api/sections/{section.id}", json={"footing_mix_design_id": None})
    assert p.status_code == 200, p.text
    after = {
        x["label"]: D(x["calc_footing_cost"])
        for x in client.get(f"/api/wall-runs?section_id={section.id}").json()
    }
    assert after["twin-default"] > before["twin-default"]
    assert after["twin-dear"] == before["twin-dear"]
