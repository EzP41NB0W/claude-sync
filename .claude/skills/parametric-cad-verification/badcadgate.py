"""badcadgate -- the generic half of a badcad build + verification gate.

The badcad twin of cadbuild.py. Extracted 2026-10-23 from the first badcad
part (a Raspberry Pi + HAT enclosure). VENDOR THIS FILE: copy it next to the
project's build.py, don't import it from the skill directory. A verified
project must keep building exactly as it did after this file improves.

A project's build.py supplies only what is specific to the part:

    import badcadgate as bg
    g = bg.Gate()
    g.single_body("base", base)
    g.no_overlap("lid does not bind", base, lid)
    g.no_overlap("hardware clears base", base, keepout)   # keepout INCLUDES plug paths
    g.probe("RJ45 opening is open", base, pt, solid=False)
    g.probe("RJ45 opening is solid", base, pt, solid=True, negative=True)
    paths = g.export(OUT, {"base": base, "lid": lid})
    art = bg.load_stl(paths["base"])                      # the ARTIFACT, not the model
    g.opening("artifact: RJ45 width", art, z=..., line=yf, inside=x, want=16.0)
    bg.mutate_if_asked(__file__, MUTATIONS)              # `--mutate` runs the mutation suite
    g.finish()                                           # exit code is the verdict

Mutation suite contract -- MUTATIONS is a list of
    (label, old_text, new_text, expect_fail_substring)
Each one copies build.py with ONE textual change, runs it, and requires a FAIL
line containing expect_fail_substring. A mutation that still PASSES means that
check is blind: it is reported and the parent run fails. This is not optional
polish -- the first badcad part shipped a gate that passed with its snap beads
flipped and with an RJ45 opening smaller than the jack.
"""
import os, re, subprocess, sys
from badcad import cross_section, load_stl, square   # re-exported for build.py

TOL_VOL = 0.01   # mm^3: an "empty" boolean comes back as +/- float dust


class Gate:
    def __init__(self):
        self.fails = []
        self.n = 0

    def check(self, name, ok, info=""):
        self.n += 1
        print(("PASS " if ok else "FAIL ") + name + (("  " + info) if info else ""), flush=True)
        if not ok:
            self.fails.append(name)
        return ok

    # -- topology / clashes ---------------------------------------------------
    def single_body(self, name, part):
        # Manifold does NOT raise on a bad primitive: cylinder(h=-0.15) is
        # Error.InvalidConstruction, and ANY boolean with it is invalid and EMPTY
        # (cube + bad cylinder -> volume 0, no exception). Check status first.
        st = str(part.status())
        self.check(f"{name} is valid", st.endswith("NoError"), st)
        k = len(part.decompose())
        return self.check(f"{name} is one solid", k == 1, f"bodies={k}")

    def no_overlap(self, name, a, b):
        v = (a & b).get_volume()
        return self.check(name, v < TOL_VOL, f"overlap={v:.4f} mm3")

    # -- point probes ---------------------------------------------------------
    def probe(self, name, part, pt, solid, negative=False):
        """negative=True: a deliberately WRONG claim that must fail. If it
        passes, the probe machinery itself is broken (wrong frame, wrong part)."""
        got = part.contains(tuple(pt))
        ok = (got == solid)
        if negative:
            return self.check(name + " (negative control must fail)", not ok, f"solid={got}")
        return self.check(name, ok, f"solid={got}")

    # -- export + artifact ----------------------------------------------------
    def export(self, out_dir, parts):
        # a mutant build must never overwrite the real STLs
        if os.environ.get("BADCADGATE_MUTANT"):
            import tempfile
            out_dir = tempfile.mkdtemp(prefix="badcadgate_mutant_")
        os.makedirs(out_dir, exist_ok=True)
        paths = {}
        for nm, p in parts.items():
            paths[nm] = os.path.join(out_dir, nm + ".stl")
            p.stl(paths[nm])
            self.check(f"exported {nm}.stl", os.path.getsize(paths[nm]) > 84)
        return paths

    def opening(self, name, solid, z, line, inside, want, tol=0.1, axis="x", band=0.4):
        """Width of the opening containing `inside`, measured on a horizontal
        slice at height z, along a thin band through a wall.
        axis="x": band runs along X at y=line (front/back walls).
        axis="y": band runs along Y at x=line (left/right walls)."""
        sec = cross_section(solid, z=z)
        if axis == "x":
            strip = square(400, band).move(-200, line - band / 2)
            pick = lambda poly: [p[0] for p in poly]
        else:
            strip = square(band, 400).move(line - band / 2, -200)
            pick = lambda poly: [p[1] for p in poly]
        runs = solid_runs([pick(poly) for poly in (sec & strip).to_polygons()])
        gaps = [(m[1], n[0]) for m, n in zip(runs, runs[1:])]
        hit = [g for g in gaps if g[0] < inside < g[1]]
        if not hit:
            return self.check(name, False, f"no opening around {inside}; solid runs {runs}")
        w = hit[0][1] - hit[0][0]
        return self.check(name, abs(w - want) < tol, f"measured {w:.2f} want {want:.2f}")

    def finish(self):
        print(f"\n{self.n} checks. VERDICT:",
              "PASS" if not self.fails else f"FAIL ({len(self.fails)}): " + ", ".join(self.fails))
        sys.exit(1 if self.fails else 0)


