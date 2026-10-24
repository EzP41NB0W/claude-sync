#!/usr/bin/env bash
# Generic OpenSCAD hygiene gate.  Deliberately CHEAP -- no CGAL render -- so it
# can be run on every project every time instead of being skipped.
#
#   1. evaluation warnings, via --export-format echo (~0.2 s per file).  These
#      are the silent killers: a forward reference becomes `undef` and exports a
#      broken part, and a failed `include` leaves EVERY module undefined so the
#      whole file renders empty while reporting success.
#   2. mesh hygiene on every STL present: zero-area triangles, shell count,
#      and files that cannot be parsed at all.
#
# This catches classes, not intent.  Part-specific point probes still have to be
# written per project -- see the skill.
set -uo pipefail
OS="${OPENSCAD:-/c/Program Files/OpenSCAD/openscad.exe}"
HERE="$(cd "$(dirname "$0")" && pwd)"
FAILS=0
fail() { FAILS=$((FAILS+1)); }

echo "== scad evaluation warnings =="
found=0
while IFS= read -r f; do
    [ -z "$f" ] && continue
    found=1
    w="$("$OS" -o /dev/null --export-format echo "$f" 2>&1 \
        | grep -E "WARNING: (Ignoring unknown|undefined operation|Unable to convert|Can't open include)" \
        | sort -u | head -6)"
    if [ -n "$w" ]; then
        echo "  $f"; echo "$w" | sed 's/^/      /'; fail
    else
        printf "  %-46s clean\n" "$f"
    fi
done < <(find . -name '*.scad' -not -name '_*' | sort)
[ "$found" = 0 ] && echo "  (no .scad files)"

echo "== mesh hygiene =="
mapfile -t stls < <(find . -name '*.stl' | sort)
if [ "${#stls[@]}" -eq 0 ]; then
    echo "  (no STLs)"
else
    python "$HERE/meshcheck.py" "${stls[@]}" || fail
fi

if [ "$FAILS" -eq 0 ]; then echo "cadcheck: PASS"
else echo "cadcheck: *** $FAILS SECTION(S) WITH FINDINGS ***"; exit 1; fi
