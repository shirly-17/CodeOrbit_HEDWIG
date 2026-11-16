import subprocess
import sys
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parents[1]
NOTIFY_SCRIPT = PROJECT_ROOT / "automation" / "reminder_notify.py"


def task_name(reminder_id):
    return f"HEDWIG_Reminder_{int(reminder_id)}"


def _ps_quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def schedule_reminder(reminder_id, due_at):
    due_at = due_at.replace(microsecond=0)
    if due_at <= datetime.now():
        raise ValueError("The reminder time must be in the future.")

    # PowerShell parses an unambiguous ISO-style date/time, avoiding
    # schtasks.exe's locale-dependent /SD date format.
    task = task_name(reminder_id)
    when = due_at.strftime("%Y-%m-%d %H:%M:%S")
    executable = str(Path(sys.executable).resolve())
    script = str(NOTIFY_SCRIPT.resolve())
    working_dir = str(PROJECT_ROOT.resolve())
    args = f'"{script}" {int(reminder_id)}'

    ps = f"""
$ErrorActionPreference = 'Stop'
$action = New-ScheduledTaskAction `
    -Execute {_ps_quote(executable)} `
    -Argument {_ps_quote(args)} `
    -WorkingDirectory {_ps_quote(working_dir)}
$runAt = [datetime]::ParseExact(
    {_ps_quote(when)},
    'yyyy-MM-dd HH:mm:ss',
    [Globalization.CultureInfo]::InvariantCulture
)
$trigger = New-ScheduledTaskTrigger -Once -At $runAt
$principal = New-ScheduledTaskPrincipal `
    -UserId "$env:USERDOMAIN\\$env:USERNAME" `
    -LogonType Interactive `
    -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -WakeToRun `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10)
$taskObject = New-ScheduledTask `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Description 'HEDWIG reminder'
Register-ScheduledTask `
    -TaskName {_ps_quote(task)} `
    -InputObject $taskObject `
    -Force | Out-Null
"""
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy",
         "Bypass", "-Command", ps],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "Unknown Task Scheduler error").strip()
        raise RuntimeError(detail[-1200:])
    return True


def cancel_scheduled_reminder(reminder_id):
    ps = (
        f"Unregister-ScheduledTask -TaskName {_ps_quote(task_name(reminder_id))} "
        "-Confirm:$false -ErrorAction SilentlyContinue"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
    )
    return result.returncode == 0
