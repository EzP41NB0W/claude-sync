---
name: disconfirming-evidence
description: How to tell whether you actually know something — test a hypothesis against its own definition, and check whether your confirmations could have come out differently if you were wrong. Use before acting on any conclusion that rewrites an assumption, and whenever a measurement, spec, log, or datasheet conflicts with a document.
---

# Disconfirming evidence

Distinct from `attention-to-detail` (did I verify this claim?) and
`systematic-hardware-debugging` (is my test isolating one variable?). This one is
about the reasoning itself: a conclusion can be carefully verified, internally
consistent, confidently written up — and wrong.

The case it comes from: a vendor drawing said 94.5 x 62.0, callipers said
92.0 x 60.0. Conclusion — the drawing must be a panel-cutout template. The model
got rewritten and three confirmations were offered. All three were computed *from*
the new assumption, so they agreed with each other by construction. The real
answer was that the two numbers measured **different features of a layered part**
and both had always been correct.

## Before acting on a conclusion

1. **Test the theory against its own definition, not only against the data.**
   "Does it explain what I see" is the weak test, and it is the one you will reach
   for first. "Is it self-contradictory" is usually free. A panel cutout is
   necessarily *larger* than the part it accepts — the drawing was smaller. One
   line, never run.
2. **For each confirmation ask: would this have come out differently if I were
   wrong?** If no, it is decoration. Three confirmations all derived from the
   hypothesis are one confirmation, and a weak one.
3. **A discriminator that does not discriminate is worse than none.** Same shape
   as dispatching on `len ==` when two message types share a length — that already
   bit an ESP32 project once (two 17-byte packet types). Before trusting a test's
   verdict, check that it can actually tell the cases apart.
4. **When a measurement fights a document, suspect they measure different things**
   before declaring either wrong. Ask "what is this number *of*?" A layered
   assembly hands you four different "outlines"; a datasheet and a scope trace can
   both be right about different nodes.
5. **Elegance is a smell in your CONCLUSIONS, and a signal in the designer's
   INPUTS.** These look contradictory and are not. "Both axes came out to exactly
   0.80" was suspicious because *I computed it* — an artifact of the frame of
   reference I had just chosen. But a physical part measuring 95.0 / 63.0 / 1.25 /
   0.25 is not suspicious at all, because a human typed those into CAD. People
   design on a grid — wholes, halves, quarters, tenths — since the number has to
   be held in a head and put on a drawing.
   **The test: did the neatness appear in a number someone would have TYPED, or
   in one you CALCULATED?** The first is signal; the second is you admiring your
   own reflection.
6. **Snap measurements to the nominal, and check the whole SET at once.** A
   calliper returns the designer's number plus tolerance plus reading error. One
   value landing near-round proves nothing; a whole set snapping to the same grid
   simultaneously — one rim width serving both axes, one clearance serving both
   axes — is a drawing. Prefer deriving hard-to-measure dimensions from easy ones:
   external jaw measurements are reliable, internal ones in a shallow pocket are
   not, so measure the part that goes IN and derive the pocket, not the reverse.
   Snap in the direction the measurement error runs, and record what the raw
   reading was so the snap can be reverted if a fit fails.
7. **Keep provenance next to the number, not in a note elsewhere.**
   `[VENDOR]` / `[MEASURED]` / `[FROM-IMAGE]` / `[CHOICE]`. A number's source is
   part of the number, and mixing trust levels silently is how a guess gets
   promoted to a fact between sessions.
8. **Chase agreement from genuinely independent routes.** Three sources that share
   an ancestor are one source. Ask what each would have said under the other
   hypothesis.

9. **Tying parameters together is only safe when they are the SAME quantity.**
   Asked to "match" three radii, I collapsed them onto one shared parameter —
   tidy, and it silently dragged one of them off a value that had just been
   confirmed against real hardware. Two numbers that look alike and happen to be
   equal are not the same number: one was set by the part, the other was free.
   Before sharing a parameter, ask what *determines* each value. If the answers
   differ, keep them separate even when they agree today.
10. **Mark hardware-confirmed values and defend them.** In a model built mostly
   from drawings, photos and inference, the handful of numbers verified against
   the physical object are worth more than everything around them. Tag them
   loudly, and treat any refactor that changes one as a bug until proven
   otherwise — including a refactor that only meant to be neater.
11. **A constraint on a DERIVED quantity is worth more than another
   measurement.** "There should be 2 mm of surface between the rim and that
   strip" is not a data point, it is a *test* — it checks the whole
   reconstruction rather than adding to it. Mine disagreed by 0.25 mm, which
   was small enough that nobody would have gone looking, and the constraint was
   right while my input was wrong. Actively ask the person holding the object
   for relationships they expect to hold, not just for more numbers.

## When it turns out you were wrong

Retract **loudly and in place**. A false conclusion in a handoff or a learnings
file gets trusted by later sessions without re-derivation — that is the whole
point of writing it down, and it cuts both ways. Strike the original where it
sits, state the disproof next to it, and keep the corrected lesson attached.
Deleting it quietly loses the more valuable half: the reason it was believable.
