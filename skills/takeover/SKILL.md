---
description: |
  Infer epic from repo state and drive Forge skills until ship-ready.
  Replaces resume and iterate.
---

# Forge Takeover

## Skill contract

- **Use when:** resuming or inferring in-flight work and driving Forge skills through to ship-ready without manual step-by-step invocation.
- **Do not use when:** you already know exactly which single skill to run next — invoke that skill directly instead.
- **Input:** repo state (+ optional `--issue`/`--design`/`--goal`). **Output artifact:** route plan + gated progression through child skill steps to a ship handoff.
- **Stops at:** handing off to `ship` once all step gates pass — takeover does not perform the ship steps itself.
- **Small-path behavior:** small/`trivial` scope skips evaluate pre/post; severity-filtered gates (critical+warning only); code-review `--effort light`; diagnose `simple` can short-circuit toward test/ship.

See `templates/scope-size-model.md` and `templates/workflow-skill-preamble.md` for shared sizing/ceremony rules.

Shared runtime: [templates/workflow-skill-preamble.md](../../templates/workflow-skill-preamble.md).

## pstack companion

Optionally run `/recall` for a chat-history brief vs Forge session files. Canonical map: `templates/pstack-contract.md`. If pstack is not installed, skip.

<invoke cmd="forge takeover" />

| Argument | Purpose |
|----------|---------|
| `--issue` | GitHub issue number or URL |
| `--design` | Path to design spec |
| `--goal` | Override default ship-ready goal |
| `--cleanup` | Legacy state file cleanup (dry-run) |

Polls `.forge/.takeover-gates/*.json` between child skills. See `forge takeover --help`.

| Step | Phase | Gate |
|------|-------|------|
| 1 | Initialize + route | — (infers entry skill, writes route plan) |
| 2 | Upstream / continue | `upstream.json` — `status: pass` |
| 3 | Plan + evaluate (pre) | `plan.json` (`status: pass`) then `evaluate-pre.json` (`open_findings_total: 0`) |
| 4 | Implement + evaluate (post) | `implement.json` (`status: pass`) then `evaluate-post.json` (`open_findings_total: 0`) |
| 5 | Code review + test | `code-review.json` (`open_findings_total: 0`) then `test.json` (`failed: 0`) |
| 6 | Report | — (writes summary, hands off to ship) |

**Steps 2–5 await their gate**: each re-runs the *same* step until its gate file passes, then advances. Write the gate JSON described in the step output and re-invoke the same `--step` to re-check.
