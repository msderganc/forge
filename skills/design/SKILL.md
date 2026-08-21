---
description: |
  Investigate, brainstorm, and evaluate solutions. Spawns agent team for
  investigation, solution evaluation, and user approval. Autonomy --auto1/2/3,
  --quick. Writes docs/forge/specs/*-design.md for medium/large scope.
---

# Forge Design — Investigation & Ideation

## Skill contract

- **Use when:** multiple viable approaches exist, requirements are unclear, or the change is greenfield-shaped and needs investigation before a plan.
- **Do not use when:** direction is already approved (go to `plan`) or intent is still fuzzy (go to `sketch` first).
- **Input:** problem statement or `sketch-decisions.md`. **Output artifact:** approved direction, plus `docs/forge/specs/*-design.md` when scope is medium/large.
- **Stops at:** handoff to `plan` once a direction is approved — design does not decompose tasks or execute code changes.
- **Small-path behavior:** for `trivial`/small scope, skip the formal spec file and lean team; approve the simplest option without a full brainstorm.

See `templates/scope-size-model.md` and `templates/workflow-skill-preamble.md` for shared sizing/ceremony rules.

Routing: [AGENTS.md](../../AGENTS.md) § Process-first.

Shared runtime: [templates/workflow-skill-preamble.md](../../templates/workflow-skill-preamble.md). Agent roster: [templates/forge-agent-roster.md](../../templates/forge-agent-roster.md).

## pstack companion

When competing shapes remain, optionally run `/arena`. Not a substitute for Forge design. Canonical map: `templates/pstack-contract.md`. If pstack is not installed, skip.

## No repo edits without permission

Do **not** modify tracked project files unless the user explicitly authorizes. Session memory and `docs/forge/specs/` only when the orchestrator directs.

## Spec gate (medium/large)

After step 2: `design-scope.json` in memory (legacy `develop-scope.json` still read). Medium/large: complete design spec + `.design-spec-gate.json` on step 6, split spec into `.design-spec-issues.json` on step 7, then handoff on step 8. See `prompts/design/scope.md`.

## Simplicity

Preamble § Simplicity (YAGNI). Score simpler options favorably; confirm speculative breadth at approval (`prompts/design/approval.md`).

When one unresolved logic/state or UI-shape question remains, **offer** the future `forge:prototype` (not yet invokable — `docs/forge/prototype-skill-stub.md`).

<invoke cmd="forge design" />

| Argument | When | Description |
|----------|------|-------------|
| `--step` | Always | Phase 1–8 |
| `--auto1` / `--auto2` / `--auto3` | Any | Autonomy level |
| `--quick` | Step 1+ | Quick mode |
| `--allow-spec-incomplete` | Step 8 only | Bypass spec gate (requires override fields) |
| `--spec-override-reason` | With bypass | Recorded in handoff |
| `--spec-override-follow-up` | With bypass | Required follow-up |
| `--spec-override-requested-by` | Optional | Who requested bypass |
| `--allow-issues-incomplete` | Step 8 only | Bypass spec → issues gate (requires override fields) |
| `--issues-override-reason` | With issues bypass | Recorded in handoff |
| `--issues-override-follow-up` | With issues bypass | Required follow-up |
| `--issues-override-requested-by` | Optional | Who requested issues bypass |

Default handoff: **`forge:plan`**.
