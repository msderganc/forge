# Brainstorming Decision Gates

> **Read by the PM only.** Dispatched sub-agents **must not** execute this file. Gate execution is a main-agent responsibility that wraps the Architect's brainstorming runs.

## Purpose

`templates/brainstorming.md` is the methods catalog the Architect follows to generate and evaluate solution candidates. This file (`brainstorming-gates.md`) defines the *interactive decision points* the PM drives between Architect dispatches so the user's judgment shapes framing, technique choice, candidate selection, and scoring weights — rather than all creative decisions being locked inside the sub-agent.

Together, `brainstorming.md` + `brainstorming-gates.md` turn Stage 2 into a **three-dispatch loop** with two gates:

1. **Dispatch 1:** Architect runs Phase 1 of `brainstorming.md` only (Requirements Exploration + HMW). Writes `solution-requirements.md` and stops.
2. **Gate 1 (PM):** Confirm driver HMW framing, pick optional advanced divergent techniques.
3. **Dispatch 2:** Architect runs Phase 2 (divergent) and Phase 3 Steps 1–3 (group → eliminate → ICE → develop candidates). Writes `divergent-ideas.md` and a *draft* (unscored) `solutions.md`. Stops before scoring.
4. **Gate 2 (PM):** Select which families to carry forward, pick the priority scoring dimension.
5. **Dispatch 3:** Architect runs Phase 3 Steps 3b–5 (Pugh Matrix → weighted scoring → recommendation) using the user's weights. Finalizes `solutions.md`.
6. **Gate 2 Q3 (PM, conditional):** Fires only if the finalized scores produce a tie. Updates `solutions.md` with the user's tiebreak winner.

This ordering guarantees that every user decision arrives *before* the Architect work it influences — Gate 1 is genuinely pre-divergence, Gate 2 Q1/Q2 is genuinely pre-scoring.

## Visual gate mode (Forge Studio)

When `studio_enabled` is true (see `templates/studio.md`):

1. Push HTML screens with **`studio-design-notes`** (agent context) plus gate options — see `templates/studio.md` and `forge_next/assets/studio/screen-example.html`.
2. User opens the local URL; they pick options and can **Send feedback** / **Done reviewing** on the page.
3. Read `forge studio events --json` for `click`, `submit`, `feedback` (free text), and `done`.
4. **Record answers and feedback in `project.md` and `current-step.md`** — Studio is transport only.
5. Fall back to AskQuestion if bind fails, events are empty, or gate id mismatches.

Gate 2 Q2 (priority dimension) and Q3 (tiebreak) stay **chat-only** unless the user asks for a visual summary.

## PM clarification micro-loop

When the user’s answer is ambiguous or contradictory:

1. **Stop** — do not advance the gate or dispatch the next Architect run.
2. Ask **one** narrowing question (prefer multiple-choice).
3. Log the resolution in `project.md`, update `current-step.md`, then proceed.

## Gate 2 — Level 1 presentation (split when possible)

For **Autonomy Level 1**, use **two separate user interactions** for Gate 2: complete **Q1** (candidate/family selection), then **Q2** (priority dimension). The combined template below remains valid for **Level 2** batching and plaintext fallbacks.

## Intermediate Artifact Contract

The Architect writes these files into `.forge/memory/` during Stage 2. The PM reads them between dispatches and cites them directly so the user is choosing from real generated content, not abstractions.

| File | Written after | Contents |
|------|---------------|----------|
| `solution-requirements.md` | Dispatch 1 (Phase 1) | Requirements Context block + HMW candidates (with a suggested driver) + optional Job Story |
| `divergent-ideas.md` | Dispatch 2 (Phase 2) | Raw ideas grouped into solution families, one family per `###` header, with the technique that produced each idea tagged inline |
| `solutions.md` (draft) | Dispatch 2 (Phase 3 Steps 1–3) | Developed candidates with approach / pros / cons / open questions. **No scores yet.** |
| `solutions.md` (final) | Dispatch 3 (Phase 3 Steps 3b–5) | Adds Pugh Matrix, weighted scoring tables, recommendation. Overwrites the draft. |

**Resume rule.** If a session is resumed and one of these files already exists, skip the corresponding dispatch and move straight to the next gate. If `solutions.md` already has scoring tables, treat the whole stage as complete.

## Gate 1 — Pre-Divergence

**Trigger:** Dispatch 1 has completed and `.forge/memory/solution-requirements.md` exists. `divergent-ideas.md` does **not** yet exist.

**Why we pause here:** The HMW framing and the technique set jointly determine the *shape* of the solution space the user will eventually choose from. Locking these in before Phase 2 runs prevents the Architect from anchoring on whichever default techniques happened to fit its own prior.

### Questions

**Q1 — Driver HMW (single-select)**

