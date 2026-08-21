# Workflow skill runtime (shared)

Read this once per skill session. Skill-specific args and gates stay in each `skills/<name>/SKILL.md`.

## Delegation

Invoking a `forge:*` workflow skill authorizes the agent dispatch that skill requires — **except `forge:sketch`** (1:1 dialogue only) **and `forge:ux-review`** (1:1 real-browser product UX audit) — neither requires a Forge agent team or Task/sub-agent spawn unless the user asks. For all other workflow skills, do not ask the user to separately delegate or spawn sub-agents.

Before spawning, read **`templates/forge-agent-roster.md`**. Use only roster roles (e.g. **Architect**, **Investigator**) — never invent composites like `backend-architect`. Full contract: [AGENTS.md](../AGENTS.md) § Forge Skill Delegation Contract.

## Graphify

See [templates/graphify-contract.md](graphify-contract.md). Refresh at **ship** only (`forge ship --step 1`). Optional during skills: read `graphify-out/GRAPH_REPORT.md` or use `graphify query` / `path` / `explain`.

## pstack

Optional companion skills from [pstack](https://github.com/cursor/plugins/tree/main/pstack/skills). Canonical map: [templates/pstack-contract.md](pstack-contract.md). Named Forge skills always win. `forge install` copies an allowlist by default; skip with `--skip-pstack`. If pstack is not installed, skip.

## Progress and continuation

The orchestrator prints a **Create Phase Todos** JSON block each step — mirror it immediately (e.g. `update_plan`). On step 1, complete **SESSION OPT-IN** first if shown.

Honor ceremony as a duration hint. Global guidance: light **5–10 min**, medium **20–40 min**, detailed **45–90 min**, comprehensive **1–2 h**. Stop or escalate at the top of the range. Per-skill floors: [`docs/ceremony.md`](../docs/ceremony.md).

**Light:** after the skill’s primary artifact exists, present the handoff (or stop). Do not walk remaining unused steps. Plan light is three slots: Frame+Orient → Act → Handoff.

**Medium and above:** do not stop between phases. See [templates/codex-runtime.md](codex-runtime.md) for continuation protocol and parallel dispatch.

## Execution order

**Run the orchestrator first** — `forge <skill> --step N` — and follow its output. Do not explore or analyze before running the script.

## Handoff

Final step emits a **WORKFLOW HANDOFF** menu. Defaults and alternatives: `scripts/shared/skill_chain.py` via `build_skill_handoff_menu()`.

## Routing

When unsure which skill to run next, see [AGENTS.md](../AGENTS.md) § Process-first skill choice.

## Simplicity (YAGNI)

- **Original scope bias:** Treat the user's initial request as the **ceiling**. The recommended path is that ask (or confirmed Recommended scope). Do not reframe a narrow fix into a larger initiative without an explicit user yes.
- **Scope expansion labeling:** Opportunities and delighters are welcome — list them under **Scope expansion (optional — not recommended)** and never promote them silently. See `templates/scope-size-model.md`.
- **YAGNI:** Build only what the current task or approved Recommended scope requires. No speculative APIs, config flags, abstraction layers, or "future-proof" hooks unless explicitly in scope.
- **Smallest correct change:** Prefer the shortest diff that satisfies acceptance criteria. A focused 5-line fix beats a 100-line refactor. Prefer **fewer tasks / fewer files / fewer waves** over completeness theater.
- **One-liners where readable:** Prefer inline expressions (ternaries, comprehensions, small lambdas, guard clauses) over one-off helpers, wrapper classes, or new files—when clarity is preserved.
- **No premature generalization:** One caller → implement at the call site; three similar call sites → then extract.
- **Anti-patterns:** no companion refactor, no "while we're here", no future flag, no unrelated test matrix, no pre-existing-cleanup task unless the user opted that expansion in.
- **When in doubt:** Ship the simpler option; pick the **lower** size tier (`templates/scope-size-model.md`); escalate breadth only with user confirmation.

## Size-scaled ceremony

Judge **small / medium / large** early and scale ceremony per `templates/scope-size-model.md`. Structural review stays on for every product-code change; scale reviewer fan-out, not whether structural runs. Use the **loop-reduction** policy there (batch findings, focused re-review, suggestions advisory, two-round cap for low-risk).

## Structural quality (build charter)

While designing, planning, and implementing, follow **`templates/structural-build-charter.md`**: complexity budget, no clones, no dead arms, no new cycles, no speculative exports. jscn/pyscn (and related probes) **verify** those rules later — they are not the first time agents should hear them. The charter does **not** authorize repayment waves or drive-bys beyond in-scope hotspots.
