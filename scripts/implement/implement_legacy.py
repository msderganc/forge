#!/usr/bin/env python3
"""Implement skill orchestrator.

Script-driven workflow that outputs formatted prompts for Codex to follow.
Each --step invocation loads state, selects the appropriate prompt template,
substitutes variables, and prints the prompt for Codex to execute.

Steps 3-5 form a wave loop: dispatch -> review -> complete, repeating
for each wave in the parallelization map.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Auto-detect repo root so this works from any working directory
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent  # scripts/implement/ -> scripts/ -> repo root

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
    runtime_memory_dir_relative,
    runtime_state_path,
    save_state,
    validate_state_path,
    validate_step,
    validate_step_or_complete,
    write_handoff,
)
from scripts.evaluate.template_engine import load_template, render_template
from scripts.evaluate.plan_resolver import AmbiguousPlanError, resolve_plan_file
from scripts.implement.plan_waves import (
    format_wave_tasks_from_custom,
    sync_waves_from_plan_file,
    wave_rows_to_custom,
)
from scripts.implement.docs_gate import (
    exit_if_gate_fails,
    gate_sidecar_path,
    handoff_docs_summary,
    load_gate_json,
    validate_documentation_gate,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_BRANCH_PREFIX = "feat"

SKILL_NAME = "implement"
MAX_STEP = 8
PROMPTS_DIR = REPO_ROOT / "prompts"

PHASE_NAMES = {
    1: "Plan Detection",
    2: "Branch Setup",
    3: "Wave Dispatch",
    4: "Wave Review",
    5: "Wave Completion",
    6: "Integration Verification",
    7: "Documentation",
    8: "Handoff",
}

TEMPLATE_NAMES = {
    1: "implement/plan_detect",
    2: "implement/branch_setup",
    3: "implement/wave_dispatch",
    4: "implement/wave_review",
    5: "implement/wave_complete",
    6: "implement/integration_check",
    7: "implement/documentation",
    8: "implement/handoff",
}

PHASE_TODOS = {
    1: [
        {"content": "Detect plan path from handoff or CLI",
         "activeForm": "Detecting plan path"},
        {"content": "Initialize implement state",
         "activeForm": "Initializing state"},
    ],
    2: [
        {"content": "Create feature branch",
         "activeForm": "Creating feature branch"},
        {"content": "Identify waves from parallelization map",
         "activeForm": "Identifying waves"},
    ],
    3: [
        {"content": "Dispatch developer agents for current wave",
         "activeForm": "Dispatching wave agents"},
        {"content": "Wait for wave task completion",
         "activeForm": "Waiting for wave completion"},
    ],
    4: [
        {"content": "Run per-task review loops (QA + Critic + Security)",
         "activeForm": "Running per-task reviews"},
        {"content": "Resolve findings from reviews",
         "activeForm": "Resolving findings"},
    ],
    5: [
        {"content": "Merge wave branches to feature branch",
         "activeForm": "Merging wave"},
        {"content": "Check for next wave or proceed to integration verification",
         "activeForm": "Checking wave status"},
    ],
    6: [
        {"content": "Verify cross-wave integration (dependencies, interfaces, architecture)",
         "activeForm": "Verifying cross-wave integration"},
        {"content": "Run regression sweep and performance check",
         "activeForm": "Running regression sweep"},
    ],
    7: [
        {"content": "Dispatch doc-writer for documentation",
         "activeForm": "Dispatching doc-writer"},
        {"content": "Create or update ADRs for significant decisions",
         "activeForm": "Updating ADRs"},
    ],
    8: [
        {"content": "Write handoff file for code-review",
         "activeForm": "Writing handoff"},
        {"content": "Render dashboard and complete",
         "activeForm": "Rendering dashboard"},
    ],
}

# Team roles and when they activate
TEAM_ROLES = [
    ("Backend Dev", "Plan assigns backend tasks"),
    ("Frontend Dev", "Plan assigns frontend tasks"),
    ("QA Reviewer", "Always (per-task review)"),
    ("Critic", "Always (per-task challenge)"),
    ("Security Reviewer", "Plan involves auth, data, APIs, or security-sensitive code"),
    ("Doc-writer", "Documentation phase + capture"),
]


# ---------------------------------------------------------------------------
# State helpers
# ---------------------------------------------------------------------------

def _get_state_path() -> Path:
    """Return the canonical state file path in cwd."""
    return runtime_state_path(SKILL_NAME)


def _resolve_implement_plan_path(state: SkillState) -> Path | None:
    """Absolute path to plan file if present and exists."""
    raw = (state.custom.get("plan_path") or "").strip()
    if not raw:
        return None
    p = Path(raw)
    if p.is_file():
        return p.resolve()
    try:
        return resolve_plan_file(raw, Path.cwd())
    except (FileNotFoundError, AmbiguousPlanError):
        return None


def _init_state(quick: bool = False) -> SkillState:
    """Create a fresh implement state."""
    state = SkillState(skill_name=SKILL_NAME)
    state.max_step = MAX_STEP
    state.quick_mode = quick
    state.started_at = now_iso()
    state.custom = {
        "plan_path": "",
        "feature_branch": "",
        "branch_prefix": DEFAULT_BRANCH_PREFIX,
        "implementation_mode": "parallel",
        "current_wave": 0,
        "total_waves": 0,
        "waves_completed": 0,
        "wave_rows": [],
        "plan_waves_parsed": False,
    }
    return state


def _sync_waves_from_plan(state: SkillState) -> None:
    """Populate total_waves and wave_rows from the plan's parallelization table."""
    plan_path = (state.custom.get("plan_path") or "").strip()
    if not plan_path:
        state.custom["wave_rows"] = []
        state.custom["plan_waves_parsed"] = False
        state.custom["implementation_mode"] = "parallel"
        return
    try:
        path = resolve_plan_file(plan_path, Path.cwd())
        total, rows = sync_waves_from_plan_file(path)
        state.custom["total_waves"] = total
        state.custom["wave_rows"] = wave_rows_to_custom(rows)
        state.custom["plan_waves_parsed"] = bool(rows)
        state.custom["implementation_mode"] = "parallel" if rows else "direct"
    except (OSError, AmbiguousPlanError, FileNotFoundError):
        state.custom["plan_waves_parsed"] = False
        state.custom["implementation_mode"] = "direct"


