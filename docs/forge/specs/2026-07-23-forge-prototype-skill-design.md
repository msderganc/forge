# Design spec: `forge:prototype`

**Date:** 2026-07-23  
**Status:** Draft (awaiting user chunk approvals)  
**Scope tier:** medium  
**Session:** `9b9b18`  
**Approved direction:** Option B (`.forge/memory/solutions.md`)

---

## Context

### Problem / opportunity

Sketch and Design already **offer** `forge:prototype` when one unresolved logic/state or UI-shape question blocks Recommended scope, but the skill is stub-only (`docs/forge/prototype-skill-stub.md`). Agents must not claim it exists. Users need a Matt Pocock–style throwaway decision aid: Logic TUI or UI variants → captured verdict → cleanup — without replacing design/plan/implement.

### Who is affected

- Agents/users in sketch/design when a design question needs a probe
- Host-project trees (temporary probe files)
- Forge maintainers (CLI, integrations, prompt assets, tests)

### Investigation links

- `.forge/memory/investigation.md`
- `.forge/memory/investigator.md`
- `.forge/memory/solutions.md`
- `.forge/memory/critic-investigation-review.md`
- `.forge/memory/qa-investigation-review.md`
- Stub contract: `docs/forge/prototype-skill-stub.md`
- Prior art: `scripts/sketch/sketch.py`

---

## Goals and non-goals

### Goals

1. Invokable **`forge prototype`** orchestrator + CLI (sketch-class, 1:1, no agent team).
2. **Both** Logic and UI branch recipes in v1 (host-stack agnostic prompts/templates).
3. **Own visual + functional representations** as the skill’s product:
   - **Functional** — interactive Logic TUI / state-machine probe (feel transitions).
   - **Visual** — structural UI variants (and optional Studio screens that *present* those variants or functional summaries when Studio is available).
4. Three steps: **Orient → Build/run (re-entrant) → Verdict + handoff**.
5. **Enforceable cleanup gate** before handoff (sidecar required; not markdown-only).
6. Verdict artifact at `.forge/memory/prototype-verdict.md` (stub schema).
7. **Sketch/design invoke prototype** when they need a visual/functional representation — do not reinvent probe UIs inside those skills; pull shared representation guidance into prototype and call `forge:prototype` from offer/handoff sites.
8. Flip all “not yet invokable” offer sites; rewrite stub into user-facing skill doc.
9. Full registration + tests; **MINOR 1.10.0 → 1.11.0** (`pyproject.toml` + Cursor `plugin.json`).

### Non-goals

- Agent-team dispatch during prototype
- Moving **all** of Design Stage-2 brainstorming gates (HMW / technique / Pugh) into prototype — those stay design-owned; only **probe-style visual/functional representations** move here
- Replacing Studio as a transport module (`forge_next.studio`) — Studio remains shared infra; prototype **uses** it when helpful
- Takeover auto-routing into prototype
- Promoting throwaway code to production inside this skill
- Git dirty-tree scans / automated branch creation in v1
- Adding prototype to `PIPELINE_SKILLS` / pipeline order

---

## Constraints

### Hard

- 1:1 skill only (match sketch / AGENTS.md / stub).
- Stay **out** of `PIPELINE_SKILLS`; add warn when design/sketch step 1 sees an active prototype session.
- Cleanup sidecar must be valid before step 3 completes handoff.
- Atomic ship set: CLI + offer flip + stub rewrite + asset sync + `generate_integrations` + test expectation updates.
- Verdict is evidence only for design — must not invent new requirements.
- **Ownership:** Prototype is the only workflow skill that authors throwaway visual/functional probes. Sketch/design **offer and invoke** it; they do not grow parallel probe implementations.
- Design prompts that currently say “no probe runs” must **route to `forge prototype`** (invoke), not leave a dead end.

### Soft

- Prefer sketch patterns (`await_same_step`, `write_handoff`, `build_skill_handoff_menu`).
- Thin recipes OK; shared core over duplicated Logic/UI ceremony.
- Optional `--branch logic|ui` on CLI; dialogue default if omitted.
- Concurrent hygiene: warn, not hard-block, in v1.
- When `studio_enabled` in the host Forge session: prototype **may** push Studio screens that summarize/compare variants or show a functional state diagram; host TUI / `?variant=` remain the primary runnable representations.
- Reuse Studio HTML patterns from `forge_next/assets/studio/` where they help presentation — do not fork a second Studio stack.

---

## Candidate comparison snapshot

| Option | Summary | Trade-off |
|--------|---------|-----------|
| A — Exact sketch 3-step clone | Minimal code | Cleanup under-gated (Critic FAIL) |
| **B — Sketch shape + hard cleanup gate** ✓ | Same ceremony, enforceable exit | Sidecar gate to implement |
| C — 4 steps (split verdict/handoff) | Clearer exit phase | Extra ceremony; defer |

---

## Chosen design

### Decision

Ship **Option B**: sketch-shaped 3-step skill with Logic + UI recipes and a **required cleanup sidecar** on step 3.

**Representation ownership (user revision):** Prototype owns **visual and functional representations**. Sketch/design **invoke** `forge:prototype` when a question needs to be seen or felt; they do not build parallel probe UIs. Studio stays shared transport; prototype may push Studio screens as a presentation aid alongside host TUI / `?variant=` probes.

### Step model

