# Forge integrations

This folder contains wrapper artifacts for editor/agent environments that call the global `forge` CLI.

## Prerequisite (all environments)

Install the CLI once:

```bash
pipx install forge-next
```

Verify:

```bash
forge doctor
```

## Contents

- `spec/commands.json`: single source of truth for supported commands and examples.
- `cursor-plugin/`: Cursor plugin bundle (`/forge:<subcommand>` slash commands).
- `claude/`: Claude Code command pack (v1).
- `codex/`: Codex skill pack (v1).

Layout for Cursor/Claude slash commands and Codex skills is enforced by `pytest tests/test_integration_install_layout.py` (matching `<cli_subcommand>.md` files under `cursor-plugin/commands/` and `claude/commands/` to `spec/commands.json`, and Codex `SKILL.md` folders).

### Slash command naming (Cursor / Claude)

- **Supported:** `/forge:<subcommand>` (for example `/forge:diagnose`). Command files are named `<subcommand>.md`; the plugin namespace is `forge` (see `cursor-plugin/.cursor-plugin/plugin.json`).
- **Cursor agent skills:** `forge install --cursor` also bundles `integrations/codex/skills/` under the plugin’s `skills/` directory so the agent can load workflows without installing the Codex pack into `~/.codex/skills/`.
- **Not supported** by current Cursor plugin schema: alias fields, `/f:<subcommand>`, or unscoped `/diagnose`. Codex uses `$forge:<subcommand>` via skill `name:` in each `SKILL.md` (skill folders remain `forge-<subcommand>/` on disk).

### Graphify (optional codebase map)

See [`docs/graphify.md`](../docs/graphify.md). Refresh at **ship** (`forge ship --step 1`); workflow steps do not print per-step GRAPHIFY banners.

| Environment | Setup |
|-------------|--------|
| **Claude** | `forge install --claude` or `forge claude-graphify` |
| **Codex** | `forge install --codex` or `forge codex-agents --force` |
| **Cursor** | Repo `.cursor/rules/graphify.mdc` + command bodies |

### pstack (optional agent skills)

[pstack](https://github.com/cursor/plugins/tree/main/pstack/skills) (poteto). `forge install` copies an allowlist from git by default. Skip with `--skip-pstack`. Guide: [`docs/pstack.md`](../docs/pstack.md). Canonical map: [`templates/pstack-contract.md`](../templates/pstack-contract.md).

### Uncodixfy (optional UI skill)

[Uncodixfy](https://github.com/cyxzdev/Uncodixfy). `forge install` copies the skill from git by default. Skip with `--skip-uncodixfy`. Guide: [`docs/uncodixfy.md`](../docs/uncodixfy.md). Canonical map: [`templates/uncodixfy-contract.md`](../templates/uncodixfy-contract.md). Design galleries: [`templates/web-design-references.md`](../templates/web-design-references.md).

### Structural quality probes (optional)

`forge install` installs **knip**, **madge**, and **pyscn** by default for Pass B review in code-review and evaluate (warns on any missing). See [`docs/structural-quality.md`](../docs/structural-quality.md).

