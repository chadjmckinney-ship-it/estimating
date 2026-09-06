"""
Register the daily Task Scheduler job that dumps the estimating database.

    python backend/register_backup_task.py                     # 6:00 PM daily, ~/Backups/estimating, keep 30
    python backend/register_backup_task.py --at 17:30
    python backend/register_backup_task.py --copy-to "C:/Users/Chad/OneDrive - S and S Concrete Contractors Inc/Backups/estimating"
    python backend/register_backup_task.py --dry-run           # show the task, register nothing
    python backend/register_backup_task.py --remove

Python rather than PowerShell on purpose. Chad, 2026-09-05, on the .ps1 this
replaces: "lol, I still have not allowed running scripts." The execution
policy stops .ps1 files; it does not stop python.exe, and schtasks.exe takes
a task as XML from anyone. So this writes the XML and hands it over.

The task runs backend/backup_db.py with the repo's own venv Python, daily,
and catches up on wake if the laptop was asleep at the time
(StartWhenAvailable). It runs as the current user without a stored password
(S4U), which is enough to reach a local PostgreSQL that trusts the OS user —
the same way the API and apply_sql.py reach it. -CopyTo puts a second copy on
another disk; OneDrive is the obvious one on this machine, and that directory
is never pruned.

Registering a scheduled task is a change to this machine, which is why this
is a script Chad runs rather than something the assistant runs for him.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from xml.sax.saxutils import escape

TASK_NAME = "Estimating DB backup"
BACKEND = Path(__file__).resolve().parent
REPO = BACKEND.parent
PYTHON = REPO / ".venv-win" / "Scripts" / "python.exe"
SCRIPT = BACKEND / "backup_db.py"


def task_xml(*, at: str, keep: int, copy_to: str | None, python: Path = PYTHON,
             script: Path = SCRIPT, workdir: Path = REPO, user: str | None = None) -> str:
    """The Task Scheduler 1.2 definition. Pure — nothing is registered here."""
    hh, mm = (int(x) for x in at.split(":"))
    start = datetime.now().replace(hour=hh, minute=mm, second=0, microsecond=0)
    if start < datetime.now():
        start += timedelta(days=1)
    user = user or f"{os.environ.get('USERDOMAIN', '')}\\{os.environ.get('USERNAME', '')}".strip("\\")
    args = f'"{script}" --keep {keep}'
    if copy_to:
        args += f' --copy-to "{copy_to}"'
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Dumps the estimating database with pg_dump and verifies the dump (backend/backup_db.py). Registered by backend/register_backup_task.py.</Description>
  </RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>{start.strftime('%Y-%m-%dT%H:%M:%S')}</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay>
    </CalendarTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>{escape(user)}</UserId>
      <LogonType>S4U</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT30M</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{escape(str(python))}</Command>
      <Arguments>{escape(args)}</Arguments>
      <WorkingDirectory>{escape(str(workdir))}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--at", default="18:00", help="time of day, 24h HH:MM (default 18:00)")
    ap.add_argument("--keep", type=int, default=30, help="dumps to keep (default 30)")
    ap.add_argument("--copy-to", help="also copy each dump here (never pruned) — e.g. a OneDrive folder")
    ap.add_argument("--dry-run", action="store_true", help="print the task definition, register nothing")
    ap.add_argument("--remove", action="store_true", help="delete the task")
    args = ap.parse_args()

    if args.remove:
        r = subprocess.run(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"], capture_output=True, text=True)
        print(r.stdout.strip() or r.stderr.strip())
        return r.returncode

    if not PYTHON.is_file():
        print(f"venv python not found at {PYTHON}", file=sys.stderr)
        return 2
    if not SCRIPT.is_file():
        print(f"backup script not found at {SCRIPT}", file=sys.stderr)
        return 2

    xml = task_xml(at=args.at, keep=args.keep, copy_to=args.copy_to)
    if args.dry_run:
        print(xml)
        print(f'would run:  schtasks /Create /TN "{TASK_NAME}" /XML <that> /F')
        return 0

    with tempfile.NamedTemporaryFile("w", suffix=".xml", encoding="utf-16", delete=False) as f:
        f.write(xml)
        xml_path = f.name
    try:
        r = subprocess.run(
            ["schtasks", "/Create", "/TN", TASK_NAME, "/XML", xml_path, "/F"],
            capture_output=True, text=True,
        )
    finally:
        os.unlink(xml_path)
    if r.returncode != 0:
        print(f"schtasks failed:\n{r.stderr.strip() or r.stdout.strip()}", file=sys.stderr)
        return r.returncode

    print(f"registered '{TASK_NAME}': daily at {args.at}, keep {args.keep}"
          + (f", copy to {args.copy_to}" if args.copy_to else ""))
    print(f'run it now to check:  schtasks /Run /TN "{TASK_NAME}"   then   python backend/backup_db.py --list')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
