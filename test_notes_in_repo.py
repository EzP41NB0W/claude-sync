#!/usr/bin/env python3
"""Test notes-in-repo mode (claude-sync.json) against a throwaway tree.

    python test_notes_in_repo.py

Builds a temp claude-sync root with: a project whose notes live only in its
repo, one with notes in BOTH places, one in an extra repo root outside the
tree, one with no notes, a relocated learnings file, and checks rollup,
search, code search, the dirty-repo report, where new entries are sent, the
watcher's fingerprint, the MCP get_project tool, and a broken config file.
"""
import json, os, shutil, subprocess, sys, tempfile, textwrap
from pathlib import Path

HERE = Path(__file__).parent
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

fails = []
def check(name, ok, info=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  ({info})" if info else ""))
    if not ok:
        fails.append(name)

tmp = Path(tempfile.mkdtemp(prefix="cs_notes_"))
root, extra, dot = tmp / "cs", tmp / "elsewhere", tmp / "dotfiles"
for d in (root / "knowledge-base/projects/beta", root / "knowledge-base/_global",
          root / "code/alpha", root / "code/beta/docs", root / "code/delta",
          extra / "gamma", dot):
    d.mkdir(parents=True)
for f in ("rollup.py", "watch.py", "mcp_server.py"):
    shutil.copy(HERE / f, root / f)

(root / "code/alpha/HANDOFF.md").write_text("# alpha\nzebracorn lives only in the repo\n", encoding="utf-8")
(root / "code/alpha/main.c").write_text("int frobnicate_alpha(void);\n", encoding="utf-8")
(root / "knowledge-base/projects/beta/handoff.md").write_text("# beta central\ncentral-only fact\n", encoding="utf-8")
(root / "code/beta/docs/HANDOFF.md").write_text("# beta repo\nrepo-only fact\n", encoding="utf-8")
(extra / "gamma/handoff.md").write_text("# gamma\nlives outside the tree\n", encoding="utf-8")
(extra / "gamma/app.py").write_text("def frobnicate_gamma(): pass\n", encoding="utf-8")
(dot / "learnings.md").write_text("# lessons\nquokka rule\n", encoding="utf-8")
subprocess.run(["git", "init", "-q", str(extra / "gamma")], check=True)

def run(code, cfg):
    """Fresh interpreter per config: rollup reads claude-sync.json at import."""
    cfgp = root / "claude-sync.json"
    if cfg is None:
        cfgp.unlink(missing_ok=True)
    elif isinstance(cfg, str):
        cfgp.write_text(cfg, encoding="utf-8")
    else:
        cfgp.write_text(json.dumps(cfg), encoding="utf-8")
    r = subprocess.run([sys.executable, "-c", textwrap.dedent(code)], cwd=root,
                       capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        print(r.stderr[-1500:])
    return r

REPO = {"notes_home": "repo", "repo_roots": ["code", str(extra)],
        "learnings_path": str(dot / "learnings.md")}

r = run("""
import json, rollup, contextlib, io
with contextlib.redirect_stdout(io.StringIO()):
    rollup.build()
m = rollup.get_manifest()
print(json.dumps({
  "names": sorted(m),
  "beta": rollup.find_section("beta", "full"),
  "sources_beta": m["beta"]["sources"],
  "search": [h["project"] for h in rollup.search("zebracorn")],
  "learn": rollup.find_section("_learnings", "full"),
  "code": sorted({h["project"] for h in rollup.search_code("frobnicate")}),
  "dirty": [d["project"] for d in rollup.dirty_code_repos()],
  "t": {n: rollup.handoff_target(n) for n in ("alpha", "beta", "delta", "newproj")},
}))
""", REPO)
d = json.loads(r.stdout.strip().splitlines()[-1])
check("repo mode indexes repo-only, both-places and extra-root projects",
      d["names"] == ["_learnings", "alpha", "beta", "gamma"], d["names"])
check("no-notes repo is not a project", "delta" not in d["names"])
check("both-places project shows both, labelled",
      "central-only fact" in d["beta"] and "repo-only fact" in d["beta"]
      and "knowledge-base/projects/beta/handoff.md" in d["beta"] and "code/beta/docs/HANDOFF.md" in d["beta"])
check("manifest lists both sources", len(d["sources_beta"]) == 2, d["sources_beta"])
check("search finds text that lives only in a repo HANDOFF.md", d["search"] == ["alpha"], d["search"])
check("learnings_path: lessons file read from elsewhere", "quokka rule" in d["learn"])
check("search_code covers every repo root", d["code"] == ["alpha", "gamma"], d["code"])
check("dirty-repo report covers extra roots", "gamma" in d["dirty"], d["dirty"])
check("new entries -> existing repo HANDOFF.md", d["t"]["alpha"] == "code/alpha/HANDOFF.md", d["t"]["alpha"])
check("new entries -> the repo file it already uses", d["t"]["beta"] == "code/beta/docs/HANDOFF.md", d["t"]["beta"])
check("new entries -> new HANDOFF.md in a repo without one", d["t"]["delta"] == "code/delta/HANDOFF.md", d["t"]["delta"])
check("new entries -> brand-new project lands under the first repo root",
      d["t"]["newproj"] == "code/newproj/HANDOFF.md", d["t"]["newproj"])

r = run("""
import json, rollup
print(json.dumps({n: rollup.handoff_target(n) for n in ("alpha", "beta")}))
""", None)
t = json.loads(r.stdout.strip().splitlines()[-1])
check("no config = kb mode: entries go to the central handoff",
      t == {"alpha": "knowledge-base/projects/alpha/handoff.md",
            "beta": "knowledge-base/projects/beta/handoff.md"}, t)

r = run("""
import time, rollup, watch
from pathlib import Path
a = watch.signature(Path('.'))
time.sleep(1.1)
p = [rollup.repo_handoff(r) for r in rollup.repo_dirs() if r.name == 'gamma'][0]
p.write_text(p.read_text() + 'edit\\n')
b = watch.signature(Path('.'))
print('changed' if a != b else 'same')
""", REPO)
check("watcher notices an edit to a repo HANDOFF.md outside the tree",
      r.stdout.strip().endswith("changed"), r.stdout.strip()[-40:])

r = run("""
import asyncio, json, contextlib, io, rollup
with contextlib.redirect_stdout(io.StringIO()):
    rollup.build()
from fastmcp import Client
import mcp_server
async def go():
    async with Client(mcp_server.mcp) as c:
        return (await c.call_tool("get_project", {"name": "alpha"})).data
print(json.dumps(go() if False else asyncio.run(go())))
""", REPO)
try:
    g = json.loads(r.stdout.strip().splitlines()[-1])
    check("MCP get_project says where to append the next entry",
          g.get("append_next_entry_to") == "code/alpha/HANDOFF.md" and g.get("notes_home") == "repo", g)
except (ValueError, IndexError):
    if "No module named 'fastmcp'" in r.stderr:
        print("SKIP MCP get_project (fastmcp not installed)")
    else:
        check("MCP get_project says where to append the next entry", False, r.stderr[-200:])

r = run("""
import rollup
print(rollup.CONFIG['notes_home'])
""", "{ this is not json")
check("broken claude-sync.json -> warning + defaults, not a crash",
      r.returncode == 0 and r.stdout.strip() == "kb" and "ignoring" in r.stderr, r.stderr.strip()[:80])

shutil.rmtree(tmp, ignore_errors=True)
print("\nALL NOTES-IN-REPO TESTS PASSED" if not fails else f"\nFAILED: {fails}")
sys.exit(1 if fails else 0)
