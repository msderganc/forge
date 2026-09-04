# Brainstorming Protocol

Used by develop Stage 2 for feature tasks. Generates solution candidates through structured divergent and convergent thinking, then feeds them into the scoring rubric.

## Phase 1 — Requirements Exploration

Before generating solutions, deepen understanding of the problem. Use a dialogue format to surface hidden requirements and constraints.

### Exploration Questions

Ask and answer each (using investigation findings, user input, and codebase evidence):

1. **Who is affected?** End users, developers, ops, other services?
2. **What does success look like?** Observable behavior when this feature works correctly.
3. **What are the hard constraints?** Performance budgets, compatibility, security, backward compatibility.
4. **What are the soft constraints?** Preferences, conventions, team familiarity.
5. **What adjacent systems are touched?** APIs, databases, config, CI/CD, documentation.
6. **What has been tried before?** Prior art in this codebase or similar projects.

Record answers in a Requirements Context block:

```
## Requirements Context
- Affected parties: [list]
- Success criteria: [observable outcomes]
- Hard constraints: [non-negotiable]
- Soft constraints: [preferred but flexible]
- Adjacent systems: [list with impact notes]
- Prior art: [what exists, what was tried, why it did/didn't work]
- Visual references: [when Frontend/web UI — sources opened + specific URLs from `templates/web-design-references.md`; Uncodixfy applied or skipped]
```

### How Might We (HMW) Reframing

Before moving on to divergence, translate the Requirements Context into 3–5 "How Might We…" statements. HMW (from IDEO / the Design Sprint literature) forces you to state the problem as an open-ended invitation to generate ideas, not as a solution in disguise. A good HMW is broad enough to allow creative answers but narrow enough to exclude the obviously irrelevant.

Rules:
1. Start with "How might we…"
2. Describe the *change you want*, not a specific mechanism.
3. Keep it user-centric — reference an affected party from the Requirements Context.
4. Avoid embedded assumptions ("How might we add a Redis cache" is a solution, not an HMW).

Example — bad → good:
- Bad: "How might we migrate to Postgres?" (solution smuggled in)
- Good: "How might we let the search feature tolerate 10× traffic spikes without degrading latency?"

Record the HMW candidates and explicitly pick the one (or two) that best captures the core tension — this becomes the driver for Phase 2:

```
## How Might We
1. HMW [statement 1]
2. HMW [statement 2]
3. HMW [statement 3]
...
**Selected driver:** HMW #[N] — [rationale]
```

### Optional: Job Story Framing

For feature work, a Job Story sharpens the "affected parties" answer and keeps divergence honest about *why* someone wants this:

> **When** [situation/context], **I want to** [motivation], **so I can** [outcome].

Example: "When I'm reviewing a PR at night with the page open for hours, I want the UI to switch to a dark palette automatically, so I can read code without eye strain."

Job Stories are optional but recommended whenever the task type is `feature`. Skip for pure bugfix/refactor work.

## Phase 2 — Divergent Thinking

Goal: **quantity over quality**. Generate as many solution candidates as possible. No filtering, no evaluation, no criticism yet.

### Rules

1. Defer judgment — do not evaluate ideas during this phase.
2. Go for volume — aim for at least 5 distinct approaches.
3. Build on ideas — combine and extend previous ideas.
4. Welcome wild ideas — impractical ideas often spark practical ones.

### Method Selection Guide

Not every technique fits every problem. The Architect applies the subset indicated by the PM — passed into the Dispatch 2 prompt as the user's Gate 1 answers (the PM, not the Architect, owns `templates/brainstorming-gates.md`). If no selection is supplied, fall back to the task-type default below.

| Task Type | Default Techniques | Why |
|-----------|-------------------|-----|
| Bugfix | First Principles, 5W1H/Starbursting, Reverse Brainstorming | Root-cause work benefits from decomposition and question-generation, not feature-generation |
| Refactor | SCAMPER, Constraint Removal, Assumption Reversal | The existing structure *is* the constraint; these techniques interrogate it |
| Feature | HMW-driven SCAMPER, Analogical Reasoning, Constraint Removal | Features need novelty and cross-domain imports; pure decomposition is too inward-looking |
| Mixed / Unclear | SCAMPER, Reverse Brainstorming, Constraint Removal (original three) | Balanced default |

Skip techniques that obviously don't fit. Record which ones you applied and which you skipped and why — the reasoning is valuable for reviewers.

### Structured Techniques

Apply each selected technique to the problem. Not every technique will yield useful ideas — that's fine. The goal is to provoke thinking from different angles.

#### SCAMPER

Work through each prompt:

| Prompt | Question to Ask |
|--------|----------------|
| **Substitute** | What component, data source, or dependency could we swap out? |
| **Combine** | Can we merge this with an existing feature or system? |
| **Adapt** | What similar solution exists elsewhere (other modules, other projects, other languages) that we could adapt? |
| **Modify** | What if we changed the scope, scale, interface, or data model? |
| **Put to other uses** | Can an existing system/module serve this purpose with minor changes? |
| **Eliminate** | What could we remove from the requirements to simplify dramatically? |
| **Reverse** | What if we inverted the flow, responsibility, or data direction? |

