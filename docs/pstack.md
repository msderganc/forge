# pstack (optional agent skills)

[pstack](https://github.com/cursor/plugins/tree/main/pstack/skills) is a third-party Cursor plugin by poteto (Lauren Tan). Forge does not vendor these skill bodies into the forge-next source tree.

Canonical agent map: [`templates/pstack-contract.md`](../templates/pstack-contract.md).

## Install (default)

`forge install` downloads the [cursor/plugins](https://github.com/cursor/plugins) git archive and copies an **allowlist** of pstack skills into:

| Host | Path |
|------|------|
| Cursor | `~/.cursor/plugins/local/pstack/` |
| Claude | `~/.claude/skills/<skill>/` |
| Codex | `~/.codex/skills/pstack/<skill>/` |

This is **on by default** (same as structural tools). Skip with:

```bash
forge install --skip-pstack
# or
set FORGE_SKIP_PSTACK=1
```

If the git download fails, Forge prints a warning and continues — Cursor/Claude/Codex Forge packs still install. pstack is not a `/forge:` command.

`forge uninstall` removes the Forge-copied pstack dests (not `using-forge` / `forge-*`).

## Host surfaces

- **Claude:** `using-forge` plus companion one-liners on source `skills/*/SKILL.md`. Named Forge skills always win. `/bro` restyles the last message when pstack is present.
- **Cursor / Codex:** thin Forge wrappers. Companions live on the preamble (`## pstack`) and source `SKILL.md` files in a Forge checkout; installed pstack skills sit beside them after `forge install`.

## Companion map

See the contract attach table. If pstack is not installed, skip. Forge still runs.
