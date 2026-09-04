---
description: |
  Execute a plan in parallel waves with per-task review, integration verification,
  documentation gate, and handoff. Supports --quick and docs-gate overrides.
---

# Forge Implement — Code Execution

## Skill contract

- **Use when:** an approved plan (or clear task list) is ready to execute in code.
- **Do not use when:** there is no plan/direction yet (go to `plan`/`design`) or the task is trivial enough for a direct edit without a wave workflow.
- **Input:** plan path (from handoff or `--plan`). **Output artifact:** code changes + documentation gate result.
- **Stops at:** handoff to `code-review` — implement does not review/merge/ship its own changes.
- **Small-path behavior:** `--quick` / small scope runs a lean single-branch pass with minimal per-task review ceremony.

See `templates/scope-size-model.md` and `templates/workflow-skill-preamble.md` for shared sizing/ceremony rules.

Shared runtime: [templates/workflow-skill-preamble.md](../../templates/workflow-skill-preamble.md).

## pstack companion

Optionally reach for `/swarm`, `/tdd`, `/typescript-best-practices`, and `/unslop`. Canonical map: `templates/pstack-contract.md`. If pstack is not installed, skip.

## Uncodixfy companion

When generating frontend UI, apply `/uncodixfy` if installed. Canonical map: `templates/uncodixfy-contract.md`. If Uncodixfy is not installed, skip.

## Simplicity

Preamble § Simplicity (YAGNI). Smallest diff per task; escalate scope creep—no drive-by refactors.

Structural charter (`templates/structural-build-charter.md`) applies while writing; probes verify at wave review (step 4).

<invoke cmd="forge implement" />

| Argument | Required | Description |
|----------|----------|-------------|
| `--step` | Yes | Phase 1–8 |
| `--plan` | Step 1 only | Plan path (auto from handoff if omitted) |
| `--quick` | No | Quick mode |
| `--allow-docs-incomplete` | Step 8 only | Bypass documentation gate |
| `--docs-override-reason` | With bypass | Recorded in handoff |
| `--docs-override-follow-up` | With bypass | Required follow-up |
| `--docs-override-requested-by` | Optional | Who requested override |

Step 8: documentation gate — plan Documentation skeleton + `.implement-documentation-gate.json` or override.

Default handoff: **`forge:code-review`**.