def _feature_branch_placeholder(state: SkillState) -> str:
    pfx = state.custom.get("branch_prefix") or DEFAULT_BRANCH_PREFIX
    return f"{pfx}/[short-description]"


def _load_or_init_state(
    state_file: str | None,
    quick: bool = False,
    *,
    parallel: bool = False,
    resolved_path: Path | None = None,
) -> tuple[SkillState, Path]:
    """Load existing state or initialize a new one.

    Returns (state, state_path). When ``resolved_path`` is set (step 1 after
    ``resolve_step1_state_path``), always use that path — never fall back to
    flat ``.forge/state/implement.json``.
    """
    if resolved_path is not None:
        sp = resolved_path
        if sp.exists():
            return load_state(sp), sp
        return _init_state(quick=quick), sp

    # Explicit/custom path handling for step 1.
    if state_file or parallel:
        sp = resolve_step1_state_path(SKILL_NAME, state_file, parallel=parallel)
        if sp.exists():
            return load_state(sp), sp
        return _init_state(quick=quick), sp

    # Search for existing state (steps 2+ without --session/--state)
    found = find_state_file(SKILL_NAME)
    if found:
        return load_state(found), found

    # Initialize fresh at a new session path (should be rare outside step 1)
    state = _init_state(quick=quick)
    sp = resolve_step1_state_path(SKILL_NAME, None, parallel=True)
    return state, sp


# ---------------------------------------------------------------------------
# Variable builders
# ---------------------------------------------------------------------------

