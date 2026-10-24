---
name: upfront-planning
description: Decompose a task before acting on it — identify what's genuinely ambiguous vs. safely assumable, sequence dependencies, and flag irreversible/risky steps for confirmation. Use for any multi-step or ambiguous task before writing code or taking action.
---

# Upfront planning

A lot of what reads as "good judgment" on a hard task is really just doing this decomposition step deliberately instead of skipping straight to the first plausible action. This skill makes that step explicit.

## Before starting a multi-step task

1. **Separate "genuinely the user's call" from "safely inferable from context."** Don't ask about things resolvable from the code, the conversation, or a sensible default — but don't silently guess on things that would send the work in a materially different direction (e.g. which of several valid architectures, which existing convention to follow). Ask a real question only when actually blocked.
2. **Sequence by dependency, not by convenience.** Identify what must happen before what — e.g. "check the contract for a conflict-of-interest clause" has to happen before "start taking side jobs in that lane," not in parallel with it. Surface hard blockers explicitly rather than burying them in a list.
3. **Flag irreversible or high-blast-radius steps separately** from routine ones (deleting things, pushing to shared systems, spending money, signing up for services) — these get a confirmation checkpoint, routine steps don't.
4. **Write the plan as an ordered list a reader can act on cold**, not a narrative of your reasoning — concrete next actions, not "I think we should consider maybe looking into."

## While executing

- Re-check the plan against new information as it comes in rather than executing the original list on autopilot — if step 2 reveals the premise behind step 4 was wrong, revise instead of plowing through.
- Don't re-derive or re-litigate a decision already made earlier in the same task — move forward from it.

## When presenting the plan

- Lead with the recommendation, not an exhaustive survey of every option considered — tradeoffs get one line each, not a paragraph.
- Distinguish clearly between "here's what I'll do" and "here's a question only you can answer" — don't bury a real decision point inside a wall of proposed actions where it can get rubber-stamped by accident.
