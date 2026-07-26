Present the plan to the user for approval.

{{MODE_CONTRACT}}

**Studio (internal):** {{STUDIO_STATUS}} — optional visual summary per `templates/studio.md` (user opens URL; agents run `forge studio` internally).

**Studio log (if any):** {{STUDIO_LOG}}

**Approved UI reference (locked — use when planning):** {{STUDIO_APPROVED}}

## Plan-Phase Safety Contract (mandatory)

- This is a planning-only phase. Do not edit product code.
- Allowed edits are limited to planning artifacts (`{{PLAN_FILE}}` and
  `{{MEMORY_DIR}}/*.md` notes referenced by this workflow).
- Do not run git mutation commands: `git add`, `git commit`, `git push`,
  `git reset`, `git rebase`, `git checkout`, `git restore`, `git cherry-pick`,
  `git merge`, `git stash`, `git tag`.
- Never use `--no-verify` in any context during plan workflow steps.
- In final summaries, do not include terminal command snippets; report outcomes
  in plain language.

## Pre-Mortem (required before approval)

Run a pre-mortem analysis per `templates/pre-mortem.md`:
1. Imagine this plan was executed 6 months from now and **failed catastrophically**.
2. Each team member generates 2-3 failure scenarios (technical, process, integration, assumption, external).
3. Categorize and prioritize by likelihood × impact.
4. Add any new risks to the plan's risk register before presenting.

## Mode-aware readiness checklist

Before asking for approval, verify against **plan mode `{{PLAN_MODE}}`**:

- [ ] No placeholder language in any section (see `templates/writing-plans.md`)
- [ ] Every task has exact file paths
- [ ] Every task has verification command + expected outcome
- [ ] TDD pairing for runtime code changes (or explicit doc/config exemption)
- [ ] Structural risks surfaced if any (complexity/clone hotspot repayment, charter gaps — `templates/structural-build-charter.md`)
- [ ] `default`: full wave map, interface contracts, expanded risk/rollback, complete doc tables
- [ ] `lite`: concise sections but same correctness checks above

{{EXECUTION_PATH_NOTE}}

## Plan Summary

Read `{{PLAN_FILE}}` and present:
1. Architecture overview
2. Task breakdown (count, assigned agents, INVEST validation status)
3. Parallelization map
4. Risk register highlights (including new risks from pre-mortem)
5. Rollback strategy
6. Estimated complexity
7. Plan mode and recommended implement execution style

## User Approval

Ask the user directly for approval (per `templates/user-questions.md`).
Use this question and these options:

- Question: `Approve this implementation plan?`
  Context: `Next step is documentation planning, then handoff to implement.`
- Options:
  - `Approve` — accept the plan and continue
  - `Revise` — send it back with your feedback
  - `Simplify` — shrink scope, then re-approve
  - `Reject` — stop; the plan is not viable

Record the user's decision in `project.md`. If approved, proceed to step 6 (documentation planning), then handoff on step 7.
If changes requested, return to step 3 (plan creation).
The orchestrator asks for confirmation before advancing from this step.