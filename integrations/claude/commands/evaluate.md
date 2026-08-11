---
name: forge:evaluate
description: Plan review (pre) or implementation audit (post). Use when the user asks to evaluate a plan, review the plan before coding, or audit implementation against a plan. Prefer code-review for full-team PR review.
---

## Hard rule — what the user sees

**Never show terminal commands** for this workflow.

**Never edit the repository** unless the phase allows it. Follow the active skill's orchestrator output for what may be written.


## Graphify

Runs at **ship** only (`forge ship --step 1`). This workflow does not print GRAPHIFY per step.


## What to tell the user first

- **Evaluate** critiques a plan (pre) or audits implementation vs plan (post).
- For full-team code review, use **code-review** (not evaluate --mode review).

## What you run (agent)

**Must run:** `forge evaluate --mode pre --plan '<plan path>' --step 1` (or `--mode post`) — the orchestrator script — before any other work.

Run **evaluate** with `--mode pre` or `--mode post` and `--plan` on step 1.
