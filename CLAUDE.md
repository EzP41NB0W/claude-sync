# claude-sync -- read before you touch anything

This folder is a cross-project knowledge base and code home. Many Claude
sessions work here over time. This file is a **signpost, not the rulebook**.

## The rulebook

**`knowledge-base/_global/learnings.md`, "Standing conventions" section.**
Read it first, every session (or call the `get_project` MCP tool with
`_learnings`). If anything conflicts with it, learnings.md wins.

## The two things you must not get wrong

1. **ALL project code lives in `code/<project-name>/`**, each its own git repo.
   Notes live in `knowledge-base/projects/<project-name>/handoff.md`.
2. **Before creating any "new" project, check `knowledge-base/projects/`** for
   an existing one of that name or lineage. A new task is often a continuation.

## Git guards (`tools/githooks/`)

Wired into the root and every `code/<name>/` repo via `core.hooksPath`
(`bash tools/githooks/install.sh`; re-run it after creating a new project repo).

- **`pre-push`** follows `tools/githooks/push-policy` (default `none`: nothing
  leaves the machine). `ALLOW_PUSH=1 git push` overrides once.
- **`commit-msg`** blocks a root commit whose message names a project whose own
  repo has uncommitted changes: the root ignores `code/`, so that commit would
  succeed and contain none of the code.

## Session end (anything that produced code or decisions)

Append a dated section to the project's `handoff.md`, put cross-project lessons
in learnings.md (`add_learning`), run `build_rollup`, then commit in BOTH
layers (the project repo for code, the root for notes).

<!-- Setup adds an "About the owner" section here: how they like to work,
     tone, what to verify on their hardware, anything else every session
     should know. -->