def _build_team_composition() -> str:
    """Build the team composition table for template substitution."""
    lines = []
    lines.append("| Role | When Activated |")
    lines.append("|------|---------------|")
    for role, condition in TEAM_ROLES:
        lines.append(f"| {role} | {condition} |")
    return "\n".join(lines)


def _studio_template_vars() -> dict[str, str]:
    from forge_next.studio.context import orchestrator_studio_variables

    return orchestrator_studio_variables()


def _build_step1_variables(state: SkillState) -> dict[str, str]:
    """Build template variables for step 1 (plan detection)."""
    return {
        "TEAM_COMPOSITION": _build_team_composition(),
        **_studio_template_vars(),
    }


def _build_step2_variables(state: SkillState) -> dict[str, str]:
    """Build template variables for step 2 (branch setup)."""
    pfx = state.custom.get("branch_prefix") or DEFAULT_BRANCH_PREFIX
    return {
        "PLAN_PATH": state.custom.get("plan_path", "(not yet detected)"),
        "BRANCH_PREFIX": pfx,
        "FEATURE_BRANCH_PATTERN": f"{pfx}/<short-slug>",
        "TASK_BRANCH_PATTERN": f"{pfx}/<short-slug>/task-<n>-<short-slug>",
        **_studio_template_vars(),
    }


def _build_wave_variables(state: SkillState) -> dict[str, str]:
    """Build template variables for wave-related steps (3, 4, 5)."""
    current_wave = state.custom.get("current_wave", 1)
    total_waves = state.custom.get("total_waves", 0)
    waves_completed = state.custom.get("waves_completed", 0)
    implementation_mode = str(state.custom.get("implementation_mode", "parallel"))
    direct_mode = implementation_mode == "direct"

    wave_rows: list[dict[str, object]] = state.custom.get("wave_rows") or []
    if wave_rows and not direct_mode:
        wave_tasks = format_wave_tasks_from_custom(wave_rows, current_wave)
        def _row_wave(rd: dict[str, object]) -> int:
            try:
                return int(rd.get("wave", 0) or 0)
            except (TypeError, ValueError):
                return 0

        agents_here = sorted(
            {
                str(r.get("agent", "")).strip()
                for r in wave_rows
                if _row_wave(r) == current_wave and str(r.get("agent", "")).strip()
            }
        )
        if agents_here:
            agent_list = "Agents for this wave: " + ", ".join(agents_here)
        else:
            agent_list = "See task list above for agent assignments."
        wave_tasks += (
            "\n\n_(Parsed from the plan parallelization table. "
            "If this looks wrong, fix the table and re-run step 2.)_"
        )
    else:
        if direct_mode:
            wave_tasks = (
                "Parallelization map parsing did not produce usable wave rows.\n"
                f"Proceed with **direct implementation** from `{state.custom.get('plan_path', '')}` in dependency order.\n"
                "Treat this as a single implementation pass and continue without asking the user to choose a fallback path."
            )
            agent_list = (
                "Direct mode: implement tasks sequentially on the feature branch, "
                "or dispatch one task at a time if delegation is still helpful."
            )
        else:
            wave_tasks = (
                f"No parallelization table parsed yet. Read the plan file at `{state.custom.get('plan_path', '')}` "
                f"and `{runtime_memory_dir_relative()}/project.md` for the Wave {current_wave} task list.\n"
                f"Each task includes: title, assigned agent, file paths, acceptance criteria."
            )
            agent_list = (
                f"Read `{runtime_memory_dir_relative()}/project.md` for the agent assignments for Wave {current_wave}.\n"
                f"Dispatch each agent per `templates/parallel-dispatch.md`."
            )

    # Quick mode note
    if state.quick_mode:
        quick_note = (
            "**QUICK MODE active.** Minimal reviews: self-review + PM validation only. "
            "Skip cross-review and critic challenge."
        )
    else:
        quick_note = "Standard mode: full four-step review loop for each task."

    # Next wave or proceed to documentation
    if direct_mode:
        next_wave_or_proceed = (
            "Direct implementation mode uses a single pass. After this pass, proceed to integration verification."
        )
    elif waves_completed < total_waves - 1:
        next_wave_or_proceed = (
            f"More waves remain. After completing this wave, proceed to Wave {current_wave + 1}."
        )
    else:
        next_wave_or_proceed = (
            "This is the final wave. After completion, proceed to the Integration Verification phase."
        )

    pfx = state.custom.get("branch_prefix") or DEFAULT_BRANCH_PREFIX

    return {
        "CURRENT_WAVE": str(current_wave),
        "TOTAL_WAVES": str(total_waves) if total_waves > 0 else "(to be determined)",
        "WAVE_TASKS": wave_tasks,
        "AGENT_LIST": agent_list,
        "WAVES_COMPLETED": str(waves_completed),
        "QUICK_MODE_NOTE": quick_note,
        "NEXT_WAVE_OR_PROCEED": next_wave_or_proceed,
        "BRANCH_PREFIX": pfx,
        "FEATURE_BRANCH_PATTERN": f"{pfx}/<short-slug>",
        "TASK_BRANCH_PATTERN": f"{pfx}/<short-slug>/task-<n>-<short-slug>",
        **_studio_template_vars(),
    }


