"""
rollup.py — Build the global cross-project knowledge rollup.

Reads every knowledge-base/projects/<name>/handoff.md, plus the standing
knowledge-base/_global/learnings.md (cross-project notes that don't belong
to any one project — fed by `learn` or the dashboard's quick-capture box),
and bin-packs them into knowledge-base/_global/rollup_NNN.md chunks, never
splitting a single section across a chunk boundary. Each section is
wrapped in explicit ##name## delimiters (blank line above and below) so
it's both human-skimmable and grep-able.

knowledge-base/_global/manifest.json stores the exact location (chunk file +
line range) of every section, for instant lookup via:

    python rollup.py find <project>

Usage:
    python rollup.py build               # drain scratch, rebuild rollup + manifest
    python rollup.py find <name>         # print a project's (or _learnings') section
    python rollup.py search <query>      # ranked, separator-insensitive search across all notes
    python rollup.py search-code <query> # same, but across the actual source under code/
    python rollup.py list                # list all known sections + locations + last-modified
    python rollup.py learn "text"        # append a note to learnings.md
    python rollup.py dirty               # code/ repos with uncommitted or unpushed work
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
PROJECTS_DIR = ROOT / "knowledge-base" / "projects"
CODE_DIR = ROOT / "code"  # each project's actual source lives here (see learnings #4)
GLOBAL_DIR = ROOT / "knowledge-base" / "_global"
MANIFEST_PATH = GLOBAL_DIR / "manifest.json"
LEARNINGS_PATH = GLOBAL_DIR / "learnings.md"  # standing cross-project notes, hand- or dashboard-edited

MAX_CHUNK_LINES = 800  # bin-packing target size per rollup file


def load_projects() -> dict[str, str]:
    """Return {project_name: handoff.md text} for every project folder,
    sorted by name for stable, reproducible output. The standing
    learnings.md (if present) is included first under the key
    "_learnings" — it isn't a project folder, it's cross-cutting notes
    that don't belong to any one project."""
    projects: dict[str, str] = {}
    if LEARNINGS_PATH.exists():
        text = LEARNINGS_PATH.read_text(encoding="utf-8").strip()
        if text:
            projects["_learnings"] = text
    if not PROJECTS_DIR.exists():
        return projects
    for proj_dir in sorted(PROJECTS_DIR.iterdir()):
        if not proj_dir.is_dir():
            continue
        handoff = proj_dir / "handoff.md"
        if handoff.exists():
            projects[proj_dir.name] = handoff.read_text(encoding="utf-8")
    return projects


def load_mtimes() -> dict[str, str]:
    """Return {project_name: ISO date of last handoff.md modification}.
    Same keys as load_projects (learnings.md mtime for '_learnings')."""
    import datetime

    def iso(p: Path) -> str:
        return datetime.date.fromtimestamp(p.stat().st_mtime).isoformat()

    mtimes: dict[str, str] = {}
    if LEARNINGS_PATH.exists():
        mtimes["_learnings"] = iso(LEARNINGS_PATH)
    if PROJECTS_DIR.exists():
        for proj_dir in sorted(PROJECTS_DIR.iterdir()):
            handoff = proj_dir / "handoff.md"
            if proj_dir.is_dir() and handoff.exists():
                mtimes[proj_dir.name] = iso(handoff)
    return mtimes


def section_lines(name: str, body: str) -> list[str]:
    """Wrap a project's body in ##name## delimiters, blank line on each
    side, as its own list of lines (no trailing blank line — that's added
    by the caller as an inter-section separator)."""
    clean_body = body.rstrip("\n")
    return [f"##{name}##", ""] + clean_body.split("\n") + ["", f"##{name}##"]


def bin_pack(projects: dict[str, str]) -> list[list[str]]:
    """Greedily bin-pack project names into chunks by line count. A single
    project is never split across chunks — if it doesn't fit in the
    current (non-empty) chunk, it starts a new one. An oversized single
    project still gets its own chunk rather than being split."""
    chunks: list[list[str]] = [[]]
    chunk_lines = [0]
    for name, body in projects.items():
        n_lines = len(section_lines(name, body)) + 1  # +1 separator line
        if chunks[-1] and chunk_lines[-1] + n_lines > MAX_CHUNK_LINES:
            chunks.append([])
            chunk_lines.append(0)
        chunks[-1].append(name)
        chunk_lines[-1] += n_lines
    return chunks


