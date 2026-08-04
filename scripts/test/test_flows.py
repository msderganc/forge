#!/usr/bin/env python3
"""Flows-mode orchestration for the test skill.

Extracted from test.py so run mode stays the primary entry; test.py delegates
here when ``--mode flows`` or when resumed state has ``mode == "flows"``.
"""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent

from scripts.evaluate.template_engine import load_template, render_template
from scripts.shared.orchestrator import (
    SkillState,
    append_skill_run_memory,
    build_next_command,
    build_skill_handoff_menu,
    clear_state_file,
    format_step_output,
    now_iso,
    save_state,
    write_handoff,
)
from scripts.test.test_layout import detect_test_layout  # pyright: ignore[reportMissingImports]

SKILL_NAME = "test"

FLOWS_PHASE_NAMES = {
    1: "Flow Context Detection",
    2: "Flow-Type Recommendation",
    3: "Scope Definition",
    4: "Scaffolding",
    5: "Mock Authoring",
    6: "Execution + Iteration",
    7: "Report + Handoff",
}

FLOWS_MAX_STEP = 7

FLOWS_PHASE_TODOS: dict[int, list[dict[str, str]]] = {}


def initialize_flow_custom(state: SkillState, args) -> None:
    """Populate flow-mode fields on ``state.custom`` (step 1)."""
    state.custom["flow_type"] = getattr(args, "flow_type", None)
    state.custom["flow_files"] = []
    state.custom["flow_scope"] = {}
    state.custom["criteria_audit"] = {}

    layout = detect_test_layout(REPO_ROOT)
    state.custom["framework"] = getattr(args, "framework", None) or layout.framework
    state.custom["framework_confidence"] = layout.framework_confidence
    state.custom["entry_point"] = getattr(args, "entry_point", None) or layout.entry_point
    state.custom["entry_point_confidence"] = layout.entry_point_confidence
    test_db_override = "none" if getattr(args, "no_db", False) else layout.test_db
    state.custom["test_db"] = test_db_override
    state.custom["has_orchestrator_pattern"] = layout.has_orchestrator_pattern
    roles_override = getattr(args, "roles", None)
    if roles_override:
        state.custom["roles"] = [r.strip() for r in roles_override.split(",")]
    else:
        state.custom["roles"] = layout.roles or ["anonymous"]

    warnings = []
    if layout.framework_confidence < 0.7:
        warnings.append(f"framework detection confidence: {layout.framework_confidence:.1%}")
    if layout.entry_point_confidence < 0.7:
        warnings.append(f"entry-point detection confidence: {layout.entry_point_confidence:.1%}")
    if warnings:
        state.custom["layout_confidence_warning"] = (
            "⚠ Low confidence on: "
            + ", ".join(warnings)
            + " — override with --framework / --entry-point / --no-db / --roles"
        )
    else:
        state.custom["layout_confidence_warning"] = ""


def _build_variables(state: SkillState, state_path: Path | None = None, *, prompts_style: str = "brief"):
    from scripts.test.test_legacy import _build_variables as _legacy_build

    return _legacy_build(state, state_path, prompts_style=prompts_style)


def _next_command(
    step: int,
    state_path: str = "",
    mode: str | None = None,
    *,
    next_step: int | None = None,
) -> str:
    extra = {}
    if state_path:
        extra["state"] = state_path
    if mode and mode != "run":
        extra["mode"] = mode
    variant = mode if mode in ("run", "flows") else "run"
    max_s = FLOWS_MAX_STEP if variant == "flows" else 6
    return build_next_command(
        SCRIPT_DIR / "test.py",
        step,
        max_s,
        next_step=next_step,
        phase_variant=variant,
        **extra,
    )


def _check_scaffold_gate(state: SkillState) -> list[str]:
    from scripts.test.test_flow_gates import check_scaffold_gate

    return check_scaffold_gate(state)


def _check_authoring_gate(state: SkillState) -> list[str]:
    from scripts.test.test_flow_gates import check_authoring_gate

    return check_authoring_gate(state)


