---
description: |
  Real-browser UX review of a web app: map purpose/users/IA/journeys, plan
  coverage, walk every page and control, capture states/screenshots, produce a
  prioritized findings report. Use this — not forge test — for live UI audits.
---

# forge ux-review — Product UX audit

## Skill contract

- **Use when:** you need a real-browser product UX audit (IA, discoverability, consistency, every reachable control/state) of a live app.
- **Do not use when:** you need automated test/coverage execution or mock-flow authoring (use `test`) or a root-cause fix (use `diagnose`).
- **Input:** app base URL. **Output artifact:** prioritized UX findings report with screenshot evidence.
- **Stops at:** handoff to `ship`, or `diagnose` when high-severity findings remain — ux-review does not fix findings itself.
- **Small-path behavior:** `--quick` narrows to critical journeys only and uses desktop-only viewport unless orientation flags the product as responsive/mobile.

See `templates/scope-size-model.md` and `templates/workflow-skill-preamble.md` for shared sizing/ceremony rules.

Walk the live UI like a real user and produce an evidence-backed UX report.

**No agent team required** for the walkthrough itself (1:1 browser work). Spawn helpers only if the user asks.

Shared runtime: [templates/workflow-skill-preamble.md](../../templates/workflow-skill-preamble.md).

## pstack companion

For pixel-match against a screenshot, optionally follow pstack visual-parity. Forge ux-review still owns the product walk. Canonical map: `templates/pstack-contract.md`. If pstack is not installed, skip.

Criteria: [templates/ux-review-criteria.md](../../templates/ux-review-criteria.md).  
Checklist: [templates/ux-review-coverage-checklist.md](../../templates/ux-review-coverage-checklist.md).  
Report: [templates/ux-review-report.md](../../templates/ux-review-report.md).

vs **`forge test`:** suite execution (`--mode run`) and mock-flow authoring (`--mode flows`). **`ux-review`** is the real-browser product UX audit (IA, discoverability, consistency, every reachable control/state).

<invoke cmd="forge ux-review" />

| Argument | When | Description |
|----------|------|-------------|
| `--step` | Always | 1–6 |
| `--base-url` | Step 1+ | App URL to review |
| `--state` | Resume | Path to session state |
| `--quick` | Optional | Narrow scope — critical journeys only |

Default next: **`forge:ship`** (or **`forge:diagnose`** when high-severity findings remain).
