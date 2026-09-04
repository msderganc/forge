# Memory Protocol

Defines conventions for the `.forge/memory/` directory used by all agents.

When updating `project.md`, prefer **section-level** edits (do not wholesale replace the file). After changing a section, add attribution: `<!-- forge-session:{session_id} -->`.

Global `handoff-{skill}.md` may be a **pointer** to `sessions/{id}/handoff.md` — use `read_handoff` / `consume_handoff` (they resolve pointers and do not delete session handoffs).

## Memory Files

| File | Owner | Content |
|------|-------|---------|
| forge-memory-synthesis.md | Forge (auto) | **Rollup only:** rewritten on each skill state save from `project.md`, `current-step.md`, and recent `handoff-*.md` excerpts so resume and new chats can open one synthesized view. Does not replace hand-written memory; refresh by running any skill step that persists state. |
| project.md | PM | Shared context: feature name, timestamps, dependency status, autonomy level/changes, task type, scope, team composition, open findings tracker, stage markers, completion summary |
| investigation.md | Architect | Five-why analysis per finding, root causes with evidence chains |
| investigator.md | Investigator | Evidence gathered, five-why chains, MECE trees, barrier analysis |
| solution-requirements.md | Architect | Requirements Context + How-Might-We framings (+ optional Job Story). Written in brainstorming Dispatch 1 (Phase 1); read by the PM to populate Gate 1 Q1 options |
| divergent-ideas.md | Architect | Raw ideas grouped into solution families with technique tags. Written in brainstorming Dispatch 2 (Phase 2); read by the Architect itself when developing candidates in Dispatch 2 Step 3 and by Dispatch 3 when scoring |
| solutions.md | Architect | Solution options per root cause. **Draft form** (candidates only, no scoring) written in brainstorming Dispatch 2 and read by the PM to populate Gate 2 Q1 options. **Final form** (Pugh Matrix + weighted rubric scores + recommendation) overwritten in brainstorming Dispatch 3 using the user's Gate 2 Q2 priority weights |
| web-references.md | Architect | When Frontend/web UI: galleries opened, specific example URLs, Uncodixfy constraints |
| plans/*.md | Planner | Implementation plans, logged by timestamp and summary (e.g. `20260414-1926-api-change-implementation.md`) |
| planner.md | Planner | Planning decisions, task decomposition rationale, trade-offs |
| backend-dev.md | Backend Dev | Implementation notes, files changed, tests written, deviations, blockers |
| frontend-dev.md | Frontend Dev | Implementation notes, files changed, tests written, deviations, blockers |
| qa-reviewer.md | QA Reviewer | Test results, coverage analysis, findings per review round |
| security-reviewer.md | Security Reviewer | OWASP audit findings, vulnerability assessments per round |
| doc-writer.md | Doc-writer | Documentation debt tracker, doc artifacts produced, cross-session context, DOC-NEEDED items |
| critic.md | Critic | Challenges raised per stage, assumptions tested, findings |

## Handoff Files

Skills write handoff files to pass context to the next skill in the flow.

| File | Written By | Read By | Purpose |
|------|-----------|---------|---------|
| `handoff-design.md` | design | plan | Approved solutions, team composition, scope (legacy `handoff-develop.md` still read) |
| `handoff-plan.md` | plan | implement, evaluate (pre) | Plan reference, task list, dependencies |
| `handoff-evaluate.md` | evaluate | implement, plan | Evaluation findings, mode used |
| `handoff-implement.md` | implement | code-review | Branch, files changed, tests written |
| `handoff-code-review.md` | code-review | test | Review findings, open issues |
| `handoff-test.md` | test | diagnose | Test results, failures, coverage |
| `handoff-diagnose.md` | diagnose | plan, implement | Root causes, fix recommendations |

Format: see `templates/handoff-protocol.md`

## Beads ID Cross-References

Every finding, root cause, solution, and task in memory files MUST reference its beads issue ID:

### Finding: Session tokens stored in plaintext [bd-xxx.1]
### Root Cause: No encryption layer in token service [bd-xxx.2]
### Solution A: Add AES-256 encryption wrapper [bd-xxx.3]
### Task 1: Implement encryption wrapper [bd-xxx.T1]

If beads is unavailable, use sequential IDs with the same format:
### Finding: Session tokens stored in plaintext [F-001]
### Root Cause: No encryption layer [RC-001]

## Architecture Decision Records

The `.forge/adr/` directory stores Architecture Decision Records for significant design decisions:

- **Location:** `.forge/adr/NNNN-title.md`
- **Format:** Follow `templates/adr-template.md`
- **Owner:** Doc-writer creates and maintains ADRs
- **Cross-reference:** Every ADR is referenced in beads via `[bd-xxx.adrN]` format
- **Lifecycle:** proposed → accepted → (deprecated | superseded)

Create an ADR when choosing between competing approaches, introducing new patterns, or making decisions that constrain future work.

## Stage Markers

Each memory file records stage transitions:

## Stage N: IN_PROGRESS [2026-03-30 14:30]
[... stage content ...]
## Stage N: COMPLETE [2026-03-30 15:45]

## Append-Only Rule

Within a stage, memory files are append-only. New review rounds, remediation batches, and findings are appended as new sections — never overwrite previous rounds. This preserves the full audit trail.

## Cross-Skill Resume

When any skill starts, it should:
1. Read `project.md` for the Skill Flow section to understand where in the flow the session is
2. Check for its own state file (`.forge/state/{skill}.json`) — if exists, offer to resume
3. Check for handoff files from the previous skill — if the previous skill completed but this one hasn't started, pick up from there
4. If no handoff and no state file, start fresh (ask user for context if needed)

## Reading Convention

Agents read memory files in this order:
1. Read handoff file from previous skill (if exists) before other memory files
2. project.md first (shared context, current state)
3. Upstream stage files (e.g., implementation agents read the plan file from `.forge/memory/plans/` before starting)
4. Peer memory files when needed for cross-review

For actual inspection and editing, follow `templates/codex-runtime.md`.

## Writing Convention

Agents write ONLY to their own memory file. The PM is the only role that writes to project.md. If an agent needs to communicate something to another agent, it writes to its own file and the PM relays or the other agent reads it.