def normalize_name(name: str) -> str:
    """Collapse case/spacing/hyphenation differences so near-duplicate
    project folder names can be detected (e.g. 'Smart Grow system' vs
    'widget' — the exact bug this function exists to catch, June 2026)."""
    return name.lower().replace(" ", "").replace("-", "").replace("_", "")


def check_duplicate_names(projects: dict[str, str]) -> None:
    """Warn if two project folders normalize to the same name. manifest.json
    is regenerated from folder names on every build, so it can't catch this
    on its own — it will happily index both as separate, valid-looking
    projects, silently splitting one project's identity in two. This is a
    warning only (doesn't block the build) since a false positive shouldn't
    stop you from getting your rollup."""
    seen: dict[str, list[str]] = {}
    for name in projects:
        if name == "_learnings":
            continue
        seen.setdefault(normalize_name(name), []).append(name)
    for key, names in seen.items():
        if len(names) > 1:
            print(f"WARNING: possible duplicate project folders (normalize to '{key}'): {', '.join(names)}")
            print(f"         These will be indexed as SEPARATE projects unless renamed to match exactly.")


def build() -> None:
    projects = load_projects()
    if not projects:
        print("No projects found under knowledge-base/projects/ — nothing to roll up.")
        return

    check_duplicate_names(projects)

    mtimes = load_mtimes()
    chunks = bin_pack(projects)
    GLOBAL_DIR.mkdir(parents=True, exist_ok=True)

    for old in GLOBAL_DIR.glob("rollup_*.md"):
        old.unlink()

    manifest: dict[str, dict] = {}

    for i, chunk_names in enumerate(chunks, start=1):
        chunk_path = GLOBAL_DIR / f"rollup_{i:03d}.md"
        out_lines: list[str] = []
        for name in chunk_names:
            lines = section_lines(name, projects[name])
            start_line = len(out_lines) + 1
            out_lines.extend(lines)
            end_line = len(out_lines)
            manifest[name] = {
                "chunk": chunk_path.name,
                "start_line": start_line,
                "end_line": end_line,
                "modified": mtimes.get(name),
            }
            out_lines.append("")  # separator before next section
        chunk_path.write_text("\n".join(out_lines).rstrip("\n") + "\n", encoding="utf-8")
        print(f"Wrote {chunk_path.name} ({len(chunk_names)} project(s), {end_line} content lines)")

    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {MANIFEST_PATH.relative_to(ROOT)} ({len(manifest)} project(s) indexed)")


