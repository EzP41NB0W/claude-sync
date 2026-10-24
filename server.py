#!/usr/bin/env python3
"""
server.py — Local HTTP bridge between the dashboard UI and rollup.py.

Binds to 127.0.0.1 ONLY — never 0.0.0.0. Not meant to be reachable from
anywhere but your own browser, on your own machine.

100% local. No claude.ai involvement, no session key, no org/project IDs.
Every endpoint calls straight into rollup.py (and scrubber.py for the
notes feed) — if this file disappeared, `python rollup.py build` from the
terminal would still do the real work. This is a thin transport layer.

Run:
    pip install flask --break-system-packages
    python server.py
    # then open dashboard.html in your browser

Endpoints:
    GET  /api/status            -> section count, total lines, watcher state, last build
    GET  /api/rollup/list        -> manifest.json contents
    GET  /api/rollup/find/<name> -> a single section's full text
    GET  /api/rollup/search      -> ranked search across handoff/learnings notes (?q=, ?max=, ?context=)
    GET  /api/code/search        -> ranked search across code/ source (?q=, ?max=, ?context=, ?project=)
    POST /api/rollup/build       -> drain scratch + rebuild the rollup
    POST /api/learn              -> append a note to learnings.md
    POST /api/watcher/start       -> start background auto-rebuild thread
    POST /api/watcher/stop        -> stop it
    GET    /api/notes               -> read notes.json (me/claude quick log)
    POST   /api/notes               -> append a note (lightly scrubbed for secrets)
    DELETE /api/notes/<id>           -> delete a single note by id
    POST   /api/notes-clear          -> wipe all notes (optional ?author=me|claude to scope it)
    GET  /api/notes/reveal         -> notes with any redactions reversed, LOCAL ONLY
"""

from __future__ import annotations

import json
import socket
import sys
import threading
import time
import uuid
from pathlib import Path

from flask import Flask, jsonify, request

import rollup
import scrubber
from secure_store import SecureStore
from watch import signature

app = Flask(__name__)


# The dashboard is opened as a local file:// page, which browsers treat as
# a different origin than http://127.0.0.1:5151. Without CORS headers the
# browser blocks every fetch() silently. We allow null (file://) and
# localhost origins only — never a wildcard.
@app.after_request
def _add_cors_headers(resp):
    origin = request.headers.get("Origin", "")
    if origin == "null" or origin.startswith("http://127.0.0.1") or origin.startswith("http://localhost"):
        resp.headers["Access-Control-Allow-Origin"] = origin
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp


@app.route("/api/<path:_any>", methods=["OPTIONS"])
def _cors_preflight(_any):
    return ("", 204)


ROOT = Path(__file__).parent
NOTES_PATH = ROOT / "notes.json"

# In-memory watcher control. A thread + flag is plenty for a local
# single-user tool.
_watcher_state = {"running": False, "stop_flag": False}
_state_lock = threading.Lock()


def _store() -> SecureStore:
    return SecureStore(ROOT)


def _load_notes() -> list[dict]:
    if NOTES_PATH.exists():
        try:
            notes = json.loads(NOTES_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
        # Backfill ids for any notes saved before delete support existed.
        changed = False
        for n in notes:
            if "id" not in n:
                n["id"] = uuid.uuid4().hex[:12]
                changed = True
        if changed:
            _save_notes(notes)
        return notes
    return []


def _save_notes(notes: list[dict]) -> None:
    NOTES_PATH.write_text(json.dumps(notes, indent=2), encoding="utf-8")


# --- Status -------------------------------------------------------------

@app.get("/api/status")
def status():
    manifest = rollup.get_manifest()
    total_lines = max((e["end_line"] for e in manifest.values()), default=0)
    last_build = None
    if rollup.MANIFEST_PATH.exists():
        last_build = rollup.MANIFEST_PATH.stat().st_mtime

    with _state_lock:
        watching = _watcher_state["running"]

    return jsonify({
        "section_count": len(manifest),
        "sections": sorted(manifest.keys()),
        "total_lines": total_lines,
        "watching": watching,
        "last_build": last_build,
    })


# --- Rollup ---------------------------------------------------------------

@app.get("/api/rollup/list")
def rollup_list():
    return jsonify(rollup.get_manifest())


@app.get("/api/rollup/find/<name>")
def rollup_find(name):
    section = rollup.find_section(name)
    if section is None:
        return jsonify({"error": f"'{name}' not found"}), 404
    return jsonify({"name": name, "content": section})


@app.get("/api/rollup/search")
def rollup_search_route():
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify({"error": "q required"}), 400
    return jsonify(rollup.search(
        q,
        max_results=int(request.args.get("max", 40)),
        context=int(request.args.get("context", 1)),
    ))


@app.get("/api/code/search")
def code_search_route():
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify({"error": "q required"}), 400
    return jsonify(rollup.search_code(
        q,
        max_results=int(request.args.get("max", 40)),
        context=int(request.args.get("context", 0)),
        project=(request.args.get("project") or None),
    ))


@app.post("/api/rollup/build")
def rollup_build_route():
    drained = rollup.drain_scratch()
    rollup.build()
    manifest = rollup.get_manifest()
    return jsonify({
        "message": "rebuilt",
        "drained_scratch_notes": drained,
        "section_count": len(manifest),
    })


# --- Learn ------------------------------------------------------------------

@app.post("/api/learn")
def learn_route():
    data = request.get_json(force=True)
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "text required"}), 400
    path = rollup.append_learning(text)
    rollup.build()
    return jsonify({"message": f"appended to {path.name} and rebuilt"})


