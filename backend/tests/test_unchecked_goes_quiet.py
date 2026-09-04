"""
An unchecked line stops asking. (sql/056)

Chad, 2026-09-04:

    "there is one thing that is good and bad.. you have it set to that when
     something shows an error if nothing is entered, I like that so I can check
     it.. but that message should go away after I uncheck it as not used"

Both halves of that matter, and the second is the bug.

The unpriced list is the most valuable thing this app produces — it is the
answer to "what on this bid has no price behind it", and it has already caught
$436,826.42 of silent zeroes. Its value depends entirely on being ANSWERABLE.
A warning that stays lit after you have dealt with it teaches people to scroll
past the list, and once they do that they scroll past the real ones too.

Two ways a warning was unanswerable before this:

  1. **Mobilization fired BECAUSE the box was unchecked** (sql/053, my bug).
     The single gesture that means "considered, not needed" was the single
     gesture that could not clear it.
  2. **Forming lines had no box at all.** Labor and equipment lines have
     carried `enabled` since the beginning; forming never did. So `RESHORING —
     forming` — a real quantity with no rate anywhere in the system — sat on
     every deck section with nothing to click.

The rule these tests pin down, in one sentence: **a line nobody has looked at
warns; a line somebody switched off does not.** A line that is ON and carrying
nothing still warns, because that is the case the list exists for.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db import get_db
from app.main import app
from app.services.costing import refresh_pour_costs
from app.services.estimate_equipment import refresh_and_store_equipment
from app.services.forming import load_stored_forming, refresh_and_store_forming
from app.services.labor import refresh_and_store_labor
from app.services.recalc import recalc_section

D = Decimal


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _build(db, estimate, mod_name, *, supervise=True):
    import importlib

    mod = importlib.import_module(f"tests.{mod_name}")
    section = mod.build(db, estimate)
    refresh_and_store_forming(db, section.id)
    refresh_and_store_labor(db, section.id)
    refresh_and_store_equipment(db, section.id)
    if supervise and hasattr(mod, "type_the_supervision"):
        mod.type_the_supervision(db, section.id)
    refresh_pour_costs(db, section)
    db.flush()
    recalc_section(db, section)
    db.flush()
    return section


def _unpriced(db, section_id) -> list[str]:
    return db.execute(
        text("SELECT calc_unpriced FROM estimate_sections WHERE id = :i"),
        {"i": str(section_id)},
    ).scalar()


def _cost(db, section_id) -> Decimal:
    return db.execute(
        text("SELECT calc_total_cost FROM estimate_sections WHERE id = :i"),
        {"i": str(section_id)},
    ).scalar()


def _forming(db, section_id) -> dict:
    return {ln["code"]: ln for ln in load_stored_forming(db, section_id)["lines"]}


# ------------------------------------------------------------- mobilization


def test_mobilization_warns_while_the_box_is_ticked_and_empty(db, estimate):
    """
    The half that was RIGHT and has to stay right. A section billing 27 days of
    crane, with the mobilization line switched ON and carrying $0, has not been
    dealt with — nobody has said anything about it either way.
    """
    section = _build(db, estimate, "deck_fixture")
    assert any("mobilization — not entered" in x for x in _unpriced(db, section.id))


def test_unchecking_mobilization_silences_it(client, db, estimate):
    """
    The bug. Chad unchecks the line to say the iron is already on site from the
    last phase — a real zero, and one sql/053 explicitly wrote down as real —
    and the warning stayed lit anyway, because the condition it fired on was
    `not mobil.enabled`.
    """
    section = _build(db, estimate, "deck_fixture")

    r = client.patch(
        f"/api/sections/{section.id}/equipment/lines/mobilization",
        json={"enabled": False, "mark_manual": False},
    )
    assert r.status_code == 200, r.text

    assert not any("mobilization" in x for x in _unpriced(db, section.id))


def test_rechecking_mobilization_brings_it_back(client, db, estimate):
    """
    Silence is a property of the switch, not a latch. Turning the line back on
    with nothing entered puts the question back — otherwise unchecking once
    would blind the section forever.
    """
    section = _build(db, estimate, "deck_fixture")
    url = f"/api/sections/{section.id}/equipment/lines/mobilization"
    client.patch(url, json={"enabled": False, "mark_manual": False})
    assert not any("mobilization" in x for x in _unpriced(db, section.id))

    client.patch(url, json={"enabled": True, "mark_manual": False})
    assert any("mobilization — not entered" in x for x in _unpriced(db, section.id))


def test_unchecking_mobilization_does_not_hide_the_other_warnings(client, db, estimate):
    """
    One box answers one question. Silencing mobilization must not take the rest
    of the list with it — that would be a far more expensive bug than the one
    being fixed.
    """
    section = _build(db, estimate, "deck_fixture")
    before = [x for x in _unpriced(db, section.id) if "mobilization" not in x]
    assert before, "deck fixture is expected to carry other warnings"

    client.patch(
        f"/api/sections/{section.id}/equipment/lines/mobilization",
        json={"enabled": False, "mark_manual": False},
    )
    after = [x for x in _unpriced(db, section.id) if "mobilization" not in x]
    assert after == before


# ------------------------------------------------------------- supervision


def test_untyped_supervision_still_warns(db, estimate):
    """
    Audit #5, unchanged: a deck nobody has typed days on prices every rental at
    $0.00 beside a correct-looking rate. −$19,638.67 on piers when it happened
    for real.
    """
    section = _build(db, estimate, "deck_fixture", supervise=False)
    assert any("superintendent days" in x for x in _unpriced(db, section.id))


def test_unchecking_the_superintendent_silences_it(client, db, estimate):
    """
    Same rule, and safe here for a specific reason: on all three typed
    assemblies the whole rental ladder derives from super days, so zero days
    means the machines are already at zero. Switching the line off is somebody
    saying that is intended, and there is nothing left for the warning to
    protect.
    """
    section = _build(db, estimate, "deck_fixture", supervise=False)
    r = client.patch(
        f"/api/sections/{section.id}/labor/lines/superintendent",
        json={"enabled": False},
    )
    assert r.status_code == 200, r.text
    assert not any("superintendent days" in x for x in _unpriced(db, section.id))


# ----------------------------------------------------------------- forming


def test_forming_lines_now_have_a_switch(db, estimate):
    """Every stored lumber line reports `enabled`, and starts on."""
    section = _build(db, estimate, "deck_fixture")
    lines = _forming(db, section.id)
    assert lines, "deck fixture stores forming lines"
    assert all(ln["enabled"] is True for ln in lines.values())


def _an_unpriced_forming_code(db, section_id) -> str:
    lines = _forming(db, section_id)
    codes = [c for c, ln in lines.items() if ln["missing_price"]]
    assert codes, "deck fixture is expected to carry an unpriced forming line"
    return codes[0]


def test_unchecking_a_forming_line_takes_it_off_the_list(client, db, estimate):
    """
    The second half of Chad's report, and the one that needed a column. On a
    deck this is RESHORING: a real quantity whose rate does not exist anywhere
    in the system, so the estimator's only honest answers were "invent a price"
    or "live with the warning".
    """
    section = _build(db, estimate, "deck_fixture")
    code = _an_unpriced_forming_code(db, section.id)
    label = _forming(db, section.id)[code]["label"]
    assert any(f"{label} — forming" in x for x in _unpriced(db, section.id))

    r = client.patch(
        f"/api/sections/{section.id}/forming-materials/lines/{code}",
        json={"enabled": False},
    )
    assert r.status_code == 200, r.text

    assert not any(f"{label} — forming" in x for x in _unpriced(db, section.id))
    ln = _forming(db, section.id)[code]
    assert ln["enabled"] is False
    # Off is not deleted. The takeoff stays on screen, so the section still
    # shows WHAT was decided, not just what was bought.
    assert D(str(ln["qty"])) > 0
    assert ln["missing_price"] is False


def test_switching_a_priced_forming_line_off_removes_its_money(client, db, estimate):
    """
    A switch that changes a warning but not a total would be a lie. Off zeroes
    the extension and the section cost drops by exactly that, uplifts included.
    """
    section = _build(db, estimate, "deck_fixture")
    priced = {
        c: ln
        for c, ln in _forming(db, section.id).items()
        if ln["ext_cost"] is not None and D(str(ln["ext_cost"])) > 0
    }
    code, line = next(iter(priced.items()))
    ext = D(str(line["ext_cost"]))
    before = _cost(db, section.id)

    client.patch(
        f"/api/sections/{section.id}/forming-materials/lines/{code}",
        json={"enabled": False},
    )
    assert D(str(_forming(db, section.id)[code]["ext_cost"])) == 0
    after = _cost(db, section.id)
    assert after < before
    # Lumber is taxed, so the section drops by more than the raw extension.
    assert after <= before - ext


def test_a_refresh_does_not_undo_the_decision(client, db, estimate):
    """
    The rule labor and equipment already follow. A refresh rewrites
    QUANTITIES; it must not quietly switch a line back on, or the warning
    returns the next time anybody touches a pour and the estimator concludes
    the checkbox does not work.
    """
    section = _build(db, estimate, "deck_fixture")
    code = _an_unpriced_forming_code(db, section.id)
    client.patch(
        f"/api/sections/{section.id}/forming-materials/lines/{code}",
        json={"enabled": False},
    )

    refresh_and_store_forming(db, section.id)
    db.flush()
    assert _forming(db, section.id)[code]["enabled"] is False


def test_rechecking_a_forming_line_restores_its_cost(client, db, estimate):
    """Reversible, and to the same number — off is not a destructive edit."""
    section = _build(db, estimate, "deck_fixture")
    priced = {
        c: ln
        for c, ln in _forming(db, section.id).items()
        if ln["ext_cost"] is not None and D(str(ln["ext_cost"])) > 0
    }
    code, line = next(iter(priced.items()))
    ext = D(str(line["ext_cost"]))
    before = _cost(db, section.id)
    url = f"/api/sections/{section.id}/forming-materials/lines/{code}"

    client.patch(url, json={"enabled": False})
    client.patch(url, json={"enabled": True})

    assert D(str(_forming(db, section.id)[code]["ext_cost"])) == ext
    assert _cost(db, section.id) == before


def test_toggling_an_unknown_forming_code_404s(client, db, estimate):
    section = _build(db, estimate, "deck_fixture")
    r = client.patch(
        f"/api/sections/{section.id}/forming-materials/lines/not_a_line",
        json={"enabled": False},
    )
    assert r.status_code == 404


def test_the_forming_switch_reaches_the_screen(client, db, estimate):
    """
    The schema-drop guard, for the sixth time. `enabled` on the model and not
    on `FormingLine` would render every box checked, forever, with the server
    disagreeing — the exact failure `perm_edge_lf` and `subcontracted` had.
    """
    section = _build(db, estimate, "deck_fixture")
    code = _an_unpriced_forming_code(db, section.id)
    client.patch(
        f"/api/sections/{section.id}/forming-materials/lines/{code}",
        json={"enabled": False},
    )
    r = client.get(f"/api/sections/{section.id}/forming-materials")
    assert r.status_code == 200, r.text
    served = {ln["code"]: ln for ln in r.json()["lines"]}
    assert "enabled" in served[code], "FormingLine dropped `enabled` on the way out"
    assert served[code]["enabled"] is False
    assert all(v["enabled"] is True for k, v in served.items() if k != code)
