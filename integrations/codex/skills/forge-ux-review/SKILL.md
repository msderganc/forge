---
name: forge:ux-review
description: Real-browser product UX audit: map IA/journeys, walk pages and controls, prioritized findings report. Use when the user asks for a UX review or to walk the product UI.
---

Read `templates/ux-review-criteria.md`. Maintain coverage checklist while testing.

Prefer a real browser. Suite runs / mock flows use `forge test`, not this skill.

When `graphify-out/` exists, read `graphify-out/GRAPH_REPORT.md` before search; refresh at ship (`forge ship --step 1`).

<invoke cmd="forge ux-review" />
