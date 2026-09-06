"""
The task definition the registrar hands to Task Scheduler — built, not
registered. Registering is Chad's to do; the XML is ours to get right.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import register_backup_task as rt

NS = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}


def _parse(xml: str) -> ET.Element:
    # The file is declared UTF-16 for schtasks; parse the text as-is.
    return ET.fromstring(xml.replace('encoding="UTF-16"', 'encoding="UTF-8"'))


def test_the_task_runs_the_backup_daily_with_the_venv_python():
    root = _parse(rt.task_xml(at="18:00", keep=30, copy_to=None, user="BOX\\chad"))
    exe = root.find("t:Actions/t:Exec", NS)
    assert exe.find("t:Command", NS).text == str(rt.PYTHON)
    assert exe.find("t:Arguments", NS).text == f'"{rt.SCRIPT}" --keep 30'
    assert exe.find("t:WorkingDirectory", NS).text == str(rt.REPO)
    assert root.find("t:Triggers/t:CalendarTrigger/t:ScheduleByDay/t:DaysInterval", NS).text == "1"
    assert root.find("t:Triggers/t:CalendarTrigger/t:StartBoundary", NS).text.endswith("T18:00:00")
    assert root.find("t:Settings/t:StartWhenAvailable", NS).text == "true"
    assert root.find("t:Principals/t:Principal/t:LogonType", NS).text == "S4U"
    assert root.find("t:Principals/t:Principal/t:UserId", NS).text == "BOX\\chad"


def test_copy_to_reaches_the_command_line_quoted():
    xml = rt.task_xml(at="17:30", keep=14, copy_to="C:/Users/Chad/OneDrive - S and S/Backups", user="BOX\\chad")
    args = _parse(xml).find("t:Actions/t:Exec/t:Arguments", NS).text
    assert args.endswith('--keep 14 --copy-to "C:/Users/Chad/OneDrive - S and S/Backups"')


def test_the_registrar_is_python_not_powershell():
    """Chad, 2026-09-05: "lol, I still have not allowed running scripts." """
    assert not (Path(rt.BACKEND) / "register_backup_task.ps1").exists()
