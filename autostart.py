#!/usr/bin/env python3
"""
autostart.py — bring the claude-sync dashboard up by itself.

Imported by mcp_server.py, which the Claude app spawns on launch. So starting
Claude is what starts the bridge; nothing has to be run by hand. Also self-heals
the tray supervisor if its scheduled task is not running.

The dashboard is NO LONGER opened automatically (changed 2026-08-25). The Claude
app spawns one MCP server per session, so every session was popping a browser
tab once the cooldown lapsed. The dashboard is now opened from the tray icon
(tray.py) on demand, or by setting CLAUDE_SYNC_AUTO_GUI=1 to get the old
behaviour back.

Everything here is best-effort and non-fatal. If any of it fails, the MCP
server must still start — knowledge-base tools working matters more than the
dashboard appearing.

CRITICAL: an MCP server talks JSON-RPC over stdout. Anything printed to stdout
corrupts the protocol and the Claude app drops the connection. Every message in
this module goes to stderr. Do not "helpfully" change these to print().

Environment overrides:
    CLAUDE_SYNC_NO_AUTOSTART=1   do nothing at all
    CLAUDE_SYNC_AUTO_GUI=1       opt IN to popping the dashboard on MCP start
    CLAUDE_SYNC_GUI_COOLDOWN=n   seconds between browser pops (default 180)
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).parent
HOST = "127.0.0.1"
PORT = 5151
STATUS_URL = f"http://{HOST}:{PORT}/api/status"
DASHBOARD = ROOT / "dashboard.html"
STATE_FILE = ROOT / ".autostart_state.json"
HEARTBEAT = ROOT / "startup" / "watchdog.heartbeat"
LOG_PATH = ROOT / "startup" / "watchdog.log"
WATCHDOG_TASK = "claude-sync tray"

# The watchdog beats every 60 s. Allow a generous multiple before calling it
# dead, so a slow loop or a busy machine does not trigger a needless relaunch.
HEARTBEAT_STALE_SEC = 300

def _default_pythonw() -> Path:
    """pythonw.exe next to the interpreter running this (no console window);
    falls back to the interpreter itself. Override with CLAUDE_SYNC_PYTHONW."""
    exe = Path(sys.executable)
    cand = exe.with_name("pythonw.exe")
    return cand if cand.exists() else exe


PYTHONW = Path(os.environ.get("CLAUDE_SYNC_PYTHONW") or _default_pythonw())


def log(msg: str) -> None:
    """Always stderr — see the module docstring."""
    print(f"[claude-sync autostart] {msg}", file=sys.stderr, flush=True)


def _serving(timeout: float = 0.5) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        return s.connect_ex((HOST, PORT)) == 0


def _read_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {}


def _write_state(state: dict) -> None:
    try:
        STATE_FILE.write_text(json.dumps(state, indent=2))
    except Exception as e:
        log(f"could not write state file: {e}")


def start_bridge(wait: float = 8.0) -> bool:
    """Launch server.py detached via pythonw. Returns True once it answers."""
    if _serving():
        return True

    exe = str(PYTHONW) if PYTHONW.exists() else sys.executable
    try:
        # DETACHED_PROCESS + CREATE_NEW_PROCESS_GROUP so the bridge outlives
        # this MCP server. Without it the dashboard dies when Claude closes.
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

    deadline = time.time() + wait
    while time.time() < deadline:
        if _serving():
            log("bridge started")
            return True
        time.sleep(0.3)
    log(f"bridge did not answer within {wait:.0f}s")
    return False


def kick_watcher() -> None:
    """Start the rollup auto-rebuild thread, same as the watchdog does."""
    try:
        req = urllib.request.Request(
            f"http://{HOST}:{PORT}/api/watcher/start", data=b"", method="POST"
        )
        urllib.request.urlopen(req, timeout=5).read()
    except Exception as e:
        log(f"watcher kick failed: {e}")


def health(timeout: float = 3.0) -> tuple[bool, bool]:
    """
    (bridge_reachable, watcher_running), read from /api/status.

    Both halves matter and they fail independently. MCP tools read files through
    rollup.py directly, so they keep working perfectly while the bridge is dead —
    which means a dead bridge or a stopped watcher thread is invisible from
    inside a Claude session. That is the failure this whole path exists to catch:
    hours of work with the rollup never rebuilding.
    """
    try:
        with urllib.request.urlopen(STATUS_URL, timeout=timeout) as r:
            if r.status != 200:
                return False, False
            data = json.loads(r.read().decode("utf-8"))
        return True, bool(data.get("watching"))
    except Exception:
        return False, False


def alert(title: str, body: str) -> None:
    """
    Surface a failure to the user. Best-effort; never fatal.

    Writes to startup/watchdog.log as well as raising the toast. A toast is
    transient and this module's log() only reaches stderr, which nobody reads —
    so without the file line there would be no durable record that a session
    started with claude-sync broken.
    """
    log(f"ALERT: {title} - {body}")
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  [autostart] ALERT: {title} - {body}\n")
    except Exception as e:
        log(f"could not write alert to log: {e}")
    try:
        import notify

        notify.alert(title, body)
    except Exception as e:
        log(f"could not raise notification: {e}")


def watchdog_alive() -> bool:
    """
    Fresh heartbeat file == watchdog running.

    Checked via the heartbeat rather than the log, because watchdog.ps1 only
    logs on state CHANGES — a healthy watchdog and a dead one look identical in
    the log. That is exactly how its death went unnoticed for ten hours.
    """
    try:
        age = time.time() - HEARTBEAT.stat().st_mtime
        return age < HEARTBEAT_STALE_SEC
    except FileNotFoundError:
        return False
    except Exception:
        return False


def ensure_watchdog(force: bool = False) -> None:
    """
    Start the tray supervisor's scheduled task if its heartbeat has gone stale.

    force=True runs it regardless — used when the bridge is down but the tray
    still looks alive, i.e. the supervisor exists but has not got to its next
    60 s poll yet. The task is MultipleInstances=IgnoreNew, so a redundant run
    is refused by the scheduler rather than stacking a second tray.

    CREATE_NO_WINDOW: schtasks is a console app, and this runs inside an MCP
    server spawned by the Claude app. Without the flag it can flash a console —
    the exact class of bug that produced the "console ghost" (2026-08-25).
    """
    if os.name != "nt":
        return
    if not force and watchdog_alive():
        return
    log("starting the tray scheduled task" + (" (forced)" if force else " - heartbeat stale or missing"))
    try:
        subprocess.run(
            ["schtasks", "/Run", "/TN", WATCHDOG_TASK],
            capture_output=True,
            timeout=15,
            check=False,
            creationflags=0x08000000 if os.name == "nt" else 0,  # CREATE_NO_WINDOW
        )
    except Exception as e:
        log(f"could not start tray task: {e}")


def open_gui() -> None:
    """
    Pop the dashboard. OPT-IN ONLY.

    Off by default since 2026-08-25: the Claude app spawns one MCP server per
    session, so this fired per session and buried the machine in browser tabs.
    The cooldown below only ever suppressed bursts, not the steady drip. Use the
    tray icon instead; set CLAUDE_SYNC_AUTO_GUI=1 to restore the old behaviour.
    """
    if os.environ.get("CLAUDE_SYNC_AUTO_GUI") != "1":
        return
    if not DASHBOARD.exists():
        log(f"dashboard not found at {DASHBOARD}")
        return

    try:
        cooldown = float(os.environ.get("CLAUDE_SYNC_GUI_COOLDOWN", "180"))
    except ValueError:
        cooldown = 180.0

    state = _read_state()
    since = time.time() - float(state.get("last_gui_open", 0))
    if since < cooldown:
        log(f"dashboard opened {since:.0f}s ago - not reopening (cooldown {cooldown:.0f}s)")
        return

    try:
        webbrowser.open(DASHBOARD.as_uri())
        state["last_gui_open"] = time.time()
        _write_state(state)
        log("dashboard opened")
    except Exception as e:
        log(f"could not open dashboard: {e}")


def run() -> None:
    """
    Entry point, called by mcp_server.py on every Claude session launch — so
    every Claude that starts checks claude-sync and tries to repair it.
    Never raises: the MCP server must start regardless.

    Escalation ladder. The point is that a Claude which CANNOT fix claude-sync
    says so out loud, because nothing else in the session will look wrong:
      1. bridge reachable?           no  -> start it directly
      2. still not reachable?        yes -> force the tray supervisor, recheck
      3. still not reachable?        yes -> ALERT the user and stop
      4. reachable but not watching? yes -> kick the watcher, ALERT if it won't
    """
    if os.environ.get("CLAUDE_SYNC_NO_AUTOSTART") == "1":
        return
    try:
        ensure_watchdog()  # keep the tray supervisor alive regardless

        up, watching = health()
        if not up:
            log("bridge not reachable - starting it")
            start_bridge()
            up, watching = health()

        if not up:
            log("bridge still down after a direct start - forcing the tray task")
            ensure_watchdog(force=True)
            time.sleep(3)  # give the supervisor a moment to bind
            up, watching = health(timeout=5.0)

        if not up:
            alert(
                "claude-sync is DOWN",
                f"The bridge on {HOST}:{PORT} could not be started. The dashboard "
                "and the rollup auto-rebuild watcher are not running. MCP tools "
                "still work, so nothing else will look wrong. "
                "See startup/watchdog.log.",
            )
            return

        if not watching:
            log("bridge up but watcher thread not running - kicking it")
            kick_watcher()
            _, watching = health()
            if not watching:
                alert(
                    "claude-sync watcher is STOPPED",
                    "The bridge is up but the rollup auto-rebuild watcher will not "
                    "start, so notes will go stale with no warning. Try Restart "
                    "Bridge from the claude-sync tray icon.",
                )
                return

        open_gui()
    except Exception as e:
        log(f"autostart failed, continuing anyway: {e}")


if __name__ == "__main__":
    run()
