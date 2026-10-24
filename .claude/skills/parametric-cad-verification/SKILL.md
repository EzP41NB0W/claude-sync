---
name: parametric-cad-verification
description: Verification discipline for parametric CAD (OpenSCAD) — derived probe coordinates, negative controls, mesh hygiene, minimum-feature gating, the coincident-surface and union-order traps that renders cannot show, features too small to probe, non-closed meshes that booleans silently delete, and what the print orientation decides (emboss vs engrave, islands vs bridges, which way tolerance error points). Ships cadbuild.py (vendorable OpenSCAD build + probe + artifact-slice harness), badcadgate.py (the badcad twin, with a built-in mutation-test runner) and meshcheck.py. Use for any .scad work, and before exporting an STL to print.
---

# Parametric CAD verification

Renders are not verification. CGAL's `Simple: yes / Volumes: 2` is topology — not
correctness, and not printability. Every rule below was learned by shipping the
bug first. Pairs with `disconfirming-evidence` for the dimensions themselves.

## Start here: vendor the harness, write only the part-specific half

`cadbuild.py` (this directory) is the generic half of a build gate, extracted
2026-09-27 after the same ~80 lines had been copied project to project:
single-instance lock, outputs wiped before regenerating, eval-warning AND
CGAL-stderr gates (rule 21), `GATE`/`INFO`/`PROBEDEF` parsing, point probes
with a mandatory negative control, export, meshcheck, and `load_stl` /
`slice_r` for measuring the exported file. Its docstring is the contract.

- **Copy `cadbuild.py` and `meshcheck.py` INTO the project.** Never import them
  from here. A verified project must keep building exactly as it did, after
  this directory improves. Older projects with their own inline copies of the
  harness: leave them alone.
- The project's `build.py` then holds only what is specific to the part:
  which files to export and what to measure on the artifact. A typical
  part's build.py is ~40 lines.
- When the harness itself improves, change it HERE, then re-vendor into the
  project you are working on. Prove the swap with a before/after diff of the
  build output and a mutation test (re-introduce a known bug, confirm FAIL).

## badcad path (Python + Manifold) -- `badcadgate.py`

For NEW parts, badcad (github.com/wrongbad/badcad, Manifold CSG in Python) plus
`badcadgate.py` (this directory) is the faster path: probes, clash tests and
body counts are one call each and answer instantly, so the whole gate reruns in
seconds. First used on a Raspberry Pi + HAT enclosure (2026-10-23). Same rules as cadbuild: VENDOR the file next
to build.py, never import it from here; leave verified OpenSCAD projects alone.

- Install per project in a venv, pinned: `pip install "badcad @ git+https://github.com/wrongbad/badcad.git@<sha>"`
  (+ `matplotlib` if you want `Solid.png()` renders). Installs fine on Python 3.14.
- **Mutation-test every gate: `python build.py --mutate`.** Each MUTATIONS
  entry is one textual bug that must produce a named FAIL. On the first part
  the gate passed with the snap beads FLIPPED and with the RJ45 opening smaller
  than the jack; both were blind spots until mutated. A survivor = a blind
  check, or a badly aimed mutation (the runner prints what it saw -- read it).
- **Manifold never raises on a bad primitive.** `cylinder(h=-0.15)` is
  `Error.InvalidConstruction`, and ANY boolean with it is invalid AND EMPTY
  (cube + bad cylinder -> volume 0, silently). `single_body()` checks
  `status()` first for this reason.
- Clash keep-outs must include PLUG PATHS (connector face projected out
  through the wall); the connector body alone never reaches the wall.
- Polygon holes come out slightly undersize; use `outer=True` on cylinders and
  circles for clearance holes. `mirror(y=1)` reflects across y=0.
- `load_stl()` crashes (TypeError) on an EMPTY STL -- an empty export means the
  part went invalid upstream; `export()` checks file size, the validity check
  says why.

## Traps a render cannot show you

1. **Cut pockets from the WHOLE part, never from a sub-part that unions later.**
   A pocket subtracted from a post gets back-filled by the wall around it. A
   feature unioned *before* a difference gets deleted by a later cut. Both render
   perfectly and both are silent. This single bug appeared **three times in one
   file** — insert pockets, corner posts, then display pads.
