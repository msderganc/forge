---
description: |
  Plan critique (pre) and implementation audit (post). Path or keyword plan lookup.
  Use before implement or after to compare work to plan. Review mode deprecated — use code-review.
---

# Evaluate — Plan Analysis & Critique

## Skill contract

- **Use when:** you need a plan critique before implementing (`pre`) or an implementation audit against the plan after (`post`).
- **Do not use when:** you need a full-team code review (`--mode review` is deprecated — use `code-review`).
- **Input:** plan path or keywords. **Output artifact:** critique/audit findings against the plan.
- **Stops at:** handoff to `implement` (pre) or the orchestrator menu (post) — evaluate does not implement fixes itself.
- **Small-path behavior:** `trivial`/small scope or `--quick` skips heavy pre/post phases (pre: codebase_alignment + risk_dependencies; post: performance + operational_readiness).

Shared runtime: [templates/workflow-skill-preamble.md](../../templates/workflow-skill-preamble.md).

## pstack companion

pstack `/eval` is for skill/prompt behavior tests, not a substitute for Forge evaluate (plan vs code). Canonical map: `templates/pstack-contract.md`. If pstack is not installed, skip.

**Modes:** `pre` (7 steps), `post` (8 steps). **`--mode review` is deprecated** — use **`forge code-review`** for full-team review.

In **post** step 4, read `.structural-probes.json` when a structural-probes banner is shown.

<invoke cmd="forge evaluate --plan '<plan path or keywords>'" />

| Argument | Required | Description |
|----------|----------|-------------|
| `--step` | Yes | Phase (7 pre, 8 post) |
| `--plan` | Step 1 (pre/post) | Plan path or keywords |
| `--mode` | No | `pre` or `post` (auto-detected) |
| `--team` | No | Team dispatch in pre/post |
| `--quick` | No | Small ceremony: skip heavy phases |
| `--effort` | No | `small`/`medium`/`large` (aliases: lite/light/standard/thorough) |

**Minimal-scope:** small/trivial/`--quick` skips pre `codebase_alignment` + `risk_dependencies`, and post `performance` + `operational_readiness`. Size is inferred from plan task count and scope tier when flags are omitted.

Default handoff (pre): **`forge:implement`**. Default handoff (post): varies — see orchestrator menu.
