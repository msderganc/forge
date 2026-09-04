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
| [uncodixfy.md](uncodixfy.md) | Optional Uncodixfy UI skill: git install, design attach, galleries |
| [structural-quality.md](structural-quality.md) | knip / madge / pyscn / skylos probes in code-review and evaluate |
| [pyscn-quality-disposition.md](pyscn-quality-disposition.md) | Forge repo pyscn complexity/clone disposition and CI thresholds |
| [sessions.md](sessions.md) | Parallel session directories under `.forge/sessions/` |
| [environment.md](environment.md) | `FORGE_*` environment variables; shared `--ceremony` CLI |
| [declarative-skills.md](declarative-skills.md) | Skill manifests, runner, gate kinds, asset sync, kill-switch |
| [ceremony.md](ceremony.md) | Shared process spine + ceremony bands; dual-axis mode×ceremony; `--ceremony` |
| [../templates/skill-process-spine.md](../templates/skill-process-spine.md) | Canonical spine slots and per-skill phase maps |

## What's new (1.17)

Current PyPI is **1.16.1** until this tree is published as **1.17.0**. In this tree:

- **1.17.0 — design web references + Uncodixfy.** When design is a website or web/app UI, agents look at matching galleries (`templates/web-design-references.md`) and apply [Uncodixfy](https://github.com/cyxzdev/Uncodixfy). `forge install` copies the skill by default; re-run to update; `forge uninstall` removes it. Skip with `--skip-uncodixfy` or `FORGE_SKIP_UNCODIXFY=1`. Guide: [uncodixfy.md](uncodixfy.md). Canonical map: [`templates/uncodixfy-contract.md`](../templates/uncodixfy-contract.md).

## What's new (1.15 / 1.16)

These are already in the tree a user gets today from PyPI 1.16.1:

- **1.16.1 — docs.** README documents all four ceremony jobs on each aligned skill; overlapping tests pruned.
- **1.16.0 — ceremony-light.** Ceremony bands are jobs (Produce / Pipeline / Handoff-grade / Adversarial), not four volumes of the same spine. Only **plan light** collapses steps (7 → 3: Frame+Orient / Act / Handoff). Other aligned skills keep their step count and honor light as produce-and-stop. `--ceremony` wins over estimate. Mode axes (evaluate `pre`/`post`, test `run`/`flows`) stay orthogonal. Guide: [ceremony.md](ceremony.md).
- **1.15.0 — pstack companion install.** `forge install` copies an allowlist of optional pstack skills by default. Named Forge skills always win. If pstack is not installed, skip. Canonical map: [`templates/pstack-contract.md`](../templates/pstack-contract.md). Forge does not vendor pstack bodies. Guide: [pstack.md](pstack.md). Skip with `--skip-pstack` or `FORGE_SKIP_PSTACK=1`.

Full version table: [../README.md](../README.md) → *Highlights since 1.0*.

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
