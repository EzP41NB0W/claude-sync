---
name: systematic-hardware-debugging
description: Methodology for debugging embedded/hardware issues (sensor protocols, radio chips, comms) so findings are actually settled rather than guessed at — isolate one variable at a time, confirm the baseline works before blaming the new thing, and scope findings to the exact hardware/firmware tested.
---

# Systematic hardware debugging

Distinct from the `attention-to-detail` skill (which is about verifying claims): this is about the debugging *process itself* when something on real hardware isn't behaving — protocol commands, sensor readings, comms link issues.

## Before concluding "it doesn't work" or "it's a dead end"

1. **Confirm the baseline first.** Before testing the specific command/feature in question, confirm the surrounding protocol/link is actually working — e.g. get a clean ACK on command-mode entry before testing whether a specific sub-command is supported. If the baseline itself is shaky, a failure downstream is ambiguous, not conclusive.
2. **Isolate one variable at a time.** Don't change timing, payload, and parsing logic in the same test run — if it fails, you won't know which one mattered.
3. **Repeat before calling it settled.** Run the failing case at least 2-3 times. A single failure could be timing/noise; a repeated identical failure right after a confirmed-working step (e.g. 0 bytes response 3x in a row immediately after a good ACK) is real signal that the chip/firmware just doesn't implement the feature — not a timing bug worth chasing further.
4. **Scope the conclusion to the exact hardware/firmware tested.** "The RD-03D doesn't implement per-gate sensitivity tuning" is a settled finding about that specific chip's firmware — it is NOT evidence about the whole radar-chip family. State findings narrowly; don't let them silently generalize.

## Labeling findings

- **Settled dead end** — reproduced 3x, baseline confirmed working, so the failure isn't attributable to test-harness error. Don't keep re-testing this; move on.
- **Retry later** — inconclusive, baseline itself uncertain, or only tested once. Flag as open, not closed.

Being explicit about which bucket a finding is in prevents both wasted re-litigation of settled dead ends and false confidence in things that were never actually nailed down.
