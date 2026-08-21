# Shared process spine and ceremony

Forge pipeline skills share **one process**. Ceremony is a **job**, not four
volumes of the same spine. Depth, review, and duration follow the band.

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

Light **merges** slots (plan light is Frame+Orient → Act → Handoff). Unused
band names **alias down** to the highest band that skill actually implements.
Detailed/comprehensive may **split** Deepen/Act but keep slot labels stable
(`phase: Deepen — 5 Whys`). Identical step *counts* are not required — identical
**slot names** and estimate/gate rules are.

Sketch stays conversational; ship stays finalize/preflight; ux-review may map
lightly. design, plan, diagnose, test, evaluate, implement, and code-review
align to the spine.

## Ceremony bands (jobs)

| Band | Job | Unique mechanic | Guidance |
|------|-----|-----------------|----------|
| **light** | **Produce** | Parent only, merged slots, no review round, stop at the artifact | 5–10 min typical |
| **medium** | **Pipeline** | Full slots, one pass, Decide ack | 20–40 min |
| **detailed** | **Handoff-grade** | Independent second role + resume sidecars | 45–90 min |
| **comprehensive** | **Adversarial** | N independent attempts, then graft | 1–2 h |

Times are **advisory** (prompts and using-forge), not runner timers. Stop or
escalate at the top of the range — do not “keep going because steps remain.”

**Alias-down:** if a skill has no unique mechanic for a band, the name still
parses but behaves as the next unique band below it (comprehensive → detailed →
medium). Plan, design, and code-review are the skills that earn all four jobs.
This release **collapses runtime steps** only for **plan + light** (7 → 3).

Integrity floors stay hard even at light: design `spec_required`, diagnose
high-severity technique gates, plan `plan_skeleton`, and other non-`soft_when`
gates. Only allowlisted `soft_when` gates soften.

Bias **down** when unsure. Estimate once per skill session; inherit from
handoff when present (`ceremony_source=inherited`).

State keys: `ceremony`, `ceremony_rationale`, `ceremony_source`
(`cli` | `estimated` | `escalated` | `inherited`).

Legacy depth knobs (`scope_tier`, internal plan narrative `plan_mode`, `--effort`,
`--quick`) still map into ceremony for estimates — user-facing plan depth is
**`--ceremony` only** (the old plan `--mode default|lite` flag was removed).
`--ceremony` keeps `plan_mode` in sync (`light` → `lite`, other bands → `default`),
including mid-session CLI overrides.

## Per-skill duration (floors)

Global ladder above is the default. These skills spend longer on light because
the artifact *is* the investigation:

| Skill | Light | Notes |
|-------|-------|--------|
| sketch, design, plan | 5–10 min | Plan light is three slots (Frame+Orient / Act / Handoff) |
| diagnose | 10–20 min | Repro is the floor |
| evaluate `--mode post` | 10–20 min | Audit vs plan |
| implement | 10–25 min | Coding floor |
| ux-review | 15–25 min | Real-browser walk |
| test | suite wall-clock is a **second clock** | Probes / browser / full suite sit on top of ceremony |
| takeover | **sum of children** | Not a separate band budget |

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
forge plan --ceremony light --step 1
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
