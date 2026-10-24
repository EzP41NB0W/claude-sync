#!/usr/bin/env python
"""cadbuild -- the generic half of an OpenSCAD build + verification gate.

VENDOR THIS FILE: copy it into the project next to build.py, don't import it
from the skill directory. A project must keep building exactly as it did when
it was verified, even after this file improves.

A project's build.py supplies only what is specific to the part:

    import cadbuild as cb
    b = cb.Build()                       # lock + wipe stl/ and .probe/
    info = b.gates("verify.scad")        # GATE/INFO lines -> ok/fail, dict
    b.probes("verify.scad")              # PROBEDEF lines -> point probes
    b.export("part", "part.scad")        # -> stl/part.stl, must exist
    b.meshcheck()                        # every STL in stl/
    tris = cb.load_stl(b.stl("part"))    # the ARTIFACT, not the model
    lo, hi = cb.slice_r(tris, z)         # inner/outer radius at a height
    b.close("label", got, want, tol)
    b.finish()                           # exit code is the verdict

verify.scad contract (PROBE=-1 dumps, PROBE=i renders probe i):
    echo(str("GATE ", name, " ", value, " >= ", minimum));
    echo(str("INFO ", name, " ", value));
    echo(str("PROBEDEF ", i, " ", name, " ", part, " ", "solid"|"empty", " ", 0|1));
    last field 1 = negative control: it is WRONG on purpose and must fail.
"""
import os, re, sys, shutil, struct, subprocess, math, atexit

OSCAD = os.environ.get("OPENSCAD", r"C:\Program Files\OpenSCAD\openscad.exe")

# Eval warnings (a forward reference is undef, not an error) AND the CGAL
# render errors of rule 21 -- those go to stderr during render and silently
# delete whole solids.
BAD = ("Ignoring unknown", "undefined operation", "undefined value",
       "Can't open include", "Unable to convert", "not closed",
       "not a valid 2-manifold")


