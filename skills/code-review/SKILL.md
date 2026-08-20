---
description: |
  Multi-mode code review: PR, deep, or architecture. Trimmed team by default;
  structural probes always on (scale fan-out). Supports --effort
  light|standard|thorough (--quick is an alias for --effort light).
---

# Forge Code Review — Multi-Mode Review

## Skill contract

- **Use when:** implemented changes (PR, branch, or files) need spec + standards review before shipping.
- **Do not use when:** nothing has been implemented yet, or you only need a plan critique (use `evaluate --mode pre`).
- **Input:** PR/branch/file target. **Output artifact:** findings report across Pass A (spec) and Pass B (standards/structural).
- **Stops at:** handoff to `test` — code-review does not fix findings or run the test suite itself.
- **Small-path behavior:** `--effort light` (alias `--quick`) uses Architect + QA only; structural stays on with the S3/S4/S8 quick subset (unrelated findings advisory).

See `templates/scope-size-model.md` and `templates/workflow-skill-preamble.md` for shared sizing/ceremony rules.

Two-axis review aligned with [mattpocock/skills code-review](https://github.com/mattpocock/skills/blob/main/skills/engineering/code-review/SKILL.md): **Pass A — Spec** (intent/requirements) and **Pass B — Standards** (repo standards + `templates/standards-review-baseline.md`). Structural probes at step 3 are Pass B tooling. Findings are reported per axis — do not merge or rerank across axes.

Shared runtime: [templates/workflow-skill-preamble.md](../../templates/workflow-skill-preamble.md).

## pstack companion

After Pass A/B, if the pstack plugin is installed, optionally run `/interrogate` on the same diff for extra multi-model pressure. Not a substitute for Forge code-review. Canonical map: `templates/pstack-contract.md`. If pstack is not installed, skip.

**Structural probes are always on** unless `--no-structural`. At step 3 the orchestrator runs probes (**pyscn** / **knip** when applicable) and writes `.structural-probes.json`. Fan-out scales with effort: **S3/S4/S8** for `light`/`standard`; full S1–S8 for `thorough`. Prefer diff-scoped findings; unrelated hits stay advisory.

**Team by effort:** `light` = Architect + QA; `standard` = Architect + QA (+ Security when auth/data); `thorough` = full six. Escalate to thorough only when ≥2 signals agree (keyword **and** file breadth).

**Steps 4–6 are blocked** only when structural probes are enabled and have not yet run (`pass` or `fail`, not `skip`). Re-run step 3 or use `--allow-structural-probes-incomplete` with override reason/follow-up to bypass. When structural probes are disabled via `--no-structural`, steps 4–6 proceed without a probe gate.

## Simplicity

Preamble § Simplicity (YAGNI). Flag over-engineering and **Speculative Generality** (`templates/standards-review-baseline.md`, `templates/code-smells.md`).

<invoke cmd="forge code-review" />

| Argument | Required | Description |
|----------|----------|-------------|
| `--step` | Yes | Phase 1–6 |
| `--mode` | No | `pr`, `deep`, or `architecture` (auto-detected) |
| `--target` | Step 1 | PR, branch, or file paths |
| `--effort` | No | `light`, `standard` (default), or `thorough` — replaces `--quick`. `light` = Architect + QA; `standard` = Architect + QA (+ Security if auth/data); `thorough` = full six |
| `--structural` / `--no-structural` | No | Structural is **on by default**. `--no-structural` opts out; `--structural` forces on |
| `--quick` | No | Alias for `--effort light` (kept for backward compatibility) |

At **step 1**, the orchestrator **recommends** `--effort` from mode, implement handoff scope, and target (printed in the prompt). CLI flags override the recommendation. Restart step 1 to change config mid-session.

Default handoff: **`forge:test`**.
