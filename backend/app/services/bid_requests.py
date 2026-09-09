"""
The bid list (sql/082): reading a bid, choosing one to estimate, and the
import from the Notion "Concrete Estimating Bid list".

"Estimate this" is the one move that crosses from the stream to the chosen
few: it copies the bid's fields onto a new project, carries the estimators
across, links the two rows, and marks the bid in progress. The bid keeps its
own status from there — submitted and awarded are still typed on the bid
list, the way they were in Notion.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, time, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.bid_request import BID_STATUSES, BidRequest, BidRequestEstimator
from app.models.estimator import Estimator
from app.models.project import Project, ProjectEstimator

OFFICE_TZ = ZoneInfo("America/Chicago")

# Notion's status names, in the app's spelling.
NOTION_STATUS = {
    "Not started": "not_started",
    "In progress": "in_progress",
    "Submitted": "submitted",
    "Awarded": "awarded",
    "Cancelation": "canceled",
    "Canceled": "canceled",
}


class EstimateThisError(ValueError):
    """The bid cannot become a project; carries the message shown."""


def to_read(db: Session, row: BidRequest) -> dict[str, Any]:
    ids = [link.estimator_id for link in (row.estimator_links or [])]
    names: list[str] = []
    if ids:
        people = {e.id: e for e in db.scalars(select(Estimator).where(Estimator.id.in_(ids))).all()}
        names = [people[i].full_name for i in ids if i in people]
    project = db.get(Project, row.project_id) if row.project_id else None
    return {
        "id": row.id,
        "name": row.name,
        "gc": row.gc,
        "location": row.location,
        "project_types": list(row.project_types or []),
        "status": row.status,
        "bid_due": row.bid_due,
        "bid_due_time": row.bid_due_time,
        "bid_date": row.bid_date,
        "plans_url": row.plans_url,
        "bid_price": row.bid_price,
        "rev_date": row.rev_date,
        "rev_price": row.rev_price,
        "notes": row.notes,
        "message_id": row.message_id,
        "notion_page_id": row.notion_page_id,
        "project_id": row.project_id,
        "project_name": project.name if project is not None else None,
        "estimator_ids": ids,
        "estimator_names": names,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def set_estimators(db: Session, bid: BidRequest, estimator_ids: list[UUID]) -> list[str]:
    """Replace who is on the bid. Returns the ids that matched nobody."""
    ids = list(dict.fromkeys(estimator_ids))
    found = set(db.scalars(select(Estimator.id).where(Estimator.id.in_(ids))).all()) if ids else set()
    missing = [str(i) for i in ids if i not in found]
    bid.estimator_links.clear()
    db.flush()
    for eid in ids:
        if eid in found:
            bid.estimator_links.append(BidRequestEstimator(bid_request_id=bid.id, estimator_id=eid))
    return missing


def estimate_this(db: Session, bid: BidRequest, user_id: UUID | None) -> Project:
    """The bid becomes a project: every field copied, the people carried, the two linked."""
    if bid.project_id is not None and db.get(Project, bid.project_id) is not None:
        raise EstimateThisError("This bid is already being estimated")
    project = Project(
        name=bid.name.strip(),
        location=bid.location,
        gc=bid.gc,
        project_types=list(bid.project_types or []),
        status="in_progress",
        bid_due=bid.bid_due,
        bid_date=bid.bid_date,
        plans_url=bid.plans_url,
        bid_price=bid.bid_price,
        rev_date=bid.rev_date,
        rev_price=bid.rev_price,
        notes=bid.notes,
        notion_message_id=bid.message_id,
        notion_page_id=bid.notion_page_id,
        created_by=user_id,
    )
    db.add(project)
    db.flush()
    for link in bid.estimator_links or []:
        project.estimator_links.append(ProjectEstimator(project_id=project.id, estimator_id=link.estimator_id))
    bid.project_id = project.id
    if bid.status == "not_started":
        bid.status = "in_progress"
    bid.updated_at = datetime.now(timezone.utc)
    db.flush()
    return project


# ------------------------------------------------------------- import ----


def _page_id(url: str | None) -> str | None:
    """The 32 hex characters at the end of a Notion page URL, dashed the way the API writes ids."""
    if not url:
        return None
    m = re.search(r"([0-9a-f]{32})(?:\?|$)", url.strip().lower())
    if not m:
        return None
    h = m.group(1)
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


def _list(v: Any) -> list[str]:
    if v is None or v == "":
        return []
    if isinstance(v, list):
        return [str(x) for x in v]
    try:
        parsed = json.loads(v)
        return [str(x) for x in parsed] if isinstance(parsed, list) else [str(v)]
    except (TypeError, ValueError):
        return [s.strip() for s in str(v).split(",") if s.strip()]


def _when(value: Any, is_datetime: Any) -> tuple[date | None, time | None]:
    """A Notion date: a day, or an instant in UTC that becomes the office's day and hour."""
    if not value:
        return None, None
    s = str(value)
    if "T" in s:
        stamp = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        local = stamp.astimezone(OFFICE_TZ)
        return local.date(), (local.time().replace(second=0, microsecond=0) if int(is_datetime or 0) else None)
    return date.fromisoformat(s[:10]), None


def _notes(v: Any) -> str | None:
    """Notion's rich text as plain lines: <br> to newlines, [text](link) to text."""
    if not v:
        return None
    s = str(v).replace("<br>", "\n").replace("\\|", "|")
    s = re.sub(r"\[([^\]]+)\]\((?:mailto:)?[^)]+\)", r"\1", s)
    return s.strip() or None


