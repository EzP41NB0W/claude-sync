# SETUP-FOR-CLAUDE.md

**You are Claude, setting up claude-sync for the person who owns this folder.
Read this whole file, then follow it. Golden rule: INTERVIEW BEFORE YOU
IMPLEMENT. Do not assume their setup matches anyone else's.**

claude-sync is a local, cross-project memory: per-project `handoff.md` files, a
rulebook (`knowledge-base/_global/learnings.md`), tools to search it all
(`rollup.py`, MCP server, web panel), and git guards. It was built by one
person and generalized; their projects and personal notes are not included.

## Step 1 -- Interview (conversational, a few questions at a time)

**Environment**
- OS and shell? Python 3 installed (`python --version`)? Where should this
  folder live?
- Which Claude products do they use (Claude Code, Desktop, claude.ai)? That
  decides how the MCP server gets registered.
- Windows? Offer the tray monitor (`install_tray.ps1`). Not Windows: skip the
  tray, `autostart`, `notify` and `secure_store` (DPAPI); everything else works.

**Their work**
- What do they build? Languages, hardware, typical project layout.
- Existing projects to bring in? For each: a name (folder-safe, lowercase,
  hyphens) and where the code lives now.

**Git and GitHub** (this sets the push policy)
- Do they want their code on GitHub? All projects (`code`), some (list the
  repo names), or none (`none`, the default)?
- The knowledge base itself should stay local unless they insist (`all`):
  explain that it will hold notes about their work and about them.

**How they like to work** (this goes into CLAUDE.md for every future session)
- Tone (terse? casual? jokes welcome?), how much explanation, how they want to
  be corrected, anything they want verified on real hardware before it's
  called done, time zone.

## Step 2 -- Install

1. `python rollup.py build`; confirm it indexes `_example-project` and
   `_learnings`.
2. `git remote -v`: if `origin` is the template's GitHub, `git remote remove
   origin` (or rename to `upstream`). Their knowledge base is private.
3. Write their push policy into `tools/githooks/push-policy`.
4. `bash tools/githooks/install.sh`.
5. Optional, per Step 1: `pip install fastmcp flask` (and `pystray pillow` on
   Windows). Register the MCP server:
   - Claude Code: `claude mcp add claude-sync -- python /full/path/to/mcp_server.py`
   - Claude Desktop: add an entry under `mcpServers` in its config file with
     `"command": "python", "args": ["/full/path/to/mcp_server.py"]`.
6. Windows + tray wanted: `powershell -ExecutionPolicy Bypass -File install_tray.ps1`;
   it must print a non-blank NextRunTime.

## Step 3 -- Tailor

- **CLAUDE.md**: fill the "About the owner" section from the interview.
- **learnings.md**: keep the Standing conventions, adjust wording to them,
  add any rules they gave you. Keep "Starter lessons" unless they object.
- **Their projects**: for each, `knowledge-base/projects/<name>/handoff.md`
  with a dated "created" entry (what it is, where the code is, what is
  verified vs assumed), and `code/<name>/` as its own repo (`git init`,
  `.gitignore`, re-run `install.sh`).
- Delete `knowledge-base/projects/_example-project/` once a real project exists.

## Step 4 -- Verify, and show them

- `python rollup.py find <a project>` returns it; `python rollup.py search
  "<a word from a handoff>"` finds it.
- If the MCP server is registered: call `list_projects` and `get_project`.
- Web panel: `python server.py`, then open `dashboard.html` in a browser (a local file; it talks to the bridge on 127.0.0.1:5151). Its status line should say the bridge is reachable.
- Push guard: in a scratch `code/` repo with a dummy remote, a push should be
  blocked or allowed exactly as their policy says.
- Commit the root (notes) and each code repo separately; `git show --stat HEAD`
  in both.

Tell them plainly what was verified and what wasn't.
