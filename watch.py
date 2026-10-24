#!/usr/bin/env python3
"""
watch.py — Auto-rebuild the global rollup whenever project notes change.

Polls knowledge-base/ (no third-party deps) and re-runs `rollup.py build`
whenever a project's handoff.md, the standing learnings.md, or the scratch
file changes. Local-only — no network calls, no claude.ai, no session key.

Usage:
    python watch.py                  # poll every 5s
    python watch.py --interval 10    # slower poll

Ctrl-C to stop.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import rollup

WATCH_GLOBS = (
    "knowledge-base/projects/*/handoff.md",
    "knowledge-base/_global/_scratch.md",
    "knowledge-base/_global/learnings.md",
)


def signature(root: Path) -> tuple:
    """A cheap fingerprint of everything we care about: (path, size, mtime)
    per watched file. Catches handoff.md edits, in-repo HANDOFF.md edits
    (notes-in-repo mode), a relocated learnings file, and scratch-file drops."""
    files = [p for pattern in WATCH_GLOBS for p in sorted(root.glob(pattern))]
    files += [h for r in rollup.repo_dirs() if (h := rollup.repo_handoff(r))]
    files.append(rollup.LEARNINGS_PATH)
    sig = []
    for p in files:
        if p.is_file():
            st = p.stat()
            sig.append((str(p), st.st_size, int(st.st_mtime)))
    return tuple(sorted(set(sig)))


def run_once() -> None:
    drained = rollup.drain_scratch()
    if drained:
        print(f"  drained {drained} scratch note(s) into learnings.md")
    rollup.build()


def main() -> int:
    ap = argparse.ArgumentParser(description="Watch knowledge-base/ and auto-rebuild the rollup.")
    ap.add_argument("--interval", type=float, default=5.0, help="poll seconds")
    args = ap.parse_args()

    root = Path(__file__).parent
    print(f"Watching {root / 'knowledge-base'} every {args.interval}s. Ctrl-C to stop.")

    last = None
    try:
        while True:
            sig = signature(root)
            if sig != last:
                print(f"\n[change detected @ {time.strftime('%H:%M:%S')}]")
                run_once()
                last = sig
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nStopped watching.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
