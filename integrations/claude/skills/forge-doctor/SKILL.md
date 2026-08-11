---
name: forge-doctor
description: >-
  Diagnose installation/PATH/encoding/runtime-root issues. Use when Forge install, PATH, or runtime setup looks broken.
---

## Hard rule — what the user sees

**Never show terminal commands** unless they explicitly ask for copy-paste for debugging.

## What to tell the user first

- **Doctor** checks Python, paths, encoding, and runtime directories after install issues or upgrades.
- You’ll summarize checks as healthy or what failed—in plain language.

## What you run (agent)

Invoke **doctor** via the launcher for this repo or another path only if they pointed you there. Report outcomes, not argv.

---
