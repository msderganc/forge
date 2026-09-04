# Design Complete — Handoff

{{DEVELOP_NO_EDIT_POLICY}}

## Handoff
Capture not only facts but the **shared framing** from the session—what opportunities surfaced, which creative directions were considered, and what the user valued—so the next skill inherits the conversation, not just artifacts.

Write `{{MEMORY_DIR}}/handoff-design.md` with:
- Approved solutions with beads IDs
- Spec path (when required) and link to `.design-spec-issues.json` / issue table
- Team composition
- Scope assessment
- Task type
- Key investigation findings
- Visual references (`web-references.md`) when Frontend/web UI was in scope, including Uncodixfy constraints

## Dashboard
Render skill completion dashboard per `templates/dashboard.md`.

## Doc-writer Capture
Dispatch Doc-writer to capture learnings in `{{MEMORY_DIR}}/doc-writer.md`.

## Suggested Next

`plan` — **only after** any required design spec gate is complete (see `.design-spec-gate.json` when `spec_required`; legacy `.develop-spec-gate.json` still read) **and** spec → issues decomposition is recorded (`.design-spec-issues.json` on step 7 when `spec_required`). The design spec path (when required) lives under `docs/forge/specs/` — plan should consume the spec **and** the issue sidecar, not sketch memory alone.

Orchestrator context:

- **Scope tier:** {{SCOPE_TIER}}
- **Spec required:** {{SPEC_REQUIRED}}
- **Spec gate status:** {{SPEC_GATE_STATUS}}
- **Spec issues gate status:** {{SPEC_ISSUES_GATE_STATUS}}

## Git Checkpoint
git add {{RUNTIME_DIR}}/ && git commit -m "workflow: design complete -- solutions approved"
