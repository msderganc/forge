---
description: |
  Iterative conversational intent dialogue before design. Synthesis checkpoints,
  loop-back on revised decisions; optional CONTEXT.md/ADRs with --with-domain-docs.
  Design (not sketch) writes docs/forge/specs design specs.
---

# forge sketch — Pre-design intent

## Skill contract

- **Use when:** intent is fuzzy — problem, constraints, or terminology still need reflection before design.
- **Do not use when:** direction is already clear (go straight to `design`) or you need investigation/specs (sketch doesn't do that).
- **Input:** user's raw ask / problem statement. **Output artifact:** `sketch-decisions.md` (Destination, Decisions so far, Not yet specified, Out of scope).
- **Stops at:** handoff to `design` once decisions stabilize — sketch never investigates the codebase or writes specs.
- **Small-path behavior:** for trivial asks, skip sketch entirely and go straight to `design`/`plan`; when used, keep the dialogue to 1–2 checkpoints instead of full fog-clearing.

See `templates/scope-size-model.md` and `templates/workflow-skill-preamble.md` for shared sizing/ceremony rules.

Iterative pair-thinking: reflect, confirm, revise — not a checklist. See `templates/sketch-protocol.md`.

Session artifact `sketch-decisions.md` uses wayfinder-inspired sections (adapted from [mattpocock/skills wayfinder](https://github.com/mattpocock/skills/blob/main/skills/engineering/wayfinder/SKILL.md)): **Destination**, **Decisions so far**, **Not yet specified** (fog), and **Out of scope**. Plan, don't do — sketch records decisions; design owns investigation and specs.

**No agent team:** Sketch is 1:1 dialogue only. Do **not** spawn Task sub-agents or Forge roster roles (`templates/forge-agent-roster.md`).

Routing and sketch vs design boundary: [AGENTS.md](../../AGENTS.md) § Process-first.

Shared runtime: [templates/workflow-skill-preamble.md](../../templates/workflow-skill-preamble.md).

## pstack companion

Optionally reach for `/how` and `/why` beside Graphify. Canonical map: `templates/pstack-contract.md`. If pstack is not installed, skip.

## Simplicity

Preamble § Simplicity (YAGNI). Separate must-have from nice-to-have; defer speculative scope unless the user opts in.

<invoke cmd="forge sketch" />

| Argument | When | Description |
|----------|------|-------------|
| `--step` | Always | 1 startup, 2 session (re-invokable), 3 handoff |
| `--with-domain-docs` | Step 1+ | Allow `CONTEXT.md` glossary and sparse `docs/adr/` |
| `--state` | Resume | Path to sketch state file |

Re-run **`forge sketch --step 2`** to continue the conversation until ready for handoff.

Default next: **`forge:design`**.
