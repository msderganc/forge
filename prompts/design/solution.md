# Stage 2 — Solution Generation

{{DEVELOP_NO_EDIT_POLICY}}

**Studio:** {{STUDIO_STATUS}} — visual gates per **`templates/studio.md`** + **`templates/brainstorming-gates.md`** (Visual gate mode).

**Studio log:** {{STUDIO_LOG}} | **Approved UI (locked):** {{STUDIO_APPROVED}}

## Protocol (read first)

| Doc | Role |
|-----|------|
| `templates/brainstorming.md` | Architect — methods catalog |
| `templates/brainstorming-gates.md` | PM only — decision gates |
| `templates/scoring-rubric.md` | Architect — weighted scoring |
| `templates/studio.md` | PM — browser gate transport |
| `templates/web-design-references.md` | Architect — when Frontend / web / landing / product UI |
| `templates/uncodixfy-contract.md` | Architect — `/uncodixfy` anti-slop filter when generating UI |

**Guards:** No implementation in Stage 2. One question at a time during PM gates. YAGNI on speculative scope — do **not** grow the solution surface past **Recommended scope** (see `templates/scope-size-model.md`). Score and recommend the **minimal** option that hits Recommended scope; list broader ideas as Scope expansion, not as the default pick. Evidence from Stage 1 or explicit user statements. Prefer solution shapes that stay under the structural charter (complexity budget, avoid clone-prone designs, acyclic deps, no speculative public surface — `templates/structural-build-charter.md`). No probe runs in design. For **trivial** scope, keep candidate count lean (often 2 directions max). If one unresolved logic/state or UI-shape question blocks choosing, **offer** future `forge:prototype` (`docs/forge/prototype-skill-stub.md`).

**Roster:** All dispatches in this stage use **Architect** only (`agents/architect.md`). See **`templates/forge-agent-roster.md`** — never spawn invented names like `backend-architect`.

**Artifacts** (`{{MEMORY_DIR}}/`): `solution-requirements.md` → `divergent-ideas.md` → `solutions.md` (draft then final). When Frontend/web UI is in scope, also `web-references.md` (galleries + Uncodixfy).

## Web / UI (when Frontend or a site/app UI is in scope)

1. Read `templates/web-design-references.md`. Pick **2–4** sources from the routing table and **open them** (browser tools when available). Record 3–5 specific references in `{{MEMORY_DIR}}/web-references.md`.
2. If `/uncodixfy` is available, apply it before proposing mockups, Studio screens, or component-kit looks (`templates/uncodixfy-contract.md`). If it is not installed, skip.
3. Marketing/landing may be more expressive; app/dashboard chrome stays Uncodixfy-normal. Do not clone award sites into product chrome.

## Loop checklist

```
Dispatch 1 → Gate 1 → Dispatch 2 → Gate 2 Q1+Q2 → Dispatch 3 → Gate 2 Q3 (if tie)
```

- [ ] **Dispatch 1 — Phase 1 only:** Architect reads `investigation.md`, writes `solution-requirements.md` (HMW framings). Stop before divergence.
- [ ] **Gate 1 (PM):** `brainstorming-gates.md` Gate 1 — HMW + optional advanced techniques. Update `current-step.md` + `project.md`. Apply autonomy routing.
- [ ] **Dispatch 2 — Phases 2 + 3 steps 1–3:** Architect applies Gate 1 choices; writes `divergent-ideas.md` + draft `solutions.md` (no scores).
- [ ] **Gate 2 Q1+Q2 (PM):** family selection + priority dimension. Record weights per gates doc.
- [ ] **Approach framing checkpoint (PM):** 2–3 coherent directions + trade-offs before Dispatch 3.
- [ ] **Dispatch 3 — Phase 3 steps 3b–5:** Pugh Matrix + weighted scoring + recommendation; finalize `solutions.md`.
- [ ] **Gate 2 Q3 (conditional):** tiebreak if Pugh net-zero or top scores within 0.5 — fires regardless of autonomy (escalation override).
- [ ] **Finalize:** Stage 2 Decision Record in `solutions.md`; `current-step.md` → `stage-2-complete`; `project.md` stage marker.

**Resume:** If intermediate artifacts exist, skip the corresponding dispatch and proceed to the next gate (see `brainstorming-gates.md` Intermediate Artifact Contract).