def _build_doc_variables(state: SkillState, state_path: Path | None = None) -> dict[str, str]:
    """Build template variables for step 7 (documentation)."""
    state_dir = (
        str(state_path.resolve().parent)
        if state_path is not None
        else "(directory containing your implement --state file)"
    )
    if state.quick_mode:
        quick_note = (
            "**QUICK MODE active.** Still satisfy the documentation gate: "
            "write `.implement-documentation-gate.json`, clear the plan "
            "`DOCUMENTATION` skeleton marker, and capture evidence for each "
            "applicable audience row."
        )
    else:
        quick_note = (
            "Standard mode: full documentation pass aligned with the plan "
            "Documentation section."
        )
    return {
        "QUICK_MODE_NOTE": quick_note,
        "STATE_DIR": state_dir,
        **_studio_template_vars(),
    }


def _build_handoff_variables(state: SkillState) -> dict[str, str]:
    """Build template variables for step 7 (handoff)."""
    fb = (state.custom.get("feature_branch") or "").strip()
    if not fb:
        fb = _feature_branch_placeholder(state)
    return {
        "FEATURE_BRANCH": fb,
        "BRANCH_PREFIX": state.custom.get("branch_prefix") or DEFAULT_BRANCH_PREFIX,
        "WAVES_COMPLETED": str(state.custom.get("waves_completed", 0)),
        "TOTAL_WAVES": str(state.custom.get("total_waves", 0)),
        **_studio_template_vars(),
    }


# ---------------------------------------------------------------------------
# Step handlers
# ---------------------------------------------------------------------------

def _wave_scoped_todos(step: int, wave: int | None) -> list[dict]:
    """Return PHASE_TODOS[step] with wave context injected for wave-loop steps."""
    todos = [dict(t) for t in PHASE_TODOS.get(step, [])]
    if wave is not None and step in (3, 4, 5):
        for todo in todos:
            todo["content"] = f"Wave {wave}: {todo['content']}"
            todo["activeForm"] = f"Wave {wave}: {todo['activeForm']}"
    return todos


