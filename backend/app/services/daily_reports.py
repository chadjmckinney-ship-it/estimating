"""
Daily reports from the field (sql/084): reading one, the grids and their
man-hours, the pick-lists, the totals by job and month, and the import of
every Jotform submission.

Two Jotform forms carry the history. The one in use (210626162682150, since
2021-03) is bilingual and has the two grids, the pour block, tax exempt and
the maintenance checks; the older one (210135509985156, Jan–Mar 2021) typed
the job and the foreman as text and had the man-power grid only. Both are
read here by question id, into the one shape the app form writes.

Man-hours: the app form asks hours EACH, so a row is workers × hours. The
Jotform grids said only "Hrs worked" and were filled both ways over the
years — "3 workers, 30 hrs" in 2021, "12 workers, 8 hrs" in 2026 — so an
imported row's hours over sixteen are read as the row's total for the day
and anything else as hours each. Nobody works a seventeen-hour day.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, object_session

from app.models.daily_report import (
    FORM_SUPPLIERS,
    MAINTENANCE,
    MAINTENANCE_LABELS,
    SUB_TRADES,
    TRADE_LABELS,
    TRADES,
    DailyReport,
    DailyReportCrew,
    DailyReportSub,
    FieldForeman,
    FieldJob,
)
from app.models.estimator import Estimator
from app.models.mix_design import ConcreteSupplier
from app.models.project import Project

OFFICE_TZ = ZoneInfo("America/Chicago")
NEW_FORM = "210626162682150"
OLD_FORM = "210135509985156"
# An imported grid row with more hours than this is a day's total, not hours each.
TOTAL_HOURS_ABOVE = Decimal("16")
UNASSIGNED_JOB = "Unassigned"


# ------------------------------------------------------------- man-hours --


def man_hours(workers: int, hours: Decimal, *, imported: bool = False) -> Decimal:
    hours = Decimal(hours)
    if imported and hours > TOTAL_HOURS_ABOVE:
        return hours.quantize(Decimal("0.01"))
    return (Decimal(workers) * hours).quantize(Decimal("0.01"))


def set_grids(report: DailyReport, crew: list[dict] | None, subs: list[dict] | None, *, imported: bool = False) -> None:
    """Replace the grids given (None leaves one as it is). Rows with nothing on them are dropped."""
    session = object_session(report)
    if crew is not None:
        report.crew.clear()
        if session is not None:
            session.flush()  # the old rows go before the new ones come, or (report_id, trade) collides
        for row in crew:
            workers, hours = int(row.get("workers") or 0), Decimal(row.get("hours") or 0)
            if not workers and not hours:
                continue
            report.crew.append(DailyReportCrew(
                trade=row["trade"], workers=workers, hours=hours,
                man_hours=man_hours(workers, hours, imported=imported),
            ))
    if subs is not None:
        report.subs.clear()
        if session is not None:
            session.flush()
        n = 0
        for row in subs:
            name = str(row.get("sub_name") or "").strip()
            workers, hours = int(row.get("workers") or 0), Decimal(row.get("hours") or 0)
            if not name and not workers and not hours:
                continue
            report.subs.append(DailyReportSub(
                sort_order=n, trade=row["trade"], sub_name=name or "(unnamed)", workers=workers, hours=hours,
                man_hours=man_hours(workers, hours, imported=imported),
            ))
            n += 1


# --------------------------------------------------------------- reading --


def to_read(db: Session, row: DailyReport, people: dict[Any, str] | None = None) -> dict[str, Any]:
    if people is None:
        people = {}
        if row.submitted_by:
            person = db.get(Estimator, row.submitted_by)
            if person is not None:
                people[person.id] = person.full_name
    crew = [
        {"trade": c.trade, "workers": c.workers, "hours": c.hours, "man_hours": c.man_hours}
        for c in sorted(row.crew or [], key=lambda c: TRADES.index(c.trade) if c.trade in TRADES else 99)
    ]
    subs = [
        {"trade": s.trade, "sub_name": s.sub_name, "workers": s.workers, "hours": s.hours, "man_hours": s.man_hours}
        for s in (row.subs or [])
    ]
    return {
        "id": row.id,
        "report_date": row.report_date,
        "job_id": row.job_id,
        "job_name": row.job.name if row.job is not None else "",
        "foremen": list(row.foremen or []),
        "work_accomplished": row.work_accomplished,
        "delays": row.delays,
        "plan_tomorrow": row.plan_tomorrow,
        "safety_concerns": row.safety_concerns,
        "comments": row.comments,
        "concrete_poured": row.concrete_poured,
        "yards_poured": row.yards_poured,
        "supplier": row.supplier,
        "what_poured": row.what_poured,
        "tax_exempt": row.tax_exempt,
        "maintenance": list(row.maintenance or []),
        "source": row.source,
        "jotform_submission_id": row.jotform_submission_id,
        "signature_url": row.signature_url,
        "submitted_at": row.submitted_at,
        "submitted_by": row.submitted_by,
        "submitted_by_name": people.get(row.submitted_by) if row.submitted_by else None,
        "crew": crew,
        "subs": subs,
        "workers": sum(c["workers"] for c in crew),
        "man_hours": sum((c["man_hours"] for c in crew), Decimal(0)),
        "sub_workers": sum(s["workers"] for s in subs),
        "sub_man_hours": sum((s["man_hours"] for s in subs), Decimal(0)),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def reads(db: Session, rows: list[DailyReport]) -> list[dict[str, Any]]:
    ids = {r.submitted_by for r in rows if r.submitted_by}
    people = (
        {e.id: e.full_name for e in db.scalars(select(Estimator).where(Estimator.id.in_(ids))).all()} if ids else {}
    )
    return [to_read(db, r, people) for r in rows]


def _usage(db: Session, column) -> dict[int, tuple[int, date | None]]:
    """reports per job (or foreman-free) key: {key: (count, last date)}."""
    db.flush()
    rows = db.execute(
        select(column, func.count(DailyReport.id), func.max(DailyReport.report_date)).group_by(column)
    ).all()
    return {k: (n, last) for k, n, last in rows}


def job_reads(db: Session) -> list[dict[str, Any]]:
    usage = _usage(db, DailyReport.job_id)
    jobs = db.scalars(select(FieldJob).order_by(FieldJob.is_active.desc(), FieldJob.sort_order, FieldJob.name)).all()
    pids = {j.project_id for j in jobs if j.project_id}
    projects = {p.id: p.name for p in db.scalars(select(Project).where(Project.id.in_(pids))).all()} if pids else {}
    return [
        {
            "id": j.id, "name": j.name, "project_id": j.project_id,
            "project_name": projects.get(j.project_id) if j.project_id else None,
            "is_active": j.is_active, "sort_order": j.sort_order,
            "reports": usage.get(j.id, (0, None))[0], "last_report": usage.get(j.id, (0, None))[1],
        }
        for j in jobs
    ]


def foreman_reads(db: Session) -> list[dict[str, Any]]:
    db.flush()
    # A report names its foremen in text; count a foreman's reports by name.
    counts: dict[str, tuple[int, date | None]] = {}
    for names, day in db.execute(select(DailyReport.foremen, DailyReport.report_date)).all():
        for name in names or []:
            n, last = counts.get(name.lower(), (0, None))
            counts[name.lower()] = (n + 1, day if last is None or day > last else last)
    rows = db.scalars(
        select(FieldForeman).order_by(FieldForeman.is_active.desc(), FieldForeman.sort_order, FieldForeman.name)
    ).all()
    return [
        {
            "id": f.id, "name": f.name, "estimator_id": f.estimator_id, "is_active": f.is_active,
            "sort_order": f.sort_order,
            "reports": counts.get(f.name.lower(), (0, None))[0], "last_report": counts.get(f.name.lower(), (0, None))[1],
        }
        for f in rows
    ]


def meta(db: Session) -> dict[str, Any]:
    catalog = db.scalars(
        select(ConcreteSupplier.name).where(ConcreteSupplier.is_active.is_(True)).order_by(ConcreteSupplier.name)
    ).all()
    suppliers = list(FORM_SUPPLIERS)
    for name in catalog:
        if name.lower() not in {s.lower() for s in suppliers}:
            suppliers.append(name)
    return {
        "jobs": job_reads(db),
        "foremen": foreman_reads(db),
        "suppliers": suppliers,
        "trades": [{"key": k, "en": TRADE_LABELS[k][0], "es": TRADE_LABELS[k][1]} for k in TRADES],
        "sub_trades": list(SUB_TRADES),
        "maintenance": [{"key": k, "en": MAINTENANCE_LABELS[k][0], "es": MAINTENANCE_LABELS[k][1]} for k in MAINTENANCE],
    }


def summary(
    db: Session, job_id: int | None = None, date_from: date | None = None, date_to: date | None = None
) -> list[dict[str, Any]]:
    """Reports, pours, yards and man-hours by job and month, newest month first."""
    db.flush()  # raw SQL after ORM writes (tests/conftest.py, autoflush=False)
    where, params = [], {}
    if job_id is not None:
        where.append("r.job_id = :job_id")
        params["job_id"] = job_id
    if date_from is not None:
        where.append("r.report_date >= :date_from")
        params["date_from"] = date_from
    if date_to is not None:
        where.append("r.report_date <= :date_to")
        params["date_to"] = date_to
    sql = f"""
        SELECT j.id AS job_id, j.name AS job_name, to_char(r.report_date, 'YYYY-MM') AS month,
               count(*) AS reports, count(*) FILTER (WHERE r.concrete_poured) AS pours,
               coalesce(sum(r.yards_poured), 0) AS yards,
               coalesce(sum(c.mh), 0) AS man_hours, coalesce(sum(s.mh), 0) AS sub_man_hours
        FROM daily_reports r
        JOIN field_jobs j ON j.id = r.job_id
        LEFT JOIN (SELECT report_id, sum(man_hours) AS mh FROM daily_report_crew GROUP BY report_id) c ON c.report_id = r.id
        LEFT JOIN (SELECT report_id, sum(man_hours) AS mh FROM daily_report_subs GROUP BY report_id) s ON s.report_id = r.id
        {"WHERE " + " AND ".join(where) if where else ""}
        GROUP BY j.id, j.name, to_char(r.report_date, 'YYYY-MM')
        ORDER BY month DESC, j.name
    """
    return [dict(row) for row in db.execute(text(sql), params).mappings().all()]


# ---------------------------------------------------------------- import --


def _strip_tags(s: str) -> str:
    return re.sub(r"<[^>]+>", " ", s or "")


def _trade_key(label: str) -> str | None:
    """'Form setters / Carpinteros' → form_setters; the old form's '<div>Laborers</div>…' too."""
    english = _strip_tags(label).split("/")[0].strip().lower()
    english = re.sub(r"\s+", " ", english)
    for key in TRADES:
        if english == TRADE_LABELS[key][0].lower():
            return key
    return None


