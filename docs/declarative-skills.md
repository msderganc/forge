# Declarative skill engine

Forge pipeline skills are driven by YAML **manifests** plus a shared **skill runner**.
Per-skill orchestrator step loops are thin shims (or kill-switch legacy bodies).
Methodology stays in prompts/templates; Python is the control plane (CLI, sessions,
hard gates).

## Success metrics (this initiative)

Measure progress as:

1. **Orchestrator LOC deleted** — step-loop bodies replaced by shims calling `run_skill`
2. **Schema gates** for design / evaluate / test sidecar **shapes** (`schema_gate`)
3. **Diagnose on the runner** with **all gates `kind: python`** (register validators stay Python)

Do **not** measure success as “all skills fully declarative” or “diagnose schema-primary.”
Diagnose methodology enforcement (causal linkage, symptom rejection, high-severity
techniques) remains Python by design for this release.

## Runner

Entry: `scripts/shared/skill_runner.py` → `run_skill(skill, argv)`.

Typical flow:

1. Load `skills/<skill>/manifest.yaml` (checkout) or packaged `forge_next/assets/skills/`
2. Parse shared CLI (`build_base_parser`) + manifest `cli_flags` / optional `pre_run`
3. Resolve session state, render the step prompt, run declared gates
4. Write handoff / menu on the final step

Kill-switch: set **`FORGE_SKILL_ENGINE=0`** to force the legacy `*_legacy.py` /
`orchestrate_legacy.py` body when present (skips the runner).

## Manifests

Authoring source of truth: `skills/<skill>/manifest.yaml` (`manifest_version: 1`).

Declared hooks (cap — no undeclared plugin surface):

| Hook | Role |
|------|------|
| `cli_flags` | Extra argparse flags on the shared parser |
| `gates` | Per-step validation (`kind: schema` or `kind: python`) |
| `pre_run` | Callable after parse (e.g. reject invalid modes) |
| `variables_callable` | Per-step template variables (`module.path:function`) |

Phases for migrated skills live **only** in the manifest. `scripts/shared/skill_phases.py`
is a fallback for unmigrated names (e.g. `iterate`) and still does manifest-first lookup.

## Gate kinds

| Kind | Behavior |
|------|----------|
| `schema` | Validate sidecar JSON shape via `scripts/shared/schema_gate.py` + files under `schemas/sidecars/` |
| `python` | Call `callable: "module.path:function"` with `(state=, step=, state_path=, gate=)` |

Design / evaluate / test use schema gates for shape (design keeps residual python for
on-disk spec path + boolean invariants). **Diagnose uses python escapes only** — there
are **no** `schemas/sidecars/diagnose/*` files in this release.

## Ship dual layout

| Concern | Path |
|---------|------|
| Engine manifest | `skills/ship/manifest.yaml` → synced to `forge_next/assets/skills/ship/` |
| Human SKILL docs | `.cursor/skills/ship/SKILL.md` and integration copies |

Do **not** relocate ship `SKILL.md` into `skills/ship/` as part of the declarative engine.

## Asset sync

Authoring trees:

- `skills/*/manifest.yaml`
- `schemas/sidecars/**/*.schema.json`

Packaged mirrors:

- `forge_next/assets/skills/`
- `forge_next/assets/schemas/`

Sync with:

```bash
python scripts/release/sync_skill_assets.py
```

`tests/test_skill_assets.py` asserts full-tree parity. Do not hand-edit packaged assets
as the primary source.

## Diagnose stance

- Step loop: `run_skill("diagnose")` via thin `scripts/diagnose/orchestrate.py`
- Legacy: `orchestrate_legacy.py` when `FORGE_SKILL_ENGINE=0`
- Vars: `scripts/diagnose/diagnose_vars.py` (must not import `skill_runner`)
- Gates: `scripts.diagnose.diagnose_gates` / register validators as **python** escapes
- Optional future ADR may revisit register schemas; not a success criterion here

## Related

- [`environment.md`](environment.md) — `FORGE_*` variables including kill-switch
- [`AGENTS.md`](../AGENTS.md) — orchestration contracts and handoffs
- [`sessions.md`](sessions.md) — `.forge/sessions/` layout
