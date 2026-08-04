"""Design template variables (no skill_runner import)."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.design.spec_gate import gate_sidecar_path, load_gate_json
from scripts.design.spec_issues import issues_status_block
from scripts.shared.orchestrator import (
    SkillState,
    runtime_memory_dir,
    runtime_memory_dir_relative,
    save_state,
)
from scripts.shared.studio_status import studio_status_block


def ensure_develop_custom(state: SkillState) -> None:
    defaults: dict[str, str | bool] = {
        "scope_tier": "unknown",
        "spec_required": False,
        "scope_rationale": "",
        "brainstorming_mode": "design_first_v2",
        "diagnose_complexity_hint": "",
    }
    for k, v in defaults.items():
        state.custom.setdefault(k, v)


def sync_develop_scope_from_memory(
    state: SkillState,
    state_path: Path | None = None,
) -> None:
    candidates: list[Path] = []
    if state_path is not None:
        parent = state_path.parent
        candidates.append(parent / "sidecars" / ".design-scope.json")
        candidates.append(parent / ".design-scope.json")
    mem = runtime_memory_dir()
    candidates.append(mem / "design-scope.json")
    candidates.append(mem / "develop-scope.json")

    path: Path | None = None
    for cand in candidates:
        if cand.is_file():
            path = cand
            break
    if path is None:
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    tier = str(data.get("scope_tier", "")).strip().lower()
    if tier in ("trivial", "medium", "large"):
        state.custom["scope_tier"] = tier
        state.custom["spec_required"] = tier in ("medium", "large")
    rationale = data.get("scope_rationale", data.get("rationale", ""))
    if rationale is not None and str(rationale).strip():
        state.custom["scope_rationale"] = str(rationale).strip()
    state.custom["scope_source"] = str(path)


def spec_gate_status_block(state: SkillState, state_path: Path) -> str:
    if not state.custom.get("spec_required"):
        return (
            "**Spec gate:** not required (`spec_required=false`, typically trivial scope).\n"
        )
    side = gate_sidecar_path(state_path)
    data = load_gate_json(side)
    if not data:
        return (
            f"**Spec gate:** required — sidecar missing or invalid (`{side.name}`).\n"
        )
    parts = [
        "**Spec gate:** required",
        f"- `spec_path`: {data.get('spec_path', '')}",
        f"- `spec_written`: {data.get('spec_written', False)}",
        f"- `self_review_passed`: {data.get('self_review_passed', False)}",
        f"- `user_approved`: {data.get('user_approved', False)}",
    ]
    return "\n".join(parts) + "\n"


def build_variables(
    state: SkillState,
    repo_root: Path,
    step: int = 1,
    state_path: Path | None = None,
) -> dict[str, str]:
    del repo_root
    ensure_develop_custom(state)
    if state_path is not None:
        sync_develop_scope_from_memory(state, state_path)
        # Autonomy from CLI flags
        if state.custom.get("auto3"):
            state.autonomy_level = 3
        elif state.custom.get("auto2"):
            state.autonomy_level = 2
        elif state.custom.get("auto1"):
            state.autonomy_level = 1
        save_state(state, state_path)

    autonomy_text = {
        1: "Level 1 (Default): Pause at every stage gate for user approval.",
        2: "Level 2: Only pause at solution approval (Stage 3).",
        3: "Level 3: Full auto -- report at end, pause only for final approval.",
    }.get(state.autonomy_level, "Level 1 (Default)")

    findings_text = ""
    if state.findings:
        for f in state.findings:
            status = f" [{f['status']}]" if f.get("status") != "open" else ""
            note = f" -- User: {f['user_note']}" if f.get("user_note") else ""
            findings_text += (
                f"- **{f['id']}** ({f['severity']}): {f['title']}{status}{note}\n"
                f"  {f['detail']}\n\n"
            )
    else:
        findings_text = "(No findings yet)"

    review_state = ""
    for step_key, loop in state.review_loops.items():
        loop_dict = loop.to_dict() if hasattr(loop, "to_dict") else loop
        review_state += (
            f"Step {step_key} review (round {loop_dict.get('round', 0)}): "
            f"self={loop_dict.get('self_review', 'pending')}, "
            f"cross={loop_dict.get('cross_review', 'pending')}, "
            f"critic={loop_dict.get('critic_review', 'pending')}, "
            f"pm={loop_dict.get('pm_validation', 'pending')}\n"
        )
    if not review_state:
        review_state = "(No review loops started)"

    solutions_summary = state.custom.get(
        "solutions_summary", "(Solutions not yet generated)"
    )
    no_edit_policy = (
        "## Permission to modify files\n\n"
        "**Hard rule — applies to every design phase:** Do **not** modify the repository "
        "(including source code, `agents/`, `prompts/`, integrations, tests, or any tracked "
        "project files) unless the user gives **explicit permission** for that specific change "
        '(e.g. “you may edit `agents/foo.md` now” or “apply the drafted updates”). '
        "Exploration must be **read-only** on the codebase.\n\n"
        "**Allowed without asking:** Append or update files **only** under design session "
        f"memory when this workflow explicitly tells you to (typically `{runtime_memory_dir_relative()}/` "
        "— e.g. `project.md`, investigation notes). If unsure whether a path counts as "
        "session memory, **ask first**.\n\n"
        "Do **not** skip this requirement based on autonomy level.\n"
    )

    tier = str(state.custom.get("scope_tier", "unknown"))
    spec_req = bool(state.custom.get("spec_required"))
    studio_status = studio_status_block(state, context="develop")
    from forge_next.studio.context import orchestrator_studio_variables

    studio_vars = orchestrator_studio_variables()
    sp = state_path or Path(".")
    variables: dict[str, str] = {
        "AUTONOMY_INSTRUCTIONS": autonomy_text,
        "DEVELOP_NO_EDIT_POLICY": no_edit_policy,
        "PREVIOUS_FINDINGS": findings_text.strip(),
        "REVIEW_STATE": review_state.strip(),
        "SOLUTIONS_SUMMARY": str(solutions_summary),
        "SCOPE_TIER": tier,
        "SPEC_REQUIRED": "yes" if spec_req else "no",
        "SCOPE_RATIONALE": str(state.custom.get("scope_rationale", "")).strip()
        or "(none yet)",
        "SPEC_GATE_STATUS": spec_gate_status_block(state, sp),
        "SPEC_ISSUES_GATE_STATUS": issues_status_block(sp),
        "STUDIO_STATUS": studio_status,
        "STUDIO_LOG": studio_vars["STUDIO_LOG"],
        "STUDIO_APPROVED": studio_vars["STUDIO_APPROVED"],
        "STATE_DIR": str(sp.resolve().parent) if state_path else "(state dir)",
    }

    append = ""
    if step == 6 and state.custom.get("spec_required"):
        try:
            from scripts.evaluate.template_engine import load_template, render_template

            spec_tmpl = load_template("design/spec_gate")
            append = "\n\n---\n\n" + render_template(spec_tmpl, variables)
        except FileNotFoundError:
            pass
    if step == 7 and not state.custom.get("spec_required"):
        append += (
            "\n\n---\n\n**Note:** `SPEC_REQUIRED` is **no** (trivial scope). "
            "No `.design-spec-issues.json` sidecar is required — proceed to "
            "`forge design --step 8` after optional beads capture from approved "
            "solutions.\n"
        )
    if append:
        variables["__APPEND__"] = append
    return variables


def build_handoff_context(state: SkillState, repo_root: Path) -> dict[str, str]:
    del repo_root
    return {
        "Scope tier": str(state.custom.get("scope_tier", "unknown")),
        "Spec required": "yes" if state.custom.get("spec_required") else "no",
        "Autonomy": str(state.autonomy_level),
    }
