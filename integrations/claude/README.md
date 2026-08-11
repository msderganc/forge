# Forge + Claude Code integration (v1)

This pack installs **slash commands** and **auto-triggerable skills** for Claude Code.

Commands are Markdown files with YAML frontmatter under `commands/`. Skills are
`skills/<name>/SKILL.md` trees installed flat into `~/.claude/skills/` so Claude
can match `description:` fields (same path Superpowers uses).

## Prerequisite

Install the CLI:

```bash
pipx install forge-next
```

Verify:

```bash
forge doctor
```

## Install

### Default location (via `forge install`)

By default, `forge install --claude` copies:

| Artifact | Destination |
| --- | --- |
| Slash commands | `~/.claude/commands/forge/` (Windows: `%USERPROFILE%\.claude\commands\forge\`) |
| Skills (`using-forge` + `forge-*`) | `~/.claude/skills/` |
| Graphify hooks | `~/.claude/settings.json` via `forge claude-graphify` |

Override the commands directory with `forge install --claude-dir <path>`.

Restart Claude Code after installing so `/help` and skill discovery pick up changes.

### Why skills (not just slash commands)

Slash commands are primarily user-invoked (`/forge:plan`). Skills with trigger-rich
`description:` fields are what Claude auto-selects when you say “plan” or
“implement”. The **`using-forge`** meta-skill parses intent and routes to the
matching `forge-*` skill before ad-hoc work or competing process skills.

### Graphify hooks

`forge install --claude` also merges Graphify hooks into `~/.claude/settings.json`
(or re-run anytime):

```bash
forge claude-graphify
```

Hooks invoke **`/path/to/forge claude-graphify-hook <event>`** (absolute pipx
`forge` binary written by `forge claude-graphify` — never bare
`python -m forge_next` on `/usr/bin/python`).

- **SessionStart** — remind when `graphify-out/` exists
- **PreToolUse** — all tools (close unused sub-agents); **Grep**, **Glob**,
  **Read**, and search-like **Bash** also get Graphify context when indexed
- **UserPromptSubmit** — when the prompt mentions `forge:` / `$forge:`

After `pipx upgrade forge-next`, re-run `forge install --claude` and
`forge claude-graphify`, then restart Claude Code.

Workflow slash commands include **Hard rule — Graphify**. Graphify refresh runs
at **ship** (`forge ship --step 1`); workflow steps do not print per-step
GRAPHIFY banners. See `docs/graphify.md`.

See [`docs/graphify.md`](../../docs/graphify.md) for the full picture (Codex
policy, `FORGE_SKIP_GRAPHIFY`, troubleshooting).

## Commands

Definitions live in `integrations/claude/commands/` as `<subcommand>.md` (for
example `diagnose.md`, `code-review.md`). They align with
[`integrations/spec/commands.json`](../spec/commands.json) and
[README.md](../../README.md#commands-in-your-apps):

| Slash command (frontmatter `name`) | Runs |
| --- | --- |
| `forge:sketch` | `forge sketch …` |
| `forge:design` | `forge design …` |
| `forge:plan` | `forge plan …` |
| `forge:evaluate` | `forge evaluate …` |
| `forge:implement` | `forge implement …` |
| `forge:code-review` | `forge code-review …` |
| `forge:test` | `forge test …` |
| `forge:diagnose` | `forge diagnose …` |
| `forge:takeover` | `forge takeover …` |
| `forge:status` | `forge status …` |
| `forge:doctor` | `forge doctor …` |
| `forge:graphify` | `forge graphify …` |
| `forge:ship` | `forge ship …` |

## Skills

Installed under `~/.claude/skills/`:

| Skill | Role |
| --- | --- |
| `using-forge` | Meta router — parse intent, prefer Forge over freestyle/Superpowers delivery flows |
| `forge-plan` / `forge-implement` / … | Workflow skills Claude can auto-match |

How Claude surfaces slash commands depends on version/UI (often under a `forge`
namespace from the install directory). If a command does not appear, confirm
files are under `~/.claude/commands/forge/` and each file begins with `---`
frontmatter plus a non-empty markdown body. If skills do not auto-trigger,
confirm `~/.claude/skills/using-forge/SKILL.md` and `forge-plan/SKILL.md` exist,
then restart Claude Code.

**Aliases:** Claude does not load separate `/f:…` or bare `/diagnose` aliases
from this pack; use the `forge:<subcommand>` id in frontmatter (same as Cursor’s
`/forge:<subcommand>` intent). **`forge develop`** is a deprecated CLI alias for
**`forge design`** only (not a separate slash command).
