"""
The grade-beam write endpoints.

These four routes had **no test at all**, and on 2026-09-02 every one of them
was returning 500. `_type_for_slab` compared `t.estimate_id != slab.estimate_id`
and `_resync_estimate_takeoffs` read `slab.estimate_id` — columns that stopped
existing in sql/034, when pours and beam types moved under a section. The suite
was at 346 green tests while `POST /api/grade-beams` could not succeed, and the
LBJ mono slab was carrying 69 beam rows nobody could edit.

Worse than a plain 500: the crash landed AFTER `db.commit()`, so the beam was
written, the client got an error, and forming/labor/equipment kept the previous
quantities. A user retrying would double the beam.

So this file asserts three separate things, and the second and third are the
ones that would have caught the shape rather than just the symptom:

  1. The routes answer at all — the regression itself.
  2. A beam change REACHES the takeoffs. Beams drive the drops lumber, the tie
     steel and the pumping; a route that writes the row and skips the resync
     looks fine in the response and is wrong on the bid.
  3. The write is ATOMIC. Nothing is left behind when a later step fails.

Plus the cross-section guard, which is what `_type_for_slab` is actually for.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db import get_db
from app.main import app
from app.services.recalc import recalc_section
from tests import mono_slab_fixture as mf


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def slab(db, estimate):
    section = mf.build(db, estimate)
    recalc_section(db, section)
    db.flush()
    return section


def _a_pour(db, section_id) -> str:
    return str(
        db.execute(
            text(
                "SELECT id FROM mono_slabs WHERE section_id = :s "
                "ORDER BY created_at LIMIT 1"
            ),
            {"s": str(section_id)},
        ).scalar()
    )


def _types(client, section_id, kind=None):
    q = f"?kind={kind}" if kind else ""
    r = client.get(f"/api/sections/{section_id}/beam-types{q}")
    assert r.status_code == 200, r.text
    return r.json()


def _beam_count(db, pour_id) -> int:
    return db.execute(
        text("SELECT count(*) FROM grade_beams WHERE mono_slab_id = :p"),
        {"p": pour_id},
    ).scalar()


# --------------------------------------------------------- the regression ----


def test_creating_a_grade_beam_does_not_500(client, db, slab):
    pour = _a_pour(db, slab.id)
    types = _types(client, slab.id)
    assert types, "the slab fixture should carry a beam schedule"

    r = client.post(
        "/api/grade-beams",
        json={
            "mono_slab_id": pour,
            "beam_type_id": types[0]["id"],
            "length_lf": 100,
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["length_lf"] is not None
    # The read model flattens the type onto the row so a grid needs no second
    # lookup — if that broke, the row would come back label-less.
    assert body["label"] == types[0]["label"]
    assert Decimal(str(body["calc_concrete_cy"])) > 0


def test_patch_and_delete_do_not_500(client, db, slab):
    pour = _a_pour(db, slab.id)
    types = _types(client, slab.id)
    created = client.post(
        "/api/grade-beams",
        json={"mono_slab_id": pour, "beam_type_id": types[0]["id"], "length_lf": 50},
    ).json()

    r = client.patch(f"/api/grade-beams/{created['id']}", json={"length_lf": 75})
    assert r.status_code == 200, r.text
    assert Decimal(str(r.json()["length_lf"])) == Decimal("75")

    r = client.delete(f"/api/grade-beams/{created['id']}")
    assert r.status_code == 204, r.text
    assert client.get(f"/api/grade-beams/{created['id']}").status_code == 404


def test_bulk_replace_does_not_500(client, db, slab):
    pour = _a_pour(db, slab.id)
    gbs = _types(client, slab.id, kind="grade_beam")
    assert gbs

    r = client.put(
        f"/api/mono-slabs/{pour}/grade-beams",
        json={"kind": "grade_beam", "beams": [
            {"beam_type_id": gbs[0]["id"], "length_lf": 120},
        ]},
    )
    assert r.status_code == 200, r.text
    assert len(r.json()) == 1


# ------------------------------------------------- the takeoffs must move ----


def _cy(client, section_id):
    """Pour concrete, off the equipment drivers (labor's schema drops it)."""
    return client.get(f"/api/sections/{section_id}/equipment").json()["drivers"]["total_concrete_cy"]


def _tons(client, section_id):
    return client.get(f"/api/sections/{section_id}/labor").json()["drivers"]["total_rebar_tons"]


def _reinforced_type(client, section_id) -> dict:
    """
    A beam type that actually carries loose steel.

    LBJ's GB 1 and GB 2 carry none — they are PT grade beams, and the tendons
    do the reinforcing. Adding 500 LF of one of those SHOULD move concrete and
    leave the tonnage alone, which is the correct behaviour and useless as an
    assertion. Writing this test against `types[0]` proved the point the hard
    way: it failed against working code.
    """
    for t in _types(client, section_id):
        if t.get("top_bars_count") and t.get("top_bars_size"):
            return t
    pytest.skip("fixture carries no reinforced beam type")


def test_a_beam_change_reaches_the_section_takeoffs(client, db, slab):
    """
    Beam concrete feeds equipment pumping and beam rebar feeds tie steel. A
    route that writes the row and skips the resync returns a perfectly good
    201 and leaves the bid on the previous quantities.
    """
    pour = _a_pour(db, slab.id)
    t = _reinforced_type(client, slab.id)

    # Concrete is read off EQUIPMENT and steel off LABOR, deliberately: the
    # resync has to reach both, and `LaborDrivers` does not carry
    # `total_concrete_cy` — it is computed and then dropped by the schema.
    before_cy = Decimal(str(_cy(client, slab.id)))
    before_tons = Decimal(str(_tons(client, slab.id)))

    r = client.post(
        "/api/grade-beams",
        json={"mono_slab_id": pour, "beam_type_id": t["id"], "length_lf": 500},
    )
    assert r.status_code == 201, r.text

    assert Decimal(str(_cy(client, slab.id))) > before_cy, (
        "500 LF of beam did not reach the equipment concrete driver"
    )
    assert Decimal(str(_tons(client, slab.id))) > before_tons, (
        "500 LF of reinforced beam did not reach the labor steel driver"
    )


def test_a_pt_beam_moves_concrete_and_not_steel(client, db, slab):
    """
    The other half, and the reason the test above has to pick its type.

    GB 1 and GB 2 are PT grade beams carrying no loose bar — the workbook's
    2-#5-with-stirrups on those sections was a support-steel allowance, not
    design steel, and removing it is what took ~44,000 lb of phantom rebar off
    this job. A resync that moved the tonnage here would mean it had come back.
    """
    pour = _a_pour(db, slab.id)
    bare = next(
        (t for t in _types(client, slab.id, kind="grade_beam")
         if not t.get("top_bars_count") and not t.get("bottom_bars_count")),
        None,
    )
    if bare is None:
        pytest.skip("fixture carries no unreinforced grade beam")

    before_cy, before_tons = _cy(client, slab.id), _tons(client, slab.id)
    client.post(
        "/api/grade-beams",
        json={"mono_slab_id": pour, "beam_type_id": bare["id"], "length_lf": 500},
    )
    assert Decimal(str(_cy(client, slab.id))) > Decimal(str(before_cy))
    assert Decimal(str(_tons(client, slab.id))) == Decimal(str(before_tons))


def test_a_beam_change_rolls_the_job_up(client, db, slab, estimate):
    """
    `refresh_pour_costs` writes the SECTION total and stops. The estimate is a
    rollup of its sections, and a beam edit moves both — a job total that sits
    one edit behind is the $15,440.35 shape.
    """
    pour = _a_pour(db, slab.id)
    types = _types(client, slab.id)

    est_cost = lambda: db.execute(
        text("SELECT calc_total_cost FROM estimates WHERE id = :i"),
        {"i": str(estimate.id)},
    ).scalar()
    sec_cost = lambda: db.execute(
        text("SELECT calc_total_cost FROM estimate_sections WHERE id = :i"),
        {"i": str(slab.id)},
    ).scalar()

    from app.services.costing import refresh_estimate_totals

    refresh_estimate_totals(db, estimate)
    db.flush()
    before_e, before_s = est_cost(), sec_cost()

    client.post(
        "/api/grade-beams",
        json={"mono_slab_id": pour, "beam_type_id": types[0]["id"], "length_lf": 800},
    )

    after_e, after_s = est_cost(), sec_cost()
    assert after_s > before_s, "the section did not move"
    assert after_e > before_e, "the section moved and the job did not follow it"
    assert after_e - before_e == after_s - before_s


# ------------------------------------------------------------ the guards ----


def test_a_pour_cannot_borrow_another_sections_beam_type(client, db, estimate, slab):
    """
    What `_type_for_slab` is actually for. It was comparing a column that no
    longer exists, so it raised instead of rejecting — and a 500 is not a
    validation error, it is an outage.
    """
    other = mf.build(db, estimate)
    db.flush()
    pour = _a_pour(db, slab.id)
    foreign = _types(client, other.id)
    assert foreign

    r = client.post(
        "/api/grade-beams",
        json={"mono_slab_id": pour, "beam_type_id": foreign[0]["id"], "length_lf": 10},
    )
    assert r.status_code == 400, r.text
    assert "different section" in r.json()["detail"]


def test_an_unknown_beam_type_is_a_400_not_a_crash(client, db, slab):
    pour = _a_pour(db, slab.id)
    r = client.post(
        "/api/grade-beams",
        json={
            "mono_slab_id": pour,
            "beam_type_id": "00000000-0000-0000-0000-000000000000",
            "length_lf": 10,
        },
    )
    assert r.status_code == 400
    assert "not found" in r.json()["detail"]


def test_a_rejected_beam_leaves_nothing_behind(client, db, estimate, slab):
    """
    The bug's real damage was the ORDER: it committed, then crashed. A refused
    write must leave the pour exactly as it was, so a retry cannot double it.
    """
    other = mf.build(db, estimate)
    db.flush()
    pour = _a_pour(db, slab.id)
    before = _beam_count(db, pour)

    client.post(
        "/api/grade-beams",
        json={
            "mono_slab_id": pour,
            "beam_type_id": _types(client, other.id)[0]["id"],
            "length_lf": 10,
        },
    )
    assert _beam_count(db, pour) == before


def test_bulk_replace_only_touches_its_own_kind(client, db, slab):
    """Saving GBs must not wipe Exp or Drops — the docstring's promise."""
    pour = _a_pour(db, slab.id)
    drops = _types(client, slab.id, kind="drop")
    if not drops:
        pytest.skip("fixture carries no drop types")

    client.put(
        f"/api/mono-slabs/{pour}/grade-beams",
        json={"kind": "drop", "beams": [{"beam_type_id": drops[0]["id"], "length_lf": 60}]},
    )
    kept = len(client.get(f"/api/grade-beams?mono_slab_id={pour}&kind=drop").json())
    assert kept == 1

    gbs = _types(client, slab.id, kind="grade_beam")
    client.put(
        f"/api/mono-slabs/{pour}/grade-beams",
        json={"kind": "grade_beam", "beams": [{"beam_type_id": gbs[0]["id"], "length_lf": 90}]},
    )
    still = len(client.get(f"/api/grade-beams?mono_slab_id={pour}&kind=drop").json())
    assert still == 1, "saving grade beams wiped the drops"
