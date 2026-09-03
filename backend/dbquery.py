"""
Run a read-only query against the estimating database.

There is no API for schema-level questions — "did the backfill land?", "how many
rows have a null section_id?" — and reaching for the app's own endpoints to
answer them only works for data the API happens to expose. This is the
smallest thing that closes that gap.

    python backend/dbquery.py --sql "SELECT count(*) FROM estimate_sections"
    python backend/dbquery.py --check sections

Read-only by construction: the statement must begin with SELECT or WITH, only
one statement is allowed, and the connection is opened in a read-only
transaction, so a cleverly worded string still cannot write.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import create_engine, text  # noqa: E402

from app.config import settings  # noqa: E402

# Named checks, so the common questions do not need retyping.
CHECKS: dict[str, str] = {
    "sections": """
        SELECT e.name AS estimate,
               count(s.id) AS sections,
               coalesce(string_agg(s.kind || ' (' || s.unit || ') margin '
                        || s.margin_pct, ', '), '—') AS detail
        FROM estimates e
        LEFT JOIN estimate_sections s ON s.estimate_id = e.id
        GROUP BY e.name ORDER BY e.name
    """,
    "orphans": """
        SELECT 'mono_slabs' AS tbl, count(*) AS null_section_id
          FROM mono_slabs WHERE section_id IS NULL
        UNION ALL SELECT 'estimate_forming_lines', count(*)
          FROM estimate_forming_lines WHERE section_id IS NULL
        UNION ALL SELECT 'estimate_labor_lines', count(*)
          FROM estimate_labor_lines WHERE section_id IS NULL
        UNION ALL SELECT 'estimate_equipment_lines', count(*)
          FROM estimate_equipment_lines WHERE section_id IS NULL
        UNION ALL SELECT 'estimate_beam_types', count(*)
          FROM estimate_beam_types WHERE section_id IS NULL
    """,
    "totals": """
        SELECT p.name AS project, e.name AS estimate, e.status,
               e.margin_pct, e.contingency_pct,
               e.calc_total_cost, e.calc_total_sale
        FROM estimates e JOIN projects p ON p.id = e.project_id
        ORDER BY p.name, e.name
    """,
    "migrations": """
        SELECT filename, applied_at FROM schema_migrations
        ORDER BY filename DESC LIMIT 12
    """,
}

_READ_ONLY = re.compile(r"^\s*(select|with)\b", re.IGNORECASE)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--sql", help="a single SELECT/WITH statement")
    g.add_argument("--check", choices=sorted(CHECKS), help="a named check")
    ap.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    args = ap.parse_args()

    sql = CHECKS[args.check] if args.check else args.sql
    if not _READ_ONLY.match(sql):
        print("Refusing: only SELECT and WITH statements are allowed.", file=sys.stderr)
        return 2
    if ";" in sql.strip().rstrip(";"):
        print("Refusing: one statement at a time.", file=sys.stderr)
        return 2

    engine = create_engine(args.database_url or settings.database_url)
    with engine.connect().execution_options(postgresql_readonly=True) as conn:
        rows = conn.execute(text(sql)).mappings().all()

    if not rows:
        print("(no rows)")
        return 0

    cols = list(rows[0].keys())
    widths = [
        max(len(c), *(len(str(r[c]) if r[c] is not None else "") for r in rows))
        for c in cols
    ]
    print("  ".join(c.ljust(w) for c, w in zip(cols, widths)))
    print("  ".join("-" * w for w in widths))
    for r in rows:
        print("  ".join(
            (str(r[c]) if r[c] is not None else "").ljust(w)
            for c, w in zip(cols, widths)
        ))
    print(f"\n{len(rows)} row(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
