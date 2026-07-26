# User Questions Protocol

Defines how workflow skills ask the user for decisions (Codex, Cursor, Claude).

## Core Principle

Ask in **plain English**. Give enough context to choose confidently — not a lecture, not a cryptic label.

Use the lightest interaction that fits:
- In normal turns, ask one clear question and wait for the reply.
- If the environment supports a structured picker, you may use it, but do not depend on it.

## When to Ask the User

- Approval gates
- Mode selection
- Finding triage
- Cross-skill transitions
- Session conflicts
- Scope confirmation

## When Not to Ask

- Information-only output
- Agent-to-agent communication
- Continuation directives that should proceed automatically

## Plain-English Bar

Before you show a question, check:

1. **Would a skilled engineer who has never used Forge understand this on first read?** If not, rewrite.
2. **Does the user know why this choice matters?** If not, add one short sentence of context (what happens next, or what differs between options).
3. **Are you leaking internal jargon?** Hide process jargon (`HMW`, `SCAMPER`, `ICE`, `Pugh`, `divergent`, `scoring dimension`, `solution families`, rubric letter codes) unless the user asked for methodology detail. Prefer everyday words: *problem framing*, *extra brainstorming methods*, *ideas to compare*, *what to prioritize*.
4. **Is the length right?** Aim for: one question sentence + optional one-sentence context + short option labels. Skip multi-paragraph preambles unless the decision is high-risk or irreversible.

## Format

When a prompt says to ask the user, present:

1. **One short question** in everyday language
2. **Optional one-sentence context** when options are not self-explanatory (what this controls, or what happens next)
3. **Two to four concrete options** — short labels; add a half-line description only when the label alone is ambiguous
4. Prefer mutually exclusive options unless multiple selections are genuinely needed

### Good example

```
Approve this implementation plan?

We'll treat your choice as the go/no-go before documentation planning.

1. Approve — continue to documentation planning
2. Revise — send it back with your feedback
3. Simplify — shrink scope, then re-approve
4. Reject — stop; plan is not viable
```

### Bad example (avoid)

```
Which How-Might-We framing should drive divergence?
Which scoring dimension matters most?
Carry solution families into full scored comparison?
```

Those fail because they assume Forge vocabulary and give no everyday meaning.

## Rules

1. Keep the question actionable (a decision, not a quiz).
2. Prefer mutually exclusive options unless multiple selections are genuinely needed.
3. If the user needs to choose from many items, narrow the list first (≤4 options when possible).
4. Record the user's answer in the relevant memory file before continuing.
5. When a template ships jargon-heavy prompt text, **rewrite it to this bar** at presentation time; keep stable option `id`s if a structured picker is used.
6. Do not pad with status dumps, file paths, or agent roster noise inside the question itself — put that in chat context above the ask if needed.
