# forge-codex team — Memory System

This directory contains the shared memory files for a forge-codex team session.

## Files

| File | Owner | Purpose |
|------|-------|---------|
| `project.md` | PM | Shared context, stage markers, autonomy log, findings tracker, Skill Flow section, completion summary |
| `studio-log.md` | Studio (auto) | Append-only browser gate feedback (clicks, probes, freeform). Read via `{{STUDIO_LOG}}` in develop/plan; summarize into `project.md` when gates close |
| `studio-approved-index.md` | Studio (auto) | Index of user-approved locked HTML under `.forge/studio/approved/`. Read via `{{STUDIO_APPROVED}}` in develop/plan/implement |
| `investigation.md` | Architect | Five-why analysis, findings, root causes with evidence |
| `investigator.md` | Investigator | Evidence gathered, five-why chains, MECE trees, barrier analysis |
| `solution-requirements.md` | Architect | Brainstorming Phase 1 output — Requirements Context + How-Might-We framings. Written in Dispatch 1, consumed by brainstorming Gate 1 |
| `divergent-ideas.md` | Architect | Brainstorming Phase 2 output — raw ideas grouped into solution families. Written in Dispatch 2, consumed by the Architect in Dispatch 3 (not by a gate directly) |
| `solutions.md` | Architect | Solution options per root cause. Exists in two states: **draft** (written in Dispatch 2 Phase 3 Steps 1–3, consumed by brainstorming Gate 2) and **final** (overwritten in Dispatch 3 with Pugh Matrix, weighted scoring, recommendation) |
| `web-references.md` | Architect | When Frontend/web UI: galleries opened, specific example URLs, Uncodixfy constraints |
| `plans/*.md` | Planner | Implementation plans, logged by timestamp and summary (e.g. `20260414-1926-api-change-implementation.md`) |
| `planner.md` | Planner | Planning decisions, task decomposition rationale, trade-offs |
| `backend-dev.md` | Backend Dev | Implementation notes, files changed, tests, deviations |
| `frontend-dev.md` | Frontend Dev | Implementation notes, files changed, tests, deviations |
| `qa-reviewer.md` | QA Reviewer | Test results, coverage, findings per review round |
| `security-reviewer.md` | Security Reviewer | OWASP audit findings, vulnerability assessments |
| `doc-writer.md` | Doc-writer | Documentation debt tracker, doc artifacts produced, cross-session context, DOC-NEEDED items |
| `critic.md` | Critic | Challenges raised per stage, assumptions tested |

## ADR Directory

The `.forge/adr/` directory stores Architecture Decision Records (ADRs) — lightweight records of significant design decisions. See `templates/adr-template.md` for format.

## Handoff Files

Skills write handoff files to `.forge/memory/` to pass context to the next skill in the flow:

| File | Written By | Read By | Purpose |
|------|-----------|---------|---------|
| `handoff-design.md` | design | plan | Approved solutions, team composition, scope (legacy `handoff-develop.md` still read) |
| `handoff-plan.md` | plan | implement, evaluate (pre) | Plan reference, task list, dependencies |
| `handoff-evaluate.md` | evaluate | implement, plan | Evaluation findings, mode used |
| `handoff-implement.md` | implement | code-review | Branch, files changed, tests written |
| `handoff-code-review.md` | code-review | test | Review findings, open issues |
| `handoff-test.md` | test | diagnose | Test results, failures, coverage |
| `handoff-diagnose.md` | diagnose | plan, implement | Root causes, fix recommendations |

See `templates/handoff-protocol.md` for the handoff file format.

## Conventions

- **Beads cross-references:** Every finding, root cause, solution, and task references its beads ID: `### Title [bd-xxx.N]`
- **Stage markers:** `## Stage N: IN_PROGRESS [timestamp]` / `## Stage N: COMPLETE [timestamp]`
- **Append-only:** Within a stage, append new sections — never overwrite previous rounds.
- **Ownership:** Agents write only to their own file. PM writes only to `project.md`.
- **ADR tracking:** Architecture decisions are recorded in `.forge/adr/` with beads cross-references per `templates/adr-template.md`.

## Resume

If the team is restarted:
1. PM reads all files, checks stage markers
2. Finds earliest incomplete stage
3. Reports state and resumes

When any skill starts, it checks `project.md` for the Skill Flow section to understand where in the flow the session is, then checks for its own state file and handoff files from the previous skill.

See `templates/memory-protocol.md` for full conventions.
