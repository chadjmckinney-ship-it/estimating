# Start the estimating API.
#
#   .\run.ps1              start on 8001, this machine only
#   .\run.ps1 -Lan         also answer other machines on the office LAN
#   .\run.ps1 -Port 8002   somewhere else
#   .\run.ps1 -Reload      restart itself when a file changes
#
# --app-dir backend is the part that matters: main.py imports `app.config`, so
# backend/ has to be the import root. `uvicorn backend.app.main:app` fails with
# ModuleNotFoundError: No module named 'app'.
#
# -Lan binds 0.0.0.0 instead of the default 127.0.0.1. The app has no login:
# anyone who reaches the URL can change catalog prices, recalculate, or delete
# an estimate, and two people saving the same section overwrite each other with
# no warning. That is a fine trade in a small trusted office. It is not
# something to leave listening on a network you do not control.

param(
    [int]$Port = 8001,
    [switch]$Reload,
    [switch]$Lan,
    [string]$Listen
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

# $Host is a reserved PowerShell variable, so the parameter is -Listen.
# An explicit -Listen wins over -Lan.
if (-not $Listen) {
    $Listen = if ($Lan) { "0.0.0.0" } else { "127.0.0.1" }
}

$python = Join-Path $PSScriptRoot ".venv-win\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Error "No venv at $python - create it, or edit the path in run.ps1."
}

# A second uvicorn can bind the same port on Windows, which means a restart can
# report success while the ORIGINAL process keeps answering. That cost five
# rounds of debugging once; better to refuse than to serve stale code.
$busy = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($busy) {
    $pids = ($busy | Select-Object -ExpandProperty OwningProcess -Unique) -join ", "
    Write-Host "Port $Port is already being served by PID $pids." -ForegroundColor Yellow
    Write-Host "Stop it first:  Stop-Process -Id $pids" -ForegroundColor Yellow
    exit 1
}

# apply_sql.py prints its banner on stderr, and 2>&1 turns that into an
# ErrorRecord. Under $ErrorActionPreference = "Stop", Windows PowerShell
# escalates that to a terminating NativeCommandError - so a migration check
# that found nothing wrong would kill the launch. Relax it for this call only,
# and flatten the records to plain strings so Select-String sees text.
$prevEA = $ErrorActionPreference
$ErrorActionPreference = "Continue"
$status = & $python backend\apply_sql.py --status 2>&1 | ForEach-Object { "$_" }
$ErrorActionPreference = $prevEA

$pending = $status | Select-String -Pattern '^\s*\[ \]'
if ($pending) {
    Write-Host "Unapplied migrations:" -ForegroundColor Yellow
    $pending | ForEach-Object { Write-Host "  $_" -ForegroundColor Yellow }
    Write-Host "The code on disk may expect a schema the database does not have." -ForegroundColor Yellow
    Write-Host ""
}

$args = @("-m", "uvicorn", "app.main:app", "--app-dir", "backend", "--host", $Listen, "--port", "$Port")
if ($Reload) { $args += "--reload" }

if ($Listen -eq "127.0.0.1") {
    Write-Host "http://127.0.0.1:$Port" -ForegroundColor Green
}
else {
    Write-Host "Listening on ${Listen}:$Port" -ForegroundColor Green
    Write-Host "  http://127.0.0.1:$Port   (this machine)" -ForegroundColor Green
    # The name is the stable bookmark; the IP moves with the network.
    Write-Host "  http://$($env:COMPUTERNAME):$Port   (this machine's name, if the client resolves it)" -ForegroundColor Green
    Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" } |
        ForEach-Object { Write-Host "  http://$($_.IPAddress):$Port   ($($_.InterfaceAlias))" -ForegroundColor Green }

    # A missing firewall rule looks exactly like a broken app from the other
    # machine: the browser just hangs. Say so here instead.
    $allowed = $false
    try {
        $allowed = [bool](Get-NetFirewallPortFilter -ErrorAction Stop |
            Where-Object { $_.Protocol -eq "TCP" -and $_.LocalPort -eq $Port } |
            Get-NetFirewallRule -ErrorAction SilentlyContinue |
            Where-Object { $_.Direction -eq "Inbound" -and $_.Enabled -eq "True" -and $_.Action -eq "Allow" })
    }
    catch { }
    if (-not $allowed) {
        Write-Host ""
        Write-Host "No inbound firewall rule for TCP $Port - other machines will time out." -ForegroundColor Yellow
        Write-Host "Run once in an elevated PowerShell:" -ForegroundColor Yellow
        Write-Host "  New-NetFirewallRule -DisplayName 'Estimating API' -Direction Inbound -Protocol TCP -LocalPort $Port -Action Allow -Profile Private,Domain" -ForegroundColor Yellow
    }

    Write-Host ""
    Write-Host "Reminder: no login. Anyone who reaches this URL can edit or delete." -ForegroundColor Yellow
}

& $python @args