def _git(repo: Path, *args: str) -> str | None:
    """Run git in `repo`, return stdout, or None if anything at all goes wrong.

    Deliberately fail-soft. This whole feature is a session-end courtesy; a
    missing git, a weird repo state or a slow disk must never take down
    build_rollup, which is the thing that actually keeps the notes coherent.
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True, text=True, timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout if out.returncode == 0 else None


def dirty_code_repos() -> list[dict]:
    """Which code/<name>/ repos have work that is not committed (or not pushed).

    Exists because of a failure on 2026-09-02: the KB root gitignores code/
    entirely, so `git add -A && git commit` at the root after doing work in
    code/<name>/ succeeds, prints a hash, and contains NONE of the code. The
    tools/githooks/commit-msg guard catches that at commit time — but only if
    you commit at all. This is the other net: build_rollup runs at session end
    by convention, which is exactly when "did I actually save the code?" wants
    answering.

    Reports, per project: uncommitted file count, and unpushed commit count
    where an upstream exists. Never raises.
    """
    out: list[dict] = []
    if not CODE_DIR.exists():
        return out
    for path in sorted(CODE_DIR.iterdir()):
        if not (path / ".git").exists():
            continue
        status = _git(path, "status", "--porcelain")
        if status is None:
            continue
        dirty = [ln for ln in status.splitlines() if ln.strip()]
        ahead_raw = _git(path, "rev-list", "--count", "@{u}..HEAD")
        ahead = int(ahead_raw.strip()) if ahead_raw and ahead_raw.strip().isdigit() else 0
        if not dirty and not ahead:
            continue
        entry: dict = {"project": path.name}
        if dirty:
            entry["uncommitted_files"] = len(dirty)
            # first few, so the reader can tell real work from a stray .bak
            entry["sample"] = [ln[3:] for ln in dirty[:5]]
        if ahead:
            entry["unpushed_commits"] = ahead
        out.append(entry)
    return out


def get_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        return {}
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


CURRENT_STATE_HEADING = "## Current state"
AUTO_FULL_MAX_LINES = 600  # part="auto": sections at/under this come back whole


def extract_current(section: str) -> str:
    """Return the bounded "current" view of a section: everything from the
    top through the end of its `## Current state` block (i.e. up to the
    next `## ` heading after it). Handoffs without that heading fall back
    to the first AUTO_FULL_MAX_LINES lines. Either way a trailer notes
    what was omitted, so a reader knows to ask for part="full"."""
    lines = section.split("\n")
    total = len(lines)
    cut = None
    in_current = False
    for i, ln in enumerate(lines):
        if ln.strip().lower() == CURRENT_STATE_HEADING.lower():
            in_current = True
        elif in_current and ln.startswith("## "):
            cut = i
            break
    if cut is None and in_current:
        return section  # Current state runs to the end — nothing to omit
    if cut is None:
        if total <= AUTO_FULL_MAX_LINES:
            return section
        cut = AUTO_FULL_MAX_LINES
    omitted = total - cut
    return "\n".join(lines[:cut]) + (
        f"\n\n[... {omitted} more lines (dated log/history) omitted — "
        f"request part=\"full\" if needed ...]"
    )


def find_section(name: str, part: str = "full") -> str | None:
    """Return a project's section text (delimiters included), or None if
    it's not in the manifest. part: "full" (everything), "current" (the
    bounded current-state view), or "auto" (full if the section is small,
    current view otherwise). Used by the CLI, server.py, and mcp_server.py."""
    manifest = get_manifest()
    entry = manifest.get(name)
    if not entry:
        return None
    chunk_path = GLOBAL_DIR / entry["chunk"]
    lines = chunk_path.read_text(encoding="utf-8").split("\n")
    section = "\n".join(lines[entry["start_line"] - 1 : entry["end_line"]])
    if part == "current":
        return extract_current(section)
    if part == "auto" and (entry["end_line"] - entry["start_line"] + 1) > AUTO_FULL_MAX_LINES:
        return extract_current(section)
    return section


# --- Search -----------------------------------------------------------------
# Two searchers share the same matching + ranking + snippet logic:
#   search()      — the rollup sections (handoffs + _learnings): "what did I
#                   decide / learn about X"
#   search_code() — the actual source under code/: "where in my code is X"
# Matching is case-insensitive AND separator-collapsed, so identifier
# variants hit: 'ESP-NOW'~'espnow', 'pushSprite'~'push_sprite'. This is a
# strict superset of the old literal-substring search (never fewer matches).

# Directories never worth walking for code search: VCS, dependency trees,
# build output, and the big on-disk data corpora some projects keep
# (gitignored per the code-repo convention in learnings.md).
SEARCH_PRUNE_DIRS = {
    ".git", ".history", "node_modules", ".pio", "build", "dist",
    "__pycache__", ".next", ".vite", ".cache", ".venv", "venv",
    "converted", "source-docs",
}
# Binary/opaque files skipped even if they slip past directory pruning.
SEARCH_SKIP_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp", ".svg",
    ".pdf", ".zip", ".gz", ".tar", ".7z", ".bin", ".exe", ".dll", ".so",
    ".o", ".a", ".lib", ".db", ".sqlite", ".woff", ".woff2", ".ttf",
    ".eot", ".mp3", ".wav", ".ogg", ".mp4", ".mov", ".pyc",
}
SEARCH_MAX_FILE_BYTES = 1_000_000  # source files aren't bigger than this
SEARCH_HARD_SCAN_CAP = 5000        # stop scanning code once this many raw hits pile up


def _search_norm(s: str) -> str:
    """Lowercase and drop separators (space/-/_) so identifier variants
    compare equal: 'ESP-NOW'->'espnow', 'push_sprite'->'pushsprite'. Same
    collapse normalize_name() uses for folder names, reused for match text."""
    return re.sub(r"[-_\s]+", "", s.lower())


def _matches(line: str, q_lower: str, q_norm: str) -> bool:
    """True if `line` contains the query literally (case-insensitive) or
    with separators collapsed."""
    return q_lower in line.lower() or (bool(q_norm) and q_norm in _search_norm(line))


def _score_hit(query: str, line: str) -> int:
    """Rank a matching line so the best hits survive max_results truncation.
    Exact substring beats normalized-only; a whole-word match and a
    markdown-heading line each add weight."""
    ql = query.lower()
    ll = line.lower()
    score = 1  # any match (incl. normalized-only) is worth at least this
    if ql in ll:
        score += 2
        if re.search(r"\b" + re.escape(ql) + r"\b", ll):
            score += 2
    if line.lstrip().startswith("#"):
        score += 1
    return score


def _snippet(lines: list[str], idx: int, context: int) -> str:
    """The matched line plus up to `context` lines on each side, joined by
    newlines. The match line is prefixed '> ' so a reader can spot it."""
    if context <= 0:
        return lines[idx].strip()
    lo = max(0, idx - context)
    hi = min(len(lines), idx + context + 1)
    return "\n".join(("> " if j == idx else "  ") + lines[j].rstrip() for j in range(lo, hi))


def search(query: str, max_results: int = 40, context: int = 1) -> list[dict]:
    """Search every indexed rollup section (handoffs + _learnings) for a
    topic. Matches case-insensitively and with separators collapsed, ranks
    best-first (exact/whole-word/heading matches win) before truncating,
    and attaches a few lines of surrounding context.

    Returns [{project, line, text, snippet, score}] — line numbers relative
    to the project's own section, matching what get_project returns."""
    q_lower = query.lower()
    q_norm = _search_norm(query)
    manifest = get_manifest()
    chunk_cache: dict[str, list[str]] = {}
    hits: list[dict] = []
    for name, entry in sorted(manifest.items()):
        if entry["chunk"] not in chunk_cache:
            chunk_cache[entry["chunk"]] = (GLOBAL_DIR / entry["chunk"]).read_text(encoding="utf-8").split("\n")
        lines = chunk_cache[entry["chunk"]][entry["start_line"] - 1 : entry["end_line"]]
        for i, ln in enumerate(lines):
            if _matches(ln, q_lower, q_norm):
                hits.append({
                    "project": name,
                    "line": i + 1,
                    "text": ln.strip(),
                    "snippet": _snippet(lines, i, context),
                    "score": _score_hit(query, ln),
                })
    hits.sort(key=lambda h: (-h["score"], h["project"], h["line"]))
    return hits[:max_results]


