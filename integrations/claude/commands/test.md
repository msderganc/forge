---
name: forge:test
description: Run tests or author mock flows (run/flows modes). Use when the user asks to run tests, check the suite, or write end-to-end mock user journeys.
---

## Hard rule — what the user sees

**Never show terminal commands** for this workflow.

**Never edit the repository** unless the phase allows it. Follow the active skill's orchestrator output for what may be written.


## Graphify

Runs at **ship** only (`forge ship --step 1`). This workflow does not print GRAPHIFY per step.


## What to tell the user first

- Run the **test** workflow from the repo root.
- Follow orchestrator phase output.

## What you run (agent)

**Must run:** `forge test --step 1` (the orchestrator script) before any other work — do not skip straight to manual investigation/analysis.

Run **test** at step one. Summarize phases without quoting invocation lines.