def _num(v: Any) -> Decimal:
    s = str(v if v is not None else "").strip().replace(",", "")
    m = re.search(r"-?\d+(\.\d+)?", s)
    if not m:
        return Decimal(0)
    try:
        return Decimal(m.group(0))
    except InvalidOperation:
        return Decimal(0)


def _pair(v: Any) -> tuple[int, Decimal]:
    """A grid cell pair — '["12","8"]' or ["12", "8"] — as (workers, hours)."""
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except ValueError:
            v = [v]
    if not isinstance(v, (list, tuple)):
        v = [v]
    workers = int(_num(v[0])) if len(v) > 0 else 0
    hours = _num(v[1]) if len(v) > 1 else Decimal(0)
    return max(workers, 0), max(hours, Decimal(0))


def _text(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, (list, tuple)):
        v = "\n".join(str(x) for x in v if x)
    s = str(v).replace("\r\n", "\n").strip()
    return s or None


def _join(*parts: str | None) -> str | None:
    kept = [p for p in parts if p]
    return "\n\n".join(kept) if kept else None


def normalize_job(name: str | None) -> str:
    """As the Notion importer did: the two Project X spellings to one each; nothing else touched."""
    s = (name or "").strip()
    low = s.lower()
    if "project x" in low:
        if "east" in low:
            return "PROJECT X EAST"
        if "west" in low:
            return "PROJECT X WEST"
    return s or UNASSIGNED_JOB


