"""
No price lives in the code (audit 2026-09-04, P3 — batch 1, 2026-09-06).

Three did, in services/estimate_equipment.py: the MISCELLANEOUS contract lump
on piers and walls (`rate=1000`), and the mono slab's HAUL OFF ($12.50/CY) and
ENGINEERING ($0.20/SF). Each is a rate on the ladder now (sql/065): the same
number, reachable from the price sheet or a section's rates card instead of a
code change. And the walls SKY TRACK line reads its own key rather than the
fork truck's — dormant while the catalog priced the machine, wrong the day it
did not.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db import get_db
from app.main import app
from app.services.estimate_equipment import load_stored_equipment, refresh_and_store_equipment
from tests import mono_slab_fixture as mf
from tests import piers_fixture as pif
from tests import walls_fixture as wf

D = Decimal


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _line(db, sid, code):
    refresh_and_store_equipment(db, sid)
    return next(ln for ln in load_stored_equipment(db, sid)["lines"] if ln["code"] == code)


def test_the_misc_contract_lump_is_a_rate_on_the_ladder(client, db, estimate):
    section = pif.build(db, estimate)
    assert D(str(_line(db, section.id, "misc_contract")["rate"])) == D("1000")  # the seed
    r = client.put(f"/api/sections/{section.id}/rates/misc_contract_ls", json={"value": "2500"})
    assert r.status_code == 200, r.text
    assert D(str(_line(db, section.id, "misc_contract")["rate"])) == D("2500")


def test_the_slab_haul_off_and_engineering_are_rates_on_the_ladder(client, db, estimate):
    section = mf.build(db, estimate)
    assert D(str(_line(db, section.id, "haul_off")["rate"])) == D("12.5")  # sql/065's slab row
    assert D(str(_line(db, section.id, "engineering")["rate"])) == D("0.2")
    r = client.put(f"/api/sections/{section.id}/rates/engineering_sf", json={"value": "0.30"})
    assert r.status_code == 200, r.text
    assert D(str(_line(db, section.id, "engineering")["rate"])) == D("0.3")


def test_the_walls_skytrack_reads_its_own_key(db, estimate):
    """
    With the machine unpriced on the job's sheet, the line falls to the rate
    key. Put a SkyTrack rate on the sheet and the line must read it — and not
    the fork truck's.
    """
    section = wf.build(db, estimate)
    db.execute(
        text("DELETE FROM estimate_prices WHERE estimate_id = :e AND kind = 'equipment' "
             "AND label ILIKE '%sky%'"),
        {"e": str(estimate.id)},
    )
    db.execute(
        text("INSERT INTO estimate_prices (estimate_id, kind, scope, ref_key, label, unit, category, "
             "catalog_value, value, is_edited) VALUES "
             "(:e, 'assembly_rate', 'walls_footings', 'equip_skytrack_day_rate', 'SkyTrack', 'DAY', "
             "'walls_footings rates', 999, 999, true), "
             "(:e, 'assembly_rate', 'walls_footings', 'equip_fork_truck_day_rate', 'Fork truck', 'DAY', "
             "'walls_footings rates', 111, 111, true)"),
        {"e": str(estimate.id)},
    )
    db.flush()
    line = _line(db, section.id, "skytrack")
    assert D(str(line["rate"])) == D("999"), line