def search_code(query: str, max_results: int = 40, context: int = 0,
                project: str | None = None) -> list[dict]:
    """Search the actual source under code/<project>/ — the gap search()
    doesn't cover (search() only sees handoff/learnings notes). Same
    case-insensitive + separator-collapsed matching and best-first ranking.
    Heavy dirs (node_modules, .pio, build, large data corpora) and
    binary/oversized files are skipped.

    Args:
        query: text to find.
        max_results: cap on returned hits (best-ranked first).
        context: lines of surrounding code per hit (default 0 — just the line).
        project: limit to one code/<name>/ subtree; None searches all.

    Returns [{project, file, line, text, snippet, score}] — file is relative
    to code/ (e.g. 'my-project/src/main.cpp')."""
    if not CODE_DIR.exists():
        return []
    q_lower = query.lower()
    q_norm = _search_norm(query)
    roots = [CODE_DIR / project] if project else [CODE_DIR]
    hits: list[dict] = []
    stop = False
    for root in roots:
        if stop or not root.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(d for d in dirnames if d not in SEARCH_PRUNE_DIRS)
            for fn in sorted(filenames):
                if os.path.splitext(fn)[1].lower() in SEARCH_SKIP_EXTS:
                    continue
                fpath = Path(dirpath) / fn
                try:
                    if fpath.stat().st_size > SEARCH_MAX_FILE_BYTES:
                        continue
                    text = fpath.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue  # unreadable, gone, or binary (non-UTF-8 bytes)
                lines = text.split("\n")
                rel = fpath.relative_to(CODE_DIR).as_posix()
                for i, ln in enumerate(lines):
                    if _matches(ln, q_lower, q_norm):
                        hits.append({
                            "project": rel.split("/", 1)[0],
                            "file": rel,
                            "line": i + 1,
                            "text": ln.strip()[:400],
                            "snippet": _snippet(lines, i, context),
                            "score": _score_hit(query, ln),
                        })
                if len(hits) >= SEARCH_HARD_SCAN_CAP:
                    stop = True
                    break
            if stop:
                break
    hits.sort(key=lambda h: (-h["score"], h["file"], h["line"]))
    return hits[:max_results]


