---
name: forge-graphify
description: >-
  Optional Graphify index: refresh status for forge takeover; install or remove a fail-soft post-commit hook. Use when setting up or troubleshooting the codebase graph index.
---

## Hard rule — what the user sees

**Never show terminal commands** unless they explicitly ask for copy-paste.

## What to tell the user first

- **Graphify** is optional: it feeds **codebase structure** into `forge takeover`. When `graphify-out/` exists, workflow `--step` may refresh in the background; the orchestrator **GRAPHIFY** banner prints on **`forge ship --step 1`** only.
- Default flow: **refresh** metadata once per clone; optionally **install-hook** so each commit re-refreshes in the background (fail-soft).
- **Claude hooks:** `forge claude-graphify` (also run by `forge install --claude`). Re-run after `pipx upgrade forge-next`.
- They need Graphify installed **or** **`FORGE_GRAPHIFY_COMMAND`**. Full guide: **`docs/graphify.md`** in the Forge repo.

## What you run (agent)

Invoke **graphify** through the launcher: default **refresh**; use **install-hook** or **uninstall-hook** when the user wants the git hook added or removed. Use **`--repo`** if working outside the project root. Paraphrase outcomes—do not paste raw argv.

---
