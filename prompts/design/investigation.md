# Stage 1 — Investigation

{{DEVELOP_NO_EDIT_POLICY}}

## Investigation + conversation

Deep investigation runs **alongside** the user, not behind their back. Share emerging hypotheses and surprising findings early. If evidence points to a **bigger opportunity** (simpler fix, better feature shape, adjacent win), say so and invite reaction—especially before investigation artifacts harden.

If `sketch-decisions.md` exists in memory, pass its **Resolved** and **Handoff notes** sections into investigation framing before dispatch.

Dispatch agents for deep investigation.

**Roster:** Follow **`templates/forge-agent-roster.md`**. This step dispatches **Investigator** and **Architect** only — use those exact role names and `agents/investigator.md` / `agents/architect.md` briefs. Never invent `backend-architect` or other layer-prefixed agents.

## Agent Dispatch

### Investigator (evidence gathering)
Explore the codebase and gather evidence:
- Read relevant code paths end-to-end
- Run existing tests, collect results
- Check git history for recent changes
- Collect error messages, stack traces, reproduction steps
- For bugfixes: follow `templates/systematic-debugging.md`

Write evidence to `{{MEMORY_DIR}}/investigator.md`

### Architect (analysis lead)
Analyze the evidence using `templates/five-why-protocol.md`:
- For each issue/challenge, drill through up to 5 why-layers
- Pattern analysis and hypothesis testing at each layer
- Record evidence at every layer
- Stop at an actionable root cause
- For features: use `templates/brainstorming.md` for requirements exploration

Write findings to `{{MEMORY_DIR}}/investigation.md`

## Web / UI prior art (when Frontend or a site/app UI is in scope)

Read **`templates/web-design-references.md`**. Pick 2–4 matching galleries and look at live examples (browser tools when available). Start `{{MEMORY_DIR}}/web-references.md` with sources opened and specific URLs. Apply **`/uncodixfy`** when installed (`templates/uncodixfy-contract.md`); if it is not installed, skip.
