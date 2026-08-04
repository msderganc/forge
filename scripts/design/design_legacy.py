#!/usr/bin/env python3
"""Legacy design orchestrator body (pre declarative skill engine).

Used when ``FORGE_SKILL_ENGINE=0``. Prefer ``scripts.design.design`` shim →
``run_skill`` when the engine is enabled.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Auto-detect repo root so this works from any working directory
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent  # scripts/design/ -> scripts/ -> repo root

# Add repo root to sys.path so imports resolve without PYTHONPATH
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.shared.orchestrator import (
    SkillState,
    append_skill_run_memory,
    apply_resolved_workflow_step,
    build_base_parser,
    build_next_command,
    build_skill_handoff_menu,
    check_same_skill_clobber,
    clear_state_file,
    find_state_file,
    format_step_output,
    print_remaining_session_warning,
    run_step1_session_hygiene,
    load_state,
    now_iso,
    render_dashboard,
    resolve_step1_state_path,
    is_state_stale,
    runtime_memory_dir,
    runtime_memory_dir_relative,
    runtime_state_path,
    save_state,
    validate_state_path,
    validate_step_or_complete,
    write_handoff,
)
from scripts.design.spec_gate import (
    exit_if_gate_fails as exit_if_spec_gate_fails,
    gate_sidecar_path,
    handoff_spec_summary,
    load_gate_json,
    validate_spec_gate,
)
from scripts.design.spec_issues import (
    exit_if_gate_fails as exit_if_issues_gate_fails,
    gate_sidecar_path as issues_gate_sidecar_path,
    handoff_issues_summary,
    issues_status_block,
    validate_spec_issues_gate,
)
from scripts.evaluate.template_engine import load_template, render_template
from scripts.shared.studio_status import studio_status_block

SKILL_NAME = "design"
MAX_STEP = 8
PROMPTS_DIR = REPO_ROOT / "prompts"

PHASE_NAMES = {
    1: "Startup",
    2: "Scope & Team",
    3: "Investigation Dispatch",
    4: "Investigation Review",
    5: "Solution Dispatch",
    6: "Solution Review & Approval",
    7: "Spec → Issues",
    8: "Handoff",
}

PHASE_TODOS = {
    1: [
        {"content": "Detect autonomy level and check for resumable session",
         "activeForm": "Detecting autonomy and session state"},
        {"content": "Initialize design state and memory directory",
         "activeForm": "Initializing state"},
    ],
    2: [
        {"content": "Assess task scope and type (feature/bugfix/refactor)",
         "activeForm": "Assessing scope"},
        {"content": "Compose agent team based on scope",
         "activeForm": "Composing team"},
    ],
    3: [
        {"content": "Dispatch Architect for investigation lead",
         "activeForm": "Dispatching Architect"},
        {"content": "Dispatch Investigator for evidence gathering",
         "activeForm": "Dispatching Investigator"},
        {"content": "Wait for investigation artifacts",
         "activeForm": "Waiting for artifacts"},
    ],
    4: [
        {"content": "Run 4-step review loop on investigation",
         "activeForm": "Running investigation review loop"},
        {"content": "Record findings and resolve blockers",
         "activeForm": "Recording findings"},
    ],
    5: [
        {"content": "Dispatch Architect for solution generation",
         "activeForm": "Dispatching Architect for solutions"},
        {"content": "Run brainstorming protocol (SCAMPER + Pugh Matrix)",
         "activeForm": "Running brainstorming"},
    ],
    6: [
        {"content": "Run review loop on proposed solutions",
         "activeForm": "Running solution review loop"},
        {"content": "Run pre-mortem analysis on recommended solution",
         "activeForm": "Running pre-mortem"},
        {"content": "Present solutions to user for approval",
         "activeForm": "Presenting solutions for approval"},
    ],
    7: [
        {"content": "Decompose approved spec into plan-ready issues",
         "activeForm": "Splitting spec into issues"},
        {"content": "Create beads issues when available and record sidecar",
         "activeForm": "Recording spec issues"},
    ],
    8: [
        {"content": "Write handoff file for next skill",
         "activeForm": "Writing handoff file"},
        {"content": "Render dashboard and complete skill",
         "activeForm": "Rendering dashboard"},
    ],
}


def _ensure_develop_custom(state: SkillState) -> None:
    """Default keys for scope/spec gate (backward compatible)."""
    defaults: dict[str, str | bool] = {
        "scope_tier": "unknown",
        "spec_required": False,
        "scope_rationale": "",
        "brainstorming_mode": "design_first_v2",
        "diagnose_complexity_hint": "",
    }
    for k, v in defaults.items():
        state.custom.setdefault(k, v)


def _sync_develop_scope_from_memory(
    state: SkillState,
    state_path: Path | None = None,
) -> None:
    """Ingest design-scope.json — prefer session sidecar, then runtime memory."""
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
    # Record which file won so agents can avoid stale global pollution
    state.custom["scope_source"] = str(path)

def _spec_gate_status_block(state: SkillState, state_path: Path) -> str:
    """Human-readable spec gate status for templates."""
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


def _state_path() -> Path:
    """Return the default state file path for the develop skill."""
    return runtime_state_path(SKILL_NAME)


def _build_variables(state: SkillState) -> dict[str, str]:
    """Build template variable dict from state."""
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

    # Review state for templates that need it
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

    # Solutions summary for approval step
    solutions_summary = state.custom.get("solutions_summary", "(Solutions not yet generated)")

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
    return {
        "AUTONOMY_INSTRUCTIONS": autonomy_text,
        "DEVELOP_NO_EDIT_POLICY": no_edit_policy,
        "PREVIOUS_FINDINGS": findings_text.strip(),
        "REVIEW_STATE": review_state.strip(),
        "SOLUTIONS_SUMMARY": solutions_summary,
        "SCOPE_TIER": tier,
        "SPEC_REQUIRED": "yes" if spec_req else "no",
        "SCOPE_RATIONALE": str(state.custom.get("scope_rationale", "")).strip() or "(none yet)",
        "SPEC_GATE_STATUS": "(not computed)",
        "SPEC_ISSUES_GATE_STATUS": "(not computed)",
        "STUDIO_STATUS": studio_status,
        "STUDIO_LOG": studio_vars["STUDIO_LOG"],
        "STUDIO_APPROVED": studio_vars["STUDIO_APPROVED"],
        "STATE_DIR": "(directory containing your develop --state file)",
    }


def _next_command(step: int, state_path: str = "") -> str:
    """Build agent-facing continuation for the next step."""
    extra = {}
    if state_path:
        extra["state"] = state_path
    return build_next_command(SCRIPT_DIR / "design.py", step, MAX_STEP, **extra)


def _format(step: int, body: str, next_cmd: str | None = None, cross_skill_next: str | None = None, handoff_menu: str | None = None, *, require_confirmation: bool | None = None) -> str:
    """Format step output with standard header, todos, and next-step directive."""
    phase_name = PHASE_NAMES.get(step, f"Step {step}")
    return format_step_output(
        SKILL_NAME, step, MAX_STEP, phase_name, body,
        next_cmd=next_cmd,
        phase_todos=PHASE_TODOS.get(step, []),
        cross_skill_next=cross_skill_next,
        handoff_menu=handoff_menu,
        all_phase_names=PHASE_NAMES,
        all_phase_todos=PHASE_TODOS,
        require_confirmation=require_confirmation,
    )


def _parse_autonomy(args: argparse.Namespace) -> int:
    """Extract autonomy level from CLI flags."""
    if getattr(args, "auto3", False):
        return 3
    if getattr(args, "auto2", False):
        return 2
    if getattr(args, "auto1", False):
        return 1
    return 1  # default


def handle_step_1(args: argparse.Namespace) -> None:
    """Step 1: Startup -- dependency detection, autonomy, session resume, init."""
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

    # Check for existing state (session resume). Important: honor the resolved
    # step-1 path so auto-parallel fan-out is not overwritten by broad
    # find_state_file() fallback.
    existing = None
    if args.state:
        existing = validate_state_path(args.state, SKILL_NAME)
    elif sp.exists():
        existing = sp

    if existing is not None:
        try:
            loaded = load_state(existing)
            # For implicit starts, stale in-progress state should be treated as
            # ignorable so a fresh session can start cleanly.
            if args.state or not is_state_stale(loaded, existing):
                state = loaded
                sp = existing
            else:
                state = None
        except Exception:
            state = None
    else:
        state = None

    if state is None:
        state = SkillState(skill_name=SKILL_NAME, max_step=MAX_STEP)
        state.started_at = now_iso()

    _ensure_develop_custom(state)
    state.autonomy_level = _parse_autonomy(args)
    state.quick_mode = getattr(args, "quick", False)
    save_state(state, sp)
    print_remaining_session_warning(SKILL_NAME)

    print(f"STATE FILE: {sp}\n", file=sys.stderr)

    template = load_template("design/startup")
    variables = _build_variables(state)
    body = render_template(template, variables)

    # Mark step 1 fully completed
    state.mark_step_complete(1)
    save_state(state, sp)
    append_skill_run_memory(
        SKILL_NAME,
        1,
        PHASE_NAMES[1],
        "Initialized develop session and startup context.",
        state=state,
        state_path=sp,
    )

    next_cmd = _next_command(1, state_path=str(sp))
    print(_format(1, body, next_cmd))


def _load_existing_state(
    step: int,
    state_file: str | None,
    session_id: str | None = None,
) -> tuple[SkillState, Path]:
    """Load existing state for steps 2-7."""
    from scripts.shared.orchestrator import resolve_step_state_path

    sp = resolve_step_state_path(
        SKILL_NAME, step, state_file=state_file, session_id=session_id
    )

    if not sp.exists():
        print("ERROR: No design session in progress. Run step 1 first.")
        print("If the state file is elsewhere, pass --state <path> or --session <id>")
        sys.exit(1)

    try:
        state = load_state(sp)
    except json.JSONDecodeError:
        print(f"ERROR: State file is corrupted: {sp}")
        print("Delete it and re-run step 1.")
        sys.exit(1)
    except KeyError as e:
        print(f"ERROR: State file is invalid -- {e}")
        print("Delete it and re-run step 1.")
        sys.exit(1)
    except FileNotFoundError:
        print(f"ERROR: State file not found at {sp}")
        sys.exit(1)

    return state, sp


def handle_step_n(
    step: int,
    state_file: str | None = None,
    args: argparse.Namespace | None = None,
    session_id: str | None = None,
) -> None:
    """Steps 2-8: Load state, render appropriate template, output prompt."""
    state, sp = _load_existing_state(step, state_file, session_id=session_id)

    _ensure_develop_custom(state)
    _sync_develop_scope_from_memory(state, sp)
    # If scope still unknown at late steps but a design spec gate exists, require medium
    if step >= 6 and str(state.custom.get("scope_tier", "unknown")) == "unknown":
        gate = sp.parent / ".design-spec-gate.json"
        legacy_gate = sp.parent / ".develop-spec-gate.json"
        if gate.is_file() or legacy_gate.is_file():
            state.custom["scope_tier"] = "medium"
            state.custom["spec_required"] = True
    save_state(state, sp)

    ns = args or argparse.Namespace()
    ts = ""
    spec_required = bool(state.custom.get("spec_required"))

    if step == 7 and spec_required:
        ok, msg = validate_spec_gate(
            sp,
            spec_required,
            allow_incomplete=False,
        )
        exit_if_spec_gate_fails(ok, msg)

    if step == MAX_STEP:
        ts = now_iso()
        ok, msg = validate_spec_gate(
            sp,
            spec_required,
            allow_incomplete=bool(getattr(ns, "allow_spec_incomplete", False)),
            override_reason=str(getattr(ns, "spec_override_reason", "") or ""),
            override_requested_by=str(getattr(ns, "spec_override_requested_by", "") or ""),
            override_follow_up=str(getattr(ns, "spec_override_follow_up", "") or ""),
            override_timestamp=ts,
        )
        exit_if_spec_gate_fails(ok, msg)

        ok, msg = validate_spec_issues_gate(
            sp,
            spec_required,
            allow_incomplete=bool(getattr(ns, "allow_issues_incomplete", False)),
            override_reason=str(getattr(ns, "issues_override_reason", "") or ""),
            override_requested_by=str(getattr(ns, "issues_override_requested_by", "") or ""),
            override_follow_up=str(getattr(ns, "issues_override_follow_up", "") or ""),
            override_timestamp=ts,
        )
        exit_if_issues_gate_fails(ok, msg)

    template_map = {
        2: "design/scope",
        3: "design/investigation",
        4: "design/investigation_review",
        5: "design/solution",
        6: "design/approval",
        7: "design/spec_issues",
        8: "design/handoff",
    }

    template_name = template_map.get(step)
    if not template_name:
        print(f"ERROR: Invalid step {step}")
        sys.exit(1)

    # Load template before mutating state — a missing template must not leave
    # state half-written.
    template = load_template(template_name)
    variables = _build_variables(state)
    variables["STATE_DIR"] = str(sp.resolve().parent)
    variables["SPEC_GATE_STATUS"] = _spec_gate_status_block(state, sp)
    variables["SPEC_ISSUES_GATE_STATUS"] = issues_status_block(sp)
    body = render_template(template, variables)

    if step == 6 and state.custom.get("spec_required"):
        try:
            spec_tmpl = load_template("design/spec_gate")
            body += "\n\n---\n\n" + render_template(spec_tmpl, variables)
        except FileNotFoundError:
            pass

    if step == 7 and not state.custom.get("spec_required"):
        body += (
            "\n\n---\n\n**Note:** `SPEC_REQUIRED` is **no** (trivial scope). "
            "No `.design-spec-issues.json` sidecar is required — proceed to "
            "`forge design --step 8` after optional beads capture from approved "
            "solutions.\n"
        )

    state.current_step = step
    save_state(state, sp)

    # Mark completion on final step
    handoff_menu = None
    handoff_path: Path | None = None
    run_summary = f"Completed step {step} ({PHASE_NAMES.get(step, f'Step {step}')})."
    if step == MAX_STEP:
        state.mark_step_complete(step)
        state.completed_at = now_iso()
        save_state(state, sp)

        ns = args or argparse.Namespace()
        spec_gate_label = (
            "overridden"
            if getattr(ns, "allow_spec_incomplete", False)
            else "passed"
        )
        gate_data = (
            None
            if getattr(ns, "allow_spec_incomplete", False)
            else load_gate_json(gate_sidecar_path(sp))
        )
        spec_summary = handoff_spec_summary(gate_data)
        issues_data = (
            None
            if getattr(ns, "allow_issues_incomplete", False)
            else load_gate_json(issues_gate_sidecar_path(sp))
        )
        issues_summary = handoff_issues_summary(issues_data)

        handoff_path = write_handoff(
            skill_name=SKILL_NAME,
            state=state,
            context={
                "Scope": state.custom.get("scope", "see investigation"),
                "Task type": state.custom.get("task_type", "unknown"),
                "Solutions summary": state.custom.get("solutions_summary", "see handoff"),
                "Autonomy level": str(state.autonomy_level),
                "Scope tier": str(state.custom.get("scope_tier", "unknown")),
                "Spec required": str(bool(state.custom.get("spec_required"))),
                "Spec gate": spec_gate_label,
                "Spec path": spec_summary.get("Spec path", ""),
                "Spec approved": spec_summary.get("Spec approved", ""),
                "Issues gate": (
                    "overridden"
                    if getattr(ns, "allow_issues_incomplete", False)
                    else ("passed" if spec_required else "not required")
                ),
                "Issues sidecar": issues_summary.get("Issues sidecar", ""),
                "Issue count": issues_summary.get("Issue count", ""),
                "Beads mode": issues_summary.get("Beads mode", ""),
                "Epic": issues_summary.get("Epic", ""),
                "Override": (
                    f"yes — reason={getattr(ns, 'spec_override_reason', '') or '(n/a)'}; "
                    f"follow_up={getattr(ns, 'spec_override_follow_up', '') or '(n/a)'}; "
                    f"requested_by={getattr(ns, 'spec_override_requested_by', '') or '(n/a)'}; "
                    f"timestamp={ts}"
                    if getattr(ns, "allow_spec_incomplete", False)
                    else "no"
                ),
                "Issues override": (
                    f"yes — reason={getattr(ns, 'issues_override_reason', '') or '(n/a)'}; "
                    f"follow_up={getattr(ns, 'issues_override_follow_up', '') or '(n/a)'}; "
                    f"requested_by={getattr(ns, 'issues_override_requested_by', '') or '(n/a)'}; "
                    f"timestamp={ts}"
                    if getattr(ns, "allow_issues_incomplete", False)
                    else "no"
                ),
            },
            suggested_next="plan",
        )

        dashboard = render_dashboard(state)
        body += f"\n\n---\n\n{dashboard}"
        body += f"\n\nHandoff written to: {handoff_path}"
        handoff_menu = build_skill_handoff_menu(SKILL_NAME, state, sp)
        clear_state_file(sp)
        run_summary = "Completed develop workflow, wrote handoff, and closed session state."

    if step != MAX_STEP:
        state.mark_step_complete(step)
        save_state(state, sp)

    append_skill_run_memory(
        SKILL_NAME,
        step,
        PHASE_NAMES.get(step, f"Step {step}"),
        run_summary,
        state=state,
        state_path=sp,
        handoff_path=handoff_path,
    )

    next_cmd = _next_command(step, state_path=str(sp)) if step < MAX_STEP else None
    require_confirm = True if step == 6 else None
    print(_format(step, body, next_cmd, handoff_menu=handoff_menu, require_confirmation=require_confirm))


def main() -> None:
    parser = build_base_parser(SKILL_NAME, MAX_STEP)
    parser.add_argument(
        "--auto1", action="store_true",
        help="Set autonomy to Level 1 (pause at every gate)",
    )
    parser.add_argument(
        "--auto2", action="store_true",
        help="Set autonomy to Level 2 (pause at approval only)",
    )
    parser.add_argument(
        "--auto3", action="store_true",
        help="Set autonomy to Level 3 (full auto, pause at final approval)",
    )
    parser.add_argument(
        "--allow-spec-incomplete",
        action="store_true",
        help=(
            "Bypass strict design-spec gate on step 8 when spec_required. "
            "Requires --spec-override-reason and --spec-override-follow-up."
        ),
    )
    parser.add_argument(
        "--spec-override-reason",
        type=str,
        default="",
        help="Recorded in handoff when using --allow-spec-incomplete.",
    )
    parser.add_argument(
        "--spec-override-requested-by",
        type=str,
        default="",
        help="Optional identifier for who requested the override.",
    )
    parser.add_argument(
        "--spec-override-follow-up",
        type=str,
        default="",
        help="Required tracked follow-up when using --allow-spec-incomplete.",
    )

    parser.add_argument(
        "--issues-override-follow-up",
        type=str,
        default="",
        help="Required tracked follow-up when using --allow-issues-incomplete.",
    )
    parser.add_argument(
        "--allow-issues-incomplete",
        action="store_true",
        help=(
            "Bypass strict design-spec-issues gate on step 8 when spec_required. "
            "Requires --issues-override-reason and --issues-override-follow-up."
        ),
    )
    parser.add_argument(
        "--issues-override-reason",
        type=str,
        default="",
        help="Recorded in handoff when using --allow-issues-incomplete.",
    )
    parser.add_argument(
        "--issues-override-requested-by",
        type=str,
        default="",
        help="Optional identifier for who requested the issues override.",
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
            args=args,
            session_id=getattr(args, "session", None),
        )


if __name__ == "__main__":
    main()
