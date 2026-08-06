# Skill process spine (canonical)

Every aligned Forge skill maps its manifest `phase:` labels onto these **slots**.
Ceremony (`light` | `medium` | `detailed` | `comprehensive`) scales how much of
the spine runs and how hard gates are — not a different process per skill.

## Slots

| Slot | Purpose | Typical artifacts |
|------|---------|-------------------|
| **1. Frame** | Confirm ask, load handoff, estimate/confirm ceremony | `ceremony`, rationale |
| **2. Orient** | Gather context / evidence / scope (domain-specific) | scope notes, repro, discovery |
| **3. Deepen** | Analysis only as deep as ceremony allows | options, 5 Whys, architecture, gaps |
| **4. Decide** | Approval / selection / ranking | user ack, chosen approach |
| **5. Act** | Produce the skill’s primary output | spec, plan, fix, tests, review findings |
| **6. Verify** | Integrity checks scaled by ceremony | gates soft on light; hard on detailed+ |
| **7. Handoff** | Write handoff + menu | `handoff-*.md` |

Light may **merge** slots (e.g. Frame+Orient, Act+Verify). Detailed/comprehensive
may **split** Deepen/Act but must keep slot labels stable in docs and manifests
(`phase: Deepen — 5 Whys`).

## Dual axis: mode × ceremony

Skills that already use manifest `variants` for an orthogonal concern keep that
axis:

| Skill | Mode axis | Ceremony axis |
|-------|-----------|---------------|
| evaluate | `pre` / `post` | overlay or compound (`pre-light`) |
| test | `run` / `flows` | overlay or compound (`flows-medium`) |
| design / plan / diagnose / implement / code-review | (none today) | ceremony only |

**Rule:** ceremony must not steal the `mode` variant key. Prefer a ceremony
**overlay** (soften gates / collapse steps on the mode-selected view) or
explicit compound variant names. Task 2 of the ceremony-process plan owns the
runner implementation; Task 3 is blocked until `pre-light` and `flows-medium`
selection tests pass.

## Phase → slot mapping (primary skills)

| Skill | Frame | Orient | Deepen | Decide | Act | Verify | Handoff |
|-------|-------|--------|--------|--------|-----|--------|---------|
| **design** | Startup | Scope & Team | Investigation (+ review) | Solution approval | Spec | Spec→issues / gates | Handoff |
| **plan** | Context Detection | Architecture dispatch | Plan creation | User approval | Plan file | Docs planning / markers | Handoff |
| **diagnose** | Problem framing | Reproduce & observe | 5 Whys / techniques | Rank root cause | Fix recommendation | Artifact gates | Handoff |
| **test** (run) | Context | Discovery | Failure analysis | (implicit) | Execution | Coverage gaps | Report |
| **test** (flows) | Flow context | Scope | Recommendation | Type choice | Scaffold + mocks | Execution | Report + handoff |
| **evaluate** | Plan parsing | Feasibility / completeness | Alignment / risk | Discussion triage | Report | Findings ingest | Handoff |
| **implement** | Plan detection | Branch / waves | (per-wave deepen) | Wave review | Dispatch / code | Integration | Handoff |
| **code-review** | Orient diff | Pass A/B collect | Deepen findings | Rank / discuss | Review report | Structural probes | Handoff |

Aliases are allowed in manifests when renaming would break muscle memory; list
them here when used.

## Ceremony collapse rules

| Band | Spine behavior | Gates |
|------|----------------|-------|
| **light** | Merge Frame+Orient; shorten Deepen; may merge Act+Verify | Only allowlisted `soft_when` gates soften; integrity (`spec_required`, high-severity diagnose) stay **hard** |
| **medium** | Full slot labels; normal depth | Default gate hardness |
| **detailed** | Full Deepen/Act | Integrity gates hard |
| **comprehensive** | Full + extra deepen splits as needed | Integrity gates hard |

Bias **down** when unsure. CLI `--ceremony` wins over estimate. Inherit from
handoff when `ceremony_source=inherited`.

## Related

- [`docs/ceremony.md`](../docs/ceremony.md) — user-facing spine + ceremony + `--ceremony`
- `scripts/shared/ceremony.py` — normalize / estimate / legacy maps
- `templates/scope-size-model.md` — size matrix maps onto ceremony
- [`docs/declarative-skills.md`](../docs/declarative-skills.md) — skill_runner + manifests
