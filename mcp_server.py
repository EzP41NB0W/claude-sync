#!/usr/bin/env python3
"""
mcp_server.py — FastMCP server exposing claude-sync's rollup knowledge base
as real MCP tools, so any MCP-connected AI client can pull project context
directly instead of going through the dashboard or a Filesystem connector
reading rollup_NNN.md by hand.

Thin wrapper only — every tool calls straight into rollup.py, same "if this
file disappeared, `python rollup.py <cmd>` from the terminal would still do
the real work" principle as server.py (the Flask dashboard bridge).

100% local. No claude.ai involvement, no network calls.

Requires: fastmcp
    pip install fastmcp --break-system-packages

Run:
    python mcp_server.py
"""

from __future__ import annotations

import sys

import rollup

from fastmcp import FastMCP

mcp = FastMCP(name="claude-sync")


@mcp.tool()
def list_projects() -> list[dict]:
    """
    List every project currently indexed in the rollup, with its rollup
    chunk location and section size. Use this to see what's available
    before calling get_project, or to sanity-check the index after a build.

    Returns an empty list if no rollup has been built yet (run
    build_rollup first).
    """
    manifest = rollup.get_manifest()
    return [
        {
            "name": name,
            "chunk": entry["chunk"],
            "lines": entry["end_line"] - entry["start_line"] + 1,
        }
        for name, entry in sorted(manifest.items())
    ]


@mcp.tool()
def get_project(name: str, part: str = "auto") -> dict:
    """
    Fetch one project's handoff.md section (or "_learnings" for the
    standing cross-project notes) from the rollup — the exact text a
    session would need to pick up context on that project.

    Args:
        name: project folder name exactly as it appears in list_projects
              (case/hyphenation-sensitive — folder names are the source of
              truth, not a fuzzy match).
        part: "auto" (default — full text for small sections, bounded
              current-state view for large ones), "current" (always the
              bounded view: everything through the `## Current state`
              block, dated log omitted), or "full" (everything; may be
              very large for long-running projects).
    """
    section = rollup.find_section(name, part=part)
    if section is None:
        manifest = rollup.get_manifest()
        return {
            "error": f"'{name}' not found",
            "known_projects": sorted(manifest),
        }
    entry = rollup.get_manifest().get(name, {})
    out = {"name": name, "part": part, "text": section,
           "sources": entry.get("sources", [])}
    if name != "_learnings":
        # notes_home (claude-sync.json) decides where the NEXT entry goes
        out["append_next_entry_to"] = rollup.handoff_target(name)
        out["notes_home"] = rollup.CONFIG["notes_home"]
    return out


@mcp.tool()
def search(query: str, max_results: int = 40, context: int = 1) -> list[dict]:
    """
    Search the knowledge-base NOTES (every project's handoff.md section
    plus _learnings) for a topic. Use this to find which project decided
    or learned something ("ESP-NOW", "pushSprite", a chip name) before
    fetching the whole thing with get_project. For the actual SOURCE CODE,
    use search_code instead.

    Matching is case-insensitive AND separator-insensitive, so "ESP-NOW"
    finds "espnow" and "pushSprite" finds "push_sprite". Results are ranked
    best-first (exact/whole-word/heading matches win) before truncation.

    Args:
        query: text to find.
        max_results: cap on returned hits.
        context: lines of surrounding text per hit (default 1).

    Returns [{project, line, text, snippet, score}] — line numbers relative
    to that project's own section; snippet includes the context lines with
    the matched line marked '> '.
    """
    return rollup.search(query, max_results=max_results, context=context)


@mcp.tool()
def search_code(query: str, max_results: int = 40, context: int = 0,
                project: str | None = None) -> list[dict]:
    """
    Search the actual SOURCE CODE under code/<project>/ — the gap that
    search() doesn't cover (search() only sees handoff/learnings notes).
    Use this for "where in my code did I do X" ("SHT40", "pushSprite",
    an I2C address, a function name).

    Same case-insensitive + separator-insensitive matching and best-first
    ranking as search(). Dependency/build dirs (node_modules, .pio, build,
    __pycache__) and the large on-disk data corpora + binary files are
    skipped automatically.

    Args:
        query: text to find.
        max_results: cap on returned hits.
        context: lines of surrounding code per hit (default 0 — just the line).
        project: limit to one code/<name>/ subtree; omit to search all.

    Returns [{project, file, line, text, snippet, score}] — file is relative
    to code/ (e.g. "my-project/src/main.cpp").
    """
    return rollup.search_code(query, max_results=max_results, context=context, project=project)


@mcp.tool()
def build_rollup() -> dict:
    """
    Rebuild the rollup: drains any pending _scratch.md notes into
    learnings.md, then re-bin-packs every project's handoff.md (plus
    learnings.md as "_learnings") into rollup_NNN.md chunks and rewrites
    manifest.json.

    Call this after editing any handoff.md by hand, or after add_learning,
    so the change is actually reflected in list_projects/get_project.

    Also reports any code/<name>/ repo holding uncommitted or unpushed work,
    under "uncommitted_code". This runs at session end by convention, which is
    exactly when "did the code actually get saved?" is worth answering — the
    KB root gitignores code/, so a root-level commit can succeed while
    containing none of it (see CLAUDE.md, "Git guards"). Read that field
    before declaring a session finished.
    """
    drained = rollup.drain_scratch()
    rollup.build()
    manifest = rollup.get_manifest()
    chunks = sorted({entry["chunk"] for entry in manifest.values()})
    result = {
        "scratch_notes_drained": drained,
        "projects_indexed": len(manifest),
        "chunks_written": len(chunks),
    }
    dirty = rollup.dirty_code_repos()
    if dirty:
        result["uncommitted_code"] = dirty
        result["reminder"] = (
            "These code repos have work not committed (or not pushed). "
            "Commit inside each project's OWN repo — a root commit will not "
            "contain it. Pushing follows your push policy (tools/githooks/push-policy)."
        )
    return result


@mcp.tool()
def add_learning(text: str) -> dict:
    """
    Append a standing cross-project note to learnings.md — for dead ends,
    lessons, or conventions that don't belong to any one project's
    handoff.md (see the "Lessons learned" convention). Rebuilds the rollup
    automatically (matches the dashboard's /api/learn behavior) so the
    note is immediately visible to list_projects/get_project.

    Args:
        text: the note to record (a timestamp is added automatically)
    """
    path = rollup.append_learning(text)
    rollup.build()
    return {"recorded_to": str(path), "rollup": "rebuilt"}


if __name__ == "__main__":
    # Every Claude session that launches runs this health check: the app spawns
    # this server, and autostart verifies the bridge is reachable AND the rollup
    # watcher is running, repairing both if not. If it cannot, it raises a
    # Windows notification — a dead bridge is otherwise invisible from inside a
    # session, because MCP tools read files through rollup.py and keep working.
    # Best-effort and non-fatal: MCP tools matter more than the dashboard, and
    # everything it prints goes to stderr so stdio JSON-RPC stays clean.
    # CLAUDE_SYNC_NO_AUTOSTART=1 disables it. The dashboard no longer opens by
    # itself — use the tray icon, or CLAUDE_SYNC_AUTO_GUI=1 for the old way.
    # Windows-only (Task Scheduler, toasts); skipped elsewhere or on any error.
    if sys.platform == "win32":
        try:
            import autostart

            autostart.run()
        except Exception as e:  # never let the health check block the MCP tools
            print(f"[claude-sync] autostart skipped: {e}", file=sys.stderr)

    mcp.run()