#### Reverse Brainstorming

Ask: **"How could we make this problem worse?"**

1. List 3-5 ways to make the situation worse.
2. Invert each — the inversion often reveals a viable solution approach.

Example:
- Worse: "Make the API call synchronous and blocking" → Solution: async processing with queue
- Worse: "Duplicate the logic in every consumer" → Solution: shared library or middleware

#### Constraint Removal

Ask: **"What if [constraint] didn't exist?"**

For each hard constraint identified in Phase 1:
1. Temporarily remove it.
2. Describe the ideal solution without that constraint.
3. Ask: how close can we get while respecting the constraint?

This often reveals solutions that satisfy the constraint in unexpected ways.

#### First Principles Decomposition

Ask: **"If I stripped this problem down to physical / logical fundamentals, what would I need?"**

1. Identify the core *invariant* — the thing that absolutely must be true for the solution to be correct (e.g., "the user's token must never leave the server unencrypted").
2. List everything else as *incidental* — conventions, prior decisions, library choices, architectural habits.
3. Rebuild the solution from the invariant upward, ignoring incidentals.
4. Compare the first-principles sketch to the "obvious" solution. The gap is where creative alternatives live.

Example:
- Obvious: "Use JWTs because everyone uses JWTs."
- Invariant: "The server must verify the caller's identity on every request."
- First-principles alternatives: HMAC-signed short-lived opaque tokens, TLS client certs, a signed request envelope keyed to a session — all satisfy the invariant without the JWT assumption.

This technique is the most valuable for bugfixes and refactors, where layers of incidental decisions have accumulated and the invariant has been lost.

#### Analogical Reasoning / Cross-Domain Transfer

Ask: **"What problem in a different domain has the same *shape* as this one?"**

Pattern-match from unrelated fields and import the solution structure, not the implementation. Domains worth scanning:

| Domain | Example Transfers |
|--------|------------------|
| Distributed systems | Consensus, quorum, idempotency, leader election, back-pressure |
| Compilers | Multi-pass transforms, IR lowering, fixpoint iteration, constant folding |
| Databases | Write-ahead logs, MVCC, index design, query planners |
| Operating systems | Pipes, copy-on-write, schedulers, page tables |
| Biology | Immune systems (retry/quarantine), mycelial networks (routing), homeostasis (feedback loops) |
| Everyday life | Queues at a bank, traffic lights, library card catalogs, kitchen workflows |
| Web / product UI | Live sites and sections from `templates/web-design-references.md` (route by job: awards vs landings vs motion vs product screens). Import structure, not a clone. Filter generated UI through `/uncodixfy` (`templates/uncodixfy-contract.md`) when installed. |

Pick 2–3 domains, describe your problem in their vocabulary, and let the mismatch surface alternatives.

Example: "Our UI freezes when the background task runs" — framed in compiler terms, this is a pipeline stall. Compilers solve stalls with *out-of-order execution* → a solution: dispatch the background work to a worker pool and let the UI render-loop continue independently.

#### Assumption Reversal

List 3–5 implicit assumptions the "obvious" solution is making. Flip each one. For every flipped assumption, check whether a solution is still possible — if yes, it's a candidate.

Example — building a notification system:

| Assumption | Reversed | New Solution Sketch |
|-----------|----------|--------------------|
| Users want real-time delivery | Users want batched delivery | Hourly digest emails |
| Notifications push to the user | Users pull notifications on demand | Inbox-only, no push |
| One notification per event | Events coalesce | Activity streams / summaries |
| Notifications live forever | Notifications expire fast | 24-hour TTL, read-once |

The power of this technique is that it surfaces solutions the obvious framing *actively hides*.

#### TRIZ Contradiction Lite

TRIZ (the Theory of Inventive Problem Solving) observes that inventive solutions resolve *contradictions* — situations where you want X *and* not-X. Instead of compromising, the inventive move finds a way to satisfy both.

Lightweight protocol (skip the full 40 principles — use 4 that apply most often in software):

1. **State the contradiction.** "We want [X] and [not X]."
   - Example: "We want the API to be *strict about types* and *tolerant of legacy callers*."
2. **Apply each inventive principle and ask what it suggests:**

| Principle | Question | Example Application |
|-----------|----------|---------------------|
| **Segmentation** | Can we split the object/process into independent parts so the contradiction disappears? | Two API versions behind a router — /v2 strict, /v1 lenient |
| **Asymmetry** | Can we make the two sides asymmetric instead of symmetric? | Strict on write path, lenient on read path |
| **Dynamics** | Can we make a previously static part adapt at runtime? | Coercion rules toggled by feature flag per caller |
| **Prior Action** | Can we do the work *before* it's needed, or pre-arrange state? | Lint/migrate legacy callers ahead of rollout, then flip to strict |

3. **Record** any principle that generated a usable idea as a candidate.

TRIZ is especially effective for performance / security / compatibility trade-offs where the team is stuck in "we have to pick one" thinking.

#### 5W1H / Starbursting

