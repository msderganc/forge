---
description: |
  Create implementation plans with task breakdown, parallelization, TDD, and risks.
  From approved design direction or standalone request. Supports --quick mode.
---

# Forge Plan — Implementation Planning

## Skill contract

- **Use when:** a single approved direction (or design handoff) needs to become concrete tasks and waves before coding.
- **Do not use when:** direction is still undecided (go to `design`) or the fix is a 1–2 file trivial change that doesn't need a plan file at all.
- **Input:** approved design direction or a standalone request. **Output artifact:** implementation plan file (tasks, waves, risks).
- **Stops at:** handoff to `evaluate --mode pre` — plan never edits product source or runs git mutation commands.
- **Small-path behavior:** `--ceremony light` runs **3 slots** (Frame+Orient → Act → Handoff), maps to `lite` narrative, ≤3 tasks, and skips Architect / 4-role review / docs-planning phases.

See `templates/scope-size-model.md` and `templates/workflow-skill-preamble.md` for shared sizing/ceremony rules.

Routing: [AGENTS.md](../../AGENTS.md) § Process-first.

Shared runtime: [templates/workflow-skill-preamble.md](../../templates/workflow-skill-preamble.md).

## pstack companion

Optionally reach for `/figure-it-out`, `/show-me-your-work`, and `/technical-writing`. Canonical map: `templates/pstack-contract.md`. If pstack is not installed, skip.

## Safety guardrails

Planning-only: no product source edits. No git mutation commands (`git add`, `commit`, `push`, `reset`, `rebase`, `checkout`, `restore`, `merge`, `stash`, `tag`). Never `--no-verify`.

## Simplicity

Preamble § Simplicity (YAGNI). Current scope only—explicit **Out of scope**; no "while we're here" tasks.

Structural charter (`templates/structural-build-charter.md`) applies during architecture/plan creation; jscn/pyscn baseline may run at step 2 for hotspot facts.

<invoke cmd="forge plan" />

| Argument | Required | Description |
|----------|----------|-------------|
| `--step` | Yes | Phase 1–7 |
| `--quick` | No | Quick mode: minimal reviews |

Default handoff: **`forge:evaluate --mode pre`**.
