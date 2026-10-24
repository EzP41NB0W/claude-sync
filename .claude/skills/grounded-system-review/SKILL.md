---
name: grounded-system-review
description: How to review/critique a codebase, tool, or system so the verdict is grounded in the actual implementation and observed failures — not vibes or generic best practices. Use when asked "is this good, where does it fall short, how do we improve it."
---

# Grounded system review

The difference between a useful review and a generic one is evidence discipline. Applied to any "review my system / is this good / min-max this" request.

## Process

1. **Read the actual implementation before passing judgment.** Not just the README — the core source files. A critique of what the code plausibly does is worthless next to a critique of what it actually does.
2. **Weight observed failures above theoretical ones.** A problem you hit during real use this session (e.g. a fetch blowing a token limit, a documented-but-missing watch glob) outranks any hypothetical concern. Say explicitly which findings came from observed pain vs. inspection.
3. **Say what's genuinely good, specifically.** "The manifest is explicitly documented as a derived cache" is praise that proves you read it; "looks solid overall" is filler. If the design is right, defend it against unnecessary rework.
4. **Rank findings by actual cost, not by how interesting they are.** The boring bug that fires weekly beats the elegant architectural concern that fires never.
5. **Check stated behavior against actual behavior.** Docstrings, READMEs, and comments that promise something the code doesn't do (e.g. "watches learnings.md" with no matching glob) are bugs — and easy to find by literally diffing the claims against the code.
6. **End with a ranked, sized fix list** — each item marked as small/medium/large — and a recommendation on which to do now, so the review converts directly into action instead of a discussion.

## When implementing the fixes

- Back up / commit before touching anything (per house convention).
- Verify each fix through the same interface the failure occurred in (if the bug appeared through MCP, re-test through MCP — not just by calling the Python function directly).
- Fix documentation that the changes invalidate in the same pass, including any skills/conventions that reference the old behavior.
