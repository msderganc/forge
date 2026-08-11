---
name: forge-ship
description: >-
  Finalize work: commit, push, PR, merge, and publish release artifacts. Use when the user says ship, finalize, release, commit and push, open a PR, merge, or publish.
---

## Graphify preflight

When `graphify-out/` exists, run first:

```bash
forge ship --step 1
```

Other workflow commands do not print GRAPHIFY per step.

## Agent

Follow the ship skill in `.cursor/skills/ship/SKILL.md` (or user-scoped copy). Use git and `gh`; never commit secrets or force-push main unless explicit.
