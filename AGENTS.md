# Forge Codex Project Instructions

## Skill Handoff Menu

When a skill completes its final step, the footer displays a **multiselect handoff** (machine-readable block + text fallback). Agents in Cursor/Claude should present options with **AskQuestion** (`allow_multiple: true`).

**Menu format:**
```
WORKFLOW HANDOFF — <skill> complete
==================================

**Agent (Cursor / Claude):** Present the `handoff-multiselect` block with AskQuestion (allow_multiple: true).

```handoff-multiselect
{ "type": "forge_handoff_multiselect", "options": [...], "default_option_ids": [...] }
```

**Text fallback** (prefix `/forge:` in Cursor/Claude, `$forge:` in Codex):

Reply "yes" or "1" for the default, or pick numbers:
  1. `/forge:<default>` — description (default)
  2. `/forge:<alt>` — description
  N. `(stop)` — exit the workflow here

State file: <path> — resume with `forge takeover` (or `/forge:takeover` / `$forge:takeover`).
```

Invocation prefix: **`/forge:`** when `FORGE_WORKFLOW_INVOCATION=slash`, repo has `.cursor/`, or `CURSOR_*` env is set; otherwise **`$forge:`** (Codex). Override with `FORGE_WORKFLOW_INVOCATION=slash|dollar`.

The canonical skill-chain mapping lives in `scripts/shared/skill_chain.py` as the `SKILL_CHAIN` dict, mapping current skill to `SkillTransition(default, alternatives)`. The renderer `build_skill_handoff_menu(current_skill, state)` in `scripts/shared/handoff_io.py` / `handoff_menu.py` produces the multiselect block and text fallback. Per-skill context-aware injection is supported — e.g., `forge:test` defaults to **`ship`** when the run is green and to **`diagnose`** when there are failures (`ship` stays as the top alternative in that case); when `forge:diagnose` finishes with `fix_complexity` **`large`**, the default next command is **`design`** (with **`plan`** as default when **`complex`**).

The `(stop)` option is always last. The state file persists, and workflows can resume with `forge takeover` at any time.

**Ship (finalize coding):** not a pipeline orchestrator — use **`$forge:ship`** / **`/forge:ship`** or the **`ship`** Cursor skill (`.cursor/skills/ship/SKILL.md`) for commit, push, PR, merge, and publish. Handoff menus after **implement**, **code-review**, and **test** list **`ship`** as an alternative.

## Session opt-in (step 1)

Orchestrator output for **step 1** of workflow skills includes a **SESSION OPT-IN** block: the agent should confirm whether the user wants structured Forge for the chat vs ad hoc help, **before** mirroring phase todos. Suppress the block in automation with **`FORGE_SKIP_SESSION_OPTIN=1`** (see README Advanced). Codex installs should run **`forge codex-agents`** so `developer_instructions` includes the same expectation.

## Declarative skill engine

Migrated workflow skills are driven by `skills/<skill>/manifest.yaml` and
`scripts/shared/skill_runner.py` (`run_skill`). Phase names for those skills live
in the manifest (not `skill_phases.py`). Kill-switch: `FORGE_SKILL_ENGINE=0` →
legacy `*_legacy` / `orchestrate_legacy` bodies. **Diagnose** gates remain
`kind: python` (register validators); there are no diagnose sidecar schemas in
this release. Guide: [`docs/declarative-skills.md`](docs/declarative-skills.md).

## Graphify in skill steps

**Graphify runs in the background:** session hooks, every `forge <skill> --step` (debounced), and `forge ship --step 1` spawn `forge graphify refresh` without blocking — continue work and read `GRAPH_REPORT.md` as-is. Ship prints the **GRAPHIFY** banner only. Suppress with **`FORGE_SKIP_GRAPHIFY=1`**. See `templates/graphify-contract.md` and `docs/graphify.md`.