def find(name: str) -> None:
    manifest = get_manifest()
    if not manifest:
        print("No manifest found — run `python rollup.py build` first.")
        return
    section = find_section(name)
    if section is None:
        print(f"'{name}' not found. Known projects: {', '.join(sorted(manifest))}")
        return
    print(section)


def list_projects() -> None:
    manifest = get_manifest()
    if not manifest:
        print("No manifest found — run `python rollup.py build` first.")
        return
    for name, entry in sorted(manifest.items()):
        mod = entry.get("modified") or "?"
        print(f"{name:20s} {entry['chunk']}  lines {entry['start_line']}-{entry['end_line']}  modified {mod}")


# --- Standing global learnings.md + scratch drain ---------------------------
# Mirrors the old sync.py "learn" / _scratch.md flow, but local-only: no
# claude.ai upload, just a hand- and dashboard-editable doc that rollup.py
# picks up as the "_learnings" section on the next build.

SCRATCH_PATH = GLOBAL_DIR / "_scratch.md"


def append_learning(text: str) -> Path:
    import datetime
    GLOBAL_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    line = f"- **[{stamp}]** {text.strip()}\n"
    header = "" if LEARNINGS_PATH.exists() else (
        "# Global Learnings\n\n"
        "Cross-project notes that don't belong to any one project's "
        "handoff.md. Rolled up automatically as the \"_learnings\" "
        "section.\n\n"
    )
    with LEARNINGS_PATH.open("a", encoding="utf-8") as f:
        if header:
            f.write(header)
        f.write(line)
    return LEARNINGS_PATH


def drain_scratch() -> int:
    """Move every non-empty line from _global/_scratch.md into
    learnings.md, then clear the scratch file. Returns count drained."""
    if not SCRATCH_PATH.exists():
        return 0
    lines = [ln.strip() for ln in SCRATCH_PATH.read_text(encoding="utf-8").splitlines()]
    lines = [ln for ln in lines if ln]
    for ln in lines:
        append_learning(ln)
    SCRATCH_PATH.write_text("", encoding="utf-8")
    return len(lines)


def main() -> None:
    # Windows consoles default to cp1252, which dies on any Unicode in the
    # notes (arrows, em dashes). Force UTF-8 for CLI output.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if len(sys.argv) < 2:
        print(__doc__)
        return
    cmd = sys.argv[1]
    if cmd == "build":
        drained = drain_scratch()
        if drained:
            print(f"Drained {drained} scratch note(s) into learnings.md.")
        build()
    elif cmd == "find" and len(sys.argv) > 2:
        find(sys.argv[2])
    elif cmd == "search" and len(sys.argv) > 2:
        hits = search(" ".join(sys.argv[2:]))
        for hit in hits:
            print(f"{hit['project']}:{hit['line']}: {hit['text']}")
        if not hits:
            print("(no matches)")
    elif cmd == "search-code" and len(sys.argv) > 2:
        hits = search_code(" ".join(sys.argv[2:]))
        for hit in hits:
            print(f"{hit['file']}:{hit['line']}: {hit['text']}")
        if not hits:
            print("(no matches)")
    elif cmd == "list":
        list_projects()
    elif cmd == "dirty":
        rows = dirty_code_repos()
        if not rows:
            print("All code/ repos committed and pushed-up-to-date.")
        for r in rows:
            bits = []
            if r.get("uncommitted_files"):
                bits.append(f"{r['uncommitted_files']} uncommitted")
            if r.get("unpushed_commits"):
                bits.append(f"{r['unpushed_commits']} unpushed")
            print(f"{r['project']:<24} {', '.join(bits)}")
            for f in r.get("sample", []):
                print(f"    {f}")
    elif cmd == "learn" and len(sys.argv) > 2:
        text = " ".join(sys.argv[2:])
        path = append_learning(text)
        print(f"Recorded to {path.name}. Run `python rollup.py build` to fold it in.")
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
