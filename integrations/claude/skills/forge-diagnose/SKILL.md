---
name: forge-diagnose
description: >-
  Deep diagnosis workflow for bugs/regressions. Use when root cause is unknown, something is broken or flaky, or the user asks to diagnose/debug a failure.
---

Announce at start: "Using forge-diagnose to run the Forge **diagnose** workflow."

## Hard rule — what the user sees

**Never show terminal commands** for this workflow.

**Never edit the repository** unless the phase allows it. Follow the active skill's orchestrator output for what may be written.


## Graphify

Runs at **ship** only (`forge ship --step 1`). This workflow does not print GRAPHIFY per step.


## What to tell the user first

- **Diagnose** runs structured RCA when root cause is unclear.

## What you run (agent)

**Must run:** `forge diagnose --step 1` (the orchestrator script) before any other work — do not skip straight to manual investigation/analysis.

Run **diagnose** at step one. Follow playbook sidecars and gates.