2. **Never let two surfaces land on the same plane, radius, or axis.** If a
   construction nets to exactly 0.0 clearance, give it 0.3–0.4 mm. Coincident
   faces shatter into zero-area slivers, which reach the user as fringe in the
   slicer. Watch for offsets that cancel: inset 0.25 then offset back out 0.25.
3. **Section cuts must overshoot.** Cut from outside the material, never exactly
   at its face, or the cut plane piles hundreds of triangles onto one plane.
4. **`hull()` is only safe on convex profiles.** Anything with a reflex corner —
   an ear, a step, an L — silently gets its *convex hull*, bridging the step and
   laying tangent lines onto fillet arcs. Use a stepped taper instead.
5. **Bias every tolerance toward the survivable failure.** Ask which direction of
   being wrong still closes. A floating lip rattles and foam tape fixes it; a
   clamped one cracks tempered glass.

## The harness

6. **Probe coordinates must be EXPRESSIONS evaluated against the model**, never
   frozen literals. Literals rot the moment a dimension moves, and they rot
   silently — the probe keeps sampling the old location and reports on nothing.
7. **Re-aim probes when a referenced value changes sign or position.** A probe
   pointed at the wrong feature is indistinguishable from one that works.
8. **Keep a negative control that MUST fire**, and confirm that it fired. A
   harness that cannot fail is worse than no harness, because it launders guesses
   into confidence.
9. **One failure must not hide the others.** Collect failures and run to the end;
   the exit code is the verdict. Chain prep and verification with `&&` — a patch
   script that dies on its own line leaves the *old* harness running and printing
   green.
10. **Gate the mesh on every exported STL**: zero-area triangles and connected-
    shell count. `meshcheck.py` ships with this skill — copy it into the project
    and call it from the build script. Shell count also *disproves* things: it
    once showed four standoffs were properly joined when they looked floating,
    preventing a needless redesign.
11. **Gate minimum feature width.** A 0.22 mm shelf is valid solid geometry and
    will not exist in plastic. `min_feat` ≈ one bead at the nozzle in use (0.45
    for a 0.4 mm nozzle). Walk every *derived* width — typed numbers get eyeballed
    by a human, derived ones never do. **Report** rather than assert when the
    dimension is faithful to a real part; assert for features you invented.

## The exported file is not the model

12. **Verify the ARTIFACT, not the model.** Every check in a harness like this
    interrogates the source; the thing that gets printed is the exported file.
    They can silently diverge — a concurrent build, a failed export, a stale file
    — and nothing downstream can tell. After the build, re-open the STL and
    measure the real features against the spec. Not a timestamp, not the build
    log: the file.
13. **Take a single-instance lock.** Two build runs writing the same outputs
    concurrently produce a file matching NEITHER version of the source, and every
    check still passes. `mkdir` a lockdir, trap EXIT to remove it, refuse to start
    if it exists. This is not a discipline problem you can solve by being careful;
    it bit twice in one session before the lock existed.
14. **Delete outputs before regenerating.** A part that fails to build must be
    ABSENT, not a stale file from the previous geometry. Absent is loud; stale is
    silent and looks exactly like success.
15. **Forward references evaluate to `undef`, they do not error.** OpenSCAD
    resolves a scope's assignments in order, so `a = b;` before `b` exists yields
    `undef`, propagates through every derived value, and exports a broken part
    with no failure. Declare in dependency order, and gate the build on the
    "Ignoring unknown variable" / "undefined operation" warnings.
16. **Pin a boundary with a PAIR of probes**, solid on one side and empty on the
    other. A lone "is it solid here" probe passes just as happily if the whole
    edge drifts three millimetres the wrong way; a pair traps it between them.
17. **Never bake a measured value into a probe's label.** Labels reading
    "(5.22 mm)" and "(0.22 mm, thin)" kept passing while quietly lying, because
    the geometry moved and the strings did not. Name the feature, not its size.