Read `solution-requirements.md` and present each HMW candidate as an option. The Architect's suggested driver should be listed first with `(Recommended)` appended to its label. Cap at 4 HMWs — if the Architect generated more, the PM reads the top 4 by the Architect's ranking.

Use the Gate 1 question template from the section below, populating options with 2–4 HMWs from `solution-requirements.md` (recommended first).

**Q2 — Advanced divergent techniques (multi-select)**

The Architect *always* applies the core three techniques (SCAMPER, Reverse Brainstorming, Constraint Removal) plus whatever the task-type Method Selection Guide recommends. Gate 1 Q2 asks the user which **advanced** techniques to add on top. Keep the list to exactly 4 options so the prompt stays easy to answer.

Use the Gate 1 question template from the section below (Q2 — Techniques).

If the task type is `bugfix`, the Architect additionally auto-applies 5W1H / Starbursting (it's the default-for-bugfix in `brainstorming.md`'s Method Selection Guide); the user does not need to select it at Gate 1.

The PM passes the Q1 answer (HMW) and the Q2 answer (additional techniques) into Dispatch 2 as explicit context lines.

## Gate 2 — Pre-Scoring

**Trigger:** Dispatch 2 has completed and `.forge/memory/solutions.md` exists in *draft* form — candidates are developed but the scoring table is empty (no Pugh Matrix, no rubric scores, no recommendation).

Gate 2 cuts candidates to ≤4, captures the user's priority dimension, and then fires Dispatch 3 which does the actual scoring with the user's weights. The tiebreak (Q3) is conditional and fires *after* Dispatch 3 if the final scores are close.

### Questions

**Q1 — Solution families (multi-select)**

Read the draft `solutions.md` and present each developed candidate. The user picks 2–4 to carry into full scoring. Candidates not picked are moved to an "Also Considered" section and are not scored. If the Architect produced more than 4 candidates, the PM pre-cuts using the ICE pre-filter from `brainstorming.md` Step 2b before presenting options.

Use the Gate 2 Q1+Q2 question template from the section below (Q1 — Candidates), populating options with up to 4 candidates from draft `solutions.md` truncated to ~60 chars.

**Q2 — Scoring dimension priority (single-select)**

Asking the user to hand-assign 5 rubric weights is too much friction. Instead, ask which axis matters *most* and the PM translates the answer into a weight multiplier. The rubric has 5 scored dimensions (Q, T, C, R, E); Gate 2 Q2 collapses them to 3 user-facing axes plus a "no preference" escape, keeping within the `maxItems: 4` schema limit:

Use the Gate 2 Q1+Q2 question template from the section below (Q2 — Priority dimension).

**Collapse rationale and weight translation:**
- **Quality** — rubric weights: Q=2.0, T=1.0, C=1.0, R=1.0, E=1.0
- **Time** — rubric weights: Q=1.0, T=2.0, C=1.0, R=1.0, E=2.0 *(E is "ease of build" so low effort is double-counted as velocity)*
- **Risk** — rubric weights: Q=1.0, T=1.0, C=2.0, R=2.0, E=1.0 *(Cost is a proxy for operational risk and is weighted with it)*
- **Balanced** — all weights 1.0

This preserves all 5 rubric dimensions in the Architect's scoring pass while asking the user only one question. The collapse is documented in `solutions.md` so reviewers can see which raw weights were applied.

**Q3 — Tiebreak (conditional, fires after Dispatch 3)**

Only presented if Dispatch 3's Pugh Matrix returns a net-zero winner (no candidate dominates) *or* the priority-weighted rubric scores differ by <0.5 between the top two candidates. Read the finalized `solutions.md`, identify the tied candidates, and present them as options.

Use the Gate 2 Q3 question template from the section below, populating options with the 2 tied candidates and their headline trade-offs.

## Autonomy Routing

| Autonomy | Gate 1 (HMW + techniques) | Gate 2 Q1 (families) | Gate 2 Q2 (priority dim) | Gate 2 Q3 (tiebreak, conditional) |
|---------:|---------------------------|----------------------|--------------------------|-----------------------------------|
| **Level 1** | Ask | Ask | Ask | Ask |
| **Level 2** | Skip — task-type defaults + Architect's suggested HMW; log in `project.md` | Skip — keep all candidates if ≤4, else ICE pre-filter to top 4 | **Ask** | Ask |
| **Level 3** | Skip — task-type defaults + Architect's suggested HMW; log | Skip — keep all if ≤4, else ICE top 4 | Skip — "Balanced" (all weights 1.0); log | Skip — keep the Pugh datum; log |

**"≤4, keep all" fallback.** When Dispatch 2 produces 4 or fewer draft candidates, the Level 2/3 "ICE top 4" default has nothing to do — all candidates carry forward unchanged. This avoids a degenerate no-op ICE call.