def solid_runs(coord_lists):
    """Solid intervals from polygon extents, merged. (Gaps between RAW vertices
    are wrong: a long solid stretch only has vertices at its two ends.)"""
    ivs = sorted((min(c), max(c)) for c in coord_lists if c)
    runs = []
    for a, b in ivs:
        if runs and a <= runs[-1][1] + 1e-6:
            runs[-1][1] = max(runs[-1][1], b)
        else:
            runs.append([a, b])
    return runs


def mutate_if_asked(script, mutations):
    """`python build.py --mutate`: run the mutation suite instead of a normal
    finish. Exits 0 only if EVERY mutation was caught."""
    if "--mutate" not in sys.argv:
        return
    src = open(script, encoding="utf-8").read()
    # only mutate the model/gate ABOVE the MUTATIONS list -- the list itself
    # contains every target string as a literal
    cut = src.find("\nMUTATIONS = [")
    head, tail = (src, "") if cut < 0 else (src[:cut], src[cut:])
    here = os.path.dirname(os.path.abspath(script))
    blind = []
    for label, old, new, expect in mutations:
        if head.count(old) != 1:
            print(f"BAD MUTATION {label}: target text found {head.count(old)}x (need exactly 1)")
            blind.append(label)
            continue
        tmp = os.path.join(here, "_mutant.py")
        open(tmp, "w", encoding="utf-8").write(head.replace(old, new) + tail)
        try:
            env = dict(os.environ, BADCADGATE_MUTANT="1")
            r = subprocess.run([sys.executable, tmp], capture_output=True, text=True,
                               cwd=here, env=env)
        finally:
            os.remove(tmp)
        fail_lines = [l for l in r.stdout.splitlines() if l.startswith("FAIL")]
        caught = r.returncode != 0 and any(expect in l for l in fail_lines)
        print(("CAUGHT " if caught else "BLIND  ") + label)
        if not caught:
            blind.append(label)
            # say what DID happen: a crash or a different FAIL means the mutation
            # was badly aimed, not that the gate is blind -- read before fixing
            for l in fail_lines[:4]:
                print("         saw: " + l)
            if r.returncode != 0 and not fail_lines:
                print("         crashed: " + (r.stderr.strip().splitlines() or ["?"])[-1])
    print(f"\nmutation suite: {len(mutations) - len(blind)}/{len(mutations)} caught")
    sys.exit(1 if blind else 0)