def _money(v: Any) -> Decimal | None:
    if v is None or v == "":
        return None
    try:
        return Decimal(str(v)).quantize(Decimal("0.01"))
    except Exception:  # noqa: BLE001 — a Notion number that is not a number is nothing
        return None


def normalise_row(row: dict[str, Any]) -> dict[str, Any]:
    """A Notion export row (the MCP's SQL or rows mode) as the fields of a bid request."""
    g = row.get
    due, due_time = _when(g("bid_due", g("date:Bid Due:start")), g("due_dt", g("date:Bid Due:is_datetime")))
    received, _ = _when(g("bid_date", g("date:Bid Date:start")), 0)
    rev, _ = _when(g("rev_date", g("date:Rev date:start")), 0)
    status = NOTION_STATUS.get(str(g("status", g("Status")) or "").strip(), "not_started")
    plans = (g("plans", g("Link to plans")) or "").strip() or None
    if plans and not plans.lower().startswith(("http://", "https://")):
        plans = None
    return {
        "name": (g("name", g("Project Name")) or "").strip() or "(untitled)",
        "gc": (g("gc", g("GC")) or "").strip() or None,
        "location": (g("location", g("Location")) or "").strip() or None,
        "project_types": _list(g("types", g("Project Type"))),
        "status": status if status in BID_STATUSES else "not_started",
        "bid_due": due,
        "bid_due_time": due_time,
        "bid_date": received,
        "plans_url": plans,
        "bid_price": _money(g("bid_price", g("Bid Price"))),
        "rev_date": rev,
        "rev_price": _money(g("rev_price", g("Rev Price"))),
        "notes": _notes(g("notes", g("Notes"))),
        "message_id": (g("message_id", g("Message ID")) or "").strip() or None,
        "notion_page_id": _page_id(g("url")),
        "estimator_names": _list(g("estimators", g("Estimator"))),
    }


IMPORTED_FIELDS = (
    "name", "gc", "location", "project_types", "status", "bid_due", "bid_due_time", "bid_date",
    "plans_url", "bid_price", "rev_date", "rev_price", "notes", "message_id",
)


def fingerprint(fields: dict[str, Any]) -> str:
    """The Notion-sourced fields, hashed — the same from a normalised row or from a stored one."""
    flat = {k: (str(fields.get(k)) if fields.get(k) is not None else None) for k in IMPORTED_FIELDS}
    flat["project_types"] = sorted(fields.get("project_types") or [])
    return hashlib.sha256(json.dumps(flat, sort_keys=True).encode("utf-8")).hexdigest()


def _stored_fields(bid: BidRequest) -> dict[str, Any]:
    return {k: getattr(bid, k) for k in IMPORTED_FIELDS}


def import_rows(db: Session, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Load a Notion export. Upserts by Notion page id, so it can run again: a
    row never touched in the app takes Notion's values afresh; a row someone
    edited here is left alone and counted as skipped. A message id already on
    another bid is a duplicate invite and is listed, not entered twice.
    """
    people = {e.full_name.strip().lower(): e.id for e in db.scalars(select(Estimator)).all()}
    people.update({e.username.strip().lower(): e.id for e in db.scalars(select(Estimator)).all()})
    created = updated = unchanged = skipped = 0
    duplicates: list[str] = []
    unknown: set[str] = set()
    seen_names: dict[tuple[str, str], str] = {}

    for raw in rows:
        f = normalise_row(raw)
        names = f.pop("estimator_names")
        ids: list[UUID] = []
        for n in names:
            eid = people.get(n.strip().lower())
            if eid is None:
                unknown.add(n)
            else:
                ids.append(eid)

        key = (f["name"].lower(), (f["gc"] or "").lower())
        if key in seen_names:
            duplicates.append(f"{f['name']} ({f['gc'] or 'no GC'}) — also {seen_names[key]}")
        else:
            seen_names[key] = f["notion_page_id"] or "typed"

        existing = None
        if f["notion_page_id"]:
            existing = db.scalars(select(BidRequest).where(BidRequest.notion_page_id == f["notion_page_id"])).first()
        if existing is None and f["message_id"]:
            other = db.scalars(select(BidRequest).where(BidRequest.message_id == f["message_id"])).first()
            if other is not None:
                duplicates.append(f"{f['name']} — same invite as {other.name}")
                skipped += 1
                continue

        if existing is not None:
            # Edited here since the import wrote it, or already being estimated: leave it.
            edited_here = existing.import_fingerprint != fingerprint(_stored_fields(existing))
            if edited_here or existing.project_id is not None:
                skipped += 1
                continue
            incoming = fingerprint(f)
            if incoming == existing.import_fingerprint:
                unchanged += 1
                continue
            for k, v in f.items():
                setattr(existing, k, v)
            existing.import_fingerprint = incoming
            set_estimators(db, existing, ids)
            updated += 1
            continue

        bid = BidRequest(**f, import_fingerprint=fingerprint(f))
        db.add(bid)
        db.flush()
        set_estimators(db, bid, ids)
        created += 1

    db.flush()
    return {
        "created": created,
        "updated": updated,
        "unchanged": unchanged,
        "skipped": skipped,
        "duplicates": duplicates,
        "unknown_estimators": sorted(unknown),
    }