18. **Re-aim probes when the ARCHITECTURE changes, not just when a number does.**
    Inverting a tier order left a probe sampling a boundary that had moved; it
    was still a valid point in space and still reported confidently.

## Order of operations

Write the probe **before** the geometry. That is the whole difference between a
thirty-second fix and a wasted print. And state plainly in any handoff whether a
part has been printed — "verified" for geometry-only work means the checks passed
on paper and nothing has touched the printer.

## Rule 19 -- never infer a height from a CUT reference part

A reference model that has been split, sectioned, or cut-and-pasted has a slice
plane through it. Every feature that crosses that plane ends flat at the SAME z.
Two features clipped by one cut are indistinguishable from two features that are
genuinely coplanar. The mesh cannot tell you which.

Seen 2026-08-30 on a display-board case: a mock-up showed four posts and a perimeter
rib both ending at 4.419 off the back face. I read that as "coplanar, they bear
on the same mating surface" and modelled both at one height. They are 5.0 and
7.0. The 4.419 was the cut plane. The reasoning was plausible and wrong, and the
artifact I checked against could not have falsified it.

Do this instead:
  1. Measure heights on the UN-CUT part if one exists. The same project's intact
     bezel gave the posts directly: boss ring Y 2.000..7.000 off a back face at
     7.000 = 5.000 exactly.
  2. Before trusting any depth off a cut part, find its cut plane -- histogram
     vertex coordinates along the thickness axis and look for a value that many
     unrelated features share, especially a non-round one. Treat every feature
     terminating there as UNKNOWN height, not as measured.
  3. A non-round number (4.419, 3.469) where every other dimension in the part
     is round is itself the tell.
  4. If no un-cut source exists, ask. One question is cheaper than a reprint.

The general form: an artifact check can only falsify what the artifact actually
records. A cut part records "at least this tall", never "this tall".

## Rule 20 -- a point probe must never TOUCH a face

Probes are small solids intersected with the model. If a probe's own face lands
exactly on a model face, the intersection is a zero-volume sliver -- and OpenSCAD
still exports it as geometry. "Not empty" then means "the probe touched
something", not "the point is inside material". Such a probe reads SOLID
everywhere and silently stops testing anything.

Seen 2026-08-30 on the same case: a 0.3-tall probe placed at vb_rib_h-0.3 had
its top face exactly on the body's back face. Three points that should have read
empty/empty/solid all read SOLID. Moving the same probe down 0.3 mm, so its span
was strictly interior, gave empty/empty/solid correctly.

  probe span 6.7..7.0  (body face at 7.0)   ->  SOLID  SOLID  SOLID   (useless)
  probe span 6.4..6.7                       ->  empty  empty  SOLID   (correct)

Rules:
  - Size every probe so its whole span is strictly INSIDE one region. Never let
    a probe start or end on a feature boundary, and never derive its extent from
    the same parameter as the face it sits near (vb_rib_h-0.3 with h=0.3 lands
    exactly on vb_rib_h).
  - Prefer a probe an order of magnitude smaller than the feature it is testing.
  - A probe that reads SOLID at every point you try is a broken probe, not a
    solid part. Confirm by moving it, not by trusting it.

This is the coincident-surface trap (rule 4) applied to the TEST rather than the
model. It is worse there: a bad model gets caught by mesh hygiene, but a bad
probe reports success.

## Rule 21 -- an edge-touching 2D union extrudes to a NON-CLOSED mesh, and the
## next boolean silently DELETES it

The worst failure this discipline has produced, because the broken object passes
every check you would think to run on it.

Seen 2026-09-09 on a toy-brick part: a logo cut as four terraces. Each level's
region was built as the union of DISJOINT remainders (`ring B minus ring C`,
etc.) inside one `linear_extrude`. Disjoint regions share edges by definition,
and a 2D union of edge-touching pieces extrudes to a non-manifold pinch.

Standalone it was perfect: right triangle count, right bounding box, right
z-levels, exports and opens fine. The moment it met a boolean:

    ERROR: The given mesh is not closed! Unable to convert to CGAL_Nef_Polyhedron