def handle_flow_step(step: int, state: SkillState, sp: Path) -> None:
    """Dispatcher for flow-mode steps 1-7 with progressive gating."""
    flow_phase_map = {
        1: ("flow_context", "Flow Context Detection"),
        2: ("flow_recommendation", "Flow-Type Recommendation"),
        3: ("flow_scope", "Scope Definition"),
        4: ("flow_scaffold", "Scaffolding"),
        5: ("flow_author", "Mock Authoring"),
        6: ("flow_execute", "Execution + Iteration"),
        7: ("flow_report", "Report + Handoff"),
    }

    if step not in flow_phase_map:
        print(f"ERROR: Invalid flow step {step}", file=sys.stderr)
        sys.exit(1)

    template_base, phase_name = flow_phase_map[step]

    from scripts.test.test_flow_steps import ingest_flow_sidecars, record_flow_gate_failures

    gate_failures = record_flow_gate_failures(step, state, sp)

    template = load_template(f"test/{template_base}")
    variables = _build_variables(state)
    variables["SCAFFOLD_GATE_FAILURES"] = (
        "\n".join(f"- {f}" for f in gate_failures) if step == 4 and gate_failures else ""
    )
    variables["AUTHORING_GATE_FAILURES"] = (
        "\n".join(f"- {f}" for f in gate_failures) if step == 5 and gate_failures else ""
    )

    body = render_template(template, variables)

    ingest_flow_sidecars(step, state, sp)

    state.current_step = step
    save_state(state, sp)

    handoff_menu = None
    handoff_path: Path | None = None
    run_summary = f"Completed flow-mode step {step} ({phase_name})."
    await_same = False
    require_confirm: bool | None = None
    blocked = bool(gate_failures) and step in (4, 5)

    if step == FLOWS_MAX_STEP:
        state.mark_step_complete(step)
        state.completed_at = now_iso()
        save_state(state, sp)

        handoff_path = write_handoff(
            skill_name=SKILL_NAME,
            state=state,
            context={
                "Mode": "flows",
                "Flow type": state.custom.get("flow_type", ""),
                "Scope": state.custom.get("flow_scope", {}),
            },
            suggested_next="(end of flow)",
        )

        body += f"\n\nHandoff written to: {handoff_path}"
        clear_state_file(sp)
        handoff_menu = build_skill_handoff_menu(SKILL_NAME, state, sp)
        run_summary = "Completed test (flows mode), wrote handoff, and closed session state."
        next_cmd = None
    elif blocked:
        body += (
            "\n\n---\n\n**GATE FAILED — do not advance.** Fix the issues above, "
            f"then re-run step {step}."
        )
        next_cmd = _next_command(step, state_path=str(sp), mode="flows", next_step=step)
        await_same = True
        require_confirm = True
        run_summary = f"Flow-mode step {step} blocked by gate; session kept open."
    else:
        state.mark_step_complete(step)
        save_state(state, sp)
        next_cmd = _next_command(step, state_path=str(sp), mode="flows")

    append_skill_run_memory(
        SKILL_NAME,
        step,
        phase_name,
        run_summary,
        state=state,
        state_path=sp,
        handoff_path=handoff_path,
    )

    print(
        format_step_output(
            SKILL_NAME,
            step,
            FLOWS_MAX_STEP,
            phase_name,
            body,
            next_cmd=next_cmd,
            phase_todos=FLOWS_PHASE_TODOS.get(step, []),
            handoff_menu=handoff_menu,
            all_phase_names=FLOWS_PHASE_NAMES,
            all_phase_todos=FLOWS_PHASE_TODOS,
            require_confirmation=require_confirm,
            await_same_step=await_same,
        )
    )


def prepare_flow_step_1(state_path: Path, flow_type: str | None) -> None:
    """Write recommendation override sidecar when ``--flow-type`` is passed."""
    if not flow_type:
        return
    from scripts.test._sidecar import log_override_to_stderr, write_recommendation_override

    write_recommendation_override(state_path.parent, flow_type)
    log_override_to_stderr(flow_type)


def required_flow_prompts() -> list[str]:
    return [
        "flow_context",
        "flow_recommendation",
        "flow_scope",
        "flow_scaffold",
        "flow_author",
        "flow_execute",
        "flow_report",
    ]
