#!/usr/bin/env python3
"""UX-review skill orchestrator — product UX audit in a real browser.

Six steps: orient → plan → walkthrough → states/viewports → findings → report.
Suite runs and mock-flow authoring stay on ``forge test`` (``--mode run`` / ``flows``).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.evaluate.template_engine import load_template, render_template
from scripts.shared.orchestrator import (
    SkillState,
    append_skill_run_memory,
    apply_resolved_workflow_step,
    build_base_parser,
    build_next_command,
    build_skill_handoff_menu,
    check_same_skill_clobber,
    clear_state_file,
    format_step_output,
    load_state,
    now_iso,
    print_remaining_session_warning,
    resolve_step1_state_path,
    resolve_step_state_path,
    run_step1_session_hygiene,
    save_state,
    validate_state_path,
    validate_step_or_complete,
    write_handoff,
)

SKILL_NAME = "ux-review"
MAX_STEP = 6

PHASE_NAMES = {
    1: "Orient",
    2: "Review plan",
    3: "Browser walkthrough",
    4: "States & viewports",
    5: "Findings",
    6: "Report + handoff",
}

PHASE_TODOS: dict[int, list[dict[str, str]]] = {
    1: [
        {
            "content": "Map purpose, users, IA, features, and critical journeys",
            "activeForm": "Orienting on the product",
        },
        {
            "content": "Confirm base URL and roles to review",
            "activeForm": "Confirming entry surfaces",
        },
    ],
    2: [
        {
            "content": "Write the structured review plan and seed the coverage checklist",
            "activeForm": "Planning the UX review",
        },
    ],
    3: [
        {
            "content": "Visit every in-scope page; exercise controls and workflows",
            "activeForm": "Walking the application",
        },
        {
            "content": "Capture screenshots; keep the coverage checklist current",
            "activeForm": "Updating coverage evidence",
        },
    ],
    4: [
        {
            "content": "Force empty, loading, validation, error, and success states",
            "activeForm": "Exercising UI states",
        },
        {
            "content": "Spot-check agreed viewports (desktop / tablet / mobile)",
            "activeForm": "Checking responsiveness",
        },
    ],
    5: [
        {
            "content": "Document findings with severity, impact, repro, and recommendations",
            "activeForm": "Writing UX findings",
        },
    ],
    6: [
        {
            "content": "Produce the prioritized report, themes, quick wins, and coverage record",
            "activeForm": "Finalizing the UX report",
        },
    ],
}

_TEMPLATE_BY_STEP = {
    1: "ux_review/orient",
    2: "ux_review/plan",
    3: "ux_review/walkthrough",
    4: "ux_review/states",
    5: "ux_review/findings",
    6: "ux_review/report",
}


def _ensure_custom(state: SkillState) -> None:
    defaults: dict = {
        "base_url": "",
        "roles": ["anonymous"],
        "orientation": {},
        "review_plan": {},
        "coverage": {
            "pages": [],
            "controls": [],
            "workflows": [],
            "states": [],
            "viewports": [],
            "skips": [],
        },
        "findings": [],
        "report_path": "",
    }
    for key, value in defaults.items():
        state.custom.setdefault(key, value)


def _build_variables(state: SkillState, sp: Path) -> dict[str, str]:
    orientation = state.custom.get("orientation") or {}
    plan = state.custom.get("review_plan") or {}
    coverage = state.custom.get("coverage") or {}
    findings = state.custom.get("findings") or []
    return {
        "BASE_URL": str(state.custom.get("base_url") or "(ask user)"),
        "ROLES": ", ".join(state.custom.get("roles") or ["anonymous"]),
        "ORIENTATION_JSON": json.dumps(orientation, indent=2) if orientation else "(empty — fill this step)",
        "REVIEW_PLAN_JSON": json.dumps(plan, indent=2) if plan else "(empty — fill this step)",
        "COVERAGE_JSON": json.dumps(coverage, indent=2),
        "FINDINGS_COUNT": str(len(findings)),
        "FINDINGS_JSON": json.dumps(findings, indent=2) if findings else "[]",
        "STATE_PATH": str(sp),
        "STATE_DIR": str(sp.parent),
        "REPORT_PATH": str(state.custom.get("report_path") or "memory/ux-review-report.md"),
        "QUICK": "yes" if state.custom.get("quick") else "no",
    }


def _next_command(step: int, state_path: str = "") -> str:
    extra: dict[str, str] = {}
    if state_path:
        extra["state"] = state_path
    return build_next_command(
        SCRIPT_DIR / "ux_review.py",
        step,
        MAX_STEP,
        **extra,
    )


def _format(
    step: int,
    body: str,
    next_cmd: str | None = None,
    handoff_menu: str | None = None,
) -> str:
    return format_step_output(
        SKILL_NAME,
        step,
        MAX_STEP,
        PHASE_NAMES.get(step, f"Step {step}"),
        body,
        next_cmd=next_cmd,
        phase_todos=PHASE_TODOS.get(step, []),
        handoff_menu=handoff_menu,
        all_phase_names=PHASE_NAMES,
        all_phase_todos=PHASE_TODOS,
    )


def _check_plan_gate(state: SkillState) -> list[str]:
    plan = state.custom.get("review_plan") or {}
    missing: list[str] = []
    if not plan.get("journeys") and not plan.get("pages"):
        missing.append("review_plan needs journeys and/or pages before walkthrough")
    if not (state.custom.get("base_url") or "").strip():
        missing.append("base_url is empty — set it before browser walkthrough")
    return missing


def _check_findings_gate(state: SkillState) -> list[str]:
    findings = state.custom.get("findings") or []
    coverage = state.custom.get("coverage") or {}
    missing: list[str] = []
    required = ("title", "severity", "location", "impact", "steps", "recommendation")
    for i, finding in enumerate(findings):
        if not isinstance(finding, dict):
            missing.append(f"findings[{i}] must be an object")
            continue
        for key in required:
            if not finding.get(key):
                missing.append(f"findings[{i}] missing '{key}'")
    if not findings and not coverage.get("clean_review"):
        missing.append(
            "findings is empty but coverage.clean_review is not true — "
            "document findings or set coverage.clean_review=true for a clean pass"
        )
    pages = coverage.get("pages") or []
    controls = coverage.get("controls") or []
    workflows = coverage.get("workflows") or []
    if not (pages or controls or workflows):
        missing.append(
            "coverage has no pages/controls/workflows — record what was reviewed before report"
        )
    return missing


def handle_step_1(args: argparse.Namespace) -> None:
    sp = resolve_step1_state_path(
        SKILL_NAME,
        args.state,
        parallel=getattr(args, "parallel", False),
        label=getattr(args, "label", None),
        session_id=getattr(args, "session", None),
    )
    sp.parent.mkdir(parents=True, exist_ok=True)

    check_same_skill_clobber(
        SKILL_NAME,
        allow_parallel=bool(getattr(args, "parallel", False) or args.state),
        target_state_path=sp,
    )
    run_step1_session_hygiene(SKILL_NAME, sp)

    existing = None
    if args.state:
        existing = validate_state_path(args.state, SKILL_NAME)
    elif sp.exists():
        existing = sp

    state = None
    if existing is not None:
        try:
            state = load_state(existing)
            sp = existing
        except Exception:
            state = None

    if state is None:
        state = SkillState(skill_name=SKILL_NAME, max_step=MAX_STEP)
        state.started_at = now_iso()

    _ensure_custom(state)
    if getattr(args, "base_url", None):
        state.custom["base_url"] = args.base_url
    state.custom["quick"] = bool(getattr(args, "quick", False))
    save_state(state, sp)
    print_remaining_session_warning(SKILL_NAME)
    print(f"STATE FILE: {sp}\n", file=sys.stderr)

    _run_step(1, state, sp)


def _load_existing_state(
    step: int,
    state_file: str | None,
    session_id: str | None = None,
) -> tuple[SkillState, Path]:
    sp = resolve_step_state_path(
        SKILL_NAME, step, state_file=state_file, session_id=session_id
    )
    if not sp.exists():
        print("ERROR: No ux-review session in progress. Run step 1 first.")
        print("If the state file is elsewhere, pass --state <path>")
        sys.exit(1)
    try:
        state = load_state(sp)
    except (json.JSONDecodeError, KeyError, FileNotFoundError) as exc:
        print(f"ERROR: Cannot load state at {sp}: {exc}")
        sys.exit(1)
    _ensure_custom(state)
    return state, sp


def handle_step_n(
    step: int,
    state_file: str | None = None,
    session_id: str | None = None,
    *,
    base_url: str | None = None,
) -> None:
    state, sp = _load_existing_state(step, state_file, session_id=session_id)
    if base_url:
        state.custom["base_url"] = base_url
    save_state(state, sp)
    _run_step(step, state, sp)


def _run_step(step: int, state: SkillState, sp: Path) -> None:
    template_name = _TEMPLATE_BY_STEP.get(step)
    if not template_name:
        print(f"ERROR: Invalid step {step}", file=sys.stderr)
        sys.exit(1)

    gate_failures: list[str] = []
    if step == 3:
        gate_failures = _check_plan_gate(state)
    elif step == 6:
        gate_failures = _check_findings_gate(state)

    variables = _build_variables(state, sp)
    variables["PLAN_GATE_FAILURES"] = (
        "\n".join(f"- {f}" for f in gate_failures) if step == 3 and gate_failures else ""
    )
    variables["FINDINGS_GATE_FAILURES"] = (
        "\n".join(f"- {f}" for f in gate_failures) if step == 6 and gate_failures else ""
    )

    template = load_template(template_name)
    body = render_template(template, variables)

    if step == 3 and gate_failures:
        body = (
            "## PLAN GATE — incomplete\n\n"
            "Finish orientation/plan (steps 1–2) before walkthrough:\n\n"
            + variables["PLAN_GATE_FAILURES"]
            + "\n\n---\n\n"
            + body
        )
        state.current_step = step
        save_state(state, sp)
        append_skill_run_memory(
            SKILL_NAME,
            step,
            PHASE_NAMES[step],
            "Walkthrough blocked by plan gate.",
            state=state,
            state_path=sp,
        )
        print(_format(step, body, _next_command(2, state_path=str(sp))))
        sys.exit(1)

    if step == 6 and gate_failures:
        body = (
            "## FINDINGS GATE — incomplete\n\n"
            "Complete structured findings (step 5) before handoff:\n\n"
            + variables["FINDINGS_GATE_FAILURES"]
            + "\n\n---\n\n"
            + body
        )
        state.current_step = step
        save_state(state, sp)
        append_skill_run_memory(
            SKILL_NAME,
            step,
            PHASE_NAMES[step],
            "Report blocked by findings gate.",
            state=state,
            state_path=sp,
        )
        print(_format(step, body, _next_command(5, state_path=str(sp))))
        sys.exit(1)

    state.current_step = step
    save_state(state, sp)

    handoff_menu = None
    handoff_path: Path | None = None
    run_summary = f"Completed step {step} ({PHASE_NAMES[step]})."

    if step == MAX_STEP:
        state.mark_step_complete(step)
        state.completed_at = now_iso()
        save_state(state, sp)

        findings = state.custom.get("findings") or []
        high = [
            f
            for f in findings
            if str(f.get("severity", "")).lower() in ("blocker", "critical", "high")
        ]
        suggested_next = "diagnose" if high else "ship"

        handoff_path = write_handoff(
            skill_name=SKILL_NAME,
            state=state,
            context={
                "Base URL": state.custom.get("base_url", ""),
                "Findings": str(len(findings)),
                "High/blocker": str(len(high)),
                "Report": str(state.custom.get("report_path") or "memory/ux-review-report.md"),
                "Suggested action": (
                    "diagnose high-severity UX issues" if high else "UX review complete"
                ),
            },
            suggested_next=suggested_next,
        )
        body += f"\n\nHandoff written to: {handoff_path}"
        handoff_menu = build_skill_handoff_menu(SKILL_NAME, state, sp)
        clear_state_file(sp)
        run_summary = "Completed ux-review, wrote handoff, and closed session state."
    else:
        state.mark_step_complete(step)
        save_state(state, sp)

    append_skill_run_memory(
        SKILL_NAME,
        step,
        PHASE_NAMES[step],
        run_summary,
        state=state,
        state_path=sp,
        handoff_path=handoff_path,
    )

    next_cmd = _next_command(step, state_path=str(sp)) if step < MAX_STEP else None
    print(_format(step, body, next_cmd, handoff_menu=handoff_menu))


def main() -> None:
    parser = build_base_parser(SKILL_NAME, MAX_STEP)
    parser.add_argument(
        "--base-url",
        type=str,
        default=None,
        help="Application base URL to review",
    )
    args = parser.parse_args()
    apply_resolved_workflow_step(args, SKILL_NAME, MAX_STEP)

    if validate_step_or_complete(args.step, MAX_STEP, SKILL_NAME):
        return
    if args.step == 1:
        handle_step_1(args)
    else:
        handle_step_n(
            args.step,
            state_file=args.state,
            session_id=getattr(args, "session", None),
            base_url=getattr(args, "base_url", None),
        )


if __name__ == "__main__":
    main()
