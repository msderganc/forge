# Uncodixfy companion contract

[Uncodixfy](https://github.com/cyxzdev/Uncodixfy) (cyxzdev) is an optional agent skill that blocks generic AI/Codex UI: glass shells, pill overload, hero-in-dashboard, decorative eyebrows, oversized radii, and the rest of the default generated aesthetic. It pushes toward **normal** product UI (Linear, Raycast, Stripe, GitHub).

Forge **does not vendor** the skill body into the forge-next source tree. `forge install` copies `SKILL.md` (and companion files) from git into the user's editor skill dirs (fail-soft if the download fails). If Uncodixfy is not installed, skip companion steps; Forge still runs.

**Named Forge skills always win.** Uncodixfy does not replace `forge:design`, `forge:implement`, or Studio gates. It is a UI-taste filter on top of an approved direction.

## Fail-soft

Treat Uncodixfy as absent unless `/uncodixfy` (or a skill named `uncodixfy`) is in the agent's available skill/command list. Do not probe GitHub at runtime. If Uncodixfy is not installed, skip — still use [`templates/web-design-references.md`](web-design-references.md) for galleries.

## Attach map

| Companion | Forge skill | When |
|-----------|-------------|------|
| `/uncodixfy` | **design** | Frontend / web / landing / product UI. After visual research, before locking generated mockups or recommending a look. |
| `/uncodixfy` | implement (Frontend Dev) | Whenever generating HTML, CSS, React, Vue, Svelte, or other frontend UI. Self-triggers from the installed skill; design should already have recorded Uncodixfy constraints in `web-references.md`. |

## How design uses it

1. If the work is web/UI, read [`templates/web-design-references.md`](web-design-references.md) and pick galleries.
2. If `/uncodixfy` is available, **read and apply it** before proposing or generating screens (Studio HTML, candidate mockups, component-kit recommendations).
3. Record banned patterns and the chosen palette source in `web-references.md`.
4. Do not let award-site experimental chrome become the default for app/dashboard UI.

## Install / update / uninstall

Default: `forge install` downloads https://github.com/cyxzdev/Uncodixfy and copies the skill into:

| Host | Path |
|------|------|
| Cursor | `~/.cursor/plugins/local/uncodixfy/` |
| Claude | `~/.claude/skills/uncodixfy/` |
| Codex | `~/.codex/skills/uncodixfy/` |

Re-run `forge install` to **update** (replace in place). `forge uninstall` removes those dests (not `using-forge` / `forge-*`). Skip with `--skip-uncodixfy` or `FORGE_SKIP_UNCODIXFY=1`.

Guide: [`docs/uncodixfy.md`](../docs/uncodixfy.md).
