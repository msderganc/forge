# pstack companion contract

Forge evaluate (plan vs code) is not pstack `/eval` (skill/prompt behavior). Do not substitute one for the other.

[pstack](https://github.com/cursor/plugins/tree/main/pstack/skills) (poteto / Lauren Tan) is an optional Cursor plugin. Forge **does not vendor** skill bodies into the forge-next source tree. `forge install` copies an **allowlist** from git into the user's editor dirs (fail-soft if the download fails). If pstack is not installed, skip companion steps; Forge still runs.

**Forge ship wins** over pstack babysit, shipping, and autopilot.

## Fail-soft

Treat pstack as absent unless a pstack skill (for example `/how`, `/interrogate`, `/unslop`) is in the agent's available skill/command list. Do not probe GitHub at runtime. If pstack is not installed, skip.

## Attach map

| pstack | Forge skill | When |
|--------|-------------|------|
| `/interrogate` | code-review | After Pass A/B, extra pressure |
| `/arena` | design | Competing shapes |
| `/how` `/why` `/teach` `/blast-radius` | diagnose, sketch | Beside Graphify, not instead of it |
| `/eval` | evaluate | Subject is a **skill/prompt**, not plan-vs-code. Upstream may ship this as a playbook rather than a skill folder — skip if absent. |
| `/recall` | takeover | Chat-history brief vs Forge session files |
| `/swarm` `/tdd` `/typescript-best-practices` `/unslop` | implement | Parallel sweeps, cheap tests, TS files, strip AI prose. MAY also use `/typescript-best-practices` in code-review when the diff is TypeScript. |
| `/tdd` | diagnose | Simple local fix |
| `/figure-it-out` `/show-me-your-work` `/technical-writing` | plan | No bundled playbook, or a committed decision trail |
| `/create-verification-skill` | test | App has no scripted prove-it path |
| visual-parity | ux-review | Pixel-match a screenshot; Forge still owns the product walk |
| `/unslop` `/technical-writing` | ship | PR/commit prose; Forge still owns merge/publish |
| `/bro` | using-forge | Restyle the last message |
| `/reflect` | docs only | After painful skill-authoring |

## Hard skips

Do not route to pstack babysit, shipping, or autopilot. Named Forge skills always win.

## Principles

pstack principle skills (laziness, subtract-before-add, prove-it-works, encode-lessons-in-structure, build-the-lever, type-system-discipline) stay upstream. Do not duplicate Forge YAGNI.

## Install

Default: `forge install` downloads https://github.com/cursor/plugins and copies the allowlisted `pstack/skills` folders. Skip with `--skip-pstack` or `FORGE_SKIP_PSTACK=1`.