| Step | Phase | Behavior |
|------|-------|----------|
| 1 | Orient | Capture question, assumption, exit criterion; select branch; init `state.custom` |
| 2 | Build/run | Re-entrant (`await_same_step=True`); agent follows Logic or UI recipe; do not mark complete |
| 3 | Verdict + handoff | Require cleanup sidecar → write verdict → `write_handoff` → handoff menu → clear state |

### `state.custom` (minimum)

- `question`, `assumption`, `exit_criterion` (strings)
- `branch`: `logic` | `ui`
- `session_visits` (int, step 2)
- `return_to`: optional `design` | `sketch` (default handoff target `design`)
- Cleanup **not** only in custom — also required as sidecar (below)

### Cleanup gate

Session sidecar: `.forge/sessions/<id>/sidecars/.prototype-cleanup.json`

```json
{
  "status": "deleted" | "throwaway_branch",
  "detail": "optional path or branch name",
  "recorded_at": "<iso8601>"
}
```

Step 3: if missing/invalid → print gate failure, `sys.exit(1)`, do not handoff. Agent fills sidecar during/after cleanup; prompts mandate it.

### Recipes / prompts

| Artifact | Role |
|----------|------|
| `templates/prototype-protocol.md` | Offer rules, guardrails, verdict schema, cleanup gate |
| `templates/prototype-logic.md` | Logic branch (pure module + TUI; Pocock-adapted) |
| `templates/prototype-ui.md` | UI branch (variants + `?variant=` switcher; Pocock-adapted) |
| `prompts/prototype/{startup,session,handoff}.md` | Step prompts |
| `skills/prototype/SKILL.md` | Skill contract + invoke |

### Verdict path

`.forge/memory/prototype-verdict.md` — fields: Question, Branch, Run, Observed, Decision, Cleanup.

### Handoff / chain

- `SKILL_CHAIN["prototype"]` → default `design`, alts `sketch`, `plan`
- Sketch/design handoff menus may list `prototype` as alternative when offer criteria apply
- `suggested_next` honors `return_to` when set

### Registration (must-touch)

CLI + `cli_dispatch`; orchestrator `scripts/prototype/`; prompts + `WORKFLOW_PROMPT_TEMPLATES`; `skill_phases`; `SKILL_CHAIN` + descriptions; `commands.json` + `COMMAND_OVERRIDES` + regenerate; `KNOWN_SKILLS` + `session_store` migration list; 1:1 prose in preamble/AGENTS/roster; README command count 14→15; tests (`test_prototype.py`, exact-set/count updates); rewrite stub; sync prompt/template assets; versions **1.11.0**.

### Boundaries

- **Owns:** Forge skill ceremony; Logic/UI recipes; visual + functional representation guidance; verdict/cleanup gates; offer/invoke contract used by sketch/design.
- **Does not own:** Design brainstorming Gate 1/2 (HMW/Pugh); Studio server/transport (`forge_next.studio`); production promote path.
- **Invokers:** Sketch/design (and later plan if needed) call into prototype when a representation is required; handoff returns verdict as evidence.

---

## Data / API / schema impact

- New CLI subcommand `prototype` (backward-compatible → MINOR).
- New session skill name `prototype` in hygiene/store lists.
- New sidecar schema `.prototype-cleanup.json` (session-local).
- No DB / network API changes.
- Packaged wheel assets gain `prompts/prototype/*` and prototype templates.

---

## Error handling and operational behavior

- Step 3 missing cleanup sidecar → fail closed (no handoff).
- Active prototype session when starting design/sketch step 1 → stderr **warn** (v1).
- Re-entrant step 2 never auto-advances; user/agent must run step 3 explicitly.
- Malformed cleanup JSON → treat as missing (fail closed).

---

## Test strategy

1. `tests/test_prototype.py` — step 1 creates state; step 2 re-entrant; step 3 refuses without sidecar; step 3 succeeds with valid sidecar + writes verdict/handoff.
2. Replace `test_prototype_stub_not_invokable` with “skill is invokable / stub retired or rewritten” assertion.
3. Update SKILL_CHAIN exact-set and `commands.json` length 14→15.
4. `generate_integrations.py --check` green; prompt/template asset parity.
5. Smoke: `forge prototype --help` and `--step 1` print Orient guidance.

---

## Rollout / rollback

- Ship in one PR: feature + registration + stub flip + version bump.
- Rollback: revert PR; offer sites would again need stub language if rolled back mid-flight (avoid partial revert).
- No data migration beyond optional ignore of leftover `.prototype-cleanup.json`.

---

## Assumptions

1. Host projects can run a one-liner (pnpm/python/etc.) for probes; Forge does not embed runtimes.
2. Agents will write the cleanup sidecar when prompted + gated (no git enforcement in v1).
3. Medium file breadth is acceptable for one MINOR release.
4. Warn-only concurrent hygiene is enough for v1.

---

## Decision record

| Field | Value |
|-------|-------|
| Date | 2026-07-23 |
| Direction | Option B |
| Solution approval | User chose **B** |
| Spec approval | Pending chunked review |
| Participants | User + design session `9b9b18` |

---

## Open questions

1. Exact wording of design/sketch concurrent-prototype warn (copy only).
2. Whether sketch/design handoff menus always list `prototype` or only when offer criteria match (prefer: list as alt always; prompts keep offer rule).
3. Retire stub file vs rewrite in place as `docs/forge/prototype.md` (prefer: rewrite stub path into real guide + remove NOT YET INVOKABLE).
4. How aggressively prototype should auto-start Studio vs only when design already has `studio_enabled` (prefer: reuse existing session flag; do not force Studio opt-in from prototype alone).
