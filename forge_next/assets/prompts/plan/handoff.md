Write the handoff file and render the dashboard.

## Handoff Content
The orchestrator writes `{{HANDOFF_FILE}}` automatically with:
- Plan location (`{{PLAN_FILE}}`)
- Task count and assignments
- Dependencies summary
- Beads state

If you have additional context to include (e.g., notes from the user during
approval), append it to the handoff file after the orchestrator writes it.
Carry forward structural constraints and any baseline `J*`/`P*` finding IDs for
evaluate-pre / implement (`templates/structural-build-charter.md`).

## Dashboard
Render the skill completion dashboard per `templates/dashboard.md`.

## Completion Gate
The orchestrator checks `{{PLAN_FILE}}` for any remaining
`<!-- FORGE_SKELETON: ... -->` markers. If any are present, the workflow does
**not** complete and you'll see a warning listing the unfilled sections —
fill them and re-run this Handoff step.

## Suggested Next
- `evaluate --mode pre` (optional: review plan before implementing)
- `implement` (proceed directly to implementation)

## Plan-Phase Safety Contract (mandatory)

- Do not run git mutation commands during plan handoff (`git add`, `git commit`,
  `git push`, `git reset`, `git rebase`, `git checkout`, `git restore`,
  `git cherry-pick`, `git merge`, `git stash`, `git tag`).
- Never use `--no-verify` in any context during plan workflow steps.
- Do not include terminal command snippets in the final summary; report
  handoff status in plain language.
