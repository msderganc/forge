# pyscn quality disposition (Forge repo)

This document plans how Forge treats **pyscn** findings in this repository. It complements [`docs/structural-quality.md`](structural-quality.md), which covers probe install and skill-chain usage.

## Measurement boundary

Complexity / quality gates for this repo measure **`scripts/`** and **`forge_next/`** only (plus shrinking tests when relevant). Ignore packaging artifacts under **`build/`** — they are not product code even when present on disk after `python -m build`.

## Current baseline (2026-07)

Full-tree `pyscn check .` (complexity + dead code, clones skipped):

| Category | Count | Disposition |
|----------|------:|-------------|
| Complexity > 10 (default CI threshold) | **47** | See tiers below |
| Clone pairs (similarity ≥ 0.8) | **~166** | Informational — track, do not gate CI |
| Dead code (critical) | **0** | Clean |

Repo config: **`.pyscn.toml`** sets `max_complexity = 15` (with `medium_threshold = 12`; pyscn requires `max_complexity > medium_threshold` or `0`) for local/CI `pyscn check` when using `-c .pyscn.toml` or project root discovery. Forge structural probes may pass `--max-complexity 15` for this repo.

## Disposition tiers

### Tier A — Accept at raised threshold (15)

**Rationale:** Workflow orchestrators, gate validators, and session hygiene are inherently branchy; forcing them under cyclomatic complexity 10 creates churn without improving agent UX.

| Area | Examples | Action |
|------|----------|--------|
| Skill `handle_step_*` / `main()` | `code_review.py`, `test.py`, `evaluate.py`, `develop.py` | **Accept @ 15** until step handlers are split into phase modules |
| Diagnose registers / gates | `repro_loop_register.validate`, `diagnose_gates.check_step7_closure_gate` | **Accept @ 15** — validation tables are exhaustive by design |
| Session / handoff runtime | `session_hygiene.*`, `session_store.*`, `handoff_io._resolve_handoff_body` | **Accept @ 15** — migration + leak detection paths |
| Structural probe runners | `structural_probe_runners.run_pyscn_probe` | **Accept @ 15** |
| CLI install | `cli_install.run_uninstall`, `structural_tools._install_npm_tools` | **Accept @ 15** |

**Gate:** No new functions in Tier A may exceed **20** without a refactor ticket.

### Tier B — Refactor (high ROI)

| Function | Complexity | Status |
|----------|------------|--------|
| `handoff_menu.resolve_handoff_commands` | 31 | **Done** — `handoff_resolvers.py` |
| `skill_phases.step_for_phase` | 17 | **Done** — `skill_phase_resolve.py` |
| `repro_loop_register.validate` | 18 | **Done** — `register_validation.py` |
| `problem_spec_register.validate` | 16 | **Done** — shared validators |
| `hypothesis_register.validate_register` / `validate_elimination` | 13 / 15 | **Done** — `hypothesis_validation.py` |
| `resolve_test_handoff` | 13 | **Open** — split green/red vs mode-alt helpers (≤12 target) |

**Target:** Bring each under **12** in a dedicated hygiene PR (no behavior change). Remaining work + test remediation: [`docs/remaining-tier-b-and-test-failures-plan.md`](remaining-tier-b-and-test-failures-plan.md).

### Tier C — Refactor (medium, wave with Tier B)

| Function | Complexity | Plan |
|----------|------------|------|
| `orchestrator.parse_continuation_command` | 13 | Token parser class + unit tests per invocation prefix |
| `resume_context.summarize_memory_for_resume` | 13 | Section builders per memory file type |
| `structural_probes_gate.validate_structural_probes_gate` | 14 | Early-return helpers per gate state |
| `test_flows.handle_flow_step` | 13 | One handler per flow step (mirror `plan.py` pattern) |

### Tier D — Clone debt (informational)

166 clone pairs at ≥ 80% similarity, heavily concentrated in:

- `tests/test_regressions.py` (fixture duplication)
- `forge_next/cli_install_*.py` (install path symmetry)
- `scripts/diagnose/*_register.py` (shared register shape)
- `tests/test_skills_friction_regressions.py` (parametric test bodies)

**Disposition:**

- CI: always `pyscn check --skip-clones` (already default in Forge probe runner for speed).
- Track via quarterly report; extract shared helpers when touching a file for other reasons.
- **Do not** block ship on clone count alone.

### Tier E — CI / probe integration

| Context | Command | Fail? |
|---------|---------|-------|
| Forge `structural-probes` Pass B (scoped paths) | `pyscn check <paths> --skip-clones --max-complexity 15` | Advisory in code-review; gate is probe **completion**, not pyscn exit code |
| Forge repo CI (optional) | `pyscn check . -c .pyscn.toml --skip-clones` | Fail only on complexity > 15 or critical dead code |
| Agent local hygiene | `pyscn check scripts/foo.py --skip-clones` | Developer discretion |

Environment overrides unchanged: `FORGE_PYSCN_COMMAND`, `FORGE_SKIP_STRUCTURAL_TOOLS`.

## Execution waves

| Wave | Scope | Outcome |
|------|-------|---------|
| **W0** (done) | `.pyscn.toml`, this doc, code-review effort recommender | Baseline + agent guidance |
| **W1** (done) | `handoff_resolvers.py`, `skill_phase_resolve.py` | Handoff + phase lookup split |
| **W2** (done) | `register_validation.py`, `hypothesis_validation.py`, repro loop refactor | Shared diagnose validators |
| **W3** (done) | `continuation_parser.py`, `resume_memory_summary.py`, probe gate helpers, `test_flow_steps.py` | Parser/summary/flow splits |
| **W4** (done) | `cli_install_templates.py`, `test_flow_gates.py`, `tests/helpers/forge_test_fixtures.py` | Install + test clone reduction |

## Code-review effort ↔ structural mapping

Code review now **recommends** `--effort` and `--structural` at step 1 from mode, handoff scope, and target (see `scripts/code_review/effort_recommendation.py`). Use this table when overriding:

| Scenario | Effort | Structural |
|----------|--------|------------|
| Single-file / tiny PR | `light` | off |
| Normal post-implement handoff | `standard` | off |
| ≥ 8 files / refactor / security | `standard`–`thorough` | on |
| Architecture or plan-linked review | `thorough` | on |
| Quick pass (`--quick`) | `light` | off |

Structural probes surface pyscn (and knip/jscn) findings in `.structural-probes.json` at step 3 — separate from this repo-hygiene disposition.
