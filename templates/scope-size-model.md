# Scope size model (shared)

User-facing sizes: **small** / **medium** / **large**.

Design persistence (`design-scope.json` `scope_tier`): **`trivial`** ≡ **small**, plus `medium`, `large`.

## Bias

When unsure between two tiers, pick the **lower** one. Escalating size or promoting a **Scope expansion** item requires an explicit user yes.

## Recommended scope vs expansion

```markdown
## Recommended scope (original ask)
- …

## Scope expansion (optional — not recommended unless user opts in)
- Opportunity: …
- Delighter: …
```

- The **recommended path** is always the user's original ask (or confirmed Recommended scope).
- Opportunities and delighters stay visible under **Scope expansion** — never silently become In scope.
- Promoting an expansion usually bumps size and must re-confirm the tier.

## Ceremony bands (user-facing depth)

Prefer **`--ceremony light|medium|detailed|comprehensive`** over scattered depth knobs.
Legacy maps (read old values; write ceremony going forward):

| Ceremony | ≈ size / `scope_tier` | Plan mode | Evaluate/CR `--effort` |
|----------|------------------------|-----------|-------------------------|
| **light** | small / `trivial` | `lite` | `light` / quick |
| **medium** | medium | `default` | `standard` |
| **detailed** | large | `default` | `thorough` |
| **comprehensive** | large (max deepen) | `default` | `thorough` |

Shared spine slots and collapse rules: `templates/skill-process-spine.md`.
API: `scripts/shared/ceremony.py`.

## Ceremony matrix (by size → band)

| Size → ceremony | Sketch | Design | Plan | Evaluate | Implement | Code-review | Test | Takeover |
|------|--------|--------|------|----------|-----------|-------------|------|----------|
| **Small** → **light** (`trivial`) | Short dialogue | No formal spec; lean team | **`lite`**, ≤3 tasks | Skip heavy pre/post phases | Lean review; single branch | **`light`** + structural probes (quick subset) | Core levels; no L8–9 by default | Skip evaluate; severity-filter gates |
| **Medium** → **medium** | Normal coverage | Spec when required | lite/default by risk | Subset of phases | Standard review | **`standard`** (trimmed team) + structural | Diff-scoped gaps | Normal pipeline; severity filter |
| **Large** → **detailed** (+ comprehensive when max deepen) | Confirm upsizing | Full spec/issues | **`default`** | Full phases | Full checklist | **`thorough`** + broader structural fan-out | Full + mutation if warranted | Full pipeline |

## Structural review (every code change)

Structural probes/review stay **on** for every product-code change. Scale **fan-out**, not whether structural runs:

- Small → probes + quick structural subset (S3/S4/S8)
- Medium/large → broader set as effort warrants
- Findings outside the changed diff are **advisory** unless the change caused them

## Loop reduction

1. Batch first-pass findings before requesting changes.
2. Re-review only changed files and unresolved **critical/warning** blockers.
3. Suggestions are advisory — they do not reopen phases or block handoff.
4. Cap low-risk loops at **two rounds**, then escalate.
5. Full extra rounds only when the fix changes design boundary, public contract, security posture, or structural probe results materially.

## Prototype (future)

When one unresolved **logic/state** or **UI-shape** question cannot be settled from discussion or written options, Sketch and Design **must offer** the future `forge:prototype` skill as a decision aid (not scope expansion). See `docs/forge/prototype-skill-stub.md`. The skill is **not yet invokable**.
