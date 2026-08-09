# Plan Modes Reference

Used by `forge plan`, planner/architect agents, and `templates/writing-plans.md`.

See also `templates/scope-size-model.md`.

## Modes (legacy) and ceremony

User-facing depth is **`--ceremony`**: `light` | `medium` | `detailed` | `comprehensive`
(see `docs/ceremony.md`). Plan still stores an internal `plan_mode` for templates:

| Ceremony | Internal `plan_mode` |
|----------|----------------------|
| `light` | `lite` |
| `medium` / `detailed` / `comprehensive` | `default` |

Legacy CLI `--mode {default,lite}` still works and maps into ceremony.

| Mode | Best for | Ceremony |
|------|----------|----------|
| `lite` | **Preferred starting point** for small/uncertain/trivial work | Concise sections, same task rigor |
| `default` | Multi-module features, moderate/high risk, handoff-heavy work | Full governance sections |

Use **`light`** (or legacy `lite`) when unsure. Escalate only with clear risk.

## Shared invariants (non-negotiable)

- No placeholder language: `TBD`, `TODO`, "implement later", "add validation", "handle edge cases" without specifics.
- Every task: exact file paths, verification command, expected outcome.
- TDD for runtime code changes (or explicit exemption for docs/config-only tasks).
- Compatible with skeleton markers, completion gates, and implement handoff.
- In scope = Recommended scope only; rejected expansions listed explicitly.

## Precedence

1. CLI `--mode <default|lite>`
2. Interactive user choice (when CLI omitted on new session)
3. Persisted preference in `.forge/memory/plan-preference.json`
4. System fallback: **`lite`**

Legacy sessions without `plan_mode` in state hydrate as `lite` with a one-time note (unless tests pin an older default).

## Preference file

Path: `.forge/memory/plan-preference.json`

```json
{
  "default_mode": "lite"
}
```

Saving preference affects **future new sessions** only, not in-progress state.
