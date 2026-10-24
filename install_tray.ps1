# install_tray.ps1 -- register the claude-sync tray monitor as a Windows scheduled task.
#
#   powershell -ExecutionPolicy Bypass -File install_tray.ps1
#   powershell -ExecutionPolicy Bypass -File install_tray.ps1 -Uninstall
#
# The tray icon (tray.py) supervises the local bridge (server.py): green = up,
# red = down; it restarts the bridge if it dies and writes a heartbeat that
# mcp_server.py's autostart check reads. Needs:  pip install pystray pillow
#
# Mirrors the settings the original install was proven with:
#   - TWO triggers: at logon (prompt start) AND a 10-minute repetition anchored
#     to a time in the past. A repetition hung off the logon trigger alone is
#     not live until the NEXT logon, so a killed tray would stay dead for hours.
#   - MultipleInstances IgnoreNew: the repeats are a no-op while it runs.
#   - ExecutionTimeLimit 0: the default (3 days) would kill a long-lived tray.
#   - runs on battery, restarts on failure every minute.
# Registered for the current user only; no admin rights expected. If your
# Windows policy refuses it, run the same command from an elevated prompt.
param(
    [string]$Python = "",
    [switch]$Uninstall
)
$ErrorActionPreference = "Stop"
$TaskName = "claude-sync tray"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Tray = Join-Path $Root "tray.py"

if ($Uninstall) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Removed scheduled task '$TaskName'."
    exit 0
}

if (-not (Test-Path $Tray)) { throw "tray.py not found next to this script ($Tray)" }

# pythonw.exe (no console window) next to the python on PATH, unless given
if (-not $Python) {
    $py = (Get-Command python -ErrorAction SilentlyContinue).Source
    if (-not $py) { throw "python not on PATH; pass -Python C:\path\to\pythonw.exe" }
    $cand = Join-Path (Split-Path -Parent $py) "pythonw.exe"
    $Python = if (Test-Path $cand) { $cand } else { $py }
}
Write-Host "Using interpreter: $Python"

$action   = New-ScheduledTaskAction -Execute $Python -Argument "`"$Tray`"" -WorkingDirectory $Root
$atLogon  = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$every10  = New-ScheduledTaskTrigger -Once -At (Get-Date).Date -RepetitionInterval (New-TimeSpan -Minutes 10)
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew `
              -ExecutionTimeLimit ([TimeSpan]::Zero) `
              -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
              -RestartInterval (New-TimeSpan -Minutes 1) -RestartCount 999
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger @($atLogon, $every10) `
    -Settings $settings -Principal $principal -Force | Out-Null

# The check that matters: a task with triggers but no NextRunTime never fires.
$info = Get-ScheduledTaskInfo -TaskName $TaskName
if (-not $info.NextRunTime) { throw "Registered, but NextRunTime is blank -- the task will not fire on its own." }
Write-Host "Registered '$TaskName'. NextRunTime: $($info.NextRunTime)"
Start-ScheduledTask -TaskName $TaskName
Write-Host "Started. Look for the claude-sync icon in the system tray."
