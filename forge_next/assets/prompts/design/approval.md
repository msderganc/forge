# Stage 3 — Solution Review & User Approval

{{DEVELOP_NO_EDIT_POLICY}}

## Review Loop
Per `templates/review-loop.md`:
| Step | Agent | Focus |
|------|-------|-------|
| Self-review | Architect | Honest cons? Consistent scores? |
| Cross-review | Security Reviewer + QA | Security implications? Testability? |
| Critic challenge | Critic | Worst-case outcome? Understated risks? |
| PM validation | PM | Enough info for user to choose? |
| Pre-mortem | All agents | Imagine this solution failed — what happened? |

Before presenting to the user, run a pre-mortem per `templates/pre-mortem.md`. Each agent generates 2-3 failure scenarios. Categorize, prioritize, and add mitigations to the risk assessment. Record any findings that change the recommendation.

## User Approval

Present scored solutions summary:
{{SOLUTIONS_SUMMARY}}

**Scope / spec track (from orchestrator):**

- **Scope tier:** {{SCOPE_TIER}}
- **Spec required:** {{SPEC_REQUIRED}}
- **Spec gate status:** {{SPEC_GATE_STATUS}}

Frame approval as **closure of a design conversation**, not a rubber stamp. If the user hesitates, explore why—**Revise** and **Alternate** are healthy paths that keep creative iteration alive.

- **YAGNI / scope:** Recommend the option that satisfies **Recommended scope** with the least surface area. If scored options include speculative breadth or Scope expansion items, call them out as **not recommended** unless the user explicitly opts in.
- **Loop reduction:** Batch review findings; suggestions are advisory; do not reopen approval for nits (see `templates/scope-size-model.md`).
- **Structural charter:** Prefer the option that keeps functions under complexity budget, avoids planned duplication, keeps deps acyclic, and does not invent speculative public APIs (`templates/structural-build-charter.md`).
- **Evidence:** The recommendation should rest on investigation outputs and explicit criteria — not untested assumptions. Flag gaps before the user approves.

Then ask the user directly for approval (per `templates/user-questions.md`).

### Solution decision

Use this question and these options (rewrite jargon at presentation time if needed):

- Question: `Go with the recommended solution?`
  Context: `This locks the approach before we write/finalize the design spec (when required) and hand off to planning.`
- Options:
  - `Approve` — use the recommendation and continue
  - `Revise` — keep exploring with your feedback
  - `Alternate` — pick a different scored option instead
  - `Reject` — stop; none of these are acceptable

### Design spec decision (only when `SPEC_REQUIRED` is **yes**)

After the user approves a solution direction, they must still approve the **written design spec** (see appended `spec_gate` block on this step when applicable). Until the spec file exists, self-review passes, **and** the user explicitly approves the spec, wait for confirmation before advancing to `forge design --step 7` (spec → issues). The orchestrator asks before continuing.

Record the user's decision in `project.md` and branch accordingly.
