---
name: forge-sketch
description: >-
  Organize intent and open decisions before design (optional CONTEXT.md/ADRs). Use when goals are fuzzy, decisions are open, or the user wants to clarify what to build before design/plan.
---

Announce at start: "Using forge-sketch to run the Forge **sketch** workflow."

## Hard rule — what the user sees

**Never show terminal commands** for this workflow.

**Never edit the repository** unless the phase allows it (session memory always; `CONTEXT.md` / `docs/adr/` only when domain-docs mode is on). **Do not** write `docs/forge/specs/` design specs.


## Graphify

Runs at **ship** only (`forge ship --step 1`). This workflow does not print GRAPHIFY per step.


## What to tell the user first

- **Sketch** is a **1:1 iterative conversation** — reflect, confirm, revise — before design investigates solutions (no agent team dispatch).
- Optional: domain glossary (`CONTEXT.md`) and ADRs when domain-docs mode is on.

## What you run (agent)

**Must run:** `forge sketch --step 1` (the orchestrator script) before any other work — do not skip straight to manual investigation/analysis.

Run **sketch** at step one. Synthesis every few exchanges; re-run step 2 to continue; step 3 only after the user confirms ready for design.
