---
name: forge:evaluate
description: Plan review (pre) or implementation audit (post). Use when the user asks to evaluate a plan, review the plan before coding, or audit implementation against a plan. Prefer code-review for full-team PR review.
---

<invoke cmd="forge evaluate --mode pre --plan '<plan path>'" />
<invoke cmd="forge evaluate --mode post --plan '<plan path>'" />

When `graphify-out/` exists, read `graphify-out/GRAPH_REPORT.md` before search; refresh at ship (`forge ship --step 1`).

