# Shared process spine and ceremony

Forge pipeline skills share **one process**. Depth scales with a binding
**ceremony** band — not a different workflow per skill.

Canonical spine definition and per-skill phase maps:
[`templates/skill-process-spine.md`](../templates/skill-process-spine.md).
Control plane: `scripts/shared/ceremony.py` + `scripts/shared/skill_runner.py`.
Manifest authoring: [`declarative-skills.md`](declarative-skills.md).

## One process

Every aligned skill maps its steps onto the same slots:

| Slot | Purpose |
|------|---------|
| **Frame** | Confirm ask, load handoff, estimate/confirm ceremony |
| **Orient** | Gather context / evidence / scope |
| **Deepen** | Analysis only as deep as ceremony allows |
| **Decide** | Approval / selection / ranking |
| **Act** | Produce the skill’s primary output |
| **Verify** | Integrity checks scaled by ceremony |
| **Handoff** | Write handoff + menu |

Light may **merge** slots (e.g. Frame+Orient). Detailed/comprehensive may
**split** Deepen/Act but keep slot labels stable (`phase: Deepen — 5 Whys`).
Identical step *counts* are not required — identical **slot names** and
estimate/gate rules are.

Sketch stays conversational; ship stays finalize/preflight; ux-review may map
lightly. design, plan, diagnose, test, evaluate, implement, and code-review
align to the spine.

## Ceremony bands

| Band | Depth | Gates |
|------|-------|-------|
| **light** | Merged/short slots | Only allowlisted `soft_when` gates soften; integrity stays hard |
| **medium** | Full slots (default) | Default hardness |
| **detailed** | Full Deepen/Act | Integrity gates hard |
| **comprehensive** | Full + extra deepen as needed | Integrity gates hard |

Bias **down** when unsure. Estimate once per skill session; inherit from
handoff when present (`ceremony_source=inherited`).

State keys: `ceremony`, `ceremony_rationale`, `ceremony_source`
(`cli` | `estimated` | `escalated` | `inherited`).

Legacy depth knobs (`scope_tier`, plan `lite`, `--effort`, `--quick`) map into
ceremony internally — prefer `--ceremony` in user vocabulary.

Integrity floors (stay hard even at light): design `spec_required`, diagnose
high-severity technique gates, and other non-`soft_when` gates.

## Dual axis: mode × ceremony

Skills that already have a **mode** keep it orthogonal to ceremony:

| Skill | Mode axis | Ceremony |
|-------|-----------|----------|
| evaluate | `pre` / `post` | overlay or compound (`pre-light`) |
| test | `run` / `flows` | overlay or compound (`flows-medium`) |
| design / plan / diagnose / implement / code-review | — | ceremony only |

Ceremony must not steal the `mode` variant key. The runner selects the mode
view first, then applies ceremony (gate softening / optional step collapse).

Examples:

```bash
forge evaluate --mode pre --ceremony light --step 1
forge test --mode flows --ceremony medium --step 1
forge design --ceremony detailed --step 1
```

## CLI: `--ceremony`

Aligned skills accept:

```text
--ceremony {light,medium,detailed,comprehensive}
```

- Wins over estimate.
- `--effort` (where present) remains an alias mapped into ceremony.
- Size / scope templates: [`templates/scope-size-model.md`](../templates/scope-size-model.md).

Env kill-switch for the declarative runner (not ceremony itself):
`FORGE_SKILL_ENGINE=0` — see [`environment.md`](environment.md).

## Related

- [`templates/skill-process-spine.md`](../templates/skill-process-spine.md) — spine + mapping tables
- [`declarative-skills.md`](declarative-skills.md) — manifests and `skill_runner`
- [`environment.md`](environment.md) — `FORGE_*` and skill CLI notes
- [AGENTS.md](../AGENTS.md) — binding ceremony for agents
