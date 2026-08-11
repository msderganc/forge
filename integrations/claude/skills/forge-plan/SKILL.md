---
name: forge-plan
description: >-
  Create an implementation plan with tasks and waves. Use when the user asks to plan, write a plan, break work into tasks, or produce an implementation plan before coding.
---

Announce at start: "Using forge-plan to run the Forge **plan** workflow."

## Hard rule — what the user sees

**Never show terminal commands** for this workflow.

**Never edit the repository** unless the phase allows it. Follow the active skill's orchestrator output for what may be written.


## Graphify

Runs at **ship** only (`forge ship --step 1`). This workflow does not print GRAPHIFY per step.


## What to tell the user first

- **Plan** turns an approved direction into tasks — no code edits during planning.

## What you run (agent)

**Must run:** `forge plan --step 1` (the orchestrator script) before any other work — do not skip straight to manual investigation/analysis.

Run **plan** at step one. Planning-only — no git mutations.
