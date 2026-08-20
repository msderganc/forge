# Forge documentation

User-facing guides for installing and running Forge workflows. Internal design notes live under `docs/plans/` and `docs/evaluations/` (not maintained as product docs).

## Getting started

| Doc | Audience |
|-----|----------|
| [../README.md](../README.md) | Install, commands, workflow overview |
| [../integrations/README.md](../integrations/README.md) | Cursor / Claude / Codex install layout |
| [../integrations/spec/commands.json](../integrations/spec/commands.json) | All 14 CLI workflows |

## Feature guides

| Doc | Topic |
|-----|--------|
| [graphify.md](graphify.md) | Knowledge graph: refresh, hooks, ship-time banner, CI flags |
| [pstack.md](pstack.md) | Optional pstack companion skills: git install, credit, attach map |
| [structural-quality.md](structural-quality.md) | knip / madge / pyscn / skylos probes in code-review and evaluate |
| [pyscn-quality-disposition.md](pyscn-quality-disposition.md) | Forge repo pyscn complexity/clone disposition and CI thresholds |
| [sessions.md](sessions.md) | Parallel session directories under `.forge/sessions/` |
| [environment.md](environment.md) | `FORGE_*` environment variables; shared `--ceremony` CLI |
| [declarative-skills.md](declarative-skills.md) | Skill manifests, runner, gate kinds, asset sync, kill-switch |
| [ceremony.md](ceremony.md) | Shared process spine + ceremony bands; dual-axis mode×ceremony; `--ceremony` |
| [../templates/skill-process-spine.md](../templates/skill-process-spine.md) | Canonical spine slots and per-skill phase maps |

## Contributors and agents

| Doc | Topic |
|-----|--------|
| [../AGENTS.md](../AGENTS.md) | Orchestration contracts, state lifecycle, diagnose sidecars |
| [../CLAUDE.md](../CLAUDE.md) | Graphify rules for this repo |
| [audit/documentation-audit-2026-06.md](audit/documentation-audit-2026-06.md) | Doc drift matrix (2026-06) |

## Internal (do not add to README workflows)

| Doc | Topic |
|-----|--------|
| [studio.md](studio.md) | Forge Studio localhost UI (design/plan gates) |
| [skylos-triage.md](skylos-triage.md) | Skylos probe notes |
| `plans/`, `evaluations/` | Historical plans and skill evaluations |

## Workflow integrity (2026-07)

User-visible fixes to skill handoffs and gates shipped in `forge-next` 1.9.0:

- **`forge:test`** now defaults its handoff to **`ship`** when the run is green and to **`diagnose`** when there are failures (previously ambiguous "diagnose or ship" ordering).
- **`forge:evaluate --mode post`** now defaults its handoff to **`code-review`** (was previously unspecified for post mode).
- **`forge:diagnose`** with `fix_complexity: large` now defaults to **`design`** (not the deprecated `develop` alias); `complex` still defaults to `plan`.
- **`forge:code-review`** gained **`--effort light|standard|thorough`** (replacing the binary `--quick`) and independent **`--structural`** / **`--no-structural`** flags — structural probes are now optional and off by default for `light`/`standard`.
- **`forge ship --step 1`** is clarified as Graphify preflight *then* the ship skill for commit/PR — not a full ship pipeline by itself.
- **Session archive** (`forge session close`) now rewrites the global `handoff-{skill}.md` pointer so it keeps resolving after the move.
- **Step-1 idle auto-close** (`FORGE_STEP1_ABANDON_HOURS`) is confirmed to apply only to step-1-only sessions — mid-pipeline sessions are never auto-closed for being idle.
- **`forge:ux-review`** is now exempt from the mandatory agent-team delegation contract, same as `forge:sketch`.

## Diagnose templates

| Doc | Topic |
|-----|--------|
| [../templates/diagnose-feedback-loop.md](../templates/diagnose-feedback-loop.md) | Repro / feedback loop before 5 Whys |
| [../templates/diagnose-execution-playbooks.md](../templates/diagnose-execution-playbooks.md) | Technique playbooks |