and CGAL discarded **the entire solid**. One of the four terraces simply was not
on the part. The STL was valid. The geometry was wrong. Nothing in the harness
noticed except an artifact check that happened to measure that terrace's depth.

  - **Never union regions that merely touch.** Overlap them in volume, or keep
    them apart in separate `difference()` operations. This is rule 2 with teeth:
    coincident faces usually cost you slivers, but coincident *edges in a 2D
    union* cost you the whole object.
  - **Gate the build on CGAL's stderr.** `not closed`, `Unable to convert`,
    `not a valid 2-manifold`. These go to stderr during the render step, not to
    the warning stream a normal eval-warning gate reads, so they are invisible
    unless you look for them by name. One grep would have named this in seconds
    instead of costing an investigation.
  - Suspect it whenever a feature is **absent rather than deformed**. Deformed
    geometry means you modelled the wrong thing; absent geometry means something
    upstream was thrown away.

## Rule 22 -- a feature narrower than probe + 2x standoff CANNOT be probed

Rule 20 says a probe must never touch a face. That has a corollary nobody
notices until it bites: a region must be at least `probe + 2 x standoff` wide to
hold a legal probe at all. With a 0.2 mm cube and 0.4 mm of standoff, that is
1.0 mm. Anything thinner has nowhere to put one.

Seen twice in one session on that part: a rod's shank-to-land step, 0.25 mm
radially, and a logo relief whose terraces step by 0.15 mm. Both attempts aimed
at `boundary - standoff`, which lands *inside the neighbouring region*, and both
read SOLID — correctly. The probes were wrong, the model was right.

  - Do NOT shrink the standoff until it "fits". You are then back to rule 20.
  - **Measure the artifact instead.** Two diameters read off two profile planes
    of the exported mesh pin a step exactly, need no standoff, and are a
    stronger instrument than the probe would have been.
  - Say so **in the harness**, next to where the probe would go, or the next
    session re-adds the broken probe and gets a confident green.

## Rule 23 -- `offset(delta=)` miters and self-intersects; `offset(r=)` cannot

`offset(delta=)` extends each edge and joins them at a miter. At a sharp or
concave corner that miter runs out until the edges cross, self-intersecting and
shedding slivers. `offset(r=)` is a Minkowski sum with a disc and has no miter
to spike.

Seen 2026-09-09: biasing a cut region by `delta` produced 56 zero-area triangles
— exactly eight clusters, one per petal of an eight-petal ring, at the concave
cusp where a neighbouring ring was cut away around each tip. Switching to
`offset(r=)` took it to 4.

**The count's symmetry is the diagnosis.** Generic meshing noise is not
eight-fold. When defects arrive in a number that matches a feature count, the
feature is the cause.

## Rule 24 -- when a defect count is NON-MONOTONIC, stop reasoning and sweep

Same session, chasing the last few slivers: bias 0.02 gave 4, so I predicted
doubling it would swallow the remaining necks. 0.04 gave **52**. The mental
model — "neck too thin, make the bias bigger than the neck" — was simply wrong.
Those defects were near-tangencies that RELOCATE as the parameter moves rather
than getting absorbed.

A short sweep found the truth immediately:

        bias:   0.010   0.020   0.030
     fn =  8:       4       0      16
     fn = 12:       8       4      16
     fn = 24:     105       8      16

Zero at one combination, 105 one row away. There is no gradient here to follow.

  - Once a quantity moves non-monotonically, reasoning about it stops working.
    Sample it. Sweep the *cheap* rendering (one part, not the whole build) so a
    trial costs a minute instead of twenty.
  - **Ship the sweep table alongside the constant, plus the conditions under
    which it must be re-run.** A swept constant with no record of the sweep is a
    landmine: the next session changes a petal count, inherits a magic number
    tuned for different geometry, and gets a mesh full of garbage with no idea
    why. Say explicitly which parameters invalidate it.

## Rule 25 -- a build that deletes its outputs will eat hand-made files

Rule 14 says delete outputs before regenerating, and that is right. The cost
nobody warns you about: the user will put their own hand-modelled parts in that
directory, because it is where parts live, and the next build removes them with
no message.

