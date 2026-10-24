---
name: attention-to-detail
description: Verification and precision checklist to run before calling anything "done" or "working" — use on any task involving code, hardware, or factual claims, regardless of which model is running.
---

# Attention to detail

A checklist for closing the gap between "looks plausible" and "actually verified." Cheaper/faster models skip these steps under time pressure; this skill makes them explicit steps instead of judgment calls.

## Before claiming something is done or working

1. **Read the actual current file/state before describing it.** Don't describe code from memory of what you wrote earlier in the conversation — re-read it. A claim that's silently false (notes say "fixed," code on disk still has the bug) is the most expensive failure mode.
2. **If it's hardware/UI, verify on the real thing**, not just "the logic looks right." Screenshot, run it, or ask the user to confirm on-device before writing "confirmed working" anywhere.
3. **State what you verified vs. what you're assuming.** "I confirmed X by reading the file; I'm assuming Y still holds from earlier" is fine — silently blurring the two is not.
4. **Match existing naming/conventions exactly** (folder names, variable names, terminology already used in the project) rather than a plausible-sounding near-match.
5. **Tag provenance when it matters.** If code or a claim came from a different session, tool, or model, say so rather than presenting it as freshly verified.

## Before presenting output to the user

1. **Precision over hedging.** Say "the RD-03D returned 0 bytes across 3 test runs" not "it seems like there might be an issue with the response." Vague language is often a tell that the underlying fact wasn't actually checked.
2. **Cite the file/line when referencing code** (`path/to/file.ts:42`) so the claim is checkable, not just assertable.
3. **If a rate/number/comparison is stated, it should come from a lookup, not a guess** — say explicitly when a number is an estimate vs. sourced.
4. **Don't pad with a summary restating what was just said.** State the result once, precisely, and stop.

## When this applies especially hard

- Any handoff doc or memory entry (these get trusted by future sessions without re-derivation — a false "verified" claim propagates)
- Any claim about external facts (pricing, specs, comparisons) that's checkable in one search or file read
- Any "it should work now" after a code change — run it or say plainly that it's untested