def _report_date(answer: Any, created_at: str | None) -> date:
    if isinstance(answer, dict):
        try:
            return date(int(answer.get("year")), int(answer.get("month")), int(answer.get("day")))
        except (TypeError, ValueError):
            pass
        dt = str(answer.get("datetime") or "")[:10]
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", dt):
            return date.fromisoformat(dt)
    if isinstance(answer, str) and re.fullmatch(r"\d{2}-\d{2}-\d{4}", answer.strip()):
        m, d, y = answer.strip().split("-")
        return date(int(y), int(m), int(d))
    return _submitted_at(created_at).date()


def _submitted_at(created_at: str | None) -> datetime:
    """Jotform writes the account's local time, 'YYYY-MM-DD HH:MM:SS'; the account is the office's."""
    if created_at:
        try:
            return datetime.strptime(created_at.strip(), "%Y-%m-%d %H:%M:%S").replace(tzinfo=OFFICE_TZ)
        except ValueError:
            pass
    return datetime.now(OFFICE_TZ)


def _maintenance(answer: Any) -> list[str]:
    out: list[str] = []
    for item in answer or []:
        low = str(item).lower()
        key = (
            "fuel" if "fuel" in low else "grease" if "greas" in low else "oil" if "oil" in low
            else "hydraulic" if "hydraul" in low else "tires" if "tire" in low else None
        )
        if key and key not in out:
            out.append(key)
    return out


