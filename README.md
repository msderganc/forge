# Forge

Forge runs multi-step, resumable workflows for AI-assisted delivery: sketch fuzzy intent, investigate and design, plan, implement, review, test, audit UX, diagnose, and ship. A **takeover** mode chains those skills autonomously until the work is ship-ready.

The same install works in **Cursor**, **Claude Code**, and **OpenAI Codex**. Cursor and Claude use slash commands (`/forge:plan`); Codex uses `$forge:plan`-style skills. Most skills call the `forge` CLI under the hood — you don't need to type `forge …` yourself inside any of these apps. For terminals and CI, see [Advanced](#advanced-terminal-and-ci).

Install once with `pipx install forge-next`, then run `forge install`. This repository is the source tree for the prompts, templates, and orchestrators that package ships.

---

## Command notation

| Product | Form | Example |
|---------|------|---------|
| Cursor | `/forge:…` | `/forge:code-review` |
| Claude Code | `/forge:…` | `/forge:code-review` |
| Codex | `$forge:…` | `$forge:code-review` |
| Terminal / CI | `forge …` (space) | `forge code-review` |

On disk, Codex skill folders use hyphens (`forge-diagnose/`) because `:` isn't valid in paths, but each `SKILL.md` sets `name: forge:diagnose`, which Codex shows as `$forge:diagnose`. If a handoff prints a plain `forge: …` label, treat it as shorthand and use the slash or `$` form for your app.

---

## Overview

Forge skills share one process spine — Frame, Orient, Deepen, Decide, Act, Verify, Handoff — and a `--ceremony` flag (`light` to `comprehensive`) that scales how much of that spine runs. See [`docs/ceremony.md`](docs/ceremony.md).

A few things carry across every skill:

- **State lives in `.forge/`.** Runs are interruptible; resume with `forge takeover` (or the matching slash/`$forge:` command).
- **Sessions are isolated but shareable.** Multiple runs can be active at once under `.forge/sessions/{id}/`, coordinating through a shared `memory/project.md`. Details: [`docs/sessions.md`](docs/sessions.md).
- **Handoffs are a numbered menu**, not a hard fork. The last step of a skill prints a default next command plus alternatives; reply `yes`, a number, or `stop`.
- **Sub-agents report progress.** Dispatched agents write heartbeats so a parent chat isn't silent mid-task.
- **Every run leaves an audit trail** in `memory/<skill>-runs.jsonl` (last 30 entries).

Graphify, Beads, pstack, and structural-quality probes (knip, madge, jscn, pyscn, skylos) are optional add-ons that several skills touch — they're covered together in [Integrations](#integrations) rather than repeated here.

---

## Requirements

