---
name: claude-sync-handoff-workflow
description: Session start/end discipline for the claude-sync cross-project knowledge base — read learnings first, back up before overwrite, update handoff.md, rebuild rollup. Use any time work happens in or references claude-sync.
---

# claude-sync handoff workflow

claude-sync is a cross-project knowledge base. A project's notes live either centrally in `knowledge-base/projects/<name>/handoff.md` or inside the project's own repo as `HANDOFF.md` (notes-in-repo mode, set by `notes_home` in `claude-sync.json`); code lives in the project repo under `code/<name>/` or another configured repo root. The rollup indexes both kinds of notes either way. This skill is the operating discipline for both, so nothing silently drifts between what the notes claim and what's actually on disk.

## At session start

1. Call `get_project` for `_learnings` (standing cross-project conventions) plus the specific project(s) relevant to the task.
2. Cross-check the actual folder listing under `knowledge-base/projects/` before creating or writing to a folder — `manifest.json` is regenerated FROM folder names on rollup build, so it's a derived cache, not a source of truth, and can be briefly stale right after a manual rename. Match existing folder names exactly (case, hyphenation, spacing).

## Finding things

Use the `search` MCP tool (or `python rollup.py search "<query>"`) to find which project mentions a topic before fetching whole sections. `get_project` defaults to `part="auto"` — full text for small projects, a bounded current-state view for large ones; pass `part="full"` only when the dated history is actually needed. `list_projects` shows a last-modified date per project — useful for spotting what's gone stale.

## Before overwriting a code file

claude-sync is a git repo (local-only by default; see the push policy). Commit before and after substantive changes — this replaced the older manual `.history/` backup convention as of 2026-07-05 (the `.history/` folders still exist for pre-git archaeology). Code files are always-overwrite-to-latest — the opposite convention from handoff.md, which is append-only.

## Handoff structure for long-running projects

Big handoffs should keep a `## Current state` section near the top that gets *rewritten* each session (bounded, the always-fresh summary), with the dated append-only log below it. `get_project` returns just through Current state for large projects unless `part="full"` is requested — so keeping Current state accurate is what makes fast context pulls work.

## After any session producing code or decisions

1. Append a dated section to the project's notes, never rewriting history. **Where:** the `append_next_entry_to` path that `get_project` returns (central `handoff.md` in `kb` mode, the repo's `HANDOFF.md` in `repo` mode). In `repo` mode the notes are committed WITH the code, in the project repo, in the same commit.
2. Save current code to `code/<name>/` (with the `.history` backup step above if overwriting).
3. Call `add_learning` for anything that's a cross-project lesson or dead end rather than project-specific (goes to `_learnings`, not buried in one project's doc).
4. Call `build_rollup` so the change is actually reflected in `list_projects`/`get_project` — editing handoff.md by hand or calling `add_learning` does NOT auto-rebuild the rollup.

## Non-negotiables

- **Verify before writing "confirmed"/"working" into handoff.md.** Read the actual current file/hardware state first — see the `attention-to-detail` skill. A false "verified" claim in a handoff doc propagates to every future session that trusts it without re-deriving.
- **Tag provenance** when code or a claim came from a different tool/session/model (Claude Code, Cowork, Copilot, a different claude.ai chat) — don't assume, ask if unsure.
- **Never write credentials, API keys, or tokens** into handoff.md, notes, or code. Secrets live in gitignored/blank-placeholder files filled in locally.