# --- Notes (me/claude quick log, separate from the project rollup) -------

@app.get("/api/notes")
def get_notes():
    return jsonify(_load_notes())


@app.post("/api/notes")
def post_note():
    data = request.get_json(force=True)
    author = data.get("author")
    text = (data.get("text") or "").strip()
    if author not in ("me", "claude") or not text:
        return jsonify({"error": "author must be me/claude, text required"}), 400

    # Light scrub: known-pattern secrets (API keys, AWS keys, etc.) get
    # auto-redacted before the note is saved. Notes never leave this
    # machine, but there's no reason to let a live key sit in notes.json
    # forever just because someone pasted it while jotting a thought.
    result = scrubber.scrub(text)
    if result.redactions:
        _store().merge_secret_map(result.redactions)

    notes = _load_notes()
    notes.append({"id": uuid.uuid4().hex[:12], "author": author, "text": result.clean_text, "ts": time.time()})
    _save_notes(notes)
    return jsonify({"message": "logged", "redacted": len(result.redactions)})


@app.delete("/api/notes/<note_id>")
def delete_note(note_id):
    notes = _load_notes()
    remaining = [n for n in notes if n.get("id") != note_id]
    if len(remaining) == len(notes):
        return jsonify({"error": "not found"}), 404
    _save_notes(remaining)
    return jsonify({"message": "deleted"})


@app.post("/api/notes-clear")
def clear_notes():
    """Wipe notes. ?author=me or ?author=claude scopes it to just that
    author's notes; with no query param, wipes everything."""
    author = request.args.get("author")
    notes = _load_notes()
    if author in ("me", "claude"):
        remaining = [n for n in notes if n.get("author") != author]
        removed = len(notes) - len(remaining)
        _save_notes(remaining)
        return jsonify({"message": f"cleared {removed} note(s) for {author}"})
    removed = len(notes)
    _save_notes([])
    return jsonify({"message": f"cleared {removed} note(s)"})


@app.get("/api/notes/reveal")
def reveal_notes():
    """Notes with redactions reversed. Local-only — never exposed to
    anything but your own browser hitting your own machine."""
    secret_map = _store().get_secret_map()
    notes = _load_notes()
    revealed = [
        {**n, "text": scrubber.reveal(n["text"], secret_map)}
        for n in notes
    ]
    return jsonify(revealed)


# --- Watcher control ---------------------------------------------------------

def _watcher_loop(interval: float):
    last = None
    while True:
        with _state_lock:
            if _watcher_state["stop_flag"]:
                break
        sig = signature(ROOT)
        if sig != last:
            drained = rollup.drain_scratch()
            if drained:
                print(f"  drained {drained} scratch note(s)")
            rollup.build()
            last = sig
        time.sleep(interval)
    with _state_lock:
        _watcher_state["running"] = False


@app.post("/api/watcher/start")
def watcher_start():
    with _state_lock:
        if _watcher_state["running"]:
            return jsonify({"message": "already running"})
        _watcher_state["stop_flag"] = False
        _watcher_state["running"] = True
        t = threading.Thread(target=_watcher_loop, args=(5.0,), daemon=True)
        t.start()
    return jsonify({"message": "watcher started"})


@app.post("/api/watcher/stop")
def watcher_stop():
    with _state_lock:
        _watcher_state["stop_flag"] = True
        _watcher_state["running"] = False
    return jsonify({"message": "watcher stopping"})


HOST = "127.0.0.1"
PORT = 5151


def already_serving(host: str = HOST, port: int = PORT, timeout: float = 0.5) -> bool:
    """
    True if something is already answering on host:port.

    This exists because Windows will happily let a SECOND copy of this server
    bind the same port. Werkzeug sets SO_REUSEADDR, so the duplicate does not
    fail — it silently shares the port, connections land on whichever, and you
    end up with two _watcher_loop threads in two processes both calling
    rollup.build() on the same files. _state_lock is per-process, so nothing
    coordinates them. That happened for real on 2026-08-24: two instances sat
    on 5151 for ten hours after the watchdog was killed.

    A connect probe is used rather than a lock file because it tests the thing
    we actually care about (is someone serving?) and cannot go stale after a
    crash. There is a small race if two copies start in the same instant; for a
    single-user local tool launched by a watchdog that is an acceptable trade.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        return s.connect_ex((host, port)) == 0


if __name__ == "__main__":
    if already_serving():
        print(
            # ASCII only: this prints to a Windows console under cp1252, where
            # an em-dash comes out as a replacement char.
            f"ERROR: something is already serving http://{HOST}:{PORT}.\n"
            "       Refusing to start a second bridge - two of them race each\n"
            "       other rebuilding the rollup.\n"
            "       Find it with:  netstat -ano | findstr :5151\n"
            "       Or just leave it; the running one is fine.",
            file=sys.stderr,
        )
        sys.exit(1)
    print(f"claude-sync bridge running on http://{HOST}:{PORT} (localhost only)")
    app.run(host=HOST, port=PORT, debug=False)