def _yes_no(answer: Any) -> bool | None:
    items = [str(x).strip().lower() for x in (answer or []) if x] if isinstance(answer, (list, tuple)) else [
        str(answer).strip().lower()
    ] if answer else []
    if not items:
        return None
    return any(x == "yes" for x in items)


def _names(answer: Any) -> list[str]:
    items = answer if isinstance(answer, (list, tuple)) else [answer]
    out: list[str] = []
    for item in items:
        s = str(item or "").strip()
        if s and s.lower() not in {o.lower() for o in out}:
            out.append(s)
    return out


def _crew(answer: Any) -> list[dict]:
    rows: list[dict] = []
    if isinstance(answer, dict):
        for label, cell in answer.items():
            key = _trade_key(label)
            if key is None:
                continue
            workers, hours = _pair(cell)
            if workers or hours:
                rows.append({"trade": key, "workers": workers, "hours": hours})
    return rows


def _subs(answer: Any) -> list[dict]:
    rows: list[dict] = []
    cells: list[tuple[str | None, Any]] = []
    if isinstance(answer, dict):
        cells = [(_trade_key(label) or _sub_trade_key(label), cell) for label, cell in answer.items()]
    elif isinstance(answer, (list, tuple)):
        cells = [(SUB_TRADES[i] if i < len(SUB_TRADES) else None, cell) for i, cell in enumerate(answer)]
    for key, cell in cells:
        if key is None or key not in SUB_TRADES:
            continue
        if isinstance(cell, str):
            try:
                cell = json.loads(cell)
            except ValueError:
                cell = [cell]
        if not isinstance(cell, (list, tuple)):
            continue
        name = str(cell[0] if len(cell) > 0 else "").strip()
        workers = int(_num(cell[1])) if len(cell) > 1 else 0
        hours = _num(cell[2]) if len(cell) > 2 else Decimal(0)
        if name or workers or hours:
            rows.append({"trade": key, "sub_name": name, "workers": max(workers, 0), "hours": max(hours, Decimal(0))})
    return rows


def _sub_trade_key(label: str) -> str | None:
    key = _trade_key(label)
    return key if key in SUB_TRADES else None


def normalise_submission(form_id: str, sub: dict) -> dict[str, Any] | None:
    """One Jotform submission, either form, in the shape the app form writes. None when it is not a report."""
    answers = sub.get("answers")
    if not isinstance(answers, dict):
        return None
    if str(sub.get("status") or "ACTIVE").upper() != "ACTIVE":
        return None

    def get(qid: int) -> Any:
        return (answers.get(str(qid)) or {}).get("answer")

    old = form_id == OLD_FORM
    job = normalize_job(_text(get(4)) if old else _text(_names(get(44))[0] if _names(get(44)) else None))
    foremen = _names(get(14) if old else get(43))
    signature = get(18)
    row = {
        "report_date": _report_date(get(17), sub.get("created_at")),
        "job_name": job,
        "foremen": foremen,
        "work_accomplished": _text(get(5)),
        "delays": _join(_text(get(6)), _text(get(7))) if old else _text(get(6)),
        "plan_tomorrow": _text(get(8)),
        "safety_concerns": _text(get(11)),
        "comments": _text(get(12)) if old else None,
        "concrete_poured": bool(_yes_no(get(31))) if not old else False,
        "yards_poured": (_num(get(32)) if _text(get(32)) else None) if not old else None,
        "supplier": _text(get(42)) if not old else None,
        "what_poured": _text(get(33)) if not old else None,
        "tax_exempt": _yes_no(get(34)) if not old else None,
        "maintenance": _maintenance(get(27)) if not old else [],
        "crew": _crew(get(22)),
        "subs": _subs(get(35)) if not old else [],
        "signature_url": signature if isinstance(signature, str) and signature.startswith("http") else None,
        "submitted_at": _submitted_at(sub.get("created_at")),
        "jotform_form_id": form_id,
        "jotform_submission_id": str(sub.get("id")),
    }
    if row["yards_poured"] is not None and row["yards_poured"] < 0:
        row["yards_poured"] = None
    return row


