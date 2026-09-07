"""
Set an estimator's password from the command line (sql/068).

    python backend/set_password.py chad          # prompts twice, never echoes
    python backend/set_password.py --list        # who can sign in

This is how the first password gets set — before anyone can sign in, nobody
can reach the estimators screen to set one there. After that an admin can
reset anyone's from the screen (POST /api/estimators/{id}/password), and each
person changes their own from the sidebar. Every open session of the person
ends when their password is set here.

Uses the same DATABASE_URL the app uses.
"""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

BACKEND = Path(__file__).resolve().parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.auth import hash_password  # noqa: E402
from app.config import settings  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("username", nargs="?", help="the estimator's username")
    ap.add_argument("--list", action="store_true", help="show who can sign in")
    args = ap.parse_args()

    eng = create_engine(settings.database_url)
    if args.list or not args.username:
        with eng.connect() as conn:
            rows = conn.execute(text(
                "SELECT username, full_name, role, is_active, password_hash IS NOT NULL AS has_pw "
                "FROM estimators ORDER BY username"
            )).all()
        for r in rows:
            flag = "can sign in" if (r.has_pw and r.is_active) else ("no password" if r.is_active else "inactive")
            print(f"  {r.username:16} {r.full_name:24} {r.role:18} {flag}")
        return 0 if args.list else 2

    with eng.connect() as conn:
        row = conn.execute(
            text("SELECT id, full_name, is_active FROM estimators WHERE lower(username) = lower(:u)"),
            {"u": args.username},
        ).first()
    if row is None:
        print(f"no estimator named {args.username!r}; add them on the estimators screen first", file=sys.stderr)
        return 2
    if not row.is_active:
        print(f"{row.full_name} is deactivated; reactivate them first", file=sys.stderr)
        return 2

    pw = getpass.getpass(f"New password for {row.full_name}: ")
    if len(pw) < 8:
        print("at least 8 characters", file=sys.stderr)
        return 2
    if getpass.getpass("Again: ") != pw:
        print("they did not match", file=sys.stderr)
        return 2

    with eng.begin() as conn:
        conn.execute(
            text("UPDATE estimators SET password_hash = :h, updated_at = now() WHERE id = :i"),
            {"h": hash_password(pw), "i": row.id},
        )
        conn.execute(text("DELETE FROM sessions WHERE estimator_id = :i"), {"i": row.id})
    print(f"password set for {row.full_name}; any open session of theirs is signed out")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
