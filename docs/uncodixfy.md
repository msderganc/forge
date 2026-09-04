# Uncodixfy (optional UI skill)

[Uncodixfy](https://github.com/cyxzdev/Uncodixfy) is a third-party agent skill that stops generic AI UI patterns. Forge does not vendor the skill body into the forge-next source tree.

Canonical agent map: [`templates/uncodixfy-contract.md`](../templates/uncodixfy-contract.md). Visual research galleries live in [`templates/web-design-references.md`](../templates/web-design-references.md).

## Install (default)

`forge install` downloads the [cyxzdev/Uncodixfy](https://github.com/cyxzdev/Uncodixfy) git archive and copies the skill into:

| Host | Path |
|------|------|
| Cursor | `~/.cursor/plugins/local/uncodixfy/` |
| Claude | `~/.claude/skills/uncodixfy/` |
| Codex | `~/.codex/skills/uncodixfy/` |

This is **on by default** (same as pstack). Skip with:

```bash
forge install --skip-uncodixfy
# or
set FORGE_SKIP_UNCODIXFY=1
```

Override source with `--uncodixfy-repo-url` and `--uncodixfy-ref` (default `main`).

If the git download fails, Forge prints a warning and continues — Cursor/Claude/Codex Forge packs still install. Uncodixfy is not a `/forge:` command; invoke it as `/uncodixfy` when present.

## Update

Re-run `forge install` (without `--skip-uncodixfy`). The copy **replaces** the previous dests.

## Uninstall

`forge uninstall` removes the Forge-copied Uncodixfy dests (not `using-forge` / `forge-*`).

## Host surfaces

- **Design:** when the work is a web app or site, consult galleries then apply Uncodixfy before locking a look. See the contract attach map.
- **Implement:** the installed skill self-triggers on frontend generation. If it is not installed, skip.

Named Forge skills always win. If Uncodixfy is not installed, skip. Forge still runs.
