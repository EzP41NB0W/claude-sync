#!/usr/bin/env python3
"""
tray.py - claude-sync system tray icon + bridge supervisor.

Replaces startup/watchdog.ps1. Launched hidden at logon by the scheduled task
"claude-sync tray", running under pythonw.exe.

WHY THIS REPLACED THE POWERSHELL WATCHDOG (2026-08-25):
watchdog.ps1 ran as a hidden powershell.exe under Task Scheduler. Hidden or
not, it still owned a console, so it could be killed by a console control
event - and it was, repeatedly, exiting 0xC000013A (STATUS_CONTROL_C_EXIT)
roughly every two hours. The 10-minute repeating trigger kept resurrecting it,
which is why the deaths went unnoticed. A pythonw process has no console at
all and therefore cannot receive CTRL_C_EVENT. The fix is structural, not a
setting.

Contract kept from watchdog.ps1 so nothing else has to change:
  - polls http://127.0.0.1:5151/api/status every POLL_SEC
  - restarts server.py via pythonw when it is down
  - kicks the rollup watcher thread after a restart
  - writes startup/watchdog.heartbeat every loop (autostart.py reads this)
  - appends to startup/watchdog.log, trimmed the same way

Menu: Open Dashboard (default action / left-click), live bridge status,
Restart Bridge, Open Log, Quit.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

from PIL import Image, ImageDraw
import pystray

ROOT = Path(__file__).parent
HOST = "127.0.0.1"
PORT = 5151
STATUS_URL = f"http://{HOST}:{PORT}/api/status"
WATCHER_URL = f"http://{HOST}:{PORT}/api/watcher/start"
DASHBOARD = ROOT / "dashboard.html"
LOG_PATH = ROOT / "startup" / "watchdog.log"
HEARTBEAT = ROOT / "startup" / "watchdog.heartbeat"

POLL_SEC = 60
START_WAIT_SEC = 8.0

def _default_pythonw() -> Path:
    """pythonw.exe next to the interpreter running this (no console window);
    falls back to the interpreter itself. Override with CLAUDE_SYNC_PYTHONW."""
    exe = Path(sys.executable)
    cand = exe.with_name("pythonw.exe")
    return cand if cand.exists() else exe


PYTHONW = Path(os.environ.get("CLAUDE_SYNC_PYTHONW") or _default_pythonw())

UP, DOWN, STARTING = "up", "down", "starting"
COLORS = {
    UP: (46, 160, 67),
    DOWN: (209, 36, 47),
    STARTING: (219, 171, 10),
}

_state = {"bridge": STARTING, "since": time.time(), "restarts": 0}
_lock = threading.Lock()


def log(msg: str) -> None:
    """Same file and trim policy as watchdog.ps1, so there is one place to look."""
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')}  [tray] {msg}"
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
        lines = LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
        if len(lines) > 1000:
            LOG_PATH.write_text("\n".join(lines[-500:]) + "\n", encoding="utf-8")
    except Exception:
        pass


def single_instance() -> bool:
    r"""Local\ mutex, not Global\ - this is a per-user app and Global needs privileges."""
    try:
        import win32event
        import winerror

        handle = win32event.CreateMutex(None, False, "Local\\claude-sync-tray")
        if win32event.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
            return False
        globals()["_mutex_handle"] = handle  # keep alive for process lifetime
        return True
    except Exception:
        return True  # never let the guard itself stop the tray from running


def bridge_up(timeout: float = 3.0) -> bool:
    try:
        with urllib.request.urlopen(STATUS_URL, timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def kick_watcher() -> None:
    try:
        req = urllib.request.Request(WATCHER_URL, data=b"", method="POST")
        urllib.request.urlopen(req, timeout=5).read()
    except Exception as e:
        log(f"watcher kick failed: {e}")


def start_bridge() -> bool:
    """Launch server.py fully detached. Returns True once it answers."""
    exe = str(PYTHONW) if PYTHONW.exists() else sys.executable
    try:
        flags = 0
        if os.name == "nt":
            flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        subprocess.Popen(
            [exe, str(ROOT / "server.py")],
            cwd=str(ROOT),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
        )
    except Exception as e:
        log(f"could not launch server.py: {e}")
        return False

    deadline = time.time() + START_WAIT_SEC
    while time.time() < deadline:
        if bridge_up(timeout=1.0):
            kick_watcher()
            return True
        time.sleep(0.3)
    return False


def make_icon(state: str) -> Image.Image:
    """Filled dot in the state colour, with a darker ring so it reads on any taskbar."""
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = COLORS[state]
    dark = tuple(max(0, v - 60) for v in c)
    d.ellipse([4, 4, size - 4, size - 4], fill=c + (255,), outline=dark + (255,), width=4)
    if state == DOWN:  # glyph as well as colour, so it is not colour-only
        d.rectangle([size // 2 - 4, 18, size // 2 + 4, 38], fill=(255, 255, 255, 255))
        d.rectangle([size // 2 - 4, 44, size // 2 + 4, 52], fill=(255, 255, 255, 255))
    return img


def status_text(_item=None) -> str:
    with _lock:
        s = _state["bridge"]
        since = _state["since"]
        n = _state["restarts"]
    mins = int((time.time() - since) // 60)
    label = {UP: "Bridge up", DOWN: "Bridge DOWN", STARTING: "Bridge starting..."}[s]
    tail = f" ({mins}m)" if mins and s == UP else ""
    suffix = ""
    if n:
        suffix = f" - {n} restart" + ("s" if n != 1 else "")
    return label + tail + suffix


def set_state(icon: pystray.Icon, new: str) -> None:
    with _lock:
        changed = _state["bridge"] != new
        if changed:
            _state["bridge"] = new
            _state["since"] = time.time()
    if changed:
        icon.icon = make_icon(new)
        icon.title = "claude-sync - " + status_text()
        icon.update_menu()


def on_open_dashboard(icon, _item=None) -> None:
    if not DASHBOARD.exists():
        log(f"dashboard not found at {DASHBOARD}")
        icon.notify("dashboard.html not found", "claude-sync")
        return
    webbrowser.open(DASHBOARD.as_uri())


def on_restart(icon, _item=None) -> None:
    log("manual restart requested from tray")
    set_state(icon, STARTING)
    ok = start_bridge()
    set_state(icon, UP if ok else DOWN)
    icon.notify("Bridge restarted" if ok else "Bridge FAILED to start", "claude-sync")


def on_open_log(icon, _item=None) -> None:
    try:
        os.startfile(str(LOG_PATH))
    except Exception as e:
        log(f"could not open log: {e}")


def on_quit(icon, _item=None) -> None:
    log("tray quit from menu - bridge left running")
    icon.stop()


def supervise(icon: pystray.Icon) -> None:
    """Poll loop. Mirrors watchdog.ps1: first pass is not treated as a crash."""
    log(f"tray started (pid {os.getpid()})")
    was_up = None
    while True:
        try:
            up = bridge_up()
            if not up:
                if was_up is None:
                    log("bridge not running at tray start - launching")
                else:
                    log("bridge DOWN - restarting")
                set_state(icon, STARTING)
                if start_bridge():
                    up = True
                    log("bridge started OK (watcher kicked)")
                    if was_up is not None:
                        with _lock:
                            _state["restarts"] += 1
                        icon.notify("Bridge went down, restarted it.", "claude-sync")
                else:
                    log("bridge FAILED to start")
                    icon.notify("Bridge FAILED to start - see watchdog.log", "claude-sync")
            set_state(icon, UP if up else DOWN)
            was_up = up

            # Freshness of this file is how autostart.py knows a supervisor is
            # alive. The log cannot answer that - it only records state CHANGES.
            try:
                HEARTBEAT.write_text(time.strftime("%Y-%m-%dT%H:%M:%S%z"), encoding="utf-8")
            except Exception:
                pass
        except Exception as e:
            log(f"supervise loop error (continuing): {e}")
        time.sleep(POLL_SEC)


def main() -> int:
    if not single_instance():
        log("another tray instance is already running - this one exiting")
        return 0

    icon = pystray.Icon(
        "claude-sync",
        icon=make_icon(STARTING),
        title="claude-sync - starting...",
        menu=pystray.Menu(
            pystray.MenuItem("Open Dashboard", on_open_dashboard, default=True),
            pystray.MenuItem(status_text, None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Restart Bridge", on_restart),
            pystray.MenuItem("Open Log", on_open_log),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", on_quit),
        ),
    )
    threading.Thread(target=supervise, args=(icon,), daemon=True).start()
    icon.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