IMPORTED_FIELDS = (
    "report_date", "foremen", "work_accomplished", "delays", "plan_tomorrow", "safety_concerns", "comments",
    "concrete_poured", "yards_poured", "supplier", "what_poured", "tax_exempt", "maintenance", "signature_url",
)


def _canon(v: Any) -> Any:
    """One spelling for a value whether it came from Jotform or back out of the database (42.5 vs 42.50)."""
    if isinstance(v, Decimal):
        return str(v.quantize(Decimal("0.01")))
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    if isinstance(v, (list, tuple)):
        return [_canon(x) for x in v]
    return v


def fingerprint(row: dict[str, Any], job_name: str, crew: list[dict], subs: list[dict]) -> str:
    """What the import wrote, hashed, so a rerun can tell untouched from edited here."""
    body = {k: _canon(row.get(k)) for k in IMPORTED_FIELDS}
    body["job_name"] = job_name.lower()
    body["crew"] = [(c["trade"], int(c["workers"]), str(Decimal(c["hours"]).quantize(Decimal("0.01")))) for c in crew]
    body["subs"] = [
        (s["trade"], s["sub_name"], int(s["workers"]), str(Decimal(s["hours"]).quantize(Decimal("0.01")))) for s in subs
    ]
    return hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _current_fingerprint(report: DailyReport) -> str:
    row = {k: getattr(report, k) for k in IMPORTED_FIELDS}
    row["foremen"] = list(report.foremen or [])
    row["maintenance"] = list(report.maintenance or [])
    crew = [{"trade": c.trade, "workers": c.workers, "hours": c.hours} for c in report.crew]
    subs = [{"trade": s.trade, "sub_name": s.sub_name, "workers": s.workers, "hours": s.hours} for s in report.subs]
    return fingerprint(row, report.job.name if report.job else "", crew, subs)


def ensure_job(db: Session, name: str, added: list[str]) -> FieldJob:
    job = db.scalars(select(FieldJob).where(func.lower(FieldJob.name) == name.lower())).first()
    if job is None:
        # Met in an old report, not on the form's list today: kept, but not offered.
        job = FieldJob(name=name, is_active=False, sort_order=999)
        db.add(job)
        db.flush()
        added.append(name)
    return job


def ensure_foremen(db: Session, names: list[str], added: list[str]) -> None:
    for name in names:
        if db.scalars(select(FieldForeman).where(func.lower(FieldForeman.name) == name.lower())).first() is None:
            db.add(FieldForeman(name=name, is_active=False, sort_order=999))
            db.flush()
            added.append(name)


def import_submissions(db: Session, form_id: str, submissions: list[dict]) -> dict[str, Any]:
    """Every submission upserted by its id. Flushes; the caller commits."""
    result: dict[str, Any] = {
        "created": 0, "updated": 0, "unchanged": 0, "skipped": 0, "jobs_added": [], "foremen_added": [], "errors": [],
    }
    for sub in submissions:
        try:
            row = normalise_submission(form_id, sub)
        except Exception as exc:  # noqa: BLE001 — one bad submission is a line in the report, not a lost import
            result["errors"].append(f"{sub.get('id')}: {exc}")
            continue
        if row is None:
            result["skipped"] += 1
            continue
        fp = fingerprint(row, row["job_name"], row["crew"], row["subs"])
        existing = db.scalars(
            select(DailyReport).where(DailyReport.jotform_submission_id == row["jotform_submission_id"])
        ).first()
        if existing is not None:
            if existing.import_fingerprint == fp:
                result["unchanged"] += 1
                continue
            if existing.import_fingerprint and _current_fingerprint(existing) != existing.import_fingerprint:
                result["skipped"] += 1  # edited here since the import; the app's version stands
                continue
        job = ensure_job(db, row["job_name"], result["jobs_added"])
        ensure_foremen(db, row["foremen"], result["foremen_added"])
        fields = {k: row[k] for k in IMPORTED_FIELDS}
        if existing is None:
            report = DailyReport(
                job_id=job.id, source="jotform", jotform_form_id=form_id,
                jotform_submission_id=row["jotform_submission_id"], submitted_at=row["submitted_at"],
                import_fingerprint=fp, **fields,
            )
            db.add(report)
            db.flush()
            set_grids(report, row["crew"], row["subs"], imported=True)
            result["created"] += 1
        else:
            for k, v in fields.items():
                setattr(existing, k, v)
            existing.job_id = job.id
            existing.submitted_at = row["submitted_at"]
            existing.import_fingerprint = fp
            set_grids(existing, row["crew"], row["subs"], imported=True)
            result["updated"] += 1
        db.flush()
    return result