**Claude Code:** `forge install --claude` or **`forge claude-graphify`** merges hooks into `~/.claude/settings.json` (SessionStart, PreToolUse for all tools — sub-agent lifecycle + Graphify on search/read tools, UserPromptSubmit for `forge:` prompts). Implementation: `forge_next/hooks/claude_graphify_hook.py`.

**Cursor:** `forge cursor-subagent-hooks` writes `.cursor/hooks.json` (`preToolUse` + `subagentStart`/`subagentStop`/`postToolUse` for Task). Suppress with `FORGE_SKIP_SUBAGENT_LIFECYCLE=1`. Implementation: `forge_next/hooks/cursor_subagent_hook.py`.

**Codex:** `forge install --codex` or **`forge codex-agents`** merges `developer_instructions` in `~/.codex/config.toml` with **Graphify rules first** (`forge_next/graphify_policy.py`). Use **`--force`** after upgrades if you previously customized that field.

**Docs:** [`docs/graphify.md`](docs/graphify.md) is the canonical user guide (refresh, hooks, orchestrator banners, CI flags, upgrade path).

**Structural quality (knip / madge / pyscn / skylos):** installed by default with `forge install` (warns if any tool missing); `forge structural-tools install` to refresh; skip with `forge install --skip-structural-tools` or `FORGE_SKIP_STRUCTURAL_TOOLS=1`. Shell helpers: `scripts/install/structural_tools.sh` and `.ps1`. Templates: `templates/structural-quality-probes.md`, `templates/structural-quality-eight-agents.md` (eight parallel Civil Learning subagents at dispatch); sidecars `.structural-probes.json`, `.structural-eight-agents.json`. See [`docs/structural-quality.md`](docs/structural-quality.md).

## Process-first skill choice (Superpowers-style)

When unsure which workflow to drive, prefer **investigation / diagnosis** before locking execution:

| Signal | Suggested direction |
|--------|---------------------|
| Intent fuzzy (problem, constraints, terminology) | **`sketch`** then **`design`** |
| Multiple approaches, unclear requirements, greenfield shape | **`design`** |
| Root cause unknown, incident, flaky failures | **`diagnose`** |
| Single approved direction or design handoff — need tasks and waves | **`plan`** |
| Regression in test suite | **`test`** then **`diagnose`** if cause unclear |

Skill-specific tables also live in `skills/design/SKILL.md`, `skills/diagnose/SKILL.md`, and `skills/plan/SKILL.md`.

## Sketch vs design

| Skill | Purpose | Writes |
|-------|---------|--------|
| **`sketch`** | Iterative conversational intent — synthesis checkpoints, loop-back on revised decisions | `sketch-decisions.md` in session memory; optional `CONTEXT.md` / ADRs with `--with-domain-docs` |
| **`design`** | Evidence, solution brainstorming, approved direction | `docs/forge/specs/YYYY-MM-DD-<slug>-design.md` when scope is medium/large |

Sketch does **not** investigate the codebase for solutions or author design specs. Design reads `sketch-decisions.md` when present.

## Forge Skill Delegation Contract

Invoking a Forge workflow skill is itself permission to dispatch the Forge agent team required by that workflow.

- `forge:sketch` is a lightweight 1:1 dialogue skill (no agent-team requirement); `forge:ux-review` is a 1:1 real-browser product UX audit (no agent-team requirement unless the user asks); `forge:design`, `forge:plan`, `forge:implement`, `forge:code-review`, `forge:test`, `forge:diagnose`, and `forge:takeover` imply automatic delegation to the relevant Forge agents (`forge:develop` is a deprecated alias for `forge:design`).
- `forge:evaluate` implies automatic delegation when team/review mode is active.
- The user should not have to separately say "use sub-agents", "delegate", or "parallelize" after invoking a Forge skill.
- If the active Codex session policy still blocks `spawn_agent`, surface that as an environment-policy limitation rather than silently falling back to single-agent execution.
- **Agent lifecycle is part of the delegation contract.** Every `spawn_agent` must be paired with a `close_agent` as soon as the agent reports its result or is no longer useful. Never carry an open agent across a wave, step, or phase boundary — Codex caps concurrent agents and leaked sessions block later dispatch. See `templates/codex-runtime.md` → *Parallel work* for the required spawn → wait → capture → close pattern.
- **Progress reporting is part of the delegation contract.** Sub-agents must not stay silent until completion. Follow `templates/subagent-progress.md`: write heartbeats under `.forge/state/subagent-progress/`; the parent Reads those files and relays short status while work is in flight (Cursor background Tasks do not stream interim chat).

