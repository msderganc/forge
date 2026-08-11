---
name: forge-code-review
description: >-
  Run structured code review workflows. Use when the user asks for code review, PR review, or a full-team review of changes.
---

Announce at start: "Using forge-code-review to run the Forge **code-review** workflow."

## Hard rule — what the user sees

**Never show terminal commands** for this workflow.

**Never edit the repository** unless the phase allows it. Follow the active skill's orchestrator output for what may be written.


## Graphify

Runs at **ship** only (`forge ship --step 1`). This workflow does not print GRAPHIFY per step.


## What to tell the user first

- Run the **code-review** workflow from the repo root.
- Follow orchestrator phase output.

## What you run (agent)

**Must run:** `forge code-review --step 1` (the orchestrator script) before any other work — do not skip straight to manual investigation/analysis.

Run **code-review** at step one. Summarize phases without quoting invocation lines.
