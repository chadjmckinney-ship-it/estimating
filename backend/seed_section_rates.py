"""
Seed every existing section's rates — the one-time backfill behind
"Rates are always per section" (Chad, 2026-09-05).

    python backend/seed_section_rates.py            # write
    python backend/seed_section_rates.py --dry-run  # say what would be written

A section made before 2026-09-05 inherited its kind's rates from the job's
price sheet, the assembly and the company, and would have followed them
forever. This writes each section-level price the section reads onto the
section at the value it resolves to right now, so nothing moves on the way in
and nothing that happens to those tables afterwards moves the section. New
sections are seeded by the API when they are created; this is for the ones
that already exist. Safe to run twice: a key already set on a section is
left alone.

Uses the same DATABASE_URL the app uses, like apply_sql.py.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

BACKEND = Path(__file__).resolve().parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.db import engine  # noqa: E402
from app.models.estimate_section import EstimateSection  # noqa: E402
from app.services import section_rates as sr  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dry-run", action="store_true", help="report, write nothing")
    args = ap.parse_args()

    with Session(engine) as db:
        sections = db.scalars(
            select(EstimateSection).order_by(EstimateSection.estimate_id, EstimateSection.sort_order)
        ).all()
        total = 0
        for s in sections:
            written = sr.seed(db, s, note="seeded 2026-09-05 (backfill)")
            total += len(written)
            print(f"{s.kind:16s} {s.name!r:34s} {len(written):3d} seeded"
                  + (f": {', '.join(written)}" if written else ""))
        if args.dry_run:
            db.rollback()
            print(f"dry run — {total} rates would be written across {len(sections)} sections")
        else:
            db.commit()
            print(f"{total} rates written across {len(sections)} sections")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