def _next_command(
    current_step: int,
    quick: bool = False,
    target_step: int | None = None,
    *,
    state_path: Path | None = None,
) -> str:
    """Build agent-facing continuation for the next step, bounded by MAX_STEP.

    Returns "" when the requested next step would exceed MAX_STEP. Use
    `target_step` to override the default `current_step + 1` (wave loops in
    step 5 jump back to step 3).
    """
    nxt = target_step if target_step is not None else current_step + 1
    if nxt > MAX_STEP:
        return ""
    fl = ("quick",) if quick else ()
    extra: dict[str, object] = {"flags": fl}
    if state_path is not None:
        extra["state"] = str(state_path)
    if target_step is not None:
        return build_next_command(
            SCRIPT_DIR / "implement.py",
            current_step,
            MAX_STEP,
            next_step=target_step,
            **extra,
        )
    return build_next_command(
        SCRIPT_DIR / "implement.py",
        current_step,
        MAX_STEP,
        **extra,
    )


def _emit(step: int, body: str, next_cmd: str | None,
          cross_skill_next: str | None = None,
          handoff_menu: str | None = None,
          phase_label: str | None = None,
          wave: int | None = None,
          state: SkillState | None = None,
          state_path: Path | None = None,
          handoff_path: Path | None = None,
          summary: str | None = None,
          require_confirmation: bool | None = None) -> None:
    """Shared output helper that injects PHASE_TODOS and continuation blocks."""
    label = phase_label or PHASE_NAMES.get(step, f"Step {step}")
    if state is not None and state_path is not None:
        append_skill_run_memory(
            SKILL_NAME,
            step,
            label,
            summary or f"Completed step {step} ({label}).",
            state=state,
            state_path=state_path,
            handoff_path=handoff_path,
        )
    print(format_step_output(
        SKILL_NAME, step, MAX_STEP, label, body,
        next_cmd=next_cmd,
        phase_todos=_wave_scoped_todos(step, wave),
        cross_skill_next=cross_skill_next,
        handoff_menu=handoff_menu,
        all_phase_names=PHASE_NAMES,
        all_phase_todos=PHASE_TODOS,
        require_confirmation=require_confirmation,
    ))


def handle_step_1(args) -> None:
    """Step 1: Plan detection and state initialization."""
    sp = resolve_step1_state_path(
        SKILL_NAME,
        args.state,
        parallel=getattr(args, "parallel", False),
        label=getattr(args, "label", None),
        session_id=getattr(args, "session", None),
    )
    check_same_skill_clobber(
        SKILL_NAME,
        allow_parallel=bool(getattr(args, "parallel", False) or args.state),
        target_state_path=sp,
    )
    run_step1_session_hygiene(SKILL_NAME, sp)
    print_remaining_session_warning(SKILL_NAME)

    state, sp = _load_or_init_state(
        args.state,
        quick=args.quick,
        parallel=getattr(args, "parallel", False),
        resolved_path=sp,
    )

    # Load template before mutating state — a missing template must not leave
    # state half-written.
    template = load_template(TEMPLATE_NAMES[1])
    variables = _build_step1_variables(state)
    body = render_template(template, variables)

    state.current_step = 1

    # Record plan path if provided via CLI (path, keywords, or native IDE plan locations)
    if args.plan:
        try:
            state.custom["plan_path"] = str(resolve_plan_file(args.plan, Path.cwd()))
        except AmbiguousPlanError as e:
            print("Multiple plans matched. Choose one:\n", file=sys.stderr)
            for i, p in enumerate(e.matches, 1):
                print(f"  {i}. {p}", file=sys.stderr)
            sys.exit(1)
        except FileNotFoundError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)

    if getattr(args, "branch_prefix", None):
        state.custom["branch_prefix"] = args.branch_prefix

    if getattr(args, "defer_graphify_waves", False):
        from forge_next.graphify_enforcement import set_graphify_defer_implement_waves

        set_graphify_defer_implement_waves(REPO_ROOT, defer=True)
        print(
            "forge implement: Graphify deferred for wave steps 3–5 "
            "(clear with `forge graphify undefer-waves`).",
            file=sys.stderr,
        )

    _sync_waves_from_plan(state)

    save_state(state, sp)
    print(f"STATE FILE: {sp}\n", file=sys.stderr)

    # Add plan path hint if provided
    if args.plan:
        body += f"\n\n---\n\n**Plan argument provided:** `{args.plan}`\n"
        body += "Use this path directly (skip detection order steps 2-4).\n"

    # Mark step complete
    state.mark_step_complete(1)
    save_state(state, sp)

    _emit(1, body, _next_command(1, quick=args.quick, state_path=sp), state=state, state_path=sp)