class Build:
    def __init__(self, here=None, stl_dir="stl", probe_dir=".probe"):
        self.here = here or os.path.dirname(os.path.abspath(sys.argv[0]))
        os.chdir(self.here)
        self.fails, self.stl_dir, self.probe_dir = [], stl_dir, probe_dir
        self.exported = []
        # Single-instance lock: two runs writing the same STLs produce a file
        # matching NEITHER source, and every check still passes.
        try:
            os.mkdir(".buildlock")
        except FileExistsError:
            sys.exit("another build is running (remove .buildlock if you are sure)")
        atexit.register(lambda: shutil.rmtree(".buildlock", ignore_errors=True))
        # Outputs are ABSENT before regenerating, never stale. Rule 25: this
        # wipes stl/ -- hand-made parts go in contrib/, which is never touched.
        for d in (stl_dir, probe_dir):
            shutil.rmtree(d, ignore_errors=True)
            os.makedirs(d)

    # ---- reporting ---------------------------------------------------------
    def fail(self, m): self.fails.append(m); print("  FAIL  " + m)
    def ok(self, m):   print("  ok    " + m)
    def note(self, m): print("  note  " + m)
    def section(self, t): print("== %s ==" % t)

    def run(self, args, tag=""):
        p = subprocess.run([OSCAD] + args, capture_output=True, text=True)
        txt = (p.stdout or "") + (p.stderr or "")
        for pat in BAD:
            if pat in txt:
                self.fail("openscad%s: %s" % (tag, pat))
        # An empty probe exits 1 with this message -- a legitimate result.
        if p.returncode != 0 and "Current top level object is empty" not in txt:
            self.fail("openscad exited %d%s: %s" % (p.returncode, tag, txt.strip()[-400:]))
        return txt

    def stl(self, name):
        return os.path.join(self.stl_dir, name + ".stl")

    # ---- gates + info ------------------------------------------------------
    def gates(self, verify="verify.scad", defines=()):
        self.section("gates")
        self.verify = verify
        echo = os.path.join(self.probe_dir, "_dump.echo")
        args = ["-D", "PROBE=-1"] + [x for d in defines for x in ("-D", d)]
        # --export-format echo writes to the FILE, not stdout. Reading stdout
        # once parsed zero probes and the run still reported green.
        self.run(args + ["-o", echo, "--export-format", "echo", verify], " (dump)")
        self.dump = open(echo, encoding="utf-8").read() if os.path.exists(echo) else ""
        gates = re.findall(r"GATE (\S+) (-?[\d.e+-]+) >= (-?[\d.e+-]+)", self.dump)
        if not gates:
            self.fail("no gates parsed -- the harness did not run")
        for name, got, want in gates:
            (self.ok if float(got) >= float(want) else self.fail)(
                "%-20s %.3f >= %.3f" % (name, float(got), float(want)))
        info = {k: float(v) for k, v in re.findall(r"INFO (\S+) (-?[\d.e+-]+)", self.dump)}
        for k, v in info.items():
            self.note("%s = %g" % (k, v))
        return info

    # ---- point probes ------------------------------------------------------
    def probes(self, verify=None, defines=()):
        self.section("point probes")
        verify = verify or self.verify
        defs = re.findall(r"PROBEDEF (\d+) (\S+) (\S+) (\S+) (\d)", self.dump)
        if not defs:
            self.fail("no probes parsed -- the harness did not run")
        neg = fired = 0
        extra = [x for d in defines for x in ("-D", d)]
        for idx, name, part, want, isneg in defs:
            out = os.path.join(self.probe_dir, "p%s.stl" % idx)
            self.run(extra + ["-o", out, "--export-format", "binstl",
                              "-D", "PROBE=%s" % idx, verify], " (probe %s)" % name)
            got = "solid" if os.path.exists(out) and os.path.getsize(out) > 84 else "empty"
            if int(isneg):
                neg += 1
                if got != want:
                    fired += 1; self.ok("NEGCTL %-22s fired as required" % name)
                else:
                    self.fail("NEGCTL %s did NOT fire -- the harness cannot fail" % name)
            elif got == want:
                self.ok("%-24s %-5s (%s)" % (name, got, part))
            else:
                self.fail("%-24s expected %s, got %s (%s)" % (name, want, got, part))
        if neg == 0:
            self.fail("no negative control defined -- a harness that cannot fail")

    # ---- export + mesh -----------------------------------------------------
    def export(self, name, scad, defines=()):
        if not self.exported:
            self.section("export")
        out = self.stl(name)
        self.run([x for d in defines for x in ("-D", d)]
                 + ["-o", out, "--export-format", "binstl", scad], " (%s)" % name)
        if os.path.exists(out):
            self.ok("%s.stl" % name); self.exported.append(out)
        else:
            self.fail("%s.stl was not produced" % name)
        return out

    def meshcheck(self):
        self.section("mesh")
        mc = os.path.join(self.here, "meshcheck.py")
        if not os.path.exists(mc):
            self.fail("meshcheck.py missing -- vendor it next to build.py"); return
        if not self.exported:
            self.fail("no STLs to check"); return
        p = subprocess.run([sys.executable, mc] + self.exported,
                           capture_output=True, text=True)
        print("  " + "\n  ".join((p.stdout + p.stderr).strip().splitlines()))
        if p.returncode != 0:
            self.fail("meshcheck")

    # ---- artifact comparisons ---------------------------------------------
    def close(self, label, got, want, tol=0.03):
        if got is None:
            self.fail("%s: nothing measured" % label); return
        (self.ok if abs(got - want) <= tol else self.fail)(
            "%-26s %.3f (spec %.3f)" % (label, got, want))

    def finish(self, passed="geometry verified on paper. NOT printed, NOT test-fit."):
        print()
        if self.fails:
            print("BUILD: *** %d FAILURE(S) ***" % len(self.fails)); sys.exit(1)
        print("BUILD: PASS -- " + passed)


# ---- reading the ARTIFACT (rule 12) ---------------------------------------
def load_stl(path):
    """Binary STL -> list of 9-float triangles. Raises on anything else --
    a reader that returns nothing for a file it can't parse reports success."""
    raw = open(path, "rb").read()
    n = struct.unpack("<I", raw[80:84])[0] if len(raw) >= 84 else -1
    if n <= 0 or 84 + n * 50 != len(raw):
        raise ValueError("%s is not a binary STL" % path)
    return [struct.unpack("<12f", raw[84 + i*50: 84 + i*50 + 48])[3:] for i in range(n)]

def z_extent(tris):
    zs = [t[k] for t in tris for k in (2, 5, 8)]
    return min(zs), max(zs)

def slice_r(tris, z, cx=0.0, cy=0.0):
    """(min, max) distance from the axis (cx, cy) of the mesh cut at height z.
    For a solid of revolution: bore radius and outer radius. Two slices at two
    heights measure a TAPER ANGLE, which no single point probe can (rule 27)."""
    rs = []
    for t in tris:
        P = (t[0:3], t[3:6], t[6:9])
        for a, b in ((0, 1), (1, 2), (2, 0)):
            za, zb = P[a][2], P[b][2]
            if (za - z) * (zb - z) < 0:
                s = (z - za) / (zb - za)
                rs.append(math.hypot(P[a][0] + s * (P[b][0] - P[a][0]) - cx,
                                     P[a][1] + s * (P[b][1] - P[a][1]) - cy))
    return (min(rs), max(rs)) if rs else (None, None)
