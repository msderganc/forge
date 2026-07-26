# Scope Assessment & Team Composition

{{DEVELOP_NO_EDIT_POLICY}}

**Studio (internal):** {{STUDIO_STATUS}} — see `templates/studio.md`. If enabling, use a **separate** opt-in message; users open a URL only, never run `forge studio`.

**Studio log (if any):** {{STUDIO_LOG}}

Size and expansion rules: **`templates/scope-size-model.md`**.

## Dialogue before labels

Treat this step as **discovery**, not a form to fill. Lock framing around the user's original ask first:

### Recommended scope (original ask)

- Co-develop a crisp problem statement for what the user asked for.
- Success signals and non-goals for **that** ask.
- Recommended answers and next steps always track Recommended scope.

### Scope expansion (optional — not recommended unless user opts in)

Still surface opportunities and delighters — list them explicitly here (and in `project.md`), **not** as the default recommendation:

- Opportunity: what could be better, faster, simpler, or newly possible
- Delighter: what would make this exciting vs merely adequate

Do **not** promote expansion items into Recommended scope without an explicit user yes (usually bumps size tier).

Stay in conversation until the user confirms Recommended scope — or explicitly opts into an expansion.

## Prior sketch session

If `{{MEMORY_DIR}}/sketch-decisions.md` exists:

- Read it before fixing scope tier and task type.
- Carry **Recommended scope**, **Size**, **Resolved** decisions, and any **Scope expansion** lists into `project.md`.
- If sketch size was **small**, prefer `trivial` unless new high-risk signals clearly fire.
- Do not re-litigate branches already closed in sketch unless the user asks.

If intent is still unclear and there is no sketch artifact, suggest **`forge sketch`** before continuing deep investigation.

## Prototype offer (mandatory when applicable)

If one unresolved **logic/state** or **UI-shape** question cannot be settled from discussion, codebase evidence, or written options, **explicitly offer** the future `forge:prototype` skill as a decision aid (not a scope expansion). The skill is **not yet invokable** — see `docs/forge/prototype-skill-stub.md`. Do not prototype “to be thorough.”

## Scope tier (required — dual track)

After dialogue, classify **`trivial`**, **`medium`**, or **`large`** using **all** signals below (deterministic). User-facing alias: **trivial ≡ small**.

**Bias when unsure:** pick the **lower** tier.

### Signals

Count **high-risk** and **medium-risk** indicators:

| Risk | Indicator |
|------|-----------|
| **High** | Security / auth / data-integrity / compliance / PII |
| **High** | Breaking API or schema change, or migration with rollback difficulty |
| **High** | Cross-cutting architecture (multiple bounded contexts or subsystems) |
| **Medium** | 3–10 files or multiple packages touched |
| **Medium** | New observability, SLO, or operational runbook burden |
| **Medium** | Significant UX or workflow change for end users |
| **Low** | 1–2 files, localized change, clear rollback |

### Tier rules

- **`large`:** ≥2 **high-risk** signals.
- **`medium`:** 1 **high-risk** OR ≥2 **medium-risk** signals (and not `large`).
- **`trivial`:** everything else after honest assessment.

### What each tier means

- **`trivial` (small):** Session memory artifacts only; **no** formal `docs/forge/specs/...` design spec; lean team / favor `--quick`; minimal solution space.
- **`medium` | `large`:** Formal design spec + self-review + user approval **before** `forge design --step 7` (see design spec gate appended at step 6). Then split the spec into plan-ready issues on step 7 before handoff (step 8). For **large**, confirm the user wants a large effort before expanding destination.

## Record scope for the orchestrator

Write **`design-scope.json`** in the **Forge runtime memory directory** (legacy `develop-scope.json` still read) (same tree as `project.md`; use `{{MEMORY_DIR}}/` — legacy `.codex/forge-codex/memory/` still read):

```json
{
  "scope_tier": "trivial",
  "scope_rationale": "1–2 sentences: which signals fired and why.",
  "recommended_scope": "one sentence original ask",
  "scope_expansion": []
}
```

Valid `scope_tier` values: `trivial`, `medium`, `large`.

Also log the same tier, Recommended scope, and any Scope expansion under sections in `project.md`.

## Original task questions

First, infer task type and layers from the user's initial description. If
anything is unclear, ask the user directly to confirm (per
`templates/user-questions.md` — plain English, short context).

- Question 1: `What kind of work is this?`
  Context: `This picks the default team shape and review emphasis.`
  - `Feature` — add or improve behavior users can notice
  - `Bugfix` — something is broken or wrong today
  - `Refactor` — restructure code without changing behavior
- Question 2: `Which parts of the stack does this touch?`
  Context: `Pick all that apply — this decides who we involve (e.g. security on backend/infra).`
  - `Frontend` — UI or client-side
  - `Backend` — API, services, or server-side logic
  - `Infra` — CI/CD, deploy, hosting, or ops config
  - `Something else` — say what in your own words

### File-count hint (secondary)

Estimate breadth (does **not** override risk-based tiering):

- Small (1-2 files)
- Medium (3-10 files)
- Large (10+ files)

## Team Composition

Read **`templates/forge-agent-roster.md`** before recording or dispatching roles.

**Layers (scope only — not agent names):** `Frontend`, `Backend`, `Infra` describe which parts of the stack are touched. Do **not** spawn `backend-architect`, `frontend-architect`, or any `{layer}-{role}` composite.

**Roles (spawn targets):**

- **`trivial`:** Architect + Investigator (add QA/Critic only if risk warrants). Prefer lean.
- **`medium` | `large`:** Base team **Architect, Investigator, QA Reviewer, Critic, Doc-writer.**

**Security activation rule:** Add the Security role whenever *any* selected layer includes Backend or Infra, or when auth/data-integrity concerns are present regardless of layer.

| Task Type | Additional Roles |
|-----------|-----------------|
| Feature | +Security (if Backend or Infra selected) |
| Bugfix | +Security (if auth/data) |
| Refactor | +Security (if auth/data) |

Record team composition in project.md.
