"""
Call the three takeoff services directly, so their traceback lands in your
console instead of behind a FastAPI 500.

    python backend/debug_section.py                 # first section found
    python backend/debug_section.py <section_id>

Read-only in intent but NOT in effect: these services write their stored lines
and summary, which is the point — the failure is in that write path. Nothing
here touches an estimate's totals.
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import text  # noqa: E402

from app.db import SessionLocal  # noqa: E402


def main() -> int:
    db = SessionLocal()
    if len(sys.argv) > 1:
        section_id = sys.argv[1]
    else:
        section_id = db.execute(
            text(
                "SELECT s.id FROM estimate_sections s "
                "JOIN estimates e ON e.id = s.estimate_id "
                "ORDER BY e.updated_at DESC, s.sort_order LIMIT 1"
            )
        ).scalar()
    if not section_id:
        print("No sections found — has sql/033 been applied?")
        return 1

    name = db.execute(
        text("SELECT name FROM estimate_sections WHERE id = :i"), {"i": str(section_id)}
    ).scalar()
    print(f"section {section_id}  ({name})\n")

    for label, dotted in (
        ("labor", "app.services.labor:refresh_and_store_labor"),
        ("forming", "app.services.forming:refresh_and_store_forming"),
        ("equipment", "app.services.estimate_equipment:refresh_and_store_equipment"),
    ):
        module, func = dotted.split(":")
        fn = getattr(__import__(module, fromlist=[func]), func)
        try:
            fn(db, section_id)
            db.commit()
            print(f"{label:10} ok")
        except Exception:
            db.rollback()
            print(f"{label:10} FAILED")
            traceback.print_exc()
            print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
