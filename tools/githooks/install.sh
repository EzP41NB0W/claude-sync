#!/usr/bin/env bash
# Point every claude-sync repo -- the KB root and each code/<name>/ -- at this
# shared hooks directory. Idempotent; safe to re-run, and re-run it after
# git-init'ing a NEW code project so the new repo is covered too.
#
#   bash tools/githooks/install.sh
#
# Why a shared dir instead of .git/hooks: .git/hooks is not tracked by git, so
# hooks written there are invisible to the repo and lost on any re-init. This
# directory lives in the KB repo, so the guards are version-controlled and a
# future session can see they exist.
set -uo pipefail
HOOKS="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HOOKS/../.." && pwd)"

setp() {
    local repo="$1"
    git -C "$repo" config core.hooksPath "$HOOKS"
    printf "  %-26s -> %s\n" "$(basename "$repo")" "core.hooksPath set"
}

echo "shared hooks: $HOOKS"
echo "== KB root =="
setp "$ROOT"
echo "== code repos =="
for d in "$ROOT"/code/*/; do
    [ -d "$d/.git" ] || continue
    setp "${d%/}"
done
echo
echo "guards active:"
echo "  pre-push    default-deny on every push   (ALLOW_PUSH=1 to override)"
echo "  commit-msg  blocks a root commit that names a project whose own"
echo "              repo is dirty                (ALLOW_DIRTY_CODE=1 to override)"
