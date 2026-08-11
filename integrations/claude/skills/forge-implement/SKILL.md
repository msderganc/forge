---
name: forge-implement
description: >-
  Execute an implementation plan in waves. Use when the user asks to implement, execute the plan, build the planned changes, or run implementation waves.
---

Announce at start: "Using forge-implement to run the Forge **implement** workflow."

## Hard rule — what the user sees

**Never show terminal commands** for this workflow.

**Never edit the repository** unless the phase allows it. Follow the active skill's orchestrator output for what may be written.


## Graphify

Runs at **ship** only (`forge ship --step 1`). This workflow does not print GRAPHIFY per step.


## What to tell the user first

- Run the **implement** workflow from the repo root.
- Follow orchestrator phase output.

## What you run (agent)

**Must run:** `forge implement --step 1` (the orchestrator script) before any other work — do not skip straight to manual investigation/analysis.

Run **implement** at step one. Summarize phases without quoting invocation lines.