Instead of generating *answers*, generate *questions*. Take the problem statement and spawn questions along all six axes. Then answer each question — the answers become solution leads.

| Axis | Example Questions |
|------|------------------|
| **Who** | Who triggers this? Who benefits? Who fails silently? Who maintains the fix? |
| **What** | What data is involved? What state changes? What could be left out? What's the minimum valid input? |
| **When** | When does it happen? When should it *not* happen? When is it detected? When is it too late? |
| **Where** | Where in the stack? Where in the request lifecycle? Where in the codebase does it belong? |
| **Why** | Why does this exist? Why hasn't it been fixed? Why is the current behavior wrong? |
| **How** | How is it currently handled? How often? How would a user work around it? How would we detect recurrence? |

Aim for 15–25 questions before answering any. Starbursting is especially valuable for bugfixes where the team has jumped to a fix before fully understanding the problem's shape.

### Output Format

List every idea generated, even rough ones:

```
## Divergent Ideas
1. [Idea title] — [one-line description]
2. [Idea title] — [one-line description]
...
```

## Phase 3 — Convergent Thinking

Goal: evaluate, group, and select the most promising candidates.

### Step 1: Group

Cluster related ideas into solution families. Label each family.

### Step 2: Eliminate Obvious Non-Starters

Remove ideas that violate hard constraints identified in Phase 1. Record why each was eliminated (don't just delete them — the reasoning is valuable).

```
### Eliminated
- [Idea]: violates [constraint] because [reason]
```

### Step 2b: ICE Pre-Filter (only if >4 survivors)

When Step 2 leaves more than 4 surviving solution families, running the full Pugh + scoring rubric on all of them is wasteful. Use ICE (Impact × Confidence × Ease) as a quick pre-cut. Each dimension is rated 1–10 from the Architect's gut, no justification required — ICE is a filter, not a decision.

| Dimension | Meaning |
|-----------|---------|
| **Impact** | How much does this move the needle on the driving HMW / core tension? |
| **Confidence** | How sure are we that this approach will actually work as described? |
| **Ease** | How cheap is it to build and ship? (high = easy) |

ICE score = `Impact × Confidence × Ease` (range 1–1000). Keep the top 4 by ICE score and drop the rest into an "Also Considered" list with the ICE numbers so reviewers see why they were cut.

ICE is *not* a replacement for the scoring rubric in Step 4 — it only decides *which* candidates get the full scoring treatment.

### Step 3: Develop Top Candidates

For each surviving solution family, develop the strongest variant into a candidate with:

```
### Solution Candidate [N]: [Title]
**Approach:** [2-3 sentence description of how it works]
**Pros:**
- [advantage]
- [advantage]
**Cons:**
- [disadvantage or risk]
- [disadvantage or risk]
**Open questions:**
- [unknowns that need investigation]
```

Aim for 2-4 developed candidates. More than 4 creates evaluation fatigue. Fewer than 2 means the divergent phase was too narrow — go back and apply more techniques.

### Step 3b: Pugh Matrix Comparison

Before scoring, do a direct head-to-head comparison using the Pugh Matrix method. This reduces anchoring bias that occurs when scoring solutions independently.

1. **Pick a datum.** Choose the strongest or most obvious candidate as the baseline.
2. **Compare every other candidate** against the datum on each criterion:
   - `+` = better than datum
   - `S` = same as datum
   - `-` = worse than datum

| Criterion | Datum (Candidate A) | Candidate B | Candidate C |
|-----------|:------------------:|:-----------:|:-----------:|
| Correctness | DATUM | + | S |
| Performance | DATUM | S | + |
| Effort | DATUM | - | - |
| Risk | DATUM | + | S |
| Maintainability | DATUM | S | + |
| **Total +** | — | 2 | 2 |
| **Total -** | — | 1 | 1 |
| **Net** | — | +1 | +1 |

3. **Interpret:** A candidate that dominates (more +'s, fewer -'s) is clearly better. If results are mixed, the detailed scoring rubric will resolve it. If the datum loses to another candidate, switch the datum and re-run.

This step is fast (~5 minutes) and catches cases where the scoring rubric's absolute numbers mask relative trade-offs.

### Step 4: Score

Score each candidate using `templates/scoring-rubric.md`. Fill in the scoring table for each candidate. The Priority auto-calculation will rank them.

### Step 5: Recommend

State a recommendation with rationale:

```
## Recommendation
**Recommended:** Solution Candidate [N] — [Title]
**Rationale:** [Why this candidate scores best on the dimensions that matter most for this task]
**Runner-up:** Solution Candidate [M] — [Title] (if the recommended candidate has significant risk)
```

## Rules

1. Never skip the divergent phase. Even if the "obvious" solution is clear, the process often surfaces better alternatives or important trade-offs.
2. Record everything. Eliminated ideas and denied approaches are valuable context for reviewers and future work.
3. The recommendation is a recommendation, not a decision. The review loop and user approval gate make the final call.
4. If the problem is simple enough that brainstorming is overkill (trivial bugfix, single-line change), state that explicitly and skip to a single candidate with scoring.
