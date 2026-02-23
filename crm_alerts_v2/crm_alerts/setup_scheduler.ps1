<#
.SYNOPSIS
    Registers the CRM Daily Stalled Alert as a Windows Scheduled Task.

.DESCRIPTION
    Creates a task that runs run.py every Monday through Friday at 9:00 AM
    (business days only). Run this script once — as Administrator — to set up
    the recurring schedule.

    The task uses the Python interpreter found on PATH and the run.py in the
    same directory as this script, so no hard-coded paths are needed.

.PARAMETER Time
    Time at which to run the task. Default: "9:00AM"
    Examples: "9:00AM"  "08:30AM"

.PARAMETER TaskName
    Name shown in Windows Task Scheduler. Default: "CRM Daily Stalled Alert"

.EXAMPLE
    .\setup_scheduler.ps1

.EXAMPLE
    .\setup_scheduler.ps1 -Time "08:30AM" -TaskName "My CRM Alert"

.EXAMPLE
    # Remove the task
    Unregister-ScheduledTask -TaskName "CRM Daily Stalled Alert" -Confirm:$false
#>

param(
    [string]$Time     = "9:00AM",
    [string]$TaskName = "CRM Daily Stalled Alert"
)

$ErrorActionPreference = "Stop"

# ─── Resolve paths ────────────────────────────────────────────────────────────
$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$RunScript  = Join-Path $ScriptDir "run.py"
$LogFile    = Join-Path $ScriptDir "scheduler_run.log"

$PythonExe = (Get-Command python -ErrorAction SilentlyContinue)?.Source
if (-not $PythonExe) {
    Write-Error "python not found on PATH. Install Python and retry."
    exit 1
}

if (-not (Test-Path $RunScript)) {
    Write-Error "run.py not found at: $RunScript"
    exit 1
}

# ─── Print summary ────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  CRM Daily Stalled Alert — Scheduler Setup" -ForegroundColor Cyan
Write-Host "  ─────────────────────────────────────────"
Write-Host "  Task name   : $TaskName"
Write-Host "  Python      : $PythonExe"
Write-Host "  Script      : $RunScript"
Write-Host "  Schedule    : Mon–Fri at $Time"
Write-Host "  Run log     : $LogFile"
Write-Host ""

# ─── Build task components ────────────────────────────────────────────────────

# Wrap in cmd /c so stdout+stderr get appended to the log file
$CmdLine = "cmd /c `"$PythonExe`" `"$RunScript`" >> `"$LogFile`" 2>&1"

$Action = New-ScheduledTaskAction `
    -Execute    "cmd.exe" `
    -Argument   "/c `"`"$PythonExe`" `"$RunScript`" >> `"$LogFile`" 2>&1`"" `
    -WorkingDirectory $ScriptDir

$Trigger = New-ScheduledTaskTrigger `
    -Weekly `
    -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday `
    -At $Time

$Settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit      (New-TimeSpan -Hours 2) `
    -RestartCount            2 `
    -RestartInterval         (New-TimeSpan -Minutes 10) `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable `
    -MultipleInstances       IgnoreNew

$Principal = New-ScheduledTaskPrincipal `
    -UserId   $env:USERNAME `
    -LogonType Interactive `
    -RunLevel Highest

# ─── Register ─────────────────────────────────────────────────────────────────
Register-ScheduledTask `
    -TaskName   $TaskName `
    -Action     $Action `
    -Trigger    $Trigger `
    -Settings   $Settings `
    -Principal  $Principal `
    -Description "Sends Zoho CRM stalled items report every business day at $Time" `
    -Force | Out-Null

Write-Host "  Task '$TaskName' registered successfully." -ForegroundColor Green
Write-Host ""
Write-Host "  Useful commands:" -ForegroundColor Yellow
Write-Host "    Run now    : Start-ScheduledTask  -TaskName '$TaskName'"
Write-Host "    Check last : Get-ScheduledTaskInfo -TaskName '$TaskName' | Select LastRunTime, LastTaskResult"
Write-Host "    View log   : Get-Content '$LogFile' -Tail 50"
Write-Host "    Remove     : Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"
Write-Host ""
