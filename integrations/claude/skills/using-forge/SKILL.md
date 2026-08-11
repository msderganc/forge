---
name: using-forge
description: >-
  Use when starting any conversation in a Forge-enabled project, or when the
  user asks to plan, design, implement, sketch, review, test, diagnose, ship,
  takeover, or otherwise drive delivery work — parses intent and routes to the
  matching forge-* skill before ad-hoc coding or Superpowers process skills.
---

<SUBAGENT-STOP>
If you were dispatched as a subagent to execute a specific task, ignore this skill.
</SUBAGENT-STOP>

<EXTREMELY-IMPORTANT>
If Forge skills are installed and the user's ask matches a Forge workflow, you
MUST route through Forge. Do not freehand a plan, design, or implementation
checklist when `forge-plan`, `forge-design`, `forge-implement`, etc. apply.

When both Superpowers and Forge are available in a Forge-enabled repo, prefer
Forge for delivery workflows (plan / implement / design / diagnose / review /
test / ship / takeover). Superpowers process skills are the fallback only when
Forge is not installed or the user explicitly wants Superpowers.
</EXTREMELY-IMPORTANT>

# using-forge — parse intent and orchestrate

## When this applies

Forge is in play when any of these are true:

- `forge` is on PATH / `forge doctor` works
- `.forge/` exists in the repo
- Claude has `forge-*` / `using-forge` skills or `/forge:*` commands installed
- The user names a Forge skill (`plan`, `forge plan`, `/forge:plan`, …)

## The rule

1. **Parse** the user message against the routing table below.
2. **Announce** `Using forge-<skill> to <purpose>`.
3. **Invoke** that skill (Skill tool / Read its `SKILL.md` / follow `/forge:<skill>`).
4. **Run** the skill's required orchestrator (`forge <skill> --step 1` …) before
   freestyle investigation — do not skip the CLI.
5. **Honor handoffs** at the end of a skill (numbered menu / user pick).

Ask the one-time session opt-in only when starting a multi-step Forge skill at
step 1 and the user has not already chosen full Forge vs informal help in this
chat. If they choose informal help, stop driving Forge state.

## Routing table (parse → skill)

Match the **strongest** signal. Explicit skill names win over fuzzy signals.

| User signal (examples) | Route to | Then run |
|------------------------|----------|----------|
| "plan", "write a plan", "implementation plan", "break into tasks/waves" | `forge-plan` | `forge plan --step 1` |
| "implement", "execute the plan", "build it", "do the waves" | `forge-implement` | `forge implement --step 1` |
| "design", "spec", "brainstorm solutions", "architecture options" | `forge-design` | `forge design --step 1` |
| Fuzzy intent, open decisions, "what are we building" | `forge-sketch` | `forge sketch --step 1` |
| Bug, regression, flaky, "why is this broken", root cause unknown | `forge-diagnose` | `forge diagnose --step 1` |
| "review the plan", evaluate pre | `forge-evaluate` | `forge evaluate --mode pre --plan … --step 1` |
| "audit vs plan", evaluate post | `forge-evaluate` | `forge evaluate --mode post --plan … --step 1` |
| "code review", "review this PR/diff" | `forge-code-review` | `forge code-review --step 1` |
| "run tests", "test suite", "mock flows" | `forge-test` | `forge test --step 1` (or `--mode flows`) |
| "UX review", walk the product UI | `forge-ux-review` | `forge ux-review --step 1` |
| "ship", "commit and PR", "merge", "publish" | `forge-ship` | follow ship skill (no step orchestrator required beyond ship step 1 graphify) |
| "takeover", "drive it", "keep going until ship-ready" | `forge-takeover` | `forge takeover` |
| "forge status" / where are we | `forge-status` | `forge status` |
| Install/PATH broken | `forge-doctor` | `forge doctor` |

### Process-first ties

When unsure which workflow fits:

| Signal | Prefer |
|--------|--------|
| Intent fuzzy | `forge-sketch` then `forge-design` |
| Multiple approaches / unclear requirements | `forge-design` |
| Root cause unknown | `forge-diagnose` |
| Single approved direction → tasks | `forge-plan` |
| Test regression, cause unclear | `forge-test` then `forge-diagnose` |

### Chain (after a skill completes)

Default next skills follow Forge handoff menus (e.g. plan → evaluate pre →
implement → code-review → test → ship). When the user says "yes" / picks a
number, invoke that next skill — do not invent a parallel process.

## How to invoke

Prefer, in order:

1. **Skill tool** on `forge-<skill>` (or `using-forge` already selected the route).
2. **Read** `~/.claude/skills/forge-<skill>/SKILL.md` (or the repo/plugin copy) and follow it.
3. **Slash command** `/forge:<skill>` if skills are missing but commands are installed.
4. **CLI** `forge <skill> --step 1` as the skill body requires.

Never show raw terminal invocation lines to the user; summarize phases instead.

## Do not route to Forge when

- Pure Q&A with no delivery ask and no Forge skill named
- User explicitly chose **informal help** for this chat
- User explicitly asked for Superpowers / another named non-Forge skill
- Subagent with a fixed delegated task (see SUBAGENT-STOP)

## Red flags (you are rationalizing)

| Thought | Reality |
|---------|---------|
| "I'll just draft a quick plan in chat" | That is `forge-plan`. |
| "Superpowers writing-plans is fine" | Forge-enabled repo → `forge-plan`. |
| "I need to explore first" | Design/diagnose/plan skills tell you how; start the skill. |
| "Forge is overkill for this" | If they asked to plan/implement/design, use the skill. |
| "I'll run forge later" | Step 1 is the first action after announce. |
