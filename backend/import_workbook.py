"""
Read an estimate workbook onto a job.

    python backend/import_workbook.py "<path>.xlsm" --dry-run          # read it, print what it would write
    python backend/import_workbook.py "<path>.xlsm"                    # write it, print the tie-out
    python backend/import_workbook.py "<path>.xlsm" --replace          # rebuild an estimate of the same name

Reads DATABASE_URL the way the app does (app.config). The project is found
by name or created; the estimate is named from the workbook's REVISION cell
unless --estimate says otherwise. See app/services/workbook_import.py.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path")
    ap.add_argument("--dry-run", action="store_true", help="read and print; write nothing")
    ap.add_argument("--replace", action="store_true", help="delete an estimate of the same name on the project first")
    ap.add_argument("--project", help="the project name to use (default: the workbook's JOB NAME)")
    ap.add_argument("--estimate", help="the estimate name to use (default: the workbook's REVISION)")
    args = ap.parse_args()

    from app.services.workbook_import import apply, describe, read_workbook, tie_out

    spec = read_workbook(args.path)
    print(describe(spec))
    if args.dry_run:
        print("\n(dry run: nothing written)")
        return 0

    from app.db import SessionLocal

    db = SessionLocal()
    try:
        report = apply(db, spec, replace=args.replace, project_name=args.project, estimate_name=args.estimate)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    print()
    print(tie_out(report))
    print(f"\nestimate: {report.estimate_id}  (#estimate/{report.estimate_id})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
