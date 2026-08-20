"""Plan template variables and step-1/7 helpers (must not import skill_runner)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from scripts.shared.orchestrator import (
    SkillState,
    consume_handoff,
    runtime_memory_dir,
    save_state,
)
from scripts.shared.studio_status import studio_status_block
from scripts.plan.plan_modes import (
    DEFAULT_MODE,
    execution_path_recommendation,
    format_mode_selection_block,
    hydrate_legacy_mode,
    load_persisted_preference,
    mode_contract_for_template,
    normalize_mode,
    recommend_mode,
    resolve_mode_for_step1,
    review_expectations_for_mode,
    save_persisted_preference,
)
from scripts.plan.plan_legacy import (
    find_unfilled_sections,
    generate_plan_filename,
    write_plan_skeleton,
)


def ensure_plan_initialized(
    state: SkillState,
    repo_root: Path,
    *,
    state_path: Path | None = None,
) -> None:
    """Idempotent step-1 setup: handoff, plan file skeleton, mode."""
    if state.custom.get("plan_file"):
        hydrate_legacy_mode(state.custom)
        return

    handoff_content = consume_handoff("design")
    plan_filename = generate_plan_filename(handoff_content)
    plans_dir = runtime_memory_dir(repo_root) / "plans"
    plans_dir.mkdir(parents=True, exist_ok=True)
    plan_file = str(plans_dir / plan_filename)
    force = bool(state.custom.get("force"))
    write_plan_skeleton(Path(plan_file), force=force)

    from scripts.shared.ceremony import map_to_plan_mode, normalize_ceremony

    # Plan no longer accepts --mode; depth is --ceremony only.
    ceremony = normalize_ceremony(
        str(state.custom.get("ceremony"))
        if state.custom.get("ceremony") is not None
        else None
    )
    ceremony_source = str(state.custom.get("ceremony_source") or "")

    recommended, rec_rationale = recommend_mode(handoff_content)
    if ceremony_source == "cli" and ceremony:
        plan_mode = map_to_plan_mode(ceremony)
        resolution_source = "cli"
    else:
        # Preference / estimate: derive plan_mode from ceremony when present.
        plan_mode, resolution_source = resolve_mode_for_step1(
            resumed_session=False,
            stored_mode=None,
        )
        if resolution_source == "fallback":
            resolution_source = "prompt"
        if ceremony and ceremony_source in ("estimated", "inherited", "escalated"):
            plan_mode = map_to_plan_mode(ceremony)

    state.custom["handoff_content"] = handoff_content
    state.custom["plan_file"] = plan_file
    state.custom["plan_mode"] = plan_mode
    state.custom["plan_mode_recommended"] = recommended
    state.custom["plan_mode_recommendation_rationale"] = rec_rationale
    state.custom["plan_mode_resolution"] = resolution_source
    if state.custom.get("save_ceremony_preference") and ceremony_source == "cli" and ceremony:
        save_persisted_preference(ceremony)
        state.custom["plan_mode_preference_saved"] = plan_mode
        state.custom["ceremony_preference_saved"] = ceremony

    # Stash mode block for step-1 append
    persisted = load_persisted_preference()
    state.custom["_mode_selection_block"] = format_mode_selection_block(
        recommended=recommended,
        rationale=rec_rationale,
        persisted=persisted,
        resolved_mode=plan_mode if resolution_source in ("cli", "session") else None,
        resolution_source=resolution_source,
        ceremony=ceremony,
        ceremony_source=ceremony_source or None,
    )
    if state_path is not None:
        save_state(state, state_path)


def inject_architecture_probes(
    state: SkillState, body: str, state_path: Path, repo_root: Path
) -> str:
    from scripts.shared.repo_paths import resolve_repo_root
    from scripts.shared.structural_probes import inject_structural_probes_section

    scan_root = resolve_repo_root(repo_root)
    body, sidecar, _payload = inject_structural_probes_section(
        body,
        skill_name="plan",
        step=2,
        repo_root=scan_root,
        state_dir=state_path.parent,
        quick_mode=state.quick_mode,
        advisory=True,
    )
    if sidecar:
        state.custom["structural_probes_sidecar"] = str(sidecar)
    return body


def build_variables(
    state: SkillState,
    repo_root: Path,
    step: int = 1,
    state_path: Path | None = None,
) -> dict[str, str]:
    if step == 1 or not state.custom.get("plan_file"):
        ensure_plan_initialized(state, repo_root, state_path=state_path)

    plan_mode = normalize_mode(state.custom.get("plan_mode"))
    mode_migrated = state.custom.get("mode_migrated_note", "")

    handoff_content = state.custom.get("handoff_content", "")
    if handoff_content:
        handoff_section = (
            "## Handoff from Design\n\n"
            "<handoff>\n"
            f"{handoff_content}\n"
            "</handoff>"
        )
    else:
        handoff_section = (
            "## No Handoff Found\n\n"
            "No handoff-design.md was found (legacy handoff-develop.md also accepted). "
            "Ask the user what needs to be planned."
        )

    plan_context = state.custom.get("plan_context", "(not yet captured)")
    architecture_notes = state.custom.get("architecture_notes", "(not yet designed)")
    mode_review = review_expectations_for_mode(plan_mode, state.quick_mode)

    if state.quick_mode:
        review_assignments = (
            mode_review
            + "**Quick mode active** — abbreviated review:\n\n"
            "| Step | Agent | Focus |\n"
            "|------|-------|-------|\n"
            "| Self-review | Planner | File paths real? TDD steps complete? No placeholders? |\n"
            "| PM validation | PM | All solutions covered? Interfaces match? |\n"
        )
    else:
        review_assignments = mode_review

    findings_text = ""
    if state.findings:
        for f in state.findings:
            status = f" [{f['status']}]" if f.get("status") != "open" else ""
            findings_text += f"- **{f['id']}** ({f['severity']}): {f['title']}{status}\n"
    else:
        findings_text = "(No findings yet)"

    plan_file = state.custom.get("plan_file")
    if not plan_file:
        sys.exit(
            "ERROR: state.custom['plan_file'] missing — "
            "re-run step 1 to initialize the plan file."
        )
    handoff_file = str(runtime_memory_dir(repo_root) / "handoff-plan.md")

    task_count_raw = state.custom.get("task_count")
    try:
        task_count = int(task_count_raw) if task_count_raw is not None else None
    except (TypeError, ValueError):
        task_count = None

    mode_contract = mode_contract_for_template(plan_mode)
    if mode_migrated:
        mode_contract += f"\n\n**Note:** {mode_migrated}\n"

    studio_status = studio_status_block(state, context="plan")
    from forge_next.studio.context import orchestrator_studio_variables

    studio_vars = orchestrator_studio_variables()

    variables: dict[str, str] = {
        "HANDOFF_CONTENT": handoff_section,
        "PLAN_CONTEXT": plan_context,
        "ARCHITECTURE_NOTES": architecture_notes,
        "REVIEW_ASSIGNMENTS": review_assignments,
        "FINDINGS": findings_text,
        "QUICK_MODE": "yes" if state.quick_mode else "no",
        "QUICK_MODE_NOTE": (
            "**Quick mode:** abbreviate narrative but keep the Documentation "
            "applicability matrix, DoD table, and external wiki checklist rows "
            "complete — they gate implement step 8."
            if state.quick_mode
            else "**Standard mode:** produce full documentation planning detail."
        ),
        "PLAN_MODE": plan_mode,
        "MODE_CONTRACT": mode_contract,
        "EXECUTION_PATH_NOTE": execution_path_recommendation(plan_mode, task_count),
        "SKILL_NAME": "plan",
        "PLAN_FILE": plan_file,
        "HANDOFF_FILE": handoff_file,
        "STUDIO_STATUS": studio_status,
        "STUDIO_LOG": studio_vars["STUDIO_LOG"],
        "STUDIO_APPROVED": studio_vars["STUDIO_APPROVED"],
    }

    append = ""
    if step == 1:
        block = state.custom.pop("_mode_selection_block", "") or ""
        if block:
            append += "\n\n" + block
    if step == 2 and state.custom.get("spine_collapse") == "plan-light":
        append += (
            "\n\n**Light ceremony:** Architect dispatch was skipped. "
            "Fill the Architecture Overview in the plan file yourself while writing tasks.\n"
        )
    elif step == 2 and state_path is not None:
        # Defer inject until after render via __APPEND__ on empty base —
        # inject needs the rendered body, so use gate instead.
        state.custom["_needs_arch_probes"] = True

    if append:
        variables["__APPEND__"] = append
    return variables


def build_handoff_context(state: SkillState, repo_root: Path) -> dict[str, str]:
    return {
        "Plan location": str(state.custom.get("plan_file", "")),
        "Plan mode": str(state.custom.get("plan_mode", DEFAULT_MODE)),
        "Task count": str(state.custom.get("task_count", "see plan")),
        "Dependencies": str(state.custom.get("dependencies_summary", "see plan")),
    }


def exit_if_plan_skeleton_incomplete(
    *, state: SkillState, step: int, state_path: Path, gate: Any
) -> None:
    """Step-7 gate: keep session open when skeleton markers remain."""
    plan_file = state.custom.get("plan_file")
    if not plan_file:
        sys.exit(
            "ERROR: state.custom['plan_file'] missing at handoff — "
            "re-run step 1 to initialize."
        )
    unfilled = find_unfilled_sections(Path(plan_file))
    if not unfilled:
        return
    warning = (
        "\n\n---\n\n"
        "**WORKFLOW NOT COMPLETE — unfilled plan sections detected.**\n\n"
        "The following sections still contain `<!-- FORGE_SKELETON: ... -->` "
        "markers and need to be filled in before the plan is ready:\n\n"
        + "\n".join(f"- {s}" for s in unfilled)
        + f"\n\nFile: `{plan_file}`\n\n"
        "Fill these sections, then re-run step "
        f"{int(state.max_step or 7)}."
    )
    state.custom["_append_body"] = warning
    state.custom["_await_same_step"] = True
    state.custom["_skip_completion"] = True
    save_state(state, state_path)


def maybe_inject_architecture_probes(
    *, state: SkillState, step: int, state_path: Path, gate: Any
) -> None:
    if not state.custom.pop("_needs_arch_probes", False):
        return
    from scripts.shared.orchestrator import _detect_repo_root

    repo_root = _detect_repo_root(Path.cwd())
    # Append probe section onto empty base then stash for body append
    injected = inject_architecture_probes(state, "", state_path, repo_root)
    if injected:
        state.custom["_append_body"] = injected
    save_state(state, state_path)
