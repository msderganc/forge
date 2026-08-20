---
description: |
  Run tests, analyze coverage and failures. Modes: run (default) and flows
  (mock-flow authoring). For real-browser product UX audits use forge ux-review.
  QA Reviewer lead.
---

# Forge Test — Execution & Coverage

## Skill contract

- **Use when:** you need to run the test suite and analyze coverage/failures (`run`), or author mock flows (`flows`).
- **Do not use when:** you need a real-browser product UX audit (use `ux-review`) or root-cause analysis of a failure (use `diagnose`).
- **Input:** test command/path or flow scope. **Output artifact:** test/coverage report, or created flow files.
- **Stops at:** handoff to `ship` (green) or `diagnose` (failures) — test does not fix failing code itself.
- **Small-path behavior:** core levels only; skips L8–9 checks by default for `trivial`/small scope.

See `templates/scope-size-model.md` and `templates/workflow-skill-preamble.md` for shared sizing/ceremony rules.

Shared runtime: [templates/workflow-skill-preamble.md](../../templates/workflow-skill-preamble.md).

## pstack companion

If the app has no scripted prove-it path, optionally run `/create-verification-skill`. Canonical map: `templates/pstack-contract.md`. If pstack is not installed, skip.

## Modes

- **`run`** (default): 6-step detect → execute → analyze → report
- **`flows`**: 7-step mock-flow authoring — see `templates/mock-flow-types.md` and `templates/test-flow-criteria.md`

Real-browser product UX audits live in **`forge ux-review`** (not a test mode). `forge test --mode ux` exits with a redirect.

## Simplicity

Preamble § Simplicity (YAGNI). Test behavior needed now—not hypothetical scaffolding.

<invoke cmd="forge test" />

| Argument | Required | Description |
|----------|----------|-------------|
| `--step` | Yes | 1–6 (run) or 1–7 (flows) |
| `--mode` | No | `run` or `flows` (`ux` exits with redirect to `forge ux-review`) |
| `--target` | No | Test command/path (run mode) |
| `--flow-type` | No | `scenario`, `bdd`, `http-replay`, `workflow-dryrun` |
| `--framework` / `--entry-point` / `--roles` / `--no-db` / `--re-record` | No | Flows overrides |

Default handoff: **`forge:ship`** when the run is green, **`forge:diagnose`** when there are failures.
