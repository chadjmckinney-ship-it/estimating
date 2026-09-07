"""
Router hygiene (audit 2026-09-04, P3 — batch 2, 2026-09-06).

Ten small things that were each true of one route and false of its
neighbours: a write that committed before it recalculated, a guard that
covered one assembly of five, a delete nothing guarded, a PATCH that took any
JSON for any key, a 500 where a 4xx belonged, a router mounted on its own
prefix, every error mapped to 404, a list that hit the ladder once per row,
a metadata that was only complete once a router had been imported, and a
crash swallowed without a word.
"""

from __future__ import annotations

import logging
import subprocess
import sys
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, text

from app.db import get_db
from app.main import app
from app.models.estimate_section import EstimateSection
from app.services.calc import _setting_numeric
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


# ------------------------------------------------------------ beam types --


def test_a_beam_type_edit_that_cannot_recalc_changes_nothing(client, db, estimate, monkeypatch):
    """Commit after the recalc, not before: a failed recalc leaves the type as it was."""
    section = mf.build(db, estimate)
    types = client.get(f"/api/sections/{section.id}/beam-types").json()
    assert types, "the slab fixture carries a beam schedule"
    t = types[0]

    import app.routers.beam_types as bt

    def boom(db_, section_id):
        raise RuntimeError("recalc blew up")

    monkeypatch.setattr(bt, "_recalc_section", boom)
    # The fixture session lives in one outer transaction; a bare rollback
    # would take the section with it. A savepoint stands in for what get_db
    # does on the server when a request raises: the flush is undone.
    sp = db.begin_nested()
    with pytest.raises(RuntimeError):
        client.patch(f"/api/beam-types/{t['id']}", json={"label": "RENAMED"})
    if sp.is_active:
        sp.rollback()
    db.expire_all()
    after = client.get(f"/api/sections/{section.id}/beam-types").json()
    assert isinstance(after, list) and after[0]["label"] == t["label"], after


# ------------------------------------------------------------- deletes --


def test_every_assembly_is_guarded_on_section_delete(client, db, estimate):
    """Until now only mono-slab pours stood between a section and its deletion."""
    for build, word in ((wf.build, "wall runs"), (pif.build, "pier groups")):
        section = build(db, estimate)
        r = client.delete(f"/api/sections/{section.id}")
        assert r.status_code == 409, r.text
        assert "takeoff rows" in r.json()["detail"] and word in r.json()["detail"]
        assert client.delete(f"/api/sections/{section.id}?force=true").status_code == 204
        assert db.get(EstimateSection, section.id) is None


def test_an_estimate_with_sections_refuses_to_delete_without_force(client, db, estimate):
    wf.build(db, estimate)
    r = client.delete(f"/api/estimates/{estimate.id}")
    assert r.status_code == 409, r.text
    assert "section" in r.json()["detail"]
    assert client.delete(f"/api/estimates/{estimate.id}?force=true").status_code == 204


def test_an_empty_estimate_deletes_without_ceremony(client, db, project):
    r = client.post("/api/estimates", json={"project_id": str(project.id), "name": "empty"})
    assert r.status_code == 201, r.text
    assert client.delete(f"/api/estimates/{r.json()['id']}").status_code == 204


# --------------------------------------------------------------- kind --


def test_a_kind_change_is_refused_once_a_section_has_rows(client, db, estimate):
    section = wf.build(db, estimate)
    r = client.patch(f"/api/sections/{section.id}", json={"kind": "piers"})
    assert r.status_code == 400 and "takeoff rows" in r.text, r.text
    empty = client.post(
        f"/api/estimates/{estimate.id}/sections", json={"kind": "piers", "name": "E", "unit": "EA"}
    ).json()
    r = client.patch(f"/api/sections/{empty['id']}", json={"kind": "columns"})
    assert r.status_code == 200 and r.json()["kind"] == "columns", r.text


# ------------------------------------------------------------ settings --


def test_a_setting_only_takes_the_shape_its_key_expects(client):
    assert client.patch("/api/system-settings/labor_forming_sf?recalc=false", json={"value": "abc"}).status_code == 400
    assert client.patch("/api/system-settings/labor_forming_sf?recalc=false", json={"value": True}).status_code == 400
    assert client.patch("/api/system-settings/labor_forming_sf?recalc=false", json={"value": "0.45"}).status_code == 200
    assert client.patch("/api/system-settings/equip_use_rental_tiers?recalc=false", json={"value": True}).status_code == 200
    assert client.patch("/api/system-settings/equip_use_rental_tiers?recalc=false", json={"value": "maybe"}).status_code == 400
    assert client.patch("/api/system-settings/default_vapor_barrier_material_id?recalc=false", json={"value": "x"}).status_code == 400
    assert client.patch("/api/system-settings/default_vapor_barrier_material_id?recalc=false", json={"value": None}).status_code == 200
    assert client.patch("/api/system-settings/mobilization_ls?recalc=false", json={"value": None}).status_code == 200


