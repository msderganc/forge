# Forge

Forge runs **multi-step, resumable workflows** for AI-assisted delivery: sketch (fuzzy intent), design/investigation, planning, plan and implementation review, implementation, code review, testing (including mock-flow authoring), real-browser UX audit, diagnostics, autonomous **takeover** through ship-ready gates, and **ship** to finalize commit/PR/publish.

The same install targets **Cursor**, **Claude Code**, and **OpenAI Codex**. Cursor and Claude Code use slash commands (for example `/forge:plan` and `/forge:doctor`). **Codex** uses `$forge:…` skills (for example `$forge:plan`, `$forge:diagnose`) installed under `~/.codex/skills/forge/` — the same workflows as [`integrations/spec/commands.json`](integrations/spec/commands.json). Most skills call the `forge` CLI via `<invoke cmd="…"/>`; **`$forge:ship`** is agent-driven (follows [`.cursor/skills/ship/SKILL.md`](.cursor/skills/ship/SKILL.md), with optional `forge ship --step 1` for Graphify preflight). In Codex chat you invoke workflows with `$forge:…`, not by typing `forge …` yourself. On disk, skill folders use hyphenated names (e.g. `forge-diagnose/`) because `:` is not allowed in paths; each `SKILL.md` sets `name: forge:…`, which Codex shows as `$forge:…`. For shells and CI without Codex, see [Advanced: terminal and CI](#advanced-terminal-and-ci).

Install once with `pipx install forge-next`, then run `forge install` to add the Cursor plugin, Claude command pack, and Codex skill pack. Use `--cursor`, `--claude`, or `--codex` if you only want one or two. Most of the time you stay in the app; use the terminal for `forge doctor`, CI hooks, or cleanup when that is easier.

This repository is the **source tree** for prompts, templates, agent briefs, and orchestrators bundled with that package.

---

## Command notation 

| Product | Form | Example |
|---------|------|---------|
| Cursor | `/forge:…` | `/forge:code-review` |
| Claude Code | `/forge:…` | `/forge:code-review` |
| Codex | `$forge:…` (mention / skill picker) | `$forge:code-review` |

**Terminal / CI** uses a space, not a colon: `forge plan`, `forge diagnose` (see [Advanced](#advanced-terminal-and-ci)).

**Note:** In Cursor or Claude, type `/forge:` then the subcommand (for example `/forge:diagnose`). In Codex, type `$forge:` or pick the skill — user-facing IDs match `$forge:<subcommand>` (same spelling as `/forge:<subcommand>`, with `$` instead of `/`).

**Slash command files:** Cursor and Claude command packs use `<subcommand>.md` under their install trees (plugin namespace `forge`), so the picker shows `/forge:<subcommand>`. Shorter aliases such as `/f:diagnose` or bare `/diagnose` are not provided — see [`integrations/README.md`](integrations/README.md).

---

## Overview

- **App-first:** Cursor and Claude Code use `/forge:…`; Codex uses `$forge:…`. See [OpenAI Codex](#openai-codex).
- **Session-safe:** Repo state lives under **`.forge/`**. Older `.codex/forge/` and `.codex/forge-codex/` trees are copied into `.forge/` on the next workflow step 1, then archived under `.forge/_archive/` (set `FORGE_KEEP_LEGACY_RUNTIME=1` to leave them in place). Stop anytime; continue with `forge takeover`, `/forge:takeover` (Cursor/Claude), or `$forge:takeover` (Codex). Each skill save also updates **`state/resume-context.json`** (schema v2: `sessions[]` + `focus`) and **`memory/forge-memory-synthesis.md`** (rollup of `project.md`, `current-step.md`, and recent handoffs). Takeover infers the next skill from sessions, handoffs, and specs.
- **Parallel sessions:** Multiple active runs can coexist under `.forge/sessions/{id}/` with isolated state/sidecars and shared collaboration via `memory/project.md` section merges. When several sessions exist for one skill, steps 2+ need `--session <id>` (or `--state`). Archive with `forge session close <id>`. Details: [`docs/sessions.md`](docs/sessions.md).
- **Handoffs:** On the last step, the orchestrator emits a **`handoff-multiselect`** block (for Cursor/Claude **AskQuestion** with `allow_multiple: true`) plus a text fallback. Labels use `/forge:…` (Cursor/Claude) or `$forge:…` (Codex). Reply `yes`, `1`, or pick options; see [AGENTS.md](AGENTS.md). Downstream step-1 intake consumes handoffs (read + close).
- **Subagent progress:** Dispatched agents write heartbeats under `.forge/state/subagent-progress/` (`templates/subagent-progress.md`); the parent relays short status while work is in flight — do not stay silent until final completion. Cursor hooks remind while agents are running (`forge cursor-subagent-hooks`).
- **Per-skill run memory:** Every workflow run appends an auditable entry to `memory/<skill>-runs.jsonl` (for example `plan-runs.jsonl`), retaining the most recent 30 entries with timestamp, phase/step, short summary, session linkage, and handoff linkage when present.
- **Integrations:** `forge install` and `forge uninstall` lay down Cursor, Claude, and Codex wrappers. Install output includes optional **Graphify** setup (CLI or `FORGE_GRAPHIFY_COMMAND`, `forge graphify refresh`, `install-hook` / `uninstall-hook`) for codebase context during **takeover** — see [`docs/graphify.md`](docs/graphify.md).
- **Memory rollup:** each time skill state is saved, Forge refreshes **`memory/forge-memory-synthesis.md`** as an explicit merge of `project.md`, `current-step.md`, and recent handoffs so resume and new chats can open one synthesized narrative (see `templates/memory-protocol.md`).

---

## Optional: Beads (issue tracking)

Workflows can hook **[Beads](https://github.com/steveyegge/beads)** (`bd` CLI) so epics, findings, tasks, and dependencies stay in sync with Forge memory and handoffs. It is **optional**: if Beads is not available, prompts fall back to memory files and sequential IDs (see `templates/beads-integration.md`).

- **Canonical guide:** `templates/beads-integration.md` (epic layout, `bd` examples, degraded mode).
- **Cross-references:** `templates/memory-protocol.md`, `templates/handoff-protocol.md` (Beads section in status handoffs).
- **Runtime:** design startup checks Beads (`prompts/develop/startup.md` — legacy prompt path). Skill state includes a `beads_available` flag in `scripts/shared/skill_state.py`, but whether Beads is used is driven by prompts and `project.md` (“beads: available/unavailable”), not by automatic detection in the orchestrator.

---

## Requirements

- Python **3.10+** (required by `forge-next`)
- **pipx** recommended so `forge` is on your PATH — [pipx documentation](https://pipx.pypa.io/) (Windows: `py -m pip install --user pipx` then `pipx ensurepath` if needed)
- A **project** that is a git repo or contains `README.md` (the launcher uses that to find the target root)

---

## Installation

### 1. Install the launcher (once per machine)

```bash
pipx install forge-next
```

### 2. Install app integrations

```bash
forge install
```

`forge install` also installs structural probes for code-review / evaluate (**knip**, **madge**, **jscn**, **pyscn**, **skylos**) and prints warnings for any that could not be installed. To skip: `forge install --skip-structural-tools`. See [`docs/structural-quality.md`](docs/structural-quality.md).

Or only what you use:

```bash
forge install --cursor
forge install --claude
forge install --codex
```

**`forge install --cursor`** installs the Cursor plugin (slash commands) and **bundles workflow agent skills** into the plugin `skills/` tree (from `integrations/codex/skills/`) so Cursor Agents can discover Forge skills without relying on `~/.codex/skills`. **`--codex`** installs skills under `~/.codex/skills/forge/`. **`--claude`** installs slash commands under `~/.claude/commands/forge/` and merges Graphify hooks.

Options (defaults are usually fine): `--ref`, `--repo-url`, `--cursor-dir`, `--claude-dir`, `--codex-dir`.

**After `forge install`:** the installer prints optional **Graphify** setup (install the Graphify CLI or set `FORGE_GRAPHIFY_COMMAND`, run `forge graphify refresh`, optionally `forge graphify install-hook` for post-commit refresh). Same hints appear in JSON output as `graphify_onboarding` when you pass `--json`. Details: [`docs/graphify.md`](docs/graphify.md).

**Note:** Running from Windows will install in the Windows Cursor/Claude/Codex locations, while WSL will use the WSL locations.

### 3. First run in the app (not in a terminal)

1. Check setup: `/forge:doctor` (Cursor/Claude), or `$forge:doctor` (Codex).
2. Start planning: `/forge:plan` (Cursor/Claude), or `$forge:plan` (Codex).
3. Follow the printed steps. Re-run the same slash command (Cursor/Claude), or the next `$forge:…` (Codex). If the transcript shows `forge: …`, treat it as a label and use the matching `/forge:…` or `$forge:…` as appropriate.

Work in another folder than the editor root only when your integration documents it (some flows pass a repo path through the launcher).

After a new `forge-next` release on PyPI, upgrade with `pipx upgrade forge-next` (or reinstall with `pipx install forge-next --force`). Pin a specific version when reproducibility matters, for example `pipx install 'forge-next==1.7.0'` (match `project.version` in `pyproject.toml`).

---

## Commands in your apps

All **14** workflows are defined in [`integrations/spec/commands.json`](integrations/spec/commands.json). Each command below uses the same layout: **invoke table**, purpose, when to use, artifacts, and methodologies.

**Terminal:** `forge <subcommand> …` (for example `forge design --step 1`, `forge graphify refresh`). **`forge develop`** is a **deprecated alias** for **`forge design`** (stderr warning).

**Sessions:** New runs allocate `.forge/sessions/{id}/`. Steps 2+ accept **`--session <id>`** (or `--state`) when multiple active sessions exist; archive with **`forge session close <id>`** — see [`docs/sessions.md`](docs/sessions.md).

**Codex:** `forge install --codex` installs skills under `~/.codex/skills/forge/` — see [`integrations/codex/README.md`](integrations/codex/README.md).

### Quick index

| Command | Anchor |
|---------|--------|
| sketch | [Sketch](#sketch) |
| design | [Design](#design) |
| plan | [Plan](#plan) |
| evaluate | [Evaluate](#evaluate) |
| implement | [Implement](#implement) |
| code-review | [Code review](#code-review) |
| test | [Test](#test) |
| ux-review | [UX review](#ux-review) |
| diagnose | [Diagnose](#diagnose) |
| takeover | [Takeover](#takeover) |
| status | [Status](#status) |
| doctor | [Doctor](#doctor) |
| ship | [Ship](#ship) |
| graphify | [Graphify](#graphify) |

### Delivery pipeline

Default linear order (evaluate, diagnose, and ux-review also run standalone):

| Step | Cursor / Claude | Codex |
|------|-----------------|-------|
| 0 (optional) | `/forge:sketch` | `$forge:sketch` |
| 1 | `/forge:design` | `$forge:design` |
| 2 | `/forge:plan` | `$forge:plan` |
| 3 (as needed) | `/forge:evaluate` | `$forge:evaluate` |
| 4 | `/forge:implement` | `$forge:implement` |
| 5 | `/forge:code-review` | `$forge:code-review` |
| 6 | `/forge:test` | `$forge:test` |

Handoff menus may recommend **evaluate** as a quality gate. **`forge takeover`** drives evaluate pre/post as ship-ready gates (not as a linear pipeline successor) — follow the last handoff menu when in doubt. **Ship** is a finalize utility (not a pipeline step); handoff menus after implement, code-review, and test often list it. For real-browser product UX audits, use [ux-review](#ux-review) (not a pipeline step).

When intent is fuzzy, run [sketch](#sketch) before [design](#design).

**Plan discovery:** For **evaluate** (`--plan`), **implement**, and **code-review**, Forge searches markdown plans in the repo and native IDE plan folders (`.cursor/plans`, `.claude/plans`, `.codex/plans`, and `~/.cursor/plans`, …).

---

### Sketch

| | Cursor / Claude | Codex | Terminal |
|--|-----------------|-------|----------|
| Invoke | `/forge:sketch` | `$forge:sketch` | `forge sketch --step 1` |

**What it does:** Organizes intent when the problem, constraints, or terminology are still fuzzy — one question at a time with a recommended answer. Plan, don't do: sketch records decisions; design owns investigation and specs.

**When to use:** Before design when requirements are unclear. Optional **`--with-domain-docs`** updates `CONTEXT.md` and sparse `docs/adr/`.

**Artifacts:** `memory/sketch-decisions.md` under `.forge/memory/` with wayfinder-inspired sections: **Destination**, **Decisions so far**, **Not yet specified** (fog), and **Out of scope**.

**Default handoff:** [design](#design). Protocol: `templates/sketch-protocol.md`.

---

### Design

| | Cursor / Claude | Codex | Terminal |
|--|-----------------|-------|----------|
| Invoke | `/forge:design` | `$forge:design` | `forge design --step 1` |

**What it does:** Back-and-forth discovery — surface opportunities, brainstorm requirements, explore and score solution directions before planning.

**When to use:** After sketch (if needed) or when you have a defined feature/problem. Read-only on the codebase unless the user explicitly allows edits.

**Artifacts:** Session memory under `.forge/memory/`; **`memory/design-scope.json`** (legacy `develop-scope.json` still read); for **medium/large** scope, named spec **`docs/forge/specs/YYYY-MM-DD-<slug>-design.md`**, gate **`.design-spec-gate.json`** on step 6 (legacy `.develop-spec-gate.json` still read), **`.design-spec-issues.json`** on step 7, handoff on step 8.

**Notable flags:** `--quick`; `--auto1` / `--auto2` / `--auto3` (autonomy); step 8 bypasses: `--allow-spec-incomplete` / `--allow-issues-incomplete` (each with override reason + follow-up).

**Deprecated:** `forge develop` remains a working CLI-only deprecated alias for `forge design` (stderr warning). There is no `/forge:develop` or `$forge:develop` command pack.

**Default handoff:** [plan](#plan) (evaluate-pre is a common alternative).

**Methodologies:** evidence-first investigation; 5 Whys; systematic debugging; brainstorming gates; HMW framing; Pugh scoring; cross-review; user approval gates. Template: `templates/design-spec.md`.

---

### Plan

| | Cursor / Claude | Codex | Terminal |
|--|-----------------|-------|----------|
| Invoke | `/forge:plan` | `$forge:plan` | `forge plan --step 1` |

**What it does:** Turns an approved direction into a concrete implementation plan with waves, tasks, and documentation sections.

**Artifacts:** Plan file under `memory/plans/`; `memory/planner.md`.

**Default handoff:** [evaluate](#evaluate) (`--mode pre`; [implement](#implement) is a common alternative).

**Notable flags:** `--quick`; `--mode default|lite`; `--save-mode-preference`.

**Methodologies:** architecture overview; INVEST tasks; parallelization map; risk register; pre-mortem; skeleton markers through step 7. Documentation step 6: audience matrix and wiki checklist.

---

### Evaluate

| | Cursor / Claude | Codex | Terminal |
|--|-----------------|-------|----------|
| Invoke | `/forge:evaluate` | `$forge:evaluate` | `forge evaluate --step 1 --mode pre` |

**What it does:** Structured plan critique — **`--mode pre`** (before implementation) or **`--mode post`** (after). For full-team code review, use [code-review](#code-review) (`evaluate --mode review` is deprecated).

**Artifacts:** `.evaluate-state.json` and `.evaluate-findings-step<N>.json` sidecars.

**Default handoff:** `--mode pre` → [implement](#implement); `--mode post` → [code-review](#code-review).

**Methodologies:** feasibility ratings; completeness audit; correctness, quality, performance, operational readiness lenses; team dispatch when enabled.

---

### Implement

| | Cursor / Claude | Codex | Terminal |
|--|-----------------|-------|----------|
| Invoke | `/forge:implement` | `$forge:implement` | `forge implement --step 1` |

**What it does:** Executes the plan in waves with per-task review loops.

**Artifacts:** `handoff-implement.md`; `.implement-documentation-gate.json` at step 8.

**Default handoff:** [code-review](#code-review).

**Methodologies:** branch setup; wave dispatch; review loop per `templates/review-loop.md`; integration check; documentation gate (step 8).

---

### Code review

| | Cursor / Claude | Codex | Terminal |
|--|-----------------|-------|----------|
| Invoke | `/forge:code-review` | `$forge:code-review` | `forge code-review --step 1` |

**What it does:** Structured PR/diff/architecture review with Pass A (spec) and Pass B (engineering quality).

**Artifacts:** `memory/code-review-report.md`; **`--effort light|standard|thorough`** picks the reviewer team (`light` = Architect + QA; `standard` = Architect + QA (+ Security when auth/data); `thorough` = full six; `--quick` is an alias for `--effort light`). Structural probes (jscn/knip/madge on Node repos; pyscn/skylos on Python) are **on by default** (S3/S4/S8 for light/standard; full fan-out for thorough); opt out with `--no-structural` — see [`docs/structural-quality.md`](docs/structural-quality.md). When structural probes are enabled, **steps 4–6 are blocked** while the probe gate is `pending` (overall status not OK); the gate clears when probes finish OK, or when `cleared` / `overridden` / `deferred_to_ship`. Re-run step 3 or bypass with `--allow-structural-probes-incomplete` (override reason + follow-up). When structural probes are disabled via `--no-structural`, no probe gate applies.

**Default handoff:** [test](#test) ([ship](#ship) is a common alternative).

**Methodologies:** mode selection (PR / deep / architecture); **two-axis** review — Pass A Spec (intent/requirements) and Pass B Standards (`templates/standards-review-baseline.md`); findings reported per axis (do not merge across axes); team dispatch; discussion and report.

---

### Test

| | Cursor / Claude | Codex | Terminal |
|--|-----------------|-------|----------|
| Invoke | `/forge:test` | `$forge:test` | `forge test --step 1` |

**What it does:** Run test suites (**run** mode) or author mock flows (**`--mode flows`**).

**Artifacts:** `memory/test-report.md` (run); flows mode updates scenario index when parseable.

**Default handoff:** [ship](#ship) when the run is green, [diagnose](#diagnose) when there are failures.

**Methodologies:** discovery, execution, failure analysis, coverage gaps; flows mode — eight quality criteria and pytest reliability checks.

For a real-browser **product UX audit**, use [ux-review](#ux-review). (`forge test --mode ux` exits with a redirect — UX audits are **ux-review only**.)

---

### UX review

| | Cursor / Claude | Codex | Terminal |
|--|-----------------|-------|----------|
| Invoke | `/forge:ux-review` | `$forge:ux-review` | `forge ux-review --step 1` |

**What it does:** Real-browser product UX audit — map purpose/users/IA/journeys, plan coverage, walk every reachable page and control, capture empty/loading/error/success states (and viewports), then write a prioritized findings report.

**When to use:** Usability / UX audits of a running web app. Not a substitute for [`test`](#test) suite runs or mock-flow authoring.

**Artifacts:** `memory/ux-review-report.md` (default) plus session sidecars (orientation, plan, coverage, findings).

**Notable flags:** `--base-url` (application URL); `--quick`.

**Default handoff:** [ship](#ship), or [diagnose](#diagnose) when blocker/high findings remain.

**Methodologies:** [`templates/ux-review-criteria.md`](templates/ux-review-criteria.md); detail: [`skills/ux-review/SKILL.md`](skills/ux-review/SKILL.md).

---

### Diagnose

| | Cursor / Claude | Codex | Terminal |
|--|-----------------|-------|----------|
| Invoke | `/forge:diagnose` | `$forge:diagnose` | `forge diagnose --step 1` |

**What it does:** Evidence-led root-cause analysis with gated JSON sidecars.

**When to use:** Incidents, regressions, flaky failures. Handoff for **`large`** fixes defaults to [design](#design); **`complex`** defaults to [plan](#plan).

**Methodologies:** playbooks in `templates/diagnose-execution-playbooks.md`; 5 Whys; hypothesis register; technique coverage. Detail: [`skills/diagnose/SKILL.md`](skills/diagnose/SKILL.md).

---

### Takeover

| | Cursor / Claude | Codex | Terminal |
|--|-----------------|-------|----------|
| Invoke | `/forge:takeover` | `$forge:takeover` | `forge takeover` |

**What it does:** Infers work from sessions, handoffs, design specs, and optional `--issue`, then drives child Forge skills until **ship-ready** quality gates pass (`plan` + evaluate pre → `implement` + evaluate post → `code-review` → `test`).

**When to use:** After interruption, to continue an epic autonomously, or to chain the delivery pipeline without manually picking each skill.

**CLI:** `--design <path>`, `--issue <n|url>`, `--goal <text>` (default goal: ship-ready). **`--cleanup`** / **`--cleanup --force`** remove stale state (migrated from legacy `forge resume --cleanup`).

**Artifacts:** `.forge/.takeover-gates/` (migrates from legacy `.forge/memory/.takeover-gates/`); deviations sidecar at session `sidecars/.takeover-deviations.json`.

See [`skills/takeover/SKILL.md`](skills/takeover/SKILL.md).

---

### Status

| | Cursor / Claude | Codex | Terminal |
|--|-----------------|-------|----------|
| Invoke | `/forge:status` | `$forge:status` | `forge status` |

**What it does:** Dashboard of handoffs, active sessions, and suggested next workflow (inspection only).

**Behavior:** Composite view from `memory/`, `sessions/`, and legacy `state/`. See [`skills/status/SKILL.md`](skills/status/SKILL.md).

---

### Doctor

| | Cursor / Claude | Codex | Terminal |
|--|-----------------|-------|----------|
| Invoke | `/forge:doctor` | `$forge:doctor` | `forge doctor` |

**What it does:** Checks installation, PATH, encoding, runtime root (`.forge/`), adaptation profile (writable alias / mount class), and common misconfiguration.

**When to use:** First run in a repo; after `pipx install forge-next` or integration install.

---

### Ship

| | Cursor / Claude | Codex | Terminal |
|--|-----------------|-------|----------|
| Invoke | `/forge:ship` | `$forge:ship` | `forge ship --step 1` (Graphify preflight) |

**What it does:** Finalizes coding work — preflight, commit, push, PR, merge, publish (PyPI/npm). **Not** a delivery pipeline step. `forge ship --step 1` is **two things in sequence**: it runs the Graphify/deferred-probe preflight (refresh + GRAPHIFY banner when `graphify-out/` exists), then the agent follows [`.cursor/skills/ship/SKILL.md`](.cursor/skills/ship/SKILL.md) for the actual commit/push/PR/merge/publish work. Running `--step 1` alone does not commit or open a PR by itself.

**When to use:** After implement, code-review, or test when you are ready to land changes. Always run `forge ship --step 1` first (Graphify preflight), then follow the ship skill for commit/PR.

---

### Graphify

| | Cursor / Claude | Codex | Terminal |
|--|-----------------|-------|----------|
| Invoke | `/forge:graphify` | `$forge:graphify` | `forge graphify refresh` |

**What it does:** Optional codebase knowledge graph — refresh index, install/uninstall post-commit hook.

**When to use:** Setup and troubleshooting; agents read `graphify-out/GRAPH_REPORT.md` before broad search. Full guide: [`docs/graphify.md`](docs/graphify.md).

**Note:** CLI-only helpers (not slash commands): `forge session close`, `forge structural-tools`, `forge structural-probes`, `forge codex-agents`, `forge claude-graphify`, `forge cursor-subagent-hooks` — see [`docs/structural-quality.md`](docs/structural-quality.md), [`docs/sessions.md`](docs/sessions.md), and [`docs/graphify.md`](docs/graphify.md).

---

## Uninstallation

**Integrations (Cursor / Claude / Codex):**

```bash
forge uninstall
```

(or `--cursor`, `--claude`, `--codex`)

**Launcher:**

```bash
pipx uninstall forge-next
```

**Project state** (optional): `forge takeover --cleanup` (terminal), or `/forge:takeover` / `$forge:takeover` with cleanup if exposed, or delete `.forge/` (and any leftover `.codex/forge*` trees) in that repo as needed.

---

## How skills work (in the apps)

1. You pick a command: `/forge:…` (Cursor/Claude), `$forge:…` (Codex), or `forge …` in a terminal when not using an editor integration ([Advanced](#advanced-terminal-and-ci)). That authorizes the multi-step flow. See [AGENTS.md](AGENTS.md). **Cursor and Claude must run `forge <skill> --step 1` first** (the orchestrator script), even before any investigation or analysis — the Cursor command packs state this explicitly ("Must run: `forge <skill> --step 1` … before any other work"). Do not skip straight to manual work on step 1.
2. **Steps:** Each run advances phase 1, 2, … Output is the prompt (and sometimes todos) for that phase, plus where state is stored.
3. **Roles:** Prompts reference architect, planner, implementers, critic, QA, security, doc-writer. Hosts with sub-agents should follow the skill dispatch pattern, require **progress heartbeats** (`templates/subagent-progress.md`), and close agents when a slice of work is done (especially on Codex — see `templates/codex-runtime.md`).
4. **Handoff menu:** Last step lists options; transcript text may include `forge: …` labels. Your next command is `/forge:…` (Cursor/Claude) or `$forge:…` (Codex).
5. **Quick mode:** Where supported, integrations pass `--quick` through to the launcher; see `skills/`.

---

## Session + handoff audit lifecycle

**Primary layout** (new runs): under `.forge/sessions/` each workflow gets a directory with `session.json`, optional `handoff.md`, and `sidecars/` for step artifacts. `index.json` lists active sessions; completed or auto-closed sessions move to `sessions/_archive/`. **Dual-layer:** isolation per session dir; collaboration via shared `memory/project.md` (section merge with session attribution), multi-session synthesis, and `state/resume-context.json` v2 (`sessions[]` + `focus`). Global `handoff-{skill}.md` is a **pointer** to the per-session handoff. See [`docs/sessions.md`](docs/sessions.md).

**Legacy layout** (still readable until archived): flat JSON under `.codex/forge*/state/` or `.forge/state/` (for example `plan.json`, `plan-foo.json`) and global `memory/handoff-{skill}.md`. Takeover and cleanup understand both layouts; step 1 migrates then archives `.codex/forge*`.

- **Run memory files:** Each skill appends a short record on every step run to `memory/<skill>-runs.jsonl` and keeps only the last ~30 records.
- **Continuity snapshot:** On every skill state save (and evaluate saves), Forge writes **`state/resume-context.json`** with skill, steps, invocation hint, state path, and pointers to the latest handoff / `current-step.md` for `forge status` focus and new chat pickup.
- **Memory synthesis:** The same saves refresh **`memory/forge-memory-synthesis.md`** — an explicit merge of `project.md`, `current-step.md`, and recent handoffs so agents can open one memory narrative (see `templates/memory-protocol.md`).
- **Audit linkage:** Run-memory records include `state_path`/`session_ref` and `handoff_path`/`handoff_ref` (when a handoff exists), plus timestamp and summary.
- **Handoff closure:** Handoffs are consumed on step-1 intake of downstream skills (for example plan consumes design handoff, code-review consumes implement handoff, test consumes code-review/implement handoffs).
- **Session completeness:** Active-session detection treats a run as complete when either `completed_at` is set or legacy state reached max step (`current_step >= max_step` and `last_completed_step >= max_step`).
- **Explicit archive:** `forge session close <id>` moves a session directory to `sessions/_archive/` and **rewrites the global `handoff-{skill}.md` pointer** in place so it keeps resolving after the move.
- **Cleanup behavior:** `forge takeover --cleanup` removes stale session directories and legacy flat state files (dry-run by default; `--force` to delete). Env: `FORGE_SESSION_MAX_AGE_DAYS` (default `7`), `FORGE_SKIP_SESSION_CLEANUP=1` to disable automatic archive of old sessions.
- **Auto-close on step 1:** Starting a pipeline skill removes superseded session JSON when a handoff exists or when you move forward in the pipeline. Idle-based auto-close (`FORGE_STEP1_ABANDON_HOURS`) applies **only to step-1-only** sessions — a session that has progressed past step 1 is never auto-closed merely for being idle (see [AGENTS.md](AGENTS.md) State Lifecycle). `forge status` / `forge doctor` report remaining leaks.

---

## OpenAI Codex

After `forge install --codex`, skills live under `~/.codex/skills/forge/<folder>/SKILL.md`. Folders use hyphenated names (`forge-design/`, `forge-diagnose/`, …) because `:` is not valid in file paths. Each `SKILL.md` sets `name: forge:<subcommand>` (for example `name: forge:diagnose`), which Codex surfaces as `$forge:diagnose`. Most skill bodies run `forge …` via `<invoke cmd="…"/>`; **`$forge:ship`** instead follows the agent ship procedure in [`.cursor/skills/ship/SKILL.md`](.cursor/skills/ship/SKILL.md).

Invoke with `$forge:…` (mention / skill picker), `/use` with the skill name, `/skills`, or implicit matching on `description`. When transcript output shows `forge: …` handoff labels, your next step in Codex is the matching `$forge:…`. The `forge` binary is what most skills run under the hood; you do not type `forge …` as the Codex-side workflow entrypoint ([Advanced](#advanced-terminal-and-ci) for shells and CI).

**Graphify + delegation:** `forge install --codex` merges **`developer_instructions`** into `~/.codex/config.toml` when empty or matching the prior Forge snippet. The text **leads with mandatory Graphify rules** (read `GRAPH_REPORT.md` before codebase search; run **`forge ship --step 1`** for the ship-time GRAPHIFY banner; background refresh may run on workflow `--step` without blocking), then Forge delegation (sub-agents + session opt-in). Source of truth: **`forge_next/graphify_policy.py`**.

**Sub-agents (delegation):** Forge workflows expect Codex to allow `spawn_agent` / `close_agent` without you typing extra “use sub-agents” wording. Dispatched agents must report progress via `templates/subagent-progress.md` (`.forge/state/subagent-progress/`); the parent relays status instead of staying silent until completion. If you already customized `developer_instructions`, run **`forge codex-agents --force`** after upgrading **forge-next** so Graphify + delegation stay current. Restart Codex after changing config.

For agent lifecycle (every `spawn_agent` paired with `close_agent` across steps), follow [AGENTS.md](AGENTS.md) and `templates/codex-runtime.md` — that is separate from `developer_instructions`.

Evaluate note: the evaluate workflow persists a local `.evaluate-state.json` and step findings sidecars (`.evaluate-findings-step*.json`). Details live in [AGENTS.md](AGENTS.md).

---

## Claude Code

After `forge install --claude`, slash commands live under `~/.claude/commands/forge/`. The installer also runs **`forge claude-graphify`**, which merges **Graphify hooks** into `~/.claude/settings.json`:

- **SessionStart** — remind when `graphify-out/` exists  
- **PreToolUse** — all tools (sub-agent lifecycle reminders; Graphify context on **Grep**, **Glob**, **Read**, and search-like **Bash**)  
- **UserPromptSubmit** — when the prompt mentions `forge:` / `$forge:`  

Re-run `forge claude-graphify` after `pipx upgrade forge-next` (hooks invoke the absolute pipx `forge` binary via `forge claude-graphify-hook <event>`, not system `python -m forge_next`). Most workflow commands include a **`## Graphify`** block noting that the orchestrator **GRAPHIFY banner** prints at **ship** only (`forge ship --step 1`); status/doctor/takeover may omit that block. Background `forge graphify refresh` may still run on workflow `--step` when an index exists. Hooks and Codex `developer_instructions` still enforce reading `GRAPH_REPORT.md` before broad search. See [`docs/graphify.md`](docs/graphify.md).

---

## Cursor

After `forge install --cursor`, the plugin under `~/.cursor/plugins/local/forge/` includes slash commands **and** bundled workflow agent skills (copied from `integrations/codex/skills/`). Invoke workflows with `/forge:…`; Agents can also discover the skill packs without `~/.codex/skills`.

**Sub-agent lifecycle:** `forge cursor-subagent-hooks` writes `.cursor/hooks.json` for Task lifecycle and progress reminders while agents are running (see `templates/subagent-progress.md`). Suppress with `FORGE_SKIP_SUBAGENT_LIFECYCLE=1`. See [AGENTS.md](AGENTS.md).

Ship finalize skill also lives at [`.cursor/skills/ship/SKILL.md`](.cursor/skills/ship/SKILL.md) in this source tree.

---

## This repository vs PyPI

- `forge-next` on PyPI installs terminal `forge` and bundled orchestrators.
- This repo is the source for `prompts/`, `templates/`, `agents/`, `scripts/`, and **`integrations/`** (installable slash commands and Codex skills — exhaustive per `commands.json`).
- **`skills/`** holds agent-facing `SKILL.md` files for most workflows (not all: **ship**, **doctor**, and **graphify** live under `integrations/` / Codex skill packs; ship also under `.cursor/skills/ship/`). Edit repo-root `prompts/` and `templates/` for orchestration content; `forge_next/assets/` mirrors them at release.

### Highlights since 1.0

| Version | What users got |
|---------|----------------|
| **1.0** | `forge takeover` replaces resume/iterate; ship-ready gate drive |
| **1.1** | Repo-local `.forge/` runtime; structural probe gates |
| **1.2** | **jscn** Node/TS structural probe |
| **1.3** | Design spec→issues gate (steps 6–8); sketch wayfinder sections; code-review two-axis Pass A/B |
| **1.4** | Parallel sessions, `--session`, `forge session close`, resume-context v2 |
| **1.6** | **ux-review** workflow; Cursor install bundles agent skills; UX audits are ux-review-only |
| **1.7** | Subagent progress heartbeats (`.forge/state/subagent-progress/`) |

PyPI: [pypi.org/project/forge-next](https://pypi.org/project/forge-next/)

Source: [github.com/msderganc/forge](https://github.com/msderganc/forge)

---

## Advanced: terminal and CI

Outside Codex chat, hooks and automation call `forge <subcommand>` with a space (e.g. `forge plan --step 1`). That is the same engine as `/forge:plan` (Cursor/Claude) and `$forge:plan` (Codex skills invoke this binary for you). `forge --help` lists flags.

**Automation / CI:** Common flags:

| Variable | Effect |
|----------|--------|
| **`FORGE_SKIP_SESSION_OPTIN=1`** | Suppress step-1 **session opt-in** banner |
| **`FORGE_SKIP_GRAPHIFY=1`** | Disable ship GRAPHIFY banner and automatic background refresh |
| **`FORGE_SKIP_GRAPHIFY_REFRESH=1`** | Suppress background refresh only (keep ship banner) |
| **`FORGE_SKIP_AUTO_CLOSE=1`** | Disable step-1 auto-close of superseded sessions |
| **`FORGE_SKIP_SUBAGENT_LIFECYCLE=1`** | Disable Cursor subagent lifecycle / progress reminders |
| **`FORGE_SKIP_STRUCTURAL_TOOLS=1`** | Skip structural probe install and runs |
| **`FORGE_SKILL_ENGINE=0`** | Force legacy per-skill orchestrator bodies (skip declarative runner) |

Full list: [`docs/environment.md`](docs/environment.md). Declarative manifests + runner: [`docs/declarative-skills.md`](docs/declarative-skills.md).

**Graphify (optional):** Build the graph with `forge graphify refresh` (or `FORGE_GRAPHIFY_COMMAND`); optional `forge graphify install-hook` for post-commit refresh. Workflow `--step` may spawn **debounced background** refresh when `graphify-out/` exists; the orchestrator **GRAPHIFY** banner prints on **`forge ship --step 1`** only. Claude hooks (`forge claude-graphify`) and Codex policy (`forge codex-agents`) enforce reading the map before search. After `pipx upgrade forge-next`, re-run those two commands. Full guide: [`docs/graphify.md`](docs/graphify.md).

---

## Contributing

Orchestration lives in `scripts/shared/` (`orchestrator.py`, `skill_chain.py`, `session_store.py`) and `scripts/takeover/` (meta-workflow). Keep [AGENTS.md](AGENTS.md), [`docs/README.md`](docs/README.md), and `skills/` aligned with behavior.

**Versions:** Any change that affects the PyPI package or editor integrations must bump semver in **[`pyproject.toml`](pyproject.toml)** (and the Cursor plugin [`plugin.json`](integrations/cursor-plugin/.cursor-plugin/plugin.json) when that bundle changes). Follow **[Versioning](AGENTS.md#versioning)** in [AGENTS.md](AGENTS.md): use **patch** for narrow fixes, **minor** for additive behavior, **major** for breaking contracts.

**PyPI:** If you bump `project.version`, **[build and upload to PyPI](AGENTS.md#pypi)** the same release (`python -m build`, `python -m twine check dist/*`, `python -m twine upload dist/*`; or `scripts/release/publish_pypi.sh`). Users installing via `pipx install forge-next` must see the new version on PyPI (`pipx upgrade forge-next`).

**Integration bundles:** After changing `integrations/cursor-plugin/`, `integrations/claude/commands/`, or `integrations/codex/skills/`, run `pytest tests/test_integration_install_layout.py` (guards layout vs **[`integrations/spec/commands.json`](integrations/spec/commands.json)**).

Tests:

- `python -m pytest`
- `python scripts/smoke.py`
