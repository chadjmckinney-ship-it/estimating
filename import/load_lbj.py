"""Load LBJ PT SOG from New Current Worksheet.xlsm into the local estimating API."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from decimal import Decimal

import openpyxl

BASE = "http://127.0.0.1:8001/api"
WB = r"C:\Users\Chad\Estimate_Projects\import\New Current Worksheet.xlsm"


def api(method: str, path: str, body=None):
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read()
            if not raw:
                return None
            return json.loads(raw)
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", "replace")
        raise SystemExit(f"{method} {path} -> {e.code} {err}") from e


def num(v):
    if v is None or v == "":
        return None
    return float(v)


def main():
    projects = api("GET", "/projects") or []
    existing = next((p for p in projects if p.get("name") == "5550 LBJ Multifamily"), None)
    if existing:
        print("project exists", existing["id"])
        project = existing
    else:
        project = api(
            "POST",
            "/projects",
            {
                "name": "5550 LBJ Multifamily",
                "job_number": "26-079",
                "location": "Dallas, TX",
                "gc": "OHT Partners",
                "project_types": ["Multifamily"],
                "status": "awarded",
                "bid_price": 2375000,
                "notes": "Imported 2026-08-27 from Estimate/New Current Worksheet.xlsm sheet 04-PT Slab on Grade. PT SOG only; podium/paving/ROW not in app schema yet.",
            },
        )
        print("created project", project["id"])

    estimates = api("GET", f"/estimates?project_id={project['id']}") or []
    existing_est = next((e for e in estimates if e.get("name") == "04-PT Slab on Grade"), None)
    if existing_est:
        raise SystemExit(f"estimate already exists {existing_est['id']} — not duplicating")

    mix_list = api("GET", "/mix-designs") or []
    mix_id = None
    for m in mix_list:
        if m.get("strength_psi") == 3000 and m.get("has_ash") and m.get("has_air"):
            mix_id = m["id"]
            print("mix", m.get("name") or m.get("code"), mix_id)
            break
    if mix_id is None:
        print("WARN no 3000 air+ash mix; pours will have mix_design_id null")

    estimators = api("GET", "/estimators") or []
    chad_id = None
    for e in estimators:
        uname = (e.get("username") or e.get("full_name") or "").lower()
        if "chad" in uname:
            chad_id = e["id"]
            break

    estimate = api(
        "POST",
        "/estimates",
        {
            "project_id": project["id"],
            "name": "04-PT Slab on Grade",
            "status": "draft",
            "estimator_id": chad_id,
            "version": 1,
            "waste_concrete": 0.06,
            "waste_rebar": 0.1,
            "form_percent": 0.5,
            "notes": "Source: New Current Worksheet.xlsm / 04-PT Slab on Grade. 16 pours. PT spacing not on the sheet.",
        },
    )
    eid = estimate["id"]
    print("created estimate", eid)

    beam_defs = [
        {
            "excel": 1,
            "label": "GB 1 — 12x32",
            "kind": "grade_beam",
            "width_in": 12,
            "height_in": 32,
            "top_bars_count": 2,
            "top_bars_size": 5,
            "stirrup_size": 3,
            "stirrup_spacing_in": 24,
            "sort_order": 10,
        },
        {
            "excel": 2,
            "label": "GB 2 — 10x30",
            "kind": "grade_beam",
            "width_in": 10,
            "height_in": 30,
            "top_bars_count": 2,
            "top_bars_size": 5,
            "stirrup_size": 3,
            "stirrup_spacing_in": 24,
            "sort_order": 20,
        },
        {
            "excel": 3,
            "label": "GB 3 — 10x30 2+2",
            "kind": "grade_beam",
            "width_in": 10,
            "height_in": 30,
            "top_bars_count": 2,
            "top_bars_size": 5,
            "bottom_bars_count": 2,
            "bottom_bars_size": 5,
            "stirrup_size": 3,
            "stirrup_spacing_in": 16,
            "sort_order": 30,
        },
        {
            "excel": 9,
            "label": "Drop 9 — 12x12",
            "kind": "drop",
            "width_in": 12,
            "height_in": 12,
            "top_bars_count": 2,
            "top_bars_size": 5,
            "bottom_bars_count": 2,
            "bottom_bars_size": 5,
            "stirrup_size": 3,
            "stirrup_spacing_in": 16,
            "sort_order": 90,
        },
    ]
    type_ids = {}
    for d in beam_defs:
        excel = d.pop("excel")
        created = api("POST", f"/estimates/{eid}/beam-types", d)
        type_ids[excel] = created["id"]
        print("beam type", excel, created["id"])

    wb = openpyxl.load_workbook(WB, data_only=True, read_only=True)
    ws = wb["04-PT Slab on Grade"]
    rows = list(ws.iter_rows(min_row=10, max_row=25, max_col=36, values_only=True))
    wb.close()

    total_sf = 0.0
    n = 0
    for row in rows:
        label = row[0]
        if label is None:
            continue
        try:
            pour_no = int(str(label).strip())
        except ValueError:
            continue
        if pour_no < 1 or pour_no > 16:
            continue
        sf = num(row[3])
        thk = num(row[5])
        if not sf or not thk:
            continue
        sand = num(row[9])
        perim = num(row[10])
        cable = str(row[7] or "").strip().lower() in {"y", "yes", "1", "true"}
        pour = api(
            "POST",
            "/mono-slabs",
            {
                "estimate_id": eid,
                "description": f"Pour {pour_no:02d}",
                "square_footage": sf,
                "thickness_in": thk,
                "post_tension": cable,
                "mix_design_id": mix_id,
                "sand_thickness_in": sand,
                "perimeter_edge_lf": perim,
                "sort_order": pour_no * 10,
            },
        )
        slab_id = pour["id"]
        total_sf += sf
        n += 1

        gb_beams = []
        for type_idx, lf_idx in ((28, 29), (30, 31), (32, 33), (34, 35)):
            tno = row[type_idx]
            lf = num(row[lf_idx])
            if tno is None or not lf:
                continue
            tno = int(tno)
            if tno not in type_ids:
                print("skip unknown GB type", tno, "pour", pour_no)
                continue
            if type_ids[tno] and beam_defs_kind(tno) == "grade_beam":
                gb_beams.append({"beam_type_id": type_ids[tno], "length_lf": lf})
        if gb_beams:
            api("PUT", f"/mono-slabs/{slab_id}/grade-beams", {"kind": "grade_beam", "beams": gb_beams})

        drop_type = row[22]
        drop_lf = num(row[23])
        if drop_type is not None and drop_lf:
            dno = int(drop_type)
            if dno in type_ids:
                api(
                    "PUT",
                    f"/mono-slabs/{slab_id}/grade-beams",
                    {"kind": "drop", "beams": [{"beam_type_id": type_ids[dno], "length_lf": drop_lf}]},
                )
        print(f"pour {pour_no:02d} sf={sf} id={slab_id}")

    totals = api("GET", f"/mono-slabs/totals?estimate_id={eid}")
    print("LOADED pours", n, "sheet_sf", total_sf)
    print("API totals", json.dumps(totals, default=str))


def beam_defs_kind(excel_no: int) -> str:
    return "drop" if excel_no == 9 else "grade_beam"


if __name__ == "__main__":
    main()
