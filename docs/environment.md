# Forge environment variables

Truth values are usually `1`, `true`, `yes`, or `on` (case-insensitive) unless noted.

## Session and lifecycle

| Variable | Default | Effect |
|----------|---------|--------|
| `FORGE_SKIP_SESSION_OPTIN` | off | Suppress step-1 session opt-in banner |
| `FORGE_SKIP_AUTO_CLOSE` | off | Disable step-1 auto-close of superseded sessions |
| `FORGE_STEP1_ABANDON_HOURS` | `1` | Hours before idle step-1-only sessions are auto-closed |
| `FORGE_STALE_SESSION_HOURS` | `24` | Stale session threshold for takeover/status |
| `FORGE_SESSION_MAX_AGE_DAYS` | `7` | Automatic archive age for session directories |
| `FORGE_SKIP_SESSION_CLEANUP` | off | Disable automatic session archive |
| `FORGE_AUTO_PARALLEL_ON_CONFLICT` | `1` | **Evaluate only:** auto-suffix evaluate state files on conflict. Pipeline skills always allocate a new `.forge/sessions/{id}/` at step 1 regardless of this flag. |
| `FORGE_KEEP_LEGACY_RUNTIME` | off | Keep `.codex/forge*` after migrate (skip archive to `.forge/_archive/`) |

## Graphify

| Variable | Effect |
|----------|--------|
| `FORGE_SKIP_GRAPHIFY` | Disable ship GRAPHIFY banner and background refresh |
| `FORGE_SKIP_GRAPHIFY_REFRESH` | Suppress background `forge graphify refresh` only |
| `FORGE_SKIP_GRAPHIFY_SESSION_REFRESH` | Suppress Claude SessionStart background refresh |
| `FORGE_GRAPHIFY_COMMAND` | Shell command to rebuild graph (default `graphify update .`) |

Per-clone prefs: `forge graphify on|off|status` writes `.forge/state/graphify-prefs.json`. See [graphify.md](graphify.md).

## Structural quality

| Variable | Effect |
|----------|--------|
| `FORGE_SKIP_STRUCTURAL_TOOLS` | Skip install and probe runs |
| `FORGE_STRUCTURAL_PROBES_AUTO` | Force auto-run on more steps |
| `FORGE_STRUCTURAL_PROBES_MANUAL` | Planning-only (no auto-run) |
| `FORGE_SKIP_STRUCTURAL_EIGHT_AGENTS` | Skip eight-agent dispatch block |
| `FORGE_STRUCTURAL_EIGHT_AGENTS_FULL` | Full eight-agent dispatch (not default trio) |
| `FORGE_SKYLOS_AUDIT` | Full Skylos audit (not dead-code-only) |
| `FORGE_KNIP_COMMAND` / `FORGE_MADGE_COMMAND` / `FORGE_JSCN_COMMAND` / `FORGE_PYSCN_COMMAND` / `FORGE_SKYLOS_COMMAND` | Override probe commands |
| `FORGE_BD_COMMAND` | Override Beads CLI (default: `bd` on PATH); may be multi-token (e.g. `uv run bd`) |
| `FORGE_STRUCTURAL_TOOLS_PREFIX` | Install prefix (Windows Store Python) |

See [structural-quality.md](structural-quality.md).

## Integrations and paths

| Variable | Effect |
|----------|--------|
| `FORGE_WORKFLOW_INVOCATION` | Agent handoff prefix: `slash` → `/forge:…` (Cursor/Claude); `dollar` → `$forge:…` (Codex). Auto: `CURSOR_*` / `CLAUDE_CODE` → slash; `CODEX_HOME` → dollar; repos with `.cursor/` → slash. Override when Codex runs inside a Cursor checkout. |
| `FORGE_REPO` | Override detected writable git root (rare; Forge normally picks a writable alias automatically — see `.forge/adaptation.json`) |
| `FORGE_USE_LAUNCHER` | Set by `forge` CLI (internal) |
| `FORGE_ASCII` | ASCII-only banners (Windows consoles) |
| `FORGE_SKIP_SUBAGENT_LIFECYCLE` | Disable Cursor subagent hooks |
| `FORGE_SKIP_PSTACK` | Skip copying allowlisted pstack skills during `forge install` |
| `FORGE_SKILL_ENGINE` | Default on. Set to `0` to force legacy skill orchestrator bodies instead of `run_skill` (see [declarative-skills.md](declarative-skills.md)) |

## Studio (internal)

| Variable | Effect |
|----------|--------|
| `FORGE_STUDIO_TOKEN` | Auth token for localhost Studio server |
| `FORGE_STUDIO_SESSION_DIR` / `FORGE_STUDIO_HOST` / `FORGE_STUDIO_PORT` | Studio server (internal) |

See [studio.md](studio.md) — not a user-facing workflow.

## Skill CLI flags (common)

Aligned pipeline skills accept a shared depth flag (orthogonal to skill-specific
`--mode` where present). Full contract: [`ceremony.md`](ceremony.md).

| Flag | Values | Effect |
|------|--------|--------|
| `--ceremony` | `light` \| `medium` \| `detailed` \| `comprehensive` | Binding job for the session; wins over estimate; persisted on state. **Plan light** collapses to 3 steps. |
| `--effort` | skill-specific (e.g. code-review `light`/`standard`/`thorough`) | Legacy alias → mapped into ceremony where supported |

Examples: `forge design --ceremony light --step 1`, `forge evaluate --mode pre --ceremony light --step 1`, `forge test --mode flows --ceremony medium --step 1`.

## CI quick reference

```bash
export FORGE_SKIP_SESSION_OPTIN=1
export FORGE_SKIP_GRAPHIFY=1
```

Optional: `FORGE_SKIP_STRUCTURAL_TOOLS=1` when probes are not installed in CI.
Optional: `FORGE_SKIP_PSTACK=1` to skip copying pstack skills during `forge install`.
