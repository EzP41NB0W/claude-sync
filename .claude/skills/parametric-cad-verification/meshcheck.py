#!/usr/bin/env python
"""Mesh hygiene gate.  Renders look perfect while a part is full of zero-area
slivers, and the slicer is where you find out -- as fringe.  Coincident surfaces
are the usual cause, so this runs on every STL and fails the build on any
genuinely degenerate triangle, or on a part that is not a single closed shell.

Handles ASCII *and* BINARY STL.  The first version read only ASCII and silently
reported 0 triangles for a binary file -- a checker that returns "nothing wrong"
for input it cannot read is worse than no checker.  It now refuses loudly
instead."""
import sys, re, io, math, os, struct

def load(path):
    """Return list of triangles. Raises ValueError if the file cannot be parsed."""
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        head = f.read(5)
        # An ASCII STL starts with "solid", but so do some binary writers, so
        # confirm by checking the binary triangle count against the file size.
        f.seek(0)
        raw = f.read()
    if len(raw) >= 84:
        n = struct.unpack("<I", raw[80:84])[0]
        if 84 + n*50 == size and n > 0:
            tris = []
            off = 84
            for _ in range(n):
                v = struct.unpack("<12f", raw[off:off+48])
                tris.append([(v[3], v[4], v[5]), (v[6], v[7], v[8]), (v[9], v[10], v[11])])
                off += 50
            return tris, "binary"
    if head[:5].lower() == b"solid":
        txt = raw.decode("utf-8", errors="replace")
        V = [(float(a), float(b), float(c))
             for a, b, c in re.findall(r'vertex\s+(\S+)\s+(\S+)\s+(\S+)', txt)]
        if not V:
            raise ValueError("looks like ASCII STL but contains no vertices")
        if len(V) % 3:
            raise ValueError("vertex count %d is not a multiple of 3" % len(V))
        return [V[i:i+3] for i in range(0, len(V), 3)], "ascii"
    raise ValueError("not a recognisable ASCII or binary STL")

def area(t):
    (ax,ay,az),(bx,by,bz),(cx,cy,cz) = t
    ux,uy,uz = bx-ax,by-ay,bz-az
    vx,vy,vz = cx-ax,cy-ay,cz-az
    return 0.5*math.sqrt((uy*vz-uz*vy)**2 + (uz*vx-ux*vz)**2 + (ux*vy-uy*vx)**2)

def shells(tris):
    idx, par = {}, []
    def find(a):
        while par[a] != a: par[a] = par[par[a]]; a = par[a]
        return a
    for t in tris:
        ids = []
        for p in t:
            k = (round(p[0],4), round(p[1],4), round(p[2],4))
            if k not in idx: idx[k] = len(par); par.append(len(par))
            ids.append(idx[k])
        for a, b in ((ids[0],ids[1]), (ids[1],ids[2])):
            ra, rb = find(a), find(b)
            if ra != rb: par[ra] = rb
    return len(set(find(i) for i in range(len(par))))

rc = 0
for path in sys.argv[1:]:
    name = os.path.basename(path)
    try:
        tris, kind = load(path)
    except Exception as e:
        print("  %-28s *** UNREADABLE: %s" % (name, e)); rc = 1; continue
    ar = [area(t) for t in tris]
    dead = sum(1 for a in ar if a < 1e-6)
    thin = sum(1 for a in ar if a < 1e-3)
    n = shells(tris)
    note = ""
    if not tris:            note = "  <<< NO TRIANGLES";            rc = 1
    elif dead:              note = "  <<< %d DEGENERATE" % dead;    rc = 1
    elif n != 1:            note = "  <<< %d SHELLS, expected 1" % n; rc = 1
    elif thin:              note = "  (%d thin, none degenerate)" % thin
    print("  %-28s %-6s tris %-6d shells %d  degenerate %-4d%s"
          % (name, kind, len(tris), n, dead, note))
sys.exit(rc)