Seen 2026-09-08: the owner dropped a cosmetic part they had modelled by hand into
`stl/`. Recovered from git only because it had been committed.

Any directory the build wipes needs a sibling it never touches (`contrib/`,
`manual/`) and a comment at the `rmtree` saying so. "It is obvious from the
script" is not a warning.

## Rule 26 -- retire a validated fit loudly, never by deletion

When a dimension that was proven in plastic gets deliberately replaced, do not
just drop it from the frozen-fits table. Move it to a RETIRED table that still
prints every build with its old value and the reason it was given up.

Otherwise the next session reads a shorter frozen list and concludes those
numbers were never proven. They were, and a decision replaced them — which is a
completely different thing from never having been tested, and leads to different
choices.

Pair it with a `note()` naming what is now UNPROVEN as a result. A design
decision that trades a validated fit for an unvalidated one is exactly the kind
of thing that should be impossible to forget.

## Rule 27 -- point probes measure POSITION; a taper's ANGLE needs two slices

Seen 2026-09-27 on a glassware adapter: a ground-glass cone meant to be 1:10 came out
1:9.76 because a tip-chamfer corner was placed at the nominal diameter one
chamfer-height up, instead of ON the taper line. Every point probe passed --
they sat 0.15 mm off the surface, and the error was 0.046 mm. Against glass
that cone would have touched only at the top edge of the joint.

What caught it: `slice_r` on the EXPORTED STL at two heights, each compared to
the diameter the taper predicts there. Two slices measure the angle; one
probe pair only brackets a position, and brackets it coarsely.

  - Any fit that depends on an ANGLE (tapers, drafts, cones, chamfers that
    seat something) gets a two-height artifact check, not just probes.
  - Put every profile vertex on the analytic line by EXPRESSION
    (`[outer_d_at(z)/2, z]`), never by reusing an endpoint value at a
    different z.
  - Mutation-test it: re-introduce the bug, confirm the build FAILS.

Related, same part: when two friction joints are in series and one must stay
put while the other releases (the adapter stays in the socket, the inserted part lifts out),
gate a grip-hierarchy proxy -- squeeze fraction x cord x contact
circumference -- so a later O-ring swap cannot silently invert it. It ranks;
it does not predict force. The test fit is still the real check.

## What the print orientation decides

Geometry that is legal in CAD can be impossible on the bed, and orientation is
what decides which. Settle it before drawing, not after.

- **Nothing can stand proud of a bed-side face.** A raised logo on the face that
  prints against glass would rest the whole part on the raised features with the
  rest of the face floating over air. On such a face you can only CUT — so build
  relief by sinking the field and leaving the "embossed" elements at the
  original plane. That is how a coin works, and it prints.
- **Which face is down decides islands vs bridges.** Cut features bridge (fine,
  short spans, anchored both sides). Proud features become first-layer islands
  (risky, and tiny ones are unprintable). A two-tone wordmark rendered as
  "engrave the dark letters, leave the light ones proud" strands the light
  letters as slivers on glass — do both as CUTS at two DEPTHS instead, and let
  shadow supply the contrast.
- **A vertical wall takes emboss and engrave equally well.** If a design truly
  needs proud relief, put it on a wall, not on the bed face or the top face.
- **Print-tolerance error has a SIGN, and it depends on orientation.** A
  vertical hole prints UNDER nominal; a part printed flat comes out OVER in XY.
  Compare those two and the errors STACK — a slot-and-tongue pair drawn with
  0.25 mm a side had near zero real clearance. Compare two vertical holes in the
  same part and the errors CANCEL.
- **So copy a proven printed nominal instead of deriving a fresh clearance.**
  When a printed feature already fits the way you want, put ITS nominal value on
  the new feature. You are not predicting the absolute size — you are
  guaranteeing the two come out the same, which is a much weaker claim and
  therefore a much safer one. Valid only for same printer, same material, same
  orientation, same feature kind.
- **The copy transfers the tolerance, not a different claim.** Copying a bore
  that holds parts nicely proves the new bore prints that size. It does NOT
  prove that something made at that size fits some third thing. Name the claim
  your evidence actually supports and write the remaining one down as unproven.