def handle_step_2(state: SkillState, sp: Path) -> None:
    """Step 2: Branch setup and wave identification."""
    _sync_waves_from_plan(state)

    template = load_template(TEMPLATE_NAMES[2])
    variables = _build_step2_variables(state)
    body = render_template(template, variables)

    state.current_step = 2
    save_state(state, sp)

    state.mark_step_complete(2)
    save_state(state, sp)

    _emit(2, body, _next_command(2, quick=state.quick_mode, state_path=sp), state=state, state_path=sp)


def handle_step_3(state: SkillState, sp: Path) -> None:
    """Step 3: Wave dispatch -- send agents for current wave."""
    template = load_template(TEMPLATE_NAMES[3])

    current_wave = state.custom.get("current_wave", 0)
    if current_wave == 0:
        state.custom["current_wave"] = 1
        current_wave = 1

    # 0-wave plans (parser could not derive waves): auto-fallback to direct
    # implementation mode instead of skipping implementation.
    total_waves = state.custom.get("total_waves", 0)
    if total_waves == 0:
        state.custom["implementation_mode"] = "direct"
        state.custom["total_waves"] = 1
        state.custom["current_wave"] = 1

    variables = _build_wave_variables(state)
    body = render_template(template, variables)

    state.current_step = 3
    save_state(state, sp)

    state.mark_step_complete(3)
    save_state(state, sp)

    _emit(3, body, _next_command(3, quick=state.quick_mode, state_path=sp), wave=current_wave, state=state, state_path=sp)


def handle_step_4(state: SkillState, sp: Path) -> None:
    """Step 4: Wave review -- per-task review loop."""
    template = load_template(TEMPLATE_NAMES[4])
    current_wave = state.custom.get("current_wave", 1)
    variables = _build_wave_variables(state)
    body = render_template(template, variables)

    from scripts.shared.structural_probes import inject_structural_probes_section
    from scripts.shared.structural_probes_gate import probe_gate_is_pending
    from scripts.shared.repo_paths import resolve_repo_root

    scan_root = resolve_repo_root(REPO_ROOT)
    state_dir = sp.parent
    body, sidecar, _payload = inject_structural_probes_section(
        body,
        skill_name=SKILL_NAME,
        step=4,
        repo_root=scan_root,
        state_dir=state_dir,
        quick_mode=state.quick_mode,
    )
    if sidecar:
        state.custom["structural_probes_sidecar"] = str(sidecar)
    probe_gate_pending = probe_gate_is_pending(state_dir)

    state.current_step = 4
    save_state(state, sp)

    state.mark_step_complete(4)
    save_state(state, sp)

    _emit(
        4,
        body,
        _next_command(4, quick=state.quick_mode, state_path=sp),
        wave=current_wave,
        state=state,
        state_path=sp,
        require_confirmation=True if probe_gate_pending else None,
    )


def handle_step_5(state: SkillState, sp: Path) -> None:
    """Step 5: Wave completion -- merge and decide next wave or proceed."""
    template = load_template(TEMPLATE_NAMES[5])

    current_wave = state.custom.get("current_wave", 1)
    total_waves = state.custom.get("total_waves", 0)

    # Mark this wave as completed
    waves_completed = state.custom.get("waves_completed", 0) + 1
    state.custom["waves_completed"] = waves_completed

    variables = _build_wave_variables(state)
    body = render_template(template, variables)

    state.current_step = 5
    save_state(state, sp)

    # Determine next step: loop back to step 3 for next wave, or proceed to step 6
    if waves_completed < total_waves:
        state.custom["current_wave"] = current_wave + 1
        save_state(state, sp)
        next_step = 3
    else:
        next_step = 6

    next_cmd = _next_command(5, quick=state.quick_mode, target_step=next_step, state_path=sp)

    phase_label = PHASE_NAMES[5]
    if waves_completed < total_waves:
        phase_label += f" (Wave {current_wave} done, {total_waves - waves_completed} remaining)"
    else:
        phase_label += " (All waves done)"

    state.mark_step_complete(5)
    save_state(state, sp)

    _emit(5, body, next_cmd, phase_label=phase_label, wave=current_wave, state=state, state_path=sp)


