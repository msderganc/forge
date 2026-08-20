# Plan depth reference

Used by `forge plan`, planner/architect agents, and `templates/writing-plans.md`.

See also `docs/ceremony.md` and `templates/scope-size-model.md`.

## Ceremony (user-facing)

Plan depth is **`--ceremony`**: `light` | `medium` | `detailed` | `comprehensive`.

| Band | Job | Runtime | Narrative depth | Guidance |
|------|-----|---------|-----------------|----------|
| `light` | Produce | **3 slots:** Frame+Orient → Act → Handoff (no Architect dispatch, 4-role review, pre-mortem, or docs-planning phase) | Concise sections, same task rigor | 5–10 min |
| `medium` | Pipeline | Full 7 slots, one pass, Decide ack | Full governance sections | 20–40 min |
| `detailed` | Handoff-grade | Full 7 + independent review | Deeper architecture and waves | 45–90 min |
| `comprehensive` | Adversarial | Full 7 + extra deepen | Full deepen + extra analysis | 1–2 h |

Bias **down** when unsure. Prefer `light`. Times are advisory — stop or
escalate at the top of the range.

Internally, plan still stores `plan_mode` for template contracts
(`light` → `lite`, other bands → `default`). Agents and CLI should speak
**ceremony**, not `lite`/`default`.

## Shared invariants (non-negotiable)

- No placeholder language: `TBD`, `TODO`, "implement later", "add validation", "handle edge cases" without specifics.
- Every task: exact file paths, verification command, expected outcome.
- TDD for runtime code changes (or explicit exemption for docs/config-only tasks).
- Compatible with skeleton markers, completion gates, and implement handoff.
- In scope = Recommended scope only; rejected expansions listed explicitly.

## Precedence

1. CLI `--ceremony <band>`
2. Interactive user choice (when CLI omitted on a new session)
3. Persisted preference in `.forge/memory/plan-preference.json`
4. System fallback: **`light`**

## Preference file

Path: `.forge/memory/plan-preference.json`

```json
{
  "default_ceremony": "light"
}
```

Older files with `"default_mode": "lite"|"default"` are still read and mapped
into ceremony. Saving preference affects **future new sessions** only.

Use `--save-ceremony-preference` with `--ceremony` to update the file.
