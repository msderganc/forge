---
name: forge:diagnose
description: Deep diagnosis workflow for bugs/regressions. Use when root cause is unknown, something is broken or flaky, or the user asks to diagnose/debug a failure.
---

Read `templates/diagnose-execution-playbooks.md` per phase.

When `graphify-out/` exists, read `graphify-out/GRAPH_REPORT.md` before search; refresh at ship (`forge ship --step 1`).

<invoke cmd="forge diagnose" />