def handle_step_6(state: SkillState, sp: Path) -> None:
    """Step 6: Integration verification -- cross-wave checks after all waves complete."""
    template = load_template(TEMPLATE_NAMES[6])
    variables = _build_wave_variables(state)
    body = render_template(template, variables)

    state.current_step = 6
    save_state(state, sp)

    state.mark_step_complete(6)
    save_state(state, sp)

    _emit(6, body, _next_command(6, quick=state.quick_mode, state_path=sp), state=state, state_path=sp)


def handle_step_7(state: SkillState, sp: Path) -> None:
    """Step 7: Documentation dispatch."""
    template = load_template(TEMPLATE_NAMES[7])
    variables = _build_doc_variables(state, sp)
    body = render_template(template, variables)

    state.current_step = 7
    save_state(state, sp)

    state.mark_step_complete(7)
    save_state(state, sp)

    _emit(7, body, _next_command(7, quick=state.quick_mode, state_path=sp), state=state, state_path=sp)


def handle_step_8(state: SkillState, sp: Path, args: argparse.Namespace | None = None) -> None:
    """Step 8: Handoff and dashboard."""
    ns = args or argparse.Namespace()
    plan_p = _resolve_implement_plan_path(state)
    ts = now_iso()
    ok, msg = validate_documentation_gate(
        sp,
        plan_p,
        allow_incomplete=bool(getattr(ns, "allow_docs_incomplete", False)),
        override_reason=str(getattr(ns, "docs_override_reason", "") or ""),
        override_requested_by=str(getattr(ns, "docs_override_requested_by", "") or ""),
        override_follow_up=str(getattr(ns, "docs_override_follow_up", "") or ""),
        override_timestamp=ts,
    )
    exit_if_gate_fails(ok, msg)

    template = load_template(TEMPLATE_NAMES[8])
    variables = _build_handoff_variables(state)
    body = render_template(template, variables)

    state.current_step = 8
    state.mark_step_complete(8)
    state.completed_at = now_iso()
    save_state(state, sp)

    # Write the handoff file
    doc_gate = "overridden" if getattr(ns, "allow_docs_incomplete", False) else "passed"
    gate_data = (
        None
        if getattr(ns, "allow_docs_incomplete", False)
        else load_gate_json(gate_sidecar_path(sp))
    )
    doc_summary = handoff_docs_summary(gate_data)
    context = {
        "Feature branch": state.custom.get("feature_branch") or _feature_branch_placeholder(state),
        "Waves completed": str(state.custom.get("waves_completed", 0)),
        "Total waves": str(state.custom.get("total_waves", 0)),
        "Plan path": state.custom.get("plan_path", ""),
        "Documentation gate": doc_gate,
        "Docs Completed": doc_summary.get("Docs Completed", ""),
        "Docs Deferred": (
            f"override — follow-up: {(getattr(ns, 'docs_override_follow_up', '') or '').strip()}"
            if getattr(ns, "allow_docs_incomplete", False)
            else "(none)"
        ),
        "External Wiki Evidence": doc_summary.get("External Wiki Evidence", ""),
        "Override Used (if any)": (
            "yes — reason: "
            + (getattr(ns, "docs_override_reason", "") or "").strip()
            + f"; requested_by={getattr(ns, 'docs_override_requested_by', '') or '(n/a)'}; "
            f"follow_up={getattr(ns, 'docs_override_follow_up', '') or '(n/a)'}; "
            f"timestamp={ts}"
            if getattr(ns, "allow_docs_incomplete", False)
            else "no"
        ),
    }
    handoff_path = write_handoff(SKILL_NAME, state, context, "code-review")
    clear_state_file(sp)

    # Append dashboard to body
    dashboard = render_dashboard(state)
    body += f"\n\n---\n\n{dashboard}"

    handoff_menu = build_skill_handoff_menu(SKILL_NAME, state, sp)
    _emit(
        8,
        body,
        None,
        handoff_menu=handoff_menu,
        state=state,
        state_path=sp,
        handoff_path=handoff_path,
        summary="Completed implement workflow, wrote handoff, and cleared implement state.",
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = build_base_parser(SKILL_NAME, MAX_STEP)
    parser.add_argument(
        "--plan", type=str, default=None,
        help="Path to plan file (step 1 only; auto-detected from handoff if omitted)"
    )
    parser.add_argument(
        "--branch-prefix",
        type=str,
        choices=("feat", "fix", "chore", "refactor", "docs", "hotfix"),
        default=None,
        help=(
            "Git branch prefix for feature/task branches (default: feat). "
            "Stored in state on step 1 when passed."
        ),
    )
    parser.add_argument(
        "--allow-docs-incomplete",
        action="store_true",
        help=(
            "Bypass strict documentation completion gate on step 8. "
            "Requires --docs-override-reason."
        ),
    )
    parser.add_argument(
        "--docs-override-reason",
        type=str,
        default="",
        help="Required when using --allow-docs-incomplete (recorded in handoff).",
    )
    parser.add_argument(
        "--docs-override-requested-by",
        type=str,
        default="",
        help="Optional identifier for who requested the override.",
    )
    parser.add_argument(
        "--docs-override-follow-up",
        type=str,
        default="",
        help=(
            "Required with --allow-docs-incomplete: tracked follow-up item "
            "(recorded in handoff)."
        ),
    )
    parser.add_argument(
        "--defer-graphify-waves",
        action="store_true",
        help=(
            "Defer GRAPHIFY banners during implement wave steps 3–5; "
            "same as `forge graphify defer-waves` (step 1 only)"
        ),
    )
    args = parser.parse_args()
    apply_resolved_workflow_step(args, SKILL_NAME, MAX_STEP)

    if validate_step_or_complete(args.step, MAX_STEP, SKILL_NAME):
        return

    if args.step == 1:
        handle_step_1(args)
    else:
        from scripts.shared.orchestrator import resolve_step_state_path

        sp = resolve_step_state_path(
            SKILL_NAME,
            args.step,
            state_file=args.state,
            session_id=getattr(args, "session", None),
        )
        if not sp.exists():
            print("ERROR: No implementation in progress. Run step 1 first.")
            print("If the state file is elsewhere, pass --state <path> or --session <id>")
            sys.exit(1)

        try:
            state = load_state(sp)
        except json.JSONDecodeError:
            print(f"ERROR: State file is corrupted: {sp}")
            print("Delete it and re-run step 1.")
            sys.exit(1)
        except (KeyError, FileNotFoundError) as e:
            print(f"ERROR: State file problem — {e}")
            sys.exit(1)

        # Apply quick mode if passed on any step
        if args.quick:
            state.quick_mode = True

        if getattr(args, "branch_prefix", None):
            state.custom["branch_prefix"] = args.branch_prefix

        if args.step == 8:
            handle_step_8(state, sp, args)
            return

        handlers = {
            2: handle_step_2,
            3: handle_step_3,
            4: handle_step_4,
            5: handle_step_5,
            6: handle_step_6,
            7: handle_step_7,
        }

        handler = handlers.get(args.step)
        if handler:
            handler(state, sp)
        else:
            print(f"ERROR: No handler for step {args.step}")
            sys.exit(1)


if __name__ == "__main__":
    main()
