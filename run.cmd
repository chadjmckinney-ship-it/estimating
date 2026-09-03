@echo off
REM Start the estimating API.
REM
REM   run              start on 8001
REM   run -Port 8002   somewhere else
REM   run -Reload      restart itself when a file changes
REM
REM A .cmd runs regardless of the PowerShell execution policy, so this wrapper
REM invokes run.ps1 with -ExecutionPolicy Bypass rather than asking you to
REM change a machine security setting. Bypass here applies to THIS invocation
REM only — nothing about the machine's policy changes.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1" %*
