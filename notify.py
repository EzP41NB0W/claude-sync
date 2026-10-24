#!/usr/bin/env python3
"""
notify.py - tell you something is wrong, from a process with no UI.

Used by autostart.py when a Claude session launches and cannot get claude-sync
into a working state. The whole point is that a silent failure is the expensive
one: MCP tools keep working when the bridge is down (they read files through
rollup.py directly), so the dashboard and the rollup auto-rebuild watcher can
be dead for hours with nothing looking wrong.

CRITICAL - two constraints that are easy to get wrong here:

1. NEVER print to stdout. This module is imported by an MCP server that speaks
   JSON-RPC over stdout. Any stray byte kills the Claude connection.

2. NEVER spawn a visible console. The toast is raised through Windows
   PowerShell (the WinRT API does not load in pwsh 7), and a bare Popen of
   powershell.exe puts a real console window on screen even with
   -WindowStyle Hidden - the conhost is created before the style applies.
   That is precisely the bug that had a blank console stealing focus over
   fullscreen video for days (2026-08-25). CREATE_NO_WINDOW is what actually
   suppresses it.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

APP_ID = "claude-sync"

# 0x08000000 CREATE_NO_WINDOW - the flag that genuinely suppresses the console.
_CREATE_NO_WINDOW = 0x08000000

_PS_TOAST = r"""
$ErrorActionPreference = 'Stop'
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
$xml = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent(
    [Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$texts = $xml.GetElementsByTagName('text')
$texts.Item(0).AppendChild($xml.CreateTextNode($env:CS_TOAST_TITLE)) | Out-Null
$texts.Item(1).AppendChild($xml.CreateTextNode($env:CS_TOAST_BODY))  | Out-Null
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($env:CS_TOAST_APP).Show(
    [Windows.UI.Notifications.ToastNotification]::new($xml))
"""


def _log(msg: str) -> None:
    """stderr only - see the module docstring."""
    print(f"[claude-sync notify] {msg}", file=sys.stderr, flush=True)


def toast(title: str, body: str, timeout: float = 15.0) -> bool:
    """
    Raise a Windows toast. Lands in the Action Center, so it survives being
    missed - which matters, because the whole failure mode here is "nobody
    noticed for hours."

    Returns True if PowerShell reported success. Never raises.
    """
    if os.name != "nt":
        _log(f"{title}: {body}")
        return False

    env = dict(os.environ)
    env["CS_TOAST_TITLE"] = title
    env["CS_TOAST_BODY"] = body
    env["CS_TOAST_APP"] = APP_ID

    try:
        proc = subprocess.run(
            [
                "powershell.exe",  # NOT pwsh - the WinRT type load fails there
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy", "Bypass",
                "-Command", _PS_TOAST,
            ],
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            creationflags=_CREATE_NO_WINDOW,
            timeout=timeout,
            check=False,
        )
    except Exception as e:
        _log(f"toast failed to launch: {e}")
        return False

    if proc.returncode != 0:
        err = (proc.stderr or b"").decode("utf-8", "replace").strip().splitlines()
        _log(f"toast failed: {err[0] if err else f'exit {proc.returncode}'}")
        return False
    return True


def modal(title: str, body: str) -> bool:
    """
    Blocking dialog. Unmissable, and obnoxious - reserved for the case where
    the toast itself could not be raised, or when CLAUDE_SYNC_ALERT_MODAL=1.

    MB_OK | MB_ICONWARNING | MB_SETFOREGROUND | MB_TOPMOST
    """
    if os.name != "nt":
        _log(f"{title}: {body}")
        return False
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(
            None, body, title, 0x00 | 0x30 | 0x10000 | 0x40000
        )
        return True
    except Exception as e:
        _log(f"modal failed: {e}")
        return False


def alert(title: str, body: str) -> None:
    """
    Escalating notification: toast, and fall back to a modal if the toast could
    not be raised at all. Set CLAUDE_SYNC_ALERT_MODAL=1 to always use the modal.
    """
    if os.environ.get("CLAUDE_SYNC_ALERT_MODAL") == "1":
        modal(title, body)
        return
    if not toast(title, body):
        modal(title, body)


if __name__ == "__main__":
    # Manual smoke test: python notify.py "title" "body"
    t = sys.argv[1] if len(sys.argv) > 1 else "claude-sync test"
    b = sys.argv[2] if len(sys.argv) > 2 else "If you can read this, notifications work."
    ok = toast(t, b)
    _log(f"toast returned {ok}")
    sys.exit(0 if ok else 1)