- Python 3.10+
- `pipx` recommended so `forge` lands on your PATH — see the [pipx docs](https://pipx.pypa.io/) (on Windows: `py -m pip install --user pipx`, then `pipx ensurepath`)
- A project that's a git repo or has a `README.md`, so the launcher can find the root

---

## Installation

**1. Install the launcher once per machine:**

```bash
pipx install forge-next
```

**2. Install app integrations:**

```bash
forge install
```

Or pick specific apps:

```bash
forge install --cursor
forge install --claude
forge install --codex
```

`--cursor` installs the Cursor plugin and bundles workflow skills into it directly. `--codex` installs skills under `~/.codex/skills/forge/`. `--claude` installs commands under `~/.claude/commands/forge/` and wires up Graphify hooks. Useful flags: `--ref`, `--repo-url`, `--cursor-dir`, `--claude-dir`, `--codex-dir`.

`forge install` also copies allowlisted pstack skills, sets up structural-quality probes, and prints Graphify onboarding hints — see [Integrations](#integrations) for what those do and how to skip them.

Running from Windows installs to Windows app locations; running from WSL installs to WSL locations.

**3. First run, inside the app (not a terminal):**

1. `/forge:doctor` (Cursor/Claude) or `$forge:doctor` (Codex) to check setup.
2. `/forge:plan` or `$forge:plan` to start.
3. Follow the printed steps and re-run the same command, or the next one the handoff suggests.

To upgrade later: `pipx upgrade forge-next`. To pin a version: `pipx install 'forge-next==1.12.0'`.

---

## Commands in your apps

All 14 workflows are defined in [`integrations/spec/commands.json`](integrations/spec/commands.json). In a terminal, invoke any of them as `forge <subcommand> …` (for example `forge design --step 1`); `forge develop` is a deprecated alias for `forge design`.

### Quick index

| Command | What it's for |
|---------|----------------|
| [Sketch](#sketch) | Pin down fuzzy intent before design, one question at a time |
| [Design](#design) | Investigate the problem and brainstorm/score solution directions |
| [Plan](#plan) | Turn an approved direction into waves, tasks, and docs |
| [Evaluate](#evaluate) | Critique a plan before implementing, or an implementation after |
| [Implement](#implement) | Execute the plan in waves with review loops |
| [Code review](#code-review) | Full-team PR/diff/architecture review |
| [Test](#test) | Run the test suite, or author mock flows |
| [UX review](#ux-review) | Real-browser audit of a running web app |
| [Diagnose](#diagnose) | Root-cause a bug, regression, or flaky failure |
| [Takeover](#takeover) | Drive skills autonomously until the work is ship-ready |
| [Status](#status) | Dashboard of active sessions and suggested next step |
| [Doctor](#doctor) | Check installation, PATH, and repo runtime health |
| [Ship](#ship) | Commit, push, PR, merge, publish |
| [Graphify](#graphify) | Refresh the codebase knowledge graph (see [Integrations](#integrations)) |

### Delivery pipeline

The default linear order — evaluate, diagnose, and ux-review can also run standalone:

| Step | Cursor / Claude | Codex |
|------|-----------------|-------|
| 0 (optional) | `/forge:sketch` | `$forge:sketch` |
| 1 | `/forge:design` | `$forge:design` |
| 2 | `/forge:plan` | `$forge:plan` |
| 3 (as needed) | `/forge:evaluate` | `$forge:evaluate` |
| 4 | `/forge:implement` | `$forge:implement` |
| 5 | `/forge:code-review` | `$forge:code-review` |
| 6 | `/forge:test` | `$forge:test` |

`forge takeover` drives evaluate pre/post as quality gates rather than a fixed pipeline step — follow the last handoff menu when in doubt. Ship isn't a pipeline step either; it's a finalize utility that handoffs after implement, code-review, and test commonly suggest. If intent is fuzzy, start at sketch.

**Plan discovery:** evaluate (`--plan`), implement, and code-review search markdown plans in the repo and native IDE plan folders (`.cursor/plans`, `.claude/plans`, `.codex/plans`, and their home-directory equivalents).

---

### Sketch

| | Cursor / Claude | Codex | Terminal |
|--|-----------------|-------|----------|
| Invoke | `/forge:sketch` | `$forge:sketch` | `forge sketch --step 1` |

Organizes intent when the problem, constraints, or terminology are still fuzzy, asking one question at a time with a suggested answer. It records decisions rather than investigating solutions — that's design's job.

**When to use:** before design, when requirements aren't settled yet. Optional `--with-domain-docs` also updates `CONTEXT.md` and light ADRs.

**Artifacts:** `memory/sketch-decisions.md` (Destination / Decisions so far / Not yet specified / Out of scope).

**Default handoff:** [design](#design). Protocol: `templates/sketch-protocol.md`.

---

### Design

| | Cursor / Claude | Codex | Terminal |
|--|-----------------|-------|----------|
| Invoke | `/forge:design` | `$forge:design` | `forge design --step 1` |

Back-and-forth discovery: surface opportunities, brainstorm requirements, and score solution directions before anyone plans tasks.

**When to use:** after sketch (if you ran it), or whenever you have a defined problem to investigate. Read-only on the codebase unless you explicitly allow edits.

**Artifacts:** session memory; `memory/design-scope.json`; for medium/large scope, a named spec at `docs/forge/specs/YYYY-MM-DD-<slug>-design.md` with gates at steps 6–8.

**Notable flags:** `--quick`; `--auto1`/`--auto2`/`--auto3` for autonomy; step-8 bypasses `--allow-spec-incomplete` / `--allow-issues-incomplete` (each needs an override reason and a follow-up).

**Default handoff:** [plan](#plan) (evaluate-pre is a common alternative). `forge develop` still works as a deprecated CLI alias, but there's no `/forge:develop` command.

**Methodologies:** evidence-first investigation, 5 Whys, systematic debugging, brainstorming gates, HMW framing, Pugh scoring, cross-review. Template: `templates/design-spec.md`.

---

### Plan

| | Cursor / Claude | Codex | Terminal |
|--|-----------------|-------|----------|
| Invoke | `/forge:plan` | `$forge:plan` | `forge plan --step 1` |

Turns an approved direction into a concrete implementation plan: waves, tasks, and documentation sections.

**Artifacts:** plan file under `memory/plans/`; `memory/planner.md`.

**Notable flags:** `--quick`; `--ceremony light|medium|detailed|comprehensive`; `--save-ceremony-preference`.

**Default handoff:** [evaluate](#evaluate) `--mode pre` (implement is a common alternative).

**Methodologies:** architecture overview, INVEST-shaped tasks, parallelization map, risk register, pre-mortem.

---

### Evaluate

| | Cursor / Claude | Codex | Terminal |
|--|-----------------|-------|----------|
| Invoke | `/forge:evaluate` | `$forge:evaluate` | `forge evaluate --step 1 --mode pre` |

Structured critique — `--mode pre` before implementation, `--mode post` after. For a full-team review, use [code-review](#code-review) instead (`--mode review` is deprecated).

**Artifacts:** `.evaluate-state.json` and per-step findings sidecars.

**Default handoff:** pre → implement; post → code-review.

**Methodologies:** feasibility ratings, completeness audit, correctness/quality/performance/operational-readiness lenses, optional team dispatch.

---

### Implement

| | Cursor / Claude | Codex | Terminal |
|--|-----------------|-------|----------|
| Invoke | `/forge:implement` | `$forge:implement` | `forge implement --step 1` |

Executes the plan in waves, with a review loop after each task.

**Artifacts:** `handoff-implement.md`; documentation gate at step 8.

**Default handoff:** [code-review](#code-review).

**Methodologies:** branch setup, wave dispatch, per-task review loop (`templates/review-loop.md`), integration check, documentation gate.

---

### Code review

| | Cursor / Claude | Codex | Terminal |
|--|-----------------|-------|----------|
| Invoke | `/forge:code-review` | `$forge:code-review` | `forge code-review --step 1` |

Structured PR/diff/architecture review with two passes: Pass A checks the change against intent and requirements, Pass B checks engineering quality against `templates/standards-review-baseline.md`. Findings from each pass are reported separately.

**Artifacts:** `memory/code-review-report.md`.

**Notable flags:** `--effort light|standard|thorough` (or `--quick` for light). Light is Architect + QA; standard adds Security when auth/data is in play; thorough is the full six-role team. Structural probes run by default and can hold steps 4–6 — `--no-structural` turns them off, `--allow-structural-probes-incomplete` bypasses a pending gate. See [Integrations](#integrations).

**Default handoff:** [test](#test) (ship is a common alternative).

---

### Test

| | Cursor / Claude | Codex | Terminal |
|--|-----------------|-------|----------|
| Invoke | `/forge:test` | `$forge:test` | `forge test --step 1` |

Runs the test suite (default `run` mode), or authors mock flows with `--mode flows`.

**Artifacts:** `memory/test-report.md`; flows mode also updates the scenario index when it parses cleanly.

**Default handoff:** ship when green, [diagnose](#diagnose) on failures.

**Methodologies:** discovery, execution, failure analysis, coverage gaps; flows mode adds eight quality criteria plus pytest reliability checks.

For a real-browser product audit, use [ux-review](#ux-review) — `forge test --mode ux` just redirects there.

---

### UX review

| | Cursor / Claude | Codex | Terminal |
|--|-----------------|-------|----------|
| Invoke | `/forge:ux-review` | `$forge:ux-review` | `forge ux-review --step 1` |

Real-browser audit of a running web app. It maps purpose, users, IA, and journeys; walks reachable pages and controls (including empty/loading/error/success states across viewports); then writes a prioritized findings report.

**When to use:** usability audits of a live app — not a replacement for [test](#test) suite runs or mock-flow authoring.

**Artifacts:** `memory/ux-review-report.md` plus session sidecars for orientation, plan, coverage, and findings.

**Notable flags:** `--base-url`; `--quick`.

**Default handoff:** ship, or diagnose when blocker/high findings remain.

**Methodologies:** [`templates/ux-review-criteria.md`](templates/ux-review-criteria.md); full detail in [`skills/ux-review/SKILL.md`](skills/ux-review/SKILL.md).

---

### Diagnose

| | Cursor / Claude | Codex | Terminal |
|--|-----------------|-------|----------|
| Invoke | `/forge:diagnose` | `$forge:diagnose` | `forge diagnose --step 1` |

Evidence-led root-cause analysis with gated JSON sidecars, for incidents, regressions, and flaky failures.

**Default handoff:** design when the fix is classified `large`, plan when `complex`.

**Methodologies:** playbooks in `templates/diagnose-execution-playbooks.md`, 5 Whys, hypothesis register, technique coverage. Full detail: [`skills/diagnose/SKILL.md`](skills/diagnose/SKILL.md).

---

### Takeover

| | Cursor / Claude | Codex | Terminal |
|--|-----------------|-------|----------|
| Invoke | `/forge:takeover` | `$forge:takeover` | `forge takeover` |

Infers what's in flight from sessions, handoffs, design specs, and an optional `--issue`, then drives child skills (plan → evaluate pre → implement → evaluate post → code-review → test) until the work is ship-ready.

**When to use:** after an interruption, to run an epic autonomously, or to skip manually picking each skill.

**CLI:** `--design <path>`, `--issue <n|url>`, `--goal <text>`; `--cleanup` / `--cleanup --force` to remove stale state.

Full detail: [`skills/takeover/SKILL.md`](skills/takeover/SKILL.md).

---

### Status

| | Cursor / Claude | Codex | Terminal |
|--|-----------------|-------|----------|
| Invoke | `/forge:status` | `$forge:status` | `forge status` |

Read-only dashboard of handoffs, active sessions, and the suggested next workflow. Detail: [`skills/status/SKILL.md`](skills/status/SKILL.md).

---

### Doctor

| | Cursor / Claude | Codex | Terminal |
|--|-----------------|-------|----------|
| Invoke | `/forge:doctor` | `$forge:doctor` | `forge doctor` |

Checks installation, PATH, encoding, the `.forge/` runtime root, and common misconfiguration. Run it right after installing, or first thing in a new repo.

---

### Ship

| | Cursor / Claude | Codex | Terminal |
|--|-----------------|-------|----------|
| Invoke | `/forge:ship` | `$forge:ship` | `forge ship --step 1` |

Finalizes coding work: preflight, commit, push, PR, merge, publish. Not a pipeline step — you reach for it after implement, code-review, or test when you're ready to land changes.

`forge ship --step 1` runs the Graphify preflight first (see [Integrations](#integrations)), then the agent follows [`.cursor/skills/ship/SKILL.md`](.cursor/skills/ship/SKILL.md) for the actual commit/PR/merge/publish work. Running step 1 alone doesn't commit anything by itself.

---

### Graphify

| | Cursor / Claude | Codex | Terminal |
|--|-----------------|-------|----------|
| Invoke | `/forge:graphify` | `$forge:graphify` | `forge graphify refresh` |

Refreshes the optional codebase knowledge graph, or installs/uninstalls the post-commit hook. See [Integrations](#integrations) for what the graph is used for.

CLI-only helpers not exposed as slash commands: `forge session close`, `forge structural-tools`, `forge structural-probes`, `forge codex-agents`, `forge claude-graphify`, `forge cursor-subagent-hooks`.

---

## Integrations

Optional add-ons. Core workflows work without them; when they're missing, Forge falls back to memory files and sequential IDs.

### Graphify — codebase knowledge graph

Graphify indexes the repo into `graphify-out/` (god nodes, communities) so agents can orient before grepping. Install the Graphify CLI (or set `FORGE_GRAPHIFY_COMMAND`), then `forge graphify refresh`. `forge graphify install-hook` refreshes after each commit.

- `forge ship --step 1` refreshes and prints the **GRAPHIFY** banner.
- Other workflow steps may start a debounced background refresh when `graphify-out/` already exists — non-blocking.
- Claude: hooks via `forge claude-graphify`. Codex: `developer_instructions` via `forge codex-agents`. Re-run after `pipx upgrade forge-next`.
- Add a repo-root `.graphifyignore` for `.forge/`, `.codex/`, `.venv/`, build output, and other dumps — Graphify ignores `.gitignore`.

Full guide: [`docs/graphify.md`](docs/graphify.md).

### pstack — optional agent skills (poteto)

[pstack](https://github.com/cursor/plugins/tree/main/pstack/skills) is a Cursor
marketplace plugin. `forge install` downloads the allowlisted skills from
[cursor/plugins](https://github.com/cursor/plugins) **by default** (not the marketplace).
Forge does not vendor these skills into the forge-next source tree. Skip with `--skip-pstack` or
`FORGE_SKIP_PSTACK=1`. When the skills are present, workflow skills may
optionally reach for pstack companions (see [`docs/pstack.md`](docs/pstack.md));
if they are missing, Forge continues unchanged. pstack is not a `/forge:` command.

### Beads — issue tracking

[Beads](https://github.com/steveyegge/beads) (`bd` CLI) can sync epics, findings, tasks, and dependencies with Forge memory and handoffs. Without it, prompts use memory files and sequential IDs. Design records `beads_available` on startup; nothing hard-requires Beads.

`forge install` and `forge doctor` surface whether `bd` is on PATH (they do not install Beads). Guide: `templates/beads-integration.md`.

### Structural probes — knip, madge, jscn, pyscn, skylos

`forge install` sets these up for code-review and evaluate (warns if install fails). Skip with `forge install --skip-structural-tools` or `FORGE_SKIP_STRUCTURAL_TOOLS=1`.

| Stack | Tools | What they catch |
|-------|-------|-----------------|
| Node / TS | knip, madge, jscn | Dead code, cycles, structural smells |
| Python | pyscn, skylos | Complexity hot spots, structural smells |

In code-review they're on by default and can hold steps 4–6. Use `--no-structural` to disable, or `--allow-structural-probes-incomplete` to bypass a pending gate with a reason.

Guide: [`docs/structural-quality.md`](docs/structural-quality.md).

---

## Uninstallation

**Integrations** (Cursor / Claude / Codex):

```bash
forge uninstall
```

(or `--cursor`, `--claude`, `--codex`)

**Launcher:**

```bash
pipx uninstall forge-next
```

**Project state** (optional): `forge takeover --cleanup`, or delete `.forge/` in that repo.

---

## How skills work

1. Pick a command — `/forge:…`, `$forge:…`, or `forge …` in a terminal. In Cursor and Claude, that command must run `forge <skill> --step 1` first, before any manual investigation.
2. Each run advances one step at a time; output is the prompt (and sometimes todos) for that step, plus where state landed.
3. Prompts reference roles — architect, planner, implementer, critic, QA, security, doc-writer. Hosts with sub-agents follow the dispatch pattern in `templates/subagent-progress.md` and close agents once their slice of work is done.
4. The last step prints a handoff menu; your next command matches whatever it recommends.
5. Where supported, `--quick` shortens the run.

---

## Sessions and handoffs

New runs live under `.forge/sessions/{id}/`: a `session.json`, an optional `handoff.md`, and a `sidecars/` folder for step artifacts. `index.json` tracks active sessions; finished or auto-closed ones move to `sessions/_archive/`. Sessions stay isolated but can collaborate through a shared `memory/project.md`. Full detail: [`docs/sessions.md`](docs/sessions.md).

A few things worth knowing:

- Every skill appends a short record to `memory/<skill>-runs.jsonl` on each run (last ~30 kept).
- `state/resume-context.json` and `memory/forge-memory-synthesis.md` refresh on every save, so `forge status` and new chats can pick up context quickly.
- Handoffs are consumed when the next skill starts (plan reads design's handoff, code-review reads implement's, and so on).
- `forge session close <id>` archives a session and rewrites the pointer at `handoff-{skill}.md` so it keeps resolving.
- `forge takeover --cleanup` removes stale sessions and legacy flat state files (dry-run unless you pass `--force`). Env: `FORGE_SESSION_MAX_AGE_DAYS` (default 7), `FORGE_SKIP_SESSION_CLEANUP=1`.
- Older flat-JSON state under `.codex/forge*/state/` or `.forge/state/` still works — step 1 of any skill migrates and archives it automatically.

---

## OpenAI Codex

After `forge install --codex`, skills live under `~/.codex/skills/forge/<folder>/SKILL.md` (folder names are hyphenated because `:` isn't valid in a path, but `name: forge:<subcommand>` is what Codex actually shows you). Invoke with `$forge:…`, `/use <skill>`, `/skills`, or implicit matching on the skill description.

Most skills run `forge …` under the hood via `<invoke cmd="…"/>`; `$forge:ship` instead follows the agent procedure in [`.cursor/skills/ship/SKILL.md`](.cursor/skills/ship/SKILL.md).

`forge install --codex` also merges Graphify-first delegation rules into `~/.codex/config.toml`'s `developer_instructions` (source: `forge_next/graphify_policy.py`), so Codex reads `GRAPH_REPORT.md` before broad search and allows `spawn_agent`/`close_agent` without extra prompting. If you've customized `developer_instructions` yourself, run `forge codex-agents --force` after upgrading `forge-next`, then restart Codex.

---

## Claude Code

After `forge install --claude`:

- **Slash commands** live under `~/.claude/commands/forge/` (`/forge:plan`, …).
- **Skills** install flat under `~/.claude/skills/` — `using-forge` (meta router) plus `forge-plan`, `forge-implement`, and the other workflow skills. Claude matches these on the skill `description` field (same mechanism as Superpowers), so asking to “plan” should route to Forge instead of freestyle or competing process skills.
- **Graphify hooks** merge into `~/.claude/settings.json` via `forge claude-graphify` (session-start reminder, pre-tool-use context on search-like tools, prompt-submit check for `forge:` mentions).

Re-run `forge install --claude` (and `forge claude-graphify` after upgrading `forge-next`), then restart Claude Code so skills are picked up.

---

## Cursor

After `forge install --cursor`, the plugin under `~/.cursor/plugins/local/forge/` bundles both slash commands and the workflow skill packs, so Agents can discover them without `~/.codex/skills`. `forge cursor-subagent-hooks` sets up Task lifecycle and progress reminders (suppress with `FORGE_SKIP_SUBAGENT_LIFECYCLE=1`). The ship skill also lives in this source tree at [`.cursor/skills/ship/SKILL.md`](.cursor/skills/ship/SKILL.md).

---

## This repository vs PyPI

- `forge-next` on PyPI installs the terminal `forge` binary and bundled orchestrators.
- This repo is the source for `prompts/`, `templates/`, `agents/`, `scripts/`, and `integrations/` (everything `commands.json` installs).
- `skills/` holds most agent-facing `SKILL.md` files — ship, doctor, and graphify live under `integrations/`/Codex skill packs instead. Edit `prompts/` and `templates/` at repo root; `forge_next/assets/` mirrors them at release time.

### Highlights since 1.0

| Version | What users got |
|---------|----------------|
| **1.0** | `forge takeover` replaces resume/iterate; ship-ready gate drive |
| **1.1** | Repo-local `.forge/` runtime; structural probe gates |
| **1.2** | jscn Node/TS structural probe |
| **1.3** | Design spec→issues gate (steps 6–8); sketch wayfinder sections; code-review two-axis Pass A/B |
| **1.4** | Parallel sessions, `--session`, `forge session close`, resume-context v2 |
| **1.6** | ux-review workflow; Cursor install bundles agent skills; UX audits are ux-review-only |
| **1.7** | Subagent progress heartbeats |
| **1.8** | Structural build charter earlier in plan/implement; probe complexity remediation for code-review Pass B |
| **1.9.x** | Context-aware handoffs; code-review `--effort` and structural flags; session archive pointers; Windows PATH/doctor prefer pipx `forge` |
| **1.10** | Minimal-scope bias; `develop` renamed to `design` (compat shims); size-adaptive ceremony seeds |
| **1.10.1** | Bundled skill templates beside each installed skill |
| **1.11** | Declarative skill engine: YAML manifests + shared `skill_runner`; schema/python gates; `FORGE_SKILL_ENGINE=0` kill-switch |
| **1.12** | Shared process spine with binding ceremony bands; dual-axis mode × ceremony; handoff AskQuestion only when the host tool exists |
| **1.12.1** | Expose `--ceremony` on the `forge` CLI and ask plan for light/medium/detailed/comprehensive (not legacy normal/lite) |
| **1.12.2** | Plan CLI `--ceremony` skips re-prompt and syncs `plan_mode`; e2e asserts outer CLI ceremony flags |
| **1.12.3** | Add `scripts/e2e_cli_skill_matrix.py` — 3+ forge-CLI scenarios per skill (ceremony/mode/reject) |
| **1.14.0** | Claude Code: `using-forge` meta-skill + `forge-*` skills under `~/.claude/skills/` for auto-routing (plan/implement/…) |
| **1.13.2** | Harden Beads install probe (UTF-8 decode; multi-token `FORGE_BD_COMMAND` display) |
| **1.13.1** | Install/doctor UX: emoji sections, structural-tool ✓/✗ marks, surface Beads (`bd`) availability |
| **1.13.0** | Plan is ceremony-only: removed `--mode default\|lite` and `--save-mode-preference`; use `--ceremony` / `--save-ceremony-preference` |

*(There was no 1.5 release — numbering jumped 1.4 to 1.6.)*

PyPI: [pypi.org/project/forge-next](https://pypi.org/project/forge-next/)

Source: [github.com/msderganc/forge](https://github.com/msderganc/forge)

---

## Advanced: terminal and CI

Outside the apps, call `forge <subcommand>` with a space — same engine as any slash command. `forge --help` lists all flags.

**Common environment variables:**

| Variable | Effect |
|----------|--------|
| `FORGE_SKIP_SESSION_OPTIN=1` | Suppress the step-1 session opt-in banner |
| `FORGE_SKIP_GRAPHIFY=1` | Disable the ship GRAPHIFY banner and background refresh |
| `FORGE_SKIP_GRAPHIFY_REFRESH=1` | Suppress background refresh only (keep the ship banner) |
| `FORGE_SKIP_AUTO_CLOSE=1` | Disable step-1 auto-close of superseded sessions |
| `FORGE_SKIP_SUBAGENT_LIFECYCLE=1` | Disable Cursor subagent lifecycle/progress reminders |
| `FORGE_SKIP_STRUCTURAL_TOOLS=1` | Skip structural probe install and runs |
| `FORGE_SKIP_PSTACK=1` | Skip copying allowlisted pstack skills during `forge install` |
| `FORGE_SKILL_ENGINE=0` | Force legacy per-skill orchestrator bodies |

Full list: [`docs/environment.md`](docs/environment.md). Declarative manifests: [`docs/declarative-skills.md`](docs/declarative-skills.md). Ceremony: [`docs/ceremony.md`](docs/ceremony.md).

---

## Contributing

Orchestration lives in `scripts/shared/` (`skill_runner.py`, `orchestrator.py`, `skill_chain.py`, `session_store.py`, `ceremony.py`) and `scripts/takeover/`. Migrated skills declare phases in `skills/<skill>/manifest.yaml`; the shared spine is [`templates/skill-process-spine.md`](templates/skill-process-spine.md). Keep [AGENTS.md](AGENTS.md), [`docs/README.md`](docs/README.md), and `skills/` aligned with actual behavior.

**Versions:** bump semver in [`pyproject.toml`](pyproject.toml) (and the Cursor plugin's [`plugin.json`](integrations/cursor-plugin/.cursor-plugin/plugin.json) when that bundle changes) for anything that touches the PyPI package or editor integrations — patch for narrow fixes, minor for additive behavior, major for breaking contracts. See [Versioning](AGENTS.md#versioning) in AGENTS.md.

**PyPI:** if you bump `project.version`, build and upload the same release (`python -m build`, `python -m twine check dist/*`, `python -m twine upload dist/*`, or `scripts/release/publish_pypi.sh`) so `pipx upgrade forge-next` picks it up.

**Integration bundles:** after changing `integrations/cursor-plugin/`, `integrations/claude/commands/`, or `integrations/codex/skills/`, run `pytest tests/test_integration_install_layout.py` to check the layout against [`integrations/spec/commands.json`](integrations/spec/commands.json).

**Tests:**

```bash
python -m pytest
python scripts/smoke.py
```
