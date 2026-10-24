---
name: polished-gui-mockup
description: Reach for the visualize MCP tool to produce a real interactive/visual mockup instead of describing a UI, dashboard, or diagram in prose. Use whenever a task involves UI layout, a dashboard, a diagram, or "what would this look like."
---

# Polished GUI mockup

The visible gap between a quick answer and a polished one is usually not reasoning depth — it's whether the model actually renders something instead of describing it. This skill is a reminder to do the former.

## When to use this

- User asks about a UI layout, dashboard, form, game, or "what would X look like"
- A flowchart, architecture diagram, or data visualization would clarify the answer better than a paragraph
- Before presenting a plan for any frontend/UI change, if a mockup would let the user react to the actual look instead of a text description

## How

1. Call `mcp__visualize__read_me` first (silently — don't narrate this step to the user), picking the relevant module(s): `mockup` for UI, `diagram` for flowcharts/architecture, `chart`/`data_viz` for data, `interactive` for anything with state, `art` for illustration.
2. Use the CSS variables and layout rules it returns — don't hardcode colors, use the theme tokens so it matches the host UI.
3. Call `mcp__visualize__show_widget` with a specific, disambiguating title (snake_case) and real content — not a placeholder.
4. Then respond with text as if you went straight to the visualization — don't narrate the read_me call.

## Attention-to-detail pairing

Combine with the `attention-to-detail` skill: if the mockup represents a real UI change to actual code, still verify against the real running app (dev server + screenshot) before calling the change done — a nice mockup is not the same as a verified implementation.
