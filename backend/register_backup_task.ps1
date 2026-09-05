<#
Register a daily Windows Task Scheduler job that dumps the estimating
database — the "backup job on the laptop DB" docs/notes.md said was missing.

    .\backend\register_backup_task.ps1                 # 6:00 PM daily, ~/Backups/estimating, keep 30
    .\backend\register_backup_task.ps1 -At 17:30
    .\backend\register_backup_task.ps1 -CopyTo "C:\Users\Chad\OneDrive - S and S Concrete Contractors Inc\Backups\estimating"
    .\backend\register_backup_task.ps1 -Remove

Runs backend/backup_db.py with the repo's own venv Python, as the current
user, whether or not anyone is logged in at the time (StartWhenAvailable, so a
laptop that was asleep at 6 PM runs it when it wakes). -CopyTo puts a second
copy on another disk; OneDrive is the obvious one on this machine, and that
directory is never pruned.

Registering a scheduled task is a change to this machine, which is why this
is a script Chad runs rather than something the assistant runs for him.
#>
[CmdletBinding()]
param(
    [string]$At = "18:00",
    [string]$CopyTo = "",
    [int]$Keep = 30,
    [switch]$Remove
)

$TaskName = "Estimating DB backup"
$Repo = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Python = Join-Path $Repo ".venv-win\Scripts\python.exe"
$Script = Join-Path $Repo "backend\backup_db.py"

if ($Remove) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "removed '$TaskName' (if it existed)"
    exit 0
}

if (-not (Test-Path $Python)) { throw "venv python not found at $Python" }
if (-not (Test-Path $Script)) { throw "backup script not found at $Script" }

$argList = "`"$Script`" --keep $Keep"
if ($CopyTo -ne "") { $argList += " --copy-to `"$CopyTo`"" }

$action = New-ScheduledTaskAction -Execute $Python -Argument $argList -WorkingDirectory $Repo
$trigger = New-ScheduledTaskTrigger -Daily -At $At
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null

Write-Host "registered '$TaskName': daily at $At"
Write-Host "  $Python $argList"
Write-Host "run it now to check:  Start-ScheduledTask -TaskName '$TaskName'; then  python backend\backup_db.py --list"
