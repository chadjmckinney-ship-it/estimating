"""
Daily reports from the field (sql/084, 2026-09-09).

Chad: "this is a daily reports for projects.. right now we use jotform then
import into notion", then "I think we need to just import everything from
jotform then set a form page to fill out here instead of the extra step of
importing"; on the proposal, "build it".

Pinned here: the form's payload files a report with its two grids and their
man-hours (hours each); the list newest first and its filters; the totals
by job and month; the two pick-lists and their edits; the foreman role,
which files and reads and does nothing else; the Jotform import of both
forms as the API hands them over — the grids, several foremen on one
report, the date as a dict, hours over sixteen as a row's total, jobs and
foremen met for the first time added inactive, the rerun, a report edited
here left alone; a misspelled field a 422; a viewer reads and does not write.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select

from app import policy
from app.models.daily_report import DailyReport, FieldForeman, FieldJob
from app.services.daily_reports import NEW_FORM, OLD_FORM, man_hours

D = Decimal

# --- three Jotform submissions, the shapes the API returned on 2026-09-09 ---

NEW_SUB = {
    "id": "6647009234615378949", "form_id": NEW_FORM, "created_at": "2026-09-08 14:22:03", "status": "ACTIVE",
    "answers": {
        "5": {"name": "workAccomplished", "type": "control_textarea",
              "answer": "They are compacting the ground w/ the jumping jack x2 & back fill the SOG Wall."},
        "6": {"name": "delays", "answer": "None"},
        "8": {"name": "planFor", "answer": "Plan for tomorrow is once they passed Compaction test."},
        "11": {"name": "safetyConcerns", "answer": "None"},
        "17": {"name": "input17", "answer": {"month": "09", "day": "08", "year": "2026", "datetime": "2026-09-08 00:00:00"}},
        "22": {"name": "manPower", "type": "control_matrix", "answer": {
            "Foreman / Mayordomo": '["1","8"]', "Assistants / Asistentes": '["",""]', "Rod busters / Fierreros": '["",""]',
            "Form setters / Carpinteros": '["12","8"]', "Finishers / Acabadores": '["",""]', "Laborers / Ayudantes<br />": '["",""]',
        }},
        "27": {"name": "maintenancePerformed", "answer": [
            "Checked fuel level", "Grease machine / Engrasado", "Check oil Level / Nivel de Aceite",
            "Check Hydraulic Fluid Level / Nivel Hidráulico", "Tire pressure / Presión de Llantas",
        ]},
        "31": {"name": "concretePoured", "answer": ["No"]},
        "34": {"name": "taxExempt", "answer": ["No"]},
        "35": {"name": "subLabor", "type": "control_matrix", "answer": [["", "", ""], ["zaca", "6", "8"], ["", "", ""], ["", "", ""]]},
        "43": {"name": "foremenmayordomo", "answer": ["Jorge", "Jose G", "Daniel", "Juan Carlos"]},
        "44": {"name": "jobName44", "answer": ["MANHEIM DALLAS"]},
    },
}

POUR_SUB = {
    "id": "6647016765102538249", "form_id": NEW_FORM, "created_at": "2026-09-08 14:34:37", "status": "ACTIVE",
    "answers": {
        "5": {"answer": "Poured the SOG, 2nd pour."}, "6": {"answer": ""}, "8": {"answer": "Strip forms."},
        "11": {"answer": "None"},
        "17": {"answer": {"month": "09", "day": "08", "year": "2026", "datetime": "2026-09-08 00:00:00"}},
        "22": {"answer": {"Foreman / Mayordomo": '["1","10"]', "Finishers / Acabadores": '["4","10"]', "Laborers / Ayudantes<br />": '["2","10"]'}},
        "27": {"answer": ["Checked fuel level", "Tire pressure / Presión de Llantas"]},
        "31": {"answer": ["Yes"]}, "32": {"answer": "42.5 yds"}, "33": {"answer": "Slab on grade"},
        "34": {"answer": ["Yes"]}, "42": {"answer": "Cowtown"},
        "43": {"answer": ["Jorge"]}, "44": {"answer": ["NORTHWEST VILLAGE"]},
    },
}

OLD_SUB = {
    "id": "4919771983184728016", "form_id": OLD_FORM, "created_at": "2021-03-19 11:33:18", "status": "ACTIVE",
    "answers": {
        "4": {"name": "jobName", "answer": "Tesla Giga Austin"},
        "5": {"answer": "Rubbing and patching columns \nGeneral cleanup"},
        "7": {"name": "progressdelays", "answer": "Jorge walked the site and said the rebar and trash is not ours"},
        "8": {"name": "workPlanned", "answer": "Rubbing and patching columns"},
        "14": {"name": "foreman", "answer": "Brian McKinney"},
        "17": {"answer": {"month": "03", "day": "18", "year": "2021"}},
        "18": {"name": "signature", "answer": "https://www.jotform.com/uploads/Chad_McKinney/210135509985156/4919771983184728016/4919771983184728016_base64_18.png"},
        "22": {"answer": {
            "Foreman": '["1","10"]', "Assistants": '["1","10"]', "Rod busters": '["",""]', "Form setters": '["3","30"]',
            "Finishers": '["",""]', "<div>Laborers</div><div><br></div>": '["2","20"]',
        }},
    },
}


def _job_id(client, name: str) -> int:
    return next(j["id"] for j in client.get("/api/daily-reports/meta").json()["jobs"] if j["name"] == name)


def _report(client, **over) -> dict:
    body = {
        "report_date": "2026-09-09", "job_id": _job_id(client, "NORTHWEST VILLAGE"), "foremen": ["Jorge"],
        "work_accomplished": "Set forms for the paving", "delays": None, "plan_tomorrow": "Pour", "safety_concerns": None,
        "comments": None, "concrete_poured": False, "yards_poured": None, "supplier": None, "what_poured": None,
        "tax_exempt": None, "maintenance": ["fuel", "grease"],
        "crew": [{"trade": "foreman", "workers": 1, "hours": 8}, {"trade": "form_setters", "workers": 4, "hours": 8}],
        "subs": [{"trade": "finishers", "sub_name": "Zacarias", "workers": 6, "hours": 8}],
    }
    body.update(over)
    r = client.post("/api/daily-reports", json=body)
    assert r.status_code == 201, r.text
    return r.json()


# ------------------------------------------------------------- the form --


def test_the_form_files_a_report_with_its_grids(client):
    r = _report(client)
    assert (r["job_name"], r["foremen"], r["source"], r["submitted_by_name"]) == ("NORTHWEST VILLAGE", ["Jorge"], "app", "Test admin")
    assert [(c["trade"], c["workers"], D(c["hours"]), D(c["man_hours"])) for c in r["crew"]] == [
        ("foreman", 1, D("8"), D("8")), ("form_setters", 4, D("8"), D("32")),
    ]
    assert (r["workers"], D(r["man_hours"]), r["sub_workers"], D(r["sub_man_hours"])) == (5, D("40"), 6, D("48"))
    assert r["maintenance"] == ["fuel", "grease"] and r["concrete_poured"] is False
    assert client.get(f"/api/daily-reports/{r['id']}").json()["id"] == r["id"]
    assert [x["id"] for x in client.get("/api/daily-reports").json()] == [r["id"]]

    # An edit replaces the grid it sends and leaves the other; blanks and zero rows are dropped.
    e = client.patch(f"/api/daily-reports/{r['id']}", json={
        "concrete_poured": True, "yards_poured": "42.5", "supplier": "Cowtown", "what_poured": "SOG",
        "crew": [{"trade": "foreman", "workers": "1", "hours": "10"}, {"trade": "laborers", "workers": "", "hours": ""}],
    }).json()
    assert (e["concrete_poured"], D(e["yards_poured"]), e["supplier"]) == (True, D("42.5"), "Cowtown")
    assert [(c["trade"], D(c["man_hours"])) for c in e["crew"]] == [("foreman", D("10"))]
    assert D(e["sub_man_hours"]) == D("48"), "the sub grid was not sent, so it stays"
    assert client.delete(f"/api/daily-reports/{r['id']}").status_code == 204
    assert client.get(f"/api/daily-reports/{r['id']}").status_code == 404


def test_the_list_newest_first_and_its_filters(client):
    nw, md = _job_id(client, "NORTHWEST VILLAGE"), _job_id(client, "MANHEIM DALLAS")
    a = _report(client, report_date="2026-09-01", job_id=nw, foremen=["Jorge"])
    b = _report(client, report_date="2026-09-03", job_id=md, foremen=["Pedro", "Rene"], concrete_poured=True,
                yards_poured=30, what_poured="Columns")
    c = _report(client, report_date="2026-09-03", job_id=nw, foremen=["jorge"], work_accomplished="Stripped the wall forms")
    ids = lambda path: [x["id"] for x in client.get(path).json()]  # noqa: E731
    assert ids("/api/daily-reports") == [c["id"], b["id"], a["id"]], "newest day first, latest filed first within it"
    assert ids(f"/api/daily-reports?job_id={md}") == [b["id"]]
    assert ids("/api/daily-reports?foreman=JORGE") == [c["id"], a["id"]]
    assert ids("/api/daily-reports?foreman=Rene") == [b["id"]]
    assert ids("/api/daily-reports?date_from=2026-09-02") == [c["id"], b["id"]]
    assert ids("/api/daily-reports?date_to=2026-09-02") == [a["id"]]
    assert ids("/api/daily-reports?poured=true") == [b["id"]]
    assert ids("/api/daily-reports?q=columns") == [b["id"]]
    assert ids("/api/daily-reports?q=wall") == [c["id"]]
    assert ids("/api/daily-reports?limit=1&offset=1") == [b["id"]]


def test_the_totals_by_job_and_month(client):
    nw, md = _job_id(client, "NORTHWEST VILLAGE"), _job_id(client, "MANHEIM DALLAS")
    _report(client, report_date="2026-08-30", job_id=nw, concrete_poured=True, yards_poured=100)
    _report(client, report_date="2026-09-01", job_id=nw, concrete_poured=True, yards_poured="42.5")
    _report(client, report_date="2026-09-02", job_id=nw)
    _report(client, report_date="2026-09-02", job_id=md, crew=[{"trade": "laborers", "workers": 3, "hours": 10}], subs=[])
    rows = client.get("/api/daily-reports/summary").json()
    assert [(r["job_name"], r["month"], r["reports"], r["pours"], D(r["yards"]), D(r["man_hours"]), D(r["sub_man_hours"])) for r in rows] == [
        ("MANHEIM DALLAS", "2026-09", 1, 0, D("0"), D("30"), D("0")),
        ("NORTHWEST VILLAGE", "2026-09", 2, 1, D("42.5"), D("80"), D("96")),
        ("NORTHWEST VILLAGE", "2026-08", 1, 1, D("100"), D("40"), D("48")),
    ]
    assert [r["month"] for r in client.get(f"/api/daily-reports/summary?job_id={nw}&date_from=2026-09-01").json()] == ["2026-09"]


def test_the_pick_lists(client, db):
    meta = client.get("/api/daily-reports/meta").json()
    active_jobs = [j["name"] for j in meta["jobs"] if j["is_active"]]
    assert "NORTHWEST VILLAGE" in active_jobs and "Office" in active_jobs and len(active_jobs) >= 15, "sql/084 seeds the form's list"
    assert [f["name"] for f in meta["foremen"] if f["is_active"]][:3] == ["Adan(Rocky)", "Benito", "Jorge"]
    assert meta["suppliers"][:2] == ["Cowtown", "Martin Marietta"] and "SRM" in meta["suppliers"]
    assert [t["key"] for t in meta["trades"]] == ["foreman", "assistants", "rod_busters", "form_setters", "finishers", "laborers"]
    assert meta["trades"][2]["es"] == "Fierreros" and [m["key"] for m in meta["maintenance"]][-1] == "tires"

    r = client.post("/api/daily-reports/jobs", json={"name": "  Pearl Landing  "})
    assert r.status_code == 201 and r.json()["name"] == "Pearl Landing" and r.json()["reports"] == 0, r.text
    assert client.post("/api/daily-reports/jobs", json={"name": "pearl landing"}).status_code == 409
    jid = r.json()["id"]
    _report(client, job_id=jid)
    off = client.patch(f"/api/daily-reports/jobs/{jid}", json={"is_active": False}).json()
    assert (off["is_active"], off["reports"], off["last_report"]) == (False, 1, "2026-09-09")
    assert next(j for j in client.get("/api/daily-reports/jobs").json() if j["id"] == jid)["is_active"] is False

    f = client.post("/api/daily-reports/foremen", json={"name": "Fidel"})
    assert f.status_code == 201, f.text
    assert client.post("/api/daily-reports/foremen", json={"name": "FIDEL"}).status_code == 409
    _report(client, foremen=["Fidel", "Jorge"])
    got = next(x for x in client.get("/api/daily-reports/foremen").json() if x["name"] == "Fidel")
    assert (got["reports"], got["last_report"]) == (1, "2026-09-09")
    assert client.patch(f"/api/daily-reports/foremen/{f.json()['id']}", json={"is_active": False}).json()["is_active"] is False


def test_man_hours_rule():
    assert man_hours(12, D("8")) == D("96") and man_hours(3, D("30")) == D("90")
    # Imported: hours over sixteen are the row's total; sixteen or under are hours each.
    assert man_hours(3, D("30"), imported=True) == D("30") and man_hours(12, D("8"), imported=True) == D("96")
    assert man_hours(2, D("16"), imported=True) == D("32") and man_hours(0, D("8")) == D("0")


# ---------------------------------------------------------- the foreman --


def test_a_foreman_files_and_reads_and_nothing_else(db, as_role):
    foreman = as_role("foreman")
    meta = foreman.get("/api/daily-reports/meta")
    assert meta.status_code == 200, meta.text
    job = meta.json()["jobs"][0]["id"]
    r = foreman.post("/api/daily-reports", json={
        "report_date": "2026-09-09", "job_id": job, "foremen": ["Jorge"], "work_accomplished": "Set forms",
        "crew": [{"trade": "foreman", "workers": 1, "hours": 8}],
    })
    assert r.status_code == 201, r.text
    assert r.json()["submitted_by_name"] == "Test foreman"
    assert foreman.get("/api/daily-reports").status_code == 200
    assert foreman.get(f"/api/daily-reports/{r.json()['id']}").status_code == 200
    assert foreman.get("/api/daily-reports/summary").status_code == 200

    for method, path, body in (
        ("patch", f"/api/daily-reports/{r.json()['id']}", {"delays": "rain"}),
        ("delete", f"/api/daily-reports/{r.json()['id']}", None),
        ("post", "/api/daily-reports/jobs", {"name": "New job"}),
        ("post", "/api/daily-reports/import", {"form_id": NEW_FORM, "submissions": []}),
        ("get", "/api/estimates", None),
        ("get", "/api/projects", None),
        ("get", "/api/bid-requests", None),
        ("get", "/api/materials", None),
        ("post", "/api/projects", {"name": "by a foreman"}),
    ):
        resp = getattr(foreman, method)(path, json=body) if body is not None else getattr(foreman, method)(path)
        assert resp.status_code == 403, (method, path, resp.text)
        assert "a foreman" in resp.json()["detail"], resp.text

    assert policy.allowed("foreman", "GET", "/api/daily-reports/meta")
    assert policy.allowed("foreman", "POST", "/api/daily-reports")
    assert not policy.allowed("foreman", "POST", "/api/daily-reports/jobs")
    assert not policy.allowed("foreman", "GET", "/api/estimates")
    assert policy.allowed("user", "GET", "/api/daily-reports") and not policy.allowed("user", "POST", "/api/daily-reports")
    assert policy.allowed("estimator", "POST", "/api/daily-reports/jobs")


def test_a_viewer_reads_and_does_not_write(db, as_role):
    viewer = as_role("user")
    assert viewer.get("/api/daily-reports").status_code == 200
    job = viewer.get("/api/daily-reports/meta").json()["jobs"][0]["id"]
    assert viewer.post("/api/daily-reports", json={"report_date": "2026-09-09", "job_id": job}).status_code == 403


def test_a_misspelled_field_is_a_422(client):
    job = _job_id(client, "Office")
    assert client.post("/api/daily-reports", json={"report_date": "2026-09-09", "job_id": job, "delay": "x"}).status_code == 422
    assert client.post("/api/daily-reports", json={"report_date": "2026-09-09", "job_id": job, "maintenance": ["wax"]}).status_code == 422
    assert client.post("/api/daily-reports", json={"report_date": "2026-09-09", "job_id": job,
                                                    "crew": [{"trade": "welders", "workers": 1, "hours": 8}]}).status_code == 422
    assert client.post("/api/daily-reports", json={"report_date": "2026-09-09", "job_id": 999999}).status_code == 400


# ---------------------------------------------------------- the import --


def test_the_jotform_import_both_forms(client, db):
    res = client.post("/api/daily-reports/import", json={"form_id": NEW_FORM, "submissions": [NEW_SUB, POUR_SUB]})
    assert res.status_code == 200, res.text
    assert res.json() == {"created": 2, "updated": 0, "unchanged": 0, "skipped": 0, "jobs_added": [], "foremen_added": [], "errors": []}

    rows = {r["jotform_submission_id"]: r for r in client.get("/api/daily-reports").json()}
    a = rows["6647009234615378949"]
    assert (a["report_date"], a["job_name"], a["foremen"], a["source"]) == (
        "2026-09-08", "MANHEIM DALLAS", ["Jorge", "Jose G", "Daniel", "Juan Carlos"], "jotform"
    )
    assert a["work_accomplished"].startswith("They are compacting") and a["delays"] == "None"
    assert (a["concrete_poured"], a["yards_poured"], a["tax_exempt"]) == (False, None, False)
    assert a["maintenance"] == ["fuel", "grease", "oil", "hydraulic", "tires"]
    assert [(c["trade"], c["workers"], D(c["hours"]), D(c["man_hours"])) for c in a["crew"]] == [
        ("foreman", 1, D("8"), D("8")), ("form_setters", 12, D("8"), D("96")),
    ]
    assert [(s["trade"], s["sub_name"], s["workers"], D(s["man_hours"])) for s in a["subs"]] == [("form_setters", "zaca", 6, D("48"))]
    assert a["submitted_at"].startswith("2026-09-08T14:22:03") and "-05:00" in a["submitted_at"], "the office's clock"

    p = rows["6647016765102538249"]
    assert (p["concrete_poured"], D(p["yards_poured"]), p["supplier"], p["what_poured"], p["tax_exempt"]) == (
        True, D("42.5"), "Cowtown", "Slab on grade", True
    )
    assert p["maintenance"] == ["fuel", "tires"] and D(p["man_hours"]) == D("70") and p["delays"] is None

    res = client.post("/api/daily-reports/import", json={"form_id": OLD_FORM, "submissions": [OLD_SUB]}).json()
    assert (res["created"], res["jobs_added"], res["foremen_added"]) == (1, ["Tesla Giga Austin"], ["Brian McKinney"])
    o = client.get("/api/daily-reports?q=Tesla").json()[0]
    assert (o["report_date"], o["foremen"], o["comments"]) == ("2021-03-18", ["Brian McKinney"], None)
    assert o["delays"] == "Jorge walked the site and said the rebar and trash is not ours"
    assert o["signature_url"].endswith("_base64_18.png")
    # 2021: "3 workers, 30 hrs" was the row's total, "1 worker, 10 hrs" hours each — 10 + 10 + 30 + 20.
    assert [(c["trade"], c["workers"], D(c["man_hours"])) for c in o["crew"]] == [
        ("foreman", 1, D("10")), ("assistants", 1, D("10")), ("form_setters", 3, D("30")), ("laborers", 2, D("20")),
    ]
    assert D(o["man_hours"]) == D("70")
    tesla = db.scalars(select(FieldJob).where(FieldJob.name == "Tesla Giga Austin")).one()
    brian = db.scalars(select(FieldForeman).where(FieldForeman.name == "Brian McKinney")).one()
    assert tesla.is_active is False and brian.is_active is False, "met in an old report, not offered on the form"

    # A rerun changes nothing, and a submission unchanged in Jotform leaves an edit made here alone;
    # one changed in Jotform comes through when nothing was edited here.
    again = client.post("/api/daily-reports/import", json={"form_id": NEW_FORM, "submissions": [NEW_SUB, POUR_SUB]}).json()
    assert (again["created"], again["updated"], again["unchanged"]) == (0, 0, 2)
    client.patch(f"/api/daily-reports/{a['id']}", json={"work_accomplished": "Corrected in the office"})
    changed = dict(POUR_SUB, answers=dict(POUR_SUB["answers"], **{"32": {"answer": "50"}}))
    third = client.post("/api/daily-reports/import", json={"form_id": NEW_FORM, "submissions": [NEW_SUB, changed]}).json()
    assert (third["updated"], third["unchanged"], third["skipped"]) == (1, 1, 0)
    assert client.get(f"/api/daily-reports/{a['id']}").json()["work_accomplished"] == "Corrected in the office"
    assert D(client.get(f"/api/daily-reports/{p['id']}").json()["yards_poured"]) == D("50")
    assert db.scalar(select(DailyReport.id).where(DailyReport.jotform_submission_id == "6647016765102538249")) is not None
    # Changed in Jotform AND edited here: the app's version stands, and the rerun says so.
    both = dict(NEW_SUB, answers=dict(NEW_SUB["answers"], **{"5": {"answer": "Changed in Jotform too"}}))
    fourth = client.post("/api/daily-reports/import", json={"form_id": NEW_FORM, "submissions": [both]}).json()
    assert (fourth["updated"], fourth["unchanged"], fourth["skipped"]) == (0, 0, 1)
    assert client.get(f"/api/daily-reports/{a['id']}").json()["work_accomplished"] == "Corrected in the office"

    # Not a report: a deleted submission, or one with no answers.
    junk = client.post("/api/daily-reports/import", json={"form_id": NEW_FORM, "submissions": [
        dict(NEW_SUB, id="1", status="DELETED"), {"id": "2", "created_at": "2026-09-08 09:00:00", "answers": []},
    ]}).json()
    assert (junk["created"], junk["skipped"]) == (0, 2)
