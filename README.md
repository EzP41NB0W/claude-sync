# claude-sync

**A local memory for working with Claude across many sessions and many projects.**

Every Claude session starts cold. claude-sync gives each of your projects a
living `handoff.md` (what it is, what's verified, what's next), a cross-project
rulebook and lessons file, and tools so any session can pull the full context
in one call instead of you re-explaining it. Plus git guards that stop the two
mistakes agents make most: committing to the wrong repo, and pushing things
nobody approved.

100% local. No accounts, no cloud, nothing leaves your machine unless your push
policy says so.

## What's in the box

| Piece | What it does |
|---|---|
| `knowledge-base/projects/<name>/handoff.md` | Each project's living memory. Dated, appended, tagged by source. |
| `knowledge-base/_global/learnings.md` | The rulebook ("Standing conventions") + cross-project lessons. |
| `rollup.py` | Packs every handoff into indexed, greppable `rollup_NNN.md` chunks. `build`, `find <project>`, `search "<text>"`, `learn "<note>"`. No dependencies. |
| `mcp_server.py` | MCP tools for Claude: `list_projects`, `get_project`, `search`, `search_code`, `add_learning`, `build_rollup`. |
| `server.py` + `dashboard.html` | Local web panel: `server.py` is a bridge on `127.0.0.1:5151`, `dashboard.html` is opened as a local file (or from the tray icon) and talks to it. Browse projects, search, quick notes (you / Claude), capture lessons, rebuild. |
| `watch.py` | Rebuilds the rollup when a handoff changes. |
| `scrubber.py` + `secure_store.py` | Redacts secrets (keys, tokens, MACs, IPs, wifi passwords) before text goes anywhere; reversible locally. `secure_store` uses Windows DPAPI. |
| `tray.py` + `install_tray.ps1` | Windows tray icon that supervises the bridge (green up / red down), restarts it, and heartbeats. |
| `autostart.py` + `notify.py` | When Claude launches the MCP server, checks the bridge and tray are alive and repairs them; Windows toast if it can't. |
| `tools/githooks/` | `pre-push` (push policy) and `commit-msg` (two-layer git trap). |
| `.claude/skills/` | Claude Code skills for working discipline: attention-to-detail, disconfirming-evidence, upfront-planning, grounded-system-review, systematic-hardware-debugging, the handoff workflow, GUI mockups, and parametric CAD verification (OpenSCAD `cadbuild.py`, badcad `badcadgate.py` with a mutation-test runner). |

## Setup (the easy way)

Clone it, open the folder in Claude Code (or hand it to any Claude with file
access) and say:

> Read `SETUP-FOR-CLAUDE.md` and set this up for me.

Claude interviews you first (OS, how you work, whether your code goes to
GitHub, how you like to be talked to) and then installs and tailors it. Don't
skip the interview: the conventions are only useful once they fit you.

## Setup (by hand)

```bash
python rollup.py build                 # index the knowledge base (stdlib only)
bash tools/githooks/install.sh         # wire the git guards
pip install fastmcp flask              # MCP server + web panel (optional)
claude mcp add claude-sync -- python /full/path/to/mcp_server.py   # Claude Code
python server.py                       # bridge on 127.0.0.1:5151; then open dashboard.html
```

Windows tray monitor (optional): `pip install pystray pillow`, then
`powershell -ExecutionPolicy Bypass -File install_tray.ps1`.

**Before your first commit:** this clone's `origin` points at the template.
Your knowledge base is private, so `git remote remove origin` (or rename it
`upstream`), and pick a push policy (below).

## Code on GitHub? The push policy

`tools/githooks/push-policy` decides what may leave the machine:

- `none` (default): every push is blocked; `ALLOW_PUSH=1 git push` for a one-off.
- `code`: every `code/<name>/` repo pushes freely; the knowledge base stays local.
- `all`: everything, notes included.
- or a list of repo names.

The knowledge base holds your notes about your work and you; most people want
`code` at most.

## Notes in each repo instead? (`claude-sync.json`)

By default notes live centrally in `knowledge-base/projects/` and never leave
the machine. If your repos already travel (cloud sessions, several machines,
`git pull` everywhere), keep each project's notes **inside its repo** as
`HANDOFF.md` and let claude-sync index them instead of owning them. Create
`claude-sync.json` next to `rollup.py` (see `claude-sync.example.json`):

```json
{
  "notes_home": "repo",
  "repo_roots": ["code", "~/src"],
  "learnings_path": "~/dotfiles/claude/learnings.md"
}
```

- `notes_home`: where NEW entries go: `kb` (central, the default) or `repo`
  (`<repo>/HANDOFF.md`, committed and pulled with the code). The rollup reads
  both kinds regardless, and a project with both shows both, labelled.
- `repo_roots`: folders whose sub-folders are your project repos; they don't
  have to live under this folder. Code search and the uncommitted-work report
  cover all of them.
- `learnings_path`: keep the cross-project lessons file somewhere that syncs
  (a dotfiles repo), instead of `knowledge-base/_global/learnings.md`.
- `repo_handoff_names` (optional): file names to look for, default
  `HANDOFF.md`, `handoff.md`, `docs/HANDOFF.md`.

`get_project` tells Claude where the next entry goes (`append_next_entry_to`).
`python test_notes_in_repo.py` exercises the whole mode on a throwaway tree.

## How a session uses it

1. Start: read `learnings.md` (the rulebook) and the project's `handoff.md`
   (`get_project`).
2. Work. Code goes in `code/<name>/`, its own repo.
3. End: append a dated entry to the handoff (what changed, what's verified vs
   assumed, what's next) where `get_project` says (`append_next_entry_to`),
   `add_learning` for cross-project lessons, `build_rollup`, and commit: in
   both layers in `kb` mode, or just the project repo in `repo` mode.

The single most important convention: **never write "working" unless it was
verified** on the real thing. Notes that overclaim poison every later session.

## Credits

Built by EzP41NB0W with Claude over a few months of firmware, CAD, web and
homelab projects, then generalized for anyone. MIT licensed.