**Level-3 determinism.** Every skipped gate must log its chosen default into `.forge/memory/project.md` under the Stage 2 marker so the decision is reproducible and auditable. A resumed session with the same inputs must produce the same outputs.

## Escalation Override

The existing develop workflow **Escalation Rules** section (under "PM RESPONSIBILITIES ACROSS ALL STAGES") forces a pause "regardless of autonomy level" when:

1. Multiple valid solutions exist with materially different trade-offs.
2. The team cannot identify a safe path with acceptable confidence.
3. Security or data-integrity concerns arise.

These rules **override** the Level 2/3 skip behavior above. Specifically: if Dispatch 3's Pugh Matrix shows a net-zero winner **or** the top two rubric scores are within 0.5, the PM **must** fire Gate 2 Q3 (tiebreak) regardless of autonomy level. Log the escalation in `project.md` so it's clear why a pause occurred when the user expected auto-proceed.

## Continuation Protocol Integration

The develop skill uses **two** persistence mechanisms and they serve different purposes:

| File | Owner | Purpose |
|------|-------|---------|
| `.forge/state/design.json` | `scripts/design/design.py` | Orchestrator step machine. Tracks which of the 8 CLI steps the skill is on. Advanced by `design.py --step N`. Legacy: `develop.json` / `scripts/develop/develop.py` shim. |
| `.forge/memory/current-step.md` | PM (Codex) | Human-readable lifeline for context-compaction resume. Tracks *sub-step* state within a CLI step (e.g., which gate is waiting). Never read by `design.py`. |

**On resume, the PM must check `current-step.md` *before* invoking `design.py`.** If `current-step.md` says `Step: gate-N-waiting` or `Step: gate-N-answered`, the PM handles the gate directly (re-fires it, or advances to the next dispatch) and only calls `design.py --step 6` after Stage 2 is truly complete. This keeps the script's coarse step machine from stomping on sub-step gate state.

### Gate-specific transitions

Before asking the user, write `current-step.md` with:

```
Stage: 2
Step: gate-1-waiting        (or gate-2-q1q2-waiting, gate-2-q3-waiting)
Next: process user answer to Gate 1 and run Dispatch 2
Status: in-progress
Artifacts:
  - solution-requirements.md: present
  - divergent-ideas.md: absent
  - solutions.md: absent
```

After the user answers, update `current-step.md` inline so a resume can pick up without re-asking:

```
Stage: 2
Step: gate-1-answered
Next: dispatch Architect Phase 2 + Phase 3 Steps 1-3
Status: in-progress
Gate 1 answers:
  - driver_hmw: [HMW text]
  - extra_techniques: [First Principles, Analogical Reasoning]
```

If a resumed session finds `Step: gate-N-waiting`, the PM re-fires that gate. If it finds `Step: gate-N-answered`, the PM proceeds to the next dispatch using the recorded answers — it does not re-ask.

## User Question Templates

Copy-paste skeletons. Replace bracketed placeholders with content from the intermediate artifacts. Present questions per `templates/user-questions.md` (plain English, one-sentence context when needed). Keep option `id`s stable for Studio / event logging — only the visible prompt/label/description text is user-facing.

Internal notes for the PM (do **not** dump into the user prompt): Q1 options come from How-Might-We candidates in `solution-requirements.md`; Q2 adds optional advanced techniques on top of the always-on core (SCAMPER, Reverse Brainstorming, Constraint Removal); Gate 2 priority maps to rubric weights (Quality→Q, Time→T+E, Risk→R+C, Balanced→all 1.0).

### Gate 1 (Level 1)

```
Ask the user:
[
  {
    "id": "gate1_hmw",
    "prompt": "Which problem framing should we use when brainstorming?\n\nWe'll generate solution ideas from the framing you pick.",
    "allow_multiple": false,
    "options": [
      {"id": "hmw_1", "label": "[framing #1 truncated] (Recommended)", "description": "[why this framing fits in one short clause]"},
      {"id": "hmw_2", "label": "[framing #2 truncated]", "description": "[why this framing fits in one short clause]"},
      {"id": "hmw_3", "label": "[framing #3 truncated]", "description": "[why this framing fits in one short clause]"}
    ]
  },
  {
    "id": "gate1_techniques",
    "prompt": "Want any extra brainstorming methods?\n\nThree standard methods already run. Pick extras only if you want a wider idea set (or choose none).",
    "allow_multiple": true,
    "options": [
      {"id": "first_principles", "label": "Rebuild from basics", "description": "Ignore current design habits; reason from requirements up"},
      {"id": "analogical_reasoning", "label": "Borrow from other domains", "description": "Adapt patterns from similar problems elsewhere"},
      {"id": "assumption_reversal", "label": "Flip assumptions", "description": "List what we take for granted and try the opposite"},
      {"id": "triz_contradiction", "label": "Resolve trade-off tensions", "description": "When we want two conflicting things, look for structural ways to get both"}
    ]
  }
]
```