## Versioning

Shipped artifacts use **semantic versioning** (`MAJOR.MINOR.PATCH`). **Bump versions in the same PR** whenever you change something users install or consume from packages—not after the fact.

Pick the digit by **magnitude of change**:

| Segment | When to bump |
|--------|----------------|
| **MAJOR** (`x.0.0`) | Breaking behavior: incompatible CLI contract, state/schema readers cannot load older files, removed subcommands, renamed default paths that break scripts or `forge install` layouts. |
| **MINOR** (`x.y.0`) | Backward-compatible capability: new `forge` subcommands or flags (old invocations still work), new slash commands / Codex skills / Claude wrappers, new workflow steps that extend—not replace—existing flows. |
| **PATCH** (`x.y.z`) | Fixes without new capabilities: bugfixes, regressions, prompt/template wording that does not change orchestration contracts, docs-only edits **when** nothing under packaged integrations or PyPI bundle behavior changed. |

**Always update these when you ship the corresponding change:**

- **`pyproject.toml`** → `project.version` (**forge-next** on PyPI).
- **`integrations/cursor-plugin/.cursor-plugin/plugin.json`** → `version` whenever `integrations/cursor-plugin/` changes in ways visible after `forge install --cursor` (commands, plugin metadata).

If several artifacts change together (CLI + Cursor plugin + Claude pack), align semver intent: a **minor** CLI feature usually pairs with a **minor** plugin bump when that feature surfaces in the plugin.

### PyPI

Whenever **`pyproject.toml`** `project.version` changes for a release users should consume via **`pipx install forge-next`** / **`pip install forge-next`**, **build and publish that version to PyPI** as part of the same release (do not leave main bumped ahead of PyPI).

From the repo root, after installing tooling once (`pip install build twine` or equivalent):