def test_a_malformed_setting_is_loud_not_a_silent_default(db):
    """The PATCH refuses one now; a row edited around it is refused on read (strict) rather than defaulted."""
    db.execute(text("""UPDATE system_settings SET value = '"abc"'::jsonb WHERE key = 'labor_forming_sf'"""))
    db.flush()
    with pytest.raises(ValueError, match="not a number"):
        _setting_numeric(db, "labor_forming_sf", D("9"))


# ------------------------------------------------------------- bulk ids --


def test_a_bulk_pour_row_with_a_bad_id_is_a_4xx_not_a_500(client, db, estimate):
    section = mf.build(db, estimate)
    r = client.put("/api/mono-slabs/bulk", json={
        "section_id": str(section.id),
        "rows": [{"id": "not-a-uuid", "description": "x", "square_footage": 100, "thickness_in": 4}],
    })
    assert r.status_code == 422 and r.json()["detail"][0]["loc"][-1] == "id", r.text
    r = client.put("/api/mono-slabs/bulk", json={
        "section_id": str(section.id),
        "rows": [{"id": str(uuid4()), "description": "x", "square_footage": 100, "thickness_in": 4}],
    })
    assert r.status_code == 400, r.text


# -------------------------------------------------------------- routes --


def test_every_section_route_lives_under_api_exactly_once():
    paths = list(app.openapi()["paths"])  # version-proof: include_router nests in newer FastAPI
    section_paths = [p for p in paths if "/sections" in p]
    assert section_paths
    assert all(p.startswith("/api/") for p in section_paths), [p for p in section_paths if not p.startswith("/api/")]
    assert not any(p.startswith("/api/api") for p in paths)
    assert any(p.endswith("/quotes/{kind}") for p in section_paths)


# ---------------------------------------------------------- line errors --


def test_an_unknown_equipment_line_is_404_and_a_bad_one_is_not_404(client, db, estimate):
    section = wf.build(db, estimate)
    client.get(f"/api/sections/{section.id}/equipment")  # stores the set
    r = client.patch(f"/api/sections/{section.id}/equipment/lines/no_such_line", json={"enabled": False})
    assert r.status_code == 404, r.text
    r = client.patch(f"/api/sections/{section.id}/equipment/lines/skid_steer", json={"rate": "not a number"})
    assert r.status_code == 422, r.text


# ------------------------------------------------------------ N+1 --


def test_listing_pours_reads_the_sections_kind_once(client, db, estimate):
    section = mf.build(db, estimate)
    hits = []

    def watch(conn, cursor, statement, parameters, context, executemany):
        if "SELECT kind FROM estimate_sections" in statement:
            hits.append(statement)

    engine = db.get_bind()
    event.listen(engine, "before_cursor_execute", watch)
    try:
        rows = client.get(f"/api/mono-slabs?section_id={section.id}").json()
    finally:
        event.remove(engine, "before_cursor_execute", watch)
    assert len(rows) > 1
    assert len(hits) <= 1, f"{len(hits)} kind lookups for {len(rows)} pours"


# ------------------------------------------------------------- models --


def test_the_metadata_is_complete_without_any_router():
    backend = Path(__file__).resolve().parents[1]
    out = subprocess.run(
        [sys.executable, "-c",
         "from app import models; from app.db import Base; print(','.join(sorted(Base.metadata.tables)))"],
        cwd=backend, capture_output=True, text=True,
    )
    assert out.returncode == 0, out.stderr
    tables = set(out.stdout.strip().split(","))
    for t in ("estimate_sections", "column_types", "wall_runs", "deck_levels", "pier_groups", "mono_slabs"):
        assert t in tables, t


# -------------------------------------------------------- rules screen --


def test_a_section_that_cannot_build_is_said_out_loud_on_the_rules_screen(client, db, estimate, monkeypatch, caplog):
    section = wf.build(db, estimate)
    import app.services.forming as fm

    def boom(db_, section_id):
        raise RuntimeError("forming fell over")

    monkeypatch.setattr(fm, "calc_forming_materials", boom)
    with caplog.at_level(logging.WARNING, logger="app.routers.estimate_rules"):
        r = client.get(f"/api/estimates/{estimate.id}/rules")
    assert r.status_code == 200, r.text
    assert any("could not build" in m and str(section.id) in m for m in caplog.messages), caplog.messages