### Gate 2 Q1 + Q2 (Level 1 / Level 2 partial)

```
Ask the user:
[
  {
    "id": "gate2_candidates",
    "prompt": "Which solution ideas should we score in detail?\n\nPick 2–4. Unpicked ideas stay as notes and won't be ranked.",
    "allow_multiple": true,
    "options": [
      {"id": "candidate_1", "label": "[Candidate 1 title]", "description": "[1-line pros/cons summary]"},
      {"id": "candidate_2", "label": "[Candidate 2 title]", "description": "[1-line pros/cons summary]"},
      {"id": "candidate_3", "label": "[Candidate 3 title]", "description": "[1-line pros/cons summary]"},
      {"id": "candidate_4", "label": "[Candidate 4 title]", "description": "[1-line pros/cons summary]"}
    ]
  },
  {
    "id": "gate2_priority",
    "prompt": "What should matter most when we rank these solutions?\n\nYour pick tilts the scoring weights; it does not discard other criteria.",
    "allow_multiple": false,
    "options": [
      {"id": "quality", "label": "Quality", "description": "Correctness, maintainability, reliability"},
      {"id": "time", "label": "Speed to ship", "description": "Finish sooner; prefer lower build effort"},
      {"id": "risk", "label": "Risk", "description": "Security, data loss, and hard-to-undo mistakes"},
      {"id": "balanced", "label": "Balanced", "description": "No single factor dominates"}
    ]
  }
]
```

**Level 2 variant:** Omit the first question entirely. Pass only the priority question. The idea list is pre-cut by ICE or kept whole if ≤4.

### Gate 2 Q3 — Tiebreak (any level, escalation-forced)

```
Ask the user:
[
  {
    "id": "gate2_tiebreak",
    "prompt": "The top options scored almost the same. Which should we go with?",
    "allow_multiple": false,
    "options": [
      {"id": "candidate_a", "label": "[Candidate A title]", "description": "[main trade-off in plain words]"},
      {"id": "candidate_b", "label": "[Candidate B title]", "description": "[main trade-off in plain words]"}
    ]
  }
]
```

## Fallback

If the environment lacks Studio (`templates/studio.md`) or structured question UI, degrade to the plain-text numbered-prompt patterns below. Gate semantics are identical; only presentation changes. Still follow `templates/user-questions.md`.

### Gate 1 fallback

```
Before brainstorming solutions

Which problem framing should we use? (We'll generate ideas from this one.)
  1. [framing #1]  (Recommended)
  2. [framing #2]
  3. [framing #3]

Want any extra brainstorming methods? Three standard methods already run.
Comma-separated numbers, or "none".
  1. Rebuild from basics
  2. Borrow from other domains
  3. Flip assumptions
  4. Resolve trade-off tensions

Enter: <framing#> / <method#s or "none">
```

### Gate 2 Q1+Q2 fallback

```
Before ranking solutions

Which solution ideas should we score in detail?
(Comma-separated numbers, 2–4 picks. Unpicked ideas stay as notes.)
  1. [Candidate 1 title] — [1-line summary]
  2. [Candidate 2 title] — [1-line summary]
  3. [Candidate 3 title] — [1-line summary]
  4. [Candidate 4 title] — [1-line summary]

What should matter most when we rank them?
  1. Quality — correctness, maintainability, reliability
  2. Speed to ship — finish sooner / lower build effort
  3. Risk — security, data loss, hard-to-undo mistakes
  4. Balanced — no single factor dominates

Enter: <idea#s> / <priority#>
```

### Gate 2 Q3 tiebreak fallback

```
Close call — pick a winner

The top options scored almost the same. Which should we go with?
  1. [Candidate A title] — [main trade-off]
  2. [Candidate B title] — [main trade-off]

Enter: <choice#>
```

## Maintenance Notes

- If you add a new divergent technique to `brainstorming.md`, decide whether it's **core** (always on — update the Phase 2 default set) or **advanced** (user-optional — update Gate 1 Q2's 4-option list, retiring a less-used advanced technique to stay within `maxItems: 4`).
- If `scoring-rubric.md` gains or drops a dimension, update Gate 2 Q2's collapse rationale and the weight translation table in lockstep.
- If the autonomy levels in `autonomy-levels.md` change, update the Autonomy Routing table above in lockstep — these two files are a pair and must not drift.
- The develop workflow's Escalation Rules section is referenced by name, not line number, so edits to the workflow guide don't require edits here.