1. Remove stale artifacts: `rm -rf dist/`
2. `python -m build`
3. `python -m twine check dist/*`
4. Upload with credentials for the **forge-next** project, for example:
   - **API token (recommended):** set `TWINE_USERNAME=__token__` and `TWINE_PASSWORD` to your [PyPI API token](https://pypi.org/manage/account/token/), then `python -m twine upload dist/*`
   - Or configure `~/.pypirc` and run `python -m twine upload dist/*`

Use **`python -m twine`** so upload works when the `twine` executable is not on `PATH` (common on Windows).

The helper script **[`scripts/release/publish_pypi.sh`](scripts/release/publish_pypi.sh)** runs build + `twine check` + upload via **`python -m twine`**. Skip PyPI only when you intentionally did **not** bump `project.version` (e.g. docs-only or repo-only integration edits pulled exclusively from GitHub via `forge install --repo-url`).

## Documentation

When editing this repo's user-facing documentation, keep the role names aligned with the current agent set. Use `doc-writer`, not the legacy `tech-writer`.

## State Lifecycle

The skill orchestrators handle state-file lifecycle so workflows are interruptible and resumable:

- **Step 1 of any skill** refuses to silently overwrite an in-progress same-skill session. To intentionally restart, delete the state file or pass `--force` (where supported, e.g., `plan.py`). To continue, use `forge takeover` or invoke the skill with `forge <skill> --step N --state <path>`.
- **Step-1 auto-close** (pipeline skills: design, plan, implement, code-review, test, diagnose): starting a skill at step 1 automatically removes superseded JSON state when (1) `handoff-{skill}.md` exists, (2) the session is **upstream** in the pipeline relative to the skill being started, or (3) the session is **step-1-only** and idle longer than `FORGE_STEP1_ABANDON_HOURS` (default `1`). The new step-1 target path is never deleted. Suppress with `FORGE_SKIP_AUTO_CLOSE=1`. Look for `AUTO-CLOSED:` lines on stderr.
- **Canonical completion** remains the final orchestrator step (`forge <skill> --step N` at max step): sets `completed_at`, writes handoff via `write_handoff`, then `clear_state_file`.
- **Cross-skill conflicts** that survive auto-close still emit a stderr warning but do not block.
- **Session directories (primary):** New runs allocate `.forge/sessions/{id}/session.json` with optional `handoff.md` and `sidecars/`; `index.json` lists actives; `sessions/_archive/` holds completed or auto-closed sessions. See [`docs/sessions.md`](docs/sessions.md) and `scripts/shared/session_store.py`.
- **`forge takeover --cleanup`** removes stale session directories and legacy flat state files (including parallel `skill-*.json` variants). Defaults to dry-run; pass `--force` to delete. Pass `--all-stale --force` to clear every state file regardless of age. From a Forge source checkout without the launcher, `python3 scripts/takeover/takeover.py --cleanup` is equivalent.
- **`forge status`** and **`forge doctor`** surface leak hints (handoff present but JSON active, misplaced state paths, step-1 abandoned) and pending structural probe gates.
- **Plan files** are now created by `scripts/plan/plan.py` itself with section-marker placeholders; agents replace markers rather than create the file. The step-6 completion gate refuses to mark the workflow complete while any markers remain.
- **Evaluate findings** persist between phases via per-step sidecar files at `<state-dir>/.evaluate-findings-step<N>.json`. Each phase's prompt instructs the LLM to write findings there; the orchestrator ingests them on the next step.
- **Design spec gate:** when `spec_required` is true (medium/large scope from `memory/design-scope.json`; legacy `develop-scope.json` still read), step 6 completes `<state-dir>/.design-spec-gate.json` (legacy `.develop-spec-gate.json` still read); step 7 decomposes the spec into `<state-dir>/.design-spec-issues.json`; step 8 validates both before handoff. Optional strict bypass: `--allow-spec-incomplete` / `--allow-issues-incomplete` with matching override reason + follow-up on `forge design --step 8`.

### Test Skill — Flows Mode State

When `--mode flows` is used in `forge:test`, additional state keys are persisted to `state.custom`:
- `mode` (default `"run"`, set to `"flows"` when `--mode flows` is invoked)
- `flow_type` (default `None`, set by recommendation phase or `--flow-type` override)
- `flow_files` (list of created flow file paths, empty until scaffold phase)
- `flow_scope` (structured dict capturing journey, entry-point, roles, external services, and sample inputs from scope phase)
- `framework` (detected framework, e.g., "pytest"; overridable via `--framework`)
- `entry_point` (detected entry point: "ui" | "http" | "cli" | "module" | "none")
- `roles` (project-discovered role names, defaults to `["anonymous"]` if none found)
- `criteria_audit` (dict tracking qual-criteria pass/fail/partial status, populated at report phase)

All reads use `.get(key, default)` pattern for backward compatibility with legacy state files lacking these keys.

The recommendation sidecar persists at `<state-dir>/.test-recommendation-step2.json` (step-numbered, mirrors evaluate's findings sidecar convention). Schema: `{"chosen": "<type>", "reasoning": "...", "confidence": 0.0-1.0, "alternatives": [...]}`. Ingested at step 3; malformed sidecar aborts with `sys.exit(1)` and stderr message.

The scenario-index update at `<scenarios_dir>/README.md` is parser-gated; on parse failure, report step aborts and leaves file unchanged. Backup written to `<runtime>/memory/scenario-index.bak` before any rewrite (runtime default `.forge/`; legacy `.codex/forge*` still read during migration).

Real-browser product UX audits use **`forge ux-review`** (not `forge test --mode ux`, which exits with a redirect).

### Diagnose — Methodology sidecars and gates

**Graphify note:** Only `scripts/diagnose/hypothesis_register.py` was historically wired into `orchestrate.py` (community 93). `prompts/diagnose/technique_catalog.md` (community 153) linked to the report phase but not decompose/analyze — execution playbooks and validators close that gap.

**Playbooks:** `templates/diagnose-execution-playbooks.md` — operational when/phase/artifact rules for all 20 catalog techniques.

**Sidecars** (under the active diagnose session directory beside `session.json`: `.forge/sessions/<id>/`; canonical runtime `.forge/`, legacy `.codex/forge*` migrated then archived):

| File | Phase | Gate steps |
|------|-------|------------|
| `.diagnose-problem-spec.json` | 1 | 2 advisory, 4+ — `framing_entry` + `problem_statement` |
| `.diagnose-feedback-loop.json` | 2 (Reproduce & Observe) | 3 — loop or `cannot_build_loop` + override |
| `.diagnose-first-principles.json` | When activated | 4 if activated |
| `.diagnose-hypotheses.json` | When activated | 4 register, 5 elimination |
| `.diagnose-mece-tree.json` | When activated | 4 if activated |
| `.diagnose-five-whys.json` | 3 draft, 4 finalize | 5, 7 — **always** |
| `.diagnose-technique-coverage.json` | 1 draft → 7 final | 5/7 activated rows only |
| `.diagnose-barriers.json` | 2–7 | 7 when high-severity profile |

- **Adaptive spine:** Phase 1 picks **one** entry framing path; Phase 3–4 always runs **5 Whys**; MECE / hypothesis / first-principles only when listed in `activated_techniques`.
- **Hypothesis register (when activated):** ≥`hypothesis_min` (default 5) falsifiable hypotheses; ≥4 fishbone categories; Phase 4 eliminates all; ≥1 `confirmed` before step 5 when register is in play.
- **5 Whys:** Follow `templates/five-why-protocol.md` § Diagnose RCA — causal linkage between layers; stop checklist + `but_for`. Gates reject **symptom-level** proposed root causes (must explain *why*, not restate the failure).
- **Gates:** **DIAGNOSE ARTIFACT GATE** at step 3 (feedback loop), steps 5 and 7 (bundle/closure), step 4 optional register + quartet when activated. One retry per gate type; `require_confirmation` on failure.
- **Overrides:** `repro_loop_override_reason`, `hypothesis_override_reason`, `five_whys_override_reason`, `technique_coverage_override_reason`, `quartet_override_reason`, `problem_spec_override_reason`, `barriers_override_reason` — high-severity mandatory techniques cannot be skipped at step 7.
- **Resume:** `forge takeover` warns on missing sidecars when continuing diagnose at step ≥3; use `repro_loop_override_reason` only after user provides access/artifacts when no automated loop is possible.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- ALWAYS read graphify-out/GRAPH_REPORT.md before reading any source files, running grep/glob searches, or answering codebase questions. The graph is your primary map of the codebase.
- IF graphify-out/wiki/index.md EXISTS, navigate it instead of reading raw files
- For cross-module "how does X relate to Y" questions, prefer `graphify query "<question>"`, `graphify path "<A>" "<B>"`, or `graphify explain "<concept>"` over grep — these traverse the graph's EXTRACTED + INFERRED edges instead of scanning files
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
- **Corpus hygiene:** Graphify ignores **`.graphifyignore` only** (not `.gitignore`). Keep `.forge/`, `.codex/`, `.pyscn/`, `.skylos/`, `.serena/`, venvs, `graphify-out/`, build artifacts, and similar runtime/analyzer dumps out of the graph. Extend `.graphifyignore` when new dump dirs appear; after edits, purge `graphify-out/cache` and `graphify update . --force`.

## Forge Studio (internal)

Studio is **not** a user-facing workflow. Agents use it during **develop** / **plan** visual gates (localhost browser UI). Users only open a URL when opted in. See [`templates/studio.md`](templates/studio.md) and [`docs/studio.md`](docs/studio.md). Do not add Studio to README workflows or `commands.json`.
