#!/usr/bin/env python3
"""Plan skill orchestrator.

Script-driven workflow that outputs formatted prompts for Codex to follow.
Each --step invocation loads state, selects the appropriate prompt template,
substitutes variables, and prints the prompt for Codex to execute.

Steps:
  1. Context Detection — check for handoff, read memory, initialize state
  2. Architecture Dispatch — Architect designs unified architecture
  3. Plan Creation Dispatch — Planner creates detailed implementation plan
  4. Plan Review Loop — self -> cross -> critic -> PM review
  5. User Approval — present plan for approval
  6. Documentation Planning — audience applicability, doc targets, external wiki checklist
  7. Handoff — write handoff file and render dashboard
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# Auto-detect repo root so this works from any working directory
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent  # scripts/plan/ -> scripts/ -> repo root

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
    consume_handoff,
    read_memory_file,
    render_dashboard,
    resolve_step1_state_path,
    runtime_memory_dir,
    runtime_state_path,
    save_state,
    validate_state_path,
    validate_step,
    validate_step_or_complete,
    write_handoff,
)
from scripts.evaluate.template_engine import load_template, render_template
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

PROMPTS_DIR = REPO_ROOT / "prompts"
SKILL_NAME = "plan"
MAX_STEP = 7

PHASE_NAMES = {
    1: "Context Detection",
    2: "Architecture Dispatch",
    3: "Plan Creation Dispatch",
    4: "Plan Review Loop",
    5: "User Approval",
    6: "Documentation Planning",
    7: "Handoff",
}

PHASE_TODOS = {
    1: [
        {"content": "Read handoff-design.md and memory files",
         "activeForm": "Reading handoff and memory"},
        {"content": "Initialize plan state",
         "activeForm": "Initializing state"},
    ],
    2: [
        {"content": "Dispatch Architect for architecture design",
         "activeForm": "Dispatching Architect"},
        {"content": "Wait for architecture artifacts",
         "activeForm": "Waiting for architecture"},
    ],
    3: [
        {"content": "Dispatch Planner with INVEST validation",
         "activeForm": "Dispatching Planner"},
        {"content": "Validate each task against INVEST criteria",
         "activeForm": "Validating INVEST"},
    ],
    4: [
        {"content": "Run 4-step review loop on plan",
         "activeForm": "Running plan review loop"},
        {"content": "Record and resolve findings",
         "activeForm": "Resolving findings"},
    ],
    5: [
        {"content": "Run pre-mortem analysis on plan",
         "activeForm": "Running pre-mortem"},
        {"content": "Present plan to user for approval",
         "activeForm": "Presenting plan for approval"},
    ],
    6: [
        {"content": "Define documentation scope and audience applicability",
         "activeForm": "Planning documentation"},
        {"content": "Confirm external wiki and repo doc targets",
         "activeForm": "Confirming doc targets"},
    ],
    7: [
        {"content": "Write handoff file for implement skill",
         "activeForm": "Writing handoff"},
        {"content": "Render dashboard and complete",
         "activeForm": "Rendering dashboard"},
    ],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _state_path() -> Path:
    """Return the default state file path."""
    return runtime_state_path(SKILL_NAME)




def _slugify(text: str, max_words: int = 5) -> str:
    """Convert text to a kebab-case slug suitable for filenames."""
    # Lowercase and keep only alphanumeric + spaces
    text = re.sub(r"[^a-z0-9\s]", " ", text.lower())
    words = text.split()
    # Take first N meaningful words (skip very short ones except common ones)
    meaningful = [w for w in words if len(w) > 1][:max_words]
    return "-".join(meaningful) if meaningful else "plan"


def _extract_summary(handoff_content: str) -> str:
    """Extract a short summary from handoff content for the plan filename."""
    if not handoff_content:
        return "plan"
    # Try to find a heading first
    for line in handoff_content.splitlines():
        line = line.strip()
        if line.startswith("#"):
            return _slugify(re.sub(r"^#+\s*", "", line))
    # Fall back to first non-empty line
    for line in handoff_content.splitlines():
        line = line.strip()
        if line and not line.startswith(("-", "|", ">")):
            return _slugify(line)
    return "plan"


def generate_plan_filename(handoff_content: str = "") -> str:
    """Generate a timestamped plan filename like 20260414-1926-api-change-implementation.md."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    slug = _extract_summary(handoff_content)
    return f"{ts}-{slug}.md"


# Sections from templates/writing-plans.md (Plan Structure, lines 9-15).
# Order matters — agents fill these in order.
PLAN_SECTIONS = [
    ("ARCHITECTURE-OVERVIEW", "Architecture Overview"),
    ("BRANCH-STRATEGY", "Branch Strategy"),
    ("TASK-BREAKDOWN", "Task Breakdown"),
    ("PARALLELIZATION-MAP", "Parallelization Map"),
    ("INTERFACE-CONTRACTS", "Interface Contracts"),
    ("RISK-REGISTER", "Risk Register"),
    ("ROLLBACK-STRATEGY", "Rollback Strategy"),
    ("DOCUMENTATION", "Documentation"),
]

# Distinctive marker so a plan section that legitimately quotes HTML comments
# (in code blocks etc.) doesn't trigger the unfilled-section gate.
SKELETON_MARKER_PREFIX = "<!-- FORGE_SKELETON: "
SKELETON_MARKER_SUFFIX = " -->"


def _is_stub_skeleton(content: str) -> bool:
    """True if the file contains only skeleton scaffolding (markers + headings)."""
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("# "):
            continue
        if stripped.startswith("## "):
            continue
        if stripped.startswith(SKELETON_MARKER_PREFIX) and stripped.endswith(SKELETON_MARKER_SUFFIX):
            continue
        return False
    return True


def write_plan_skeleton(plan_path: Path, force: bool = False) -> None:
    """Materialize the canonical plan structure with section markers.

    Sections come from `templates/writing-plans.md` (the single source of
    truth). Each section is followed by a `<!-- FORGE_SKELETON: ID -->`
    marker on its own line — agents replace the marker with their content,
    and the step-7 completion gate refuses to mark the workflow complete
    while any markers remain.

    Overwrite policy:
      - File missing → write skeleton.
      - File exists but contains only scaffolding → overwrite.
      - File exists with real content → refuse unless `force=True`.
    """
    if plan_path.exists():
        existing = plan_path.read_text(encoding="utf-8")
        if existing.strip() and not _is_stub_skeleton(existing) and not force:
            sys.exit(
                f"ERROR: Plan file already exists with content: {plan_path}\n"
                "Delete it or pass --force to overwrite."
            )

    lines = ["# Implementation Plan", ""]
    for marker_id, heading in PLAN_SECTIONS:
        lines.append(f"## {heading}")
        lines.append("")
        lines.append(f"{SKELETON_MARKER_PREFIX}{marker_id}{SKELETON_MARKER_SUFFIX}")
        lines.append("")

    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text("\n".join(lines), encoding="utf-8")


def find_unfilled_sections(plan_path: Path) -> list[str]:
    """Return human-readable section names that still contain skeleton markers."""
    if not plan_path.exists():
        return [name for _, name in PLAN_SECTIONS]
    content = plan_path.read_text(encoding="utf-8")
    unfilled = []
    for marker_id, heading in PLAN_SECTIONS:
        marker = f"{SKELETON_MARKER_PREFIX}{marker_id}{SKELETON_MARKER_SUFFIX}"
        if marker in content:
            unfilled.append(heading)
    return unfilled


def _build_variables(state: SkillState) -> dict[str, str]:
    """Build template variable dict from state."""
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
            "No handoff-design.md was found (legacy handoff-develop.md also accepted). Ask the user what needs to be planned."
        )

    plan_context = state.custom.get("plan_context", "(not yet captured)")
    architecture_notes = state.custom.get("architecture_notes", "(not yet designed)")

    mode_review = review_expectations_for_mode(plan_mode, state.quick_mode)

    # Build review assignments based on quick mode
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
        review_assignments = mode_review  # Template has full table when empty

    # Findings summary
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
    handoff_file = str(runtime_memory_dir() / "handoff-plan.md")

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

    return {
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
        "SKILL_NAME": SKILL_NAME,
        "PLAN_FILE": plan_file,
        "HANDOFF_FILE": handoff_file,
        "STUDIO_STATUS": studio_status,
        "STUDIO_LOG": studio_vars["STUDIO_LOG"],
        "STUDIO_APPROVED": studio_vars["STUDIO_APPROVED"],
    }


def _upgrade_plan_max_step(state: SkillState) -> None:
    """Migrate in-progress sessions when MAX_STEP increases."""
    if state.max_step < MAX_STEP:
        state.max_step = MAX_STEP


def _next_command(step: int, state_path: str = "") -> str:
    """Build the command for the next step."""
    extra = {}
    if state_path:
        extra["state"] = state_path
    return build_next_command(SCRIPT_DIR / "plan.py", step, MAX_STEP, **extra)


# ---------------------------------------------------------------------------
# Step handlers
# ---------------------------------------------------------------------------

def handle_step_1(args: argparse.Namespace) -> None:
    """Step 1: Context Detection — check for handoff, read memory, init state."""
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

    handoff_content = consume_handoff("design")

    run_step1_session_hygiene(SKILL_NAME, sp)
    print_remaining_session_warning(SKILL_NAME)

    plan_file = None
    prior_mode: str | None = None
    plan_filename = generate_plan_filename(handoff_content)
    plans_dir = runtime_memory_dir() / "plans"
    plans_dir.mkdir(parents=True, exist_ok=True)
    plan_file = str(plans_dir / plan_filename)

    # Materialize the skeleton file so Architect/Planner replace markers
    # rather than invent structure.
    write_plan_skeleton(Path(plan_file), force=getattr(args, "force", False))

    from scripts.shared.session_store import session_id_from_state_path

    state = SkillState(skill_name=SKILL_NAME, max_step=MAX_STEP)
    sid = session_id_from_state_path(sp)
    if sid:
        state.session_id = sid
    state.current_step = 1
    state.quick_mode = args.quick
    state.started_at = now_iso()
    state.custom["handoff_content"] = handoff_content
    state.custom["plan_file"] = plan_file

    cli_mode = getattr(args, "mode", None)
    persisted = load_persisted_preference()
    recommended, rec_rationale = recommend_mode(handoff_content)

    plan_mode, resolution_source = resolve_mode_for_step1(
        cli_mode,
        resumed_session=False,
        stored_mode=prior_mode,
    )
    if resolution_source == "fallback":
        resolution_source = "prompt"

    state.custom["plan_mode"] = plan_mode
    state.custom["plan_mode_recommended"] = recommended
    state.custom["plan_mode_recommendation_rationale"] = rec_rationale
    state.custom["plan_mode_resolution"] = resolution_source
    if getattr(args, "save_mode_preference", False) and cli_mode:
        save_persisted_preference(plan_mode)
        state.custom["plan_mode_preference_saved"] = plan_mode

    save_state(state, sp, label=getattr(args, "label", None))

    # Print state path so Codex knows where it is
    print(f"STATE FILE: {sp}\n", file=sys.stderr)

    template = load_template("plan/context")
    variables = _build_variables(state)
    body = render_template(template, variables)
    body += "\n\n" + format_mode_selection_block(
        recommended=recommended,
        rationale=rec_rationale,
        persisted=persisted,
        resolved_mode=plan_mode if resolution_source in ("cli", "session") else None,
        resolution_source=resolution_source,
    )

    # Mark step 1 complete
    state.mark_step_complete(1)
    save_state(state, sp, label=getattr(args, "label", None))
    append_skill_run_memory(
        SKILL_NAME,
        1,
        PHASE_NAMES[1],
        "Initialized plan session and loaded context.",
        state=state,
        state_path=sp,
    )

    phase_name = PHASE_NAMES[1]
    next_cmd = _next_command(1, state_path=str(sp))
    print(format_step_output(
        SKILL_NAME, 1, MAX_STEP, phase_name, body,
        next_cmd=next_cmd,
        phase_todos=PHASE_TODOS.get(1, []),
        all_phase_names=PHASE_NAMES,
        all_phase_todos=PHASE_TODOS,
    ))


def _inject_plan_architecture_probes(state: SkillState, body: str, sp: Path) -> str:
    """Step-2 architecture phase: advisory structural probe inject."""
    from scripts.shared.repo_paths import resolve_repo_root
    from scripts.shared.structural_probes import inject_structural_probes_section

    scan_root = resolve_repo_root(REPO_ROOT)
    body, sidecar, _payload = inject_structural_probes_section(
        body,
        skill_name=SKILL_NAME,
        step=2,
        repo_root=scan_root,
        state_dir=sp.parent,
        quick_mode=state.quick_mode,
        advisory=True,
    )
    if sidecar:
        state.custom["structural_probes_sidecar"] = str(sidecar)
    return body


def _load_plan_step_state(
    step: int, state_file: str | None, session_id: str | None
) -> tuple[SkillState, Path]:
    from scripts.shared.orchestrator import resolve_step_state_path

    sp = resolve_step_state_path(
        SKILL_NAME, step, state_file=state_file, session_id=session_id
    )
    if not sp.exists():
        print("ERROR: No plan session in progress. Run step 1 first.")
        print(f"Expected state file at: {_state_path()}")
        sys.exit(1)
    try:
        state = load_state(sp)
    except Exception as e:
        print(f"ERROR: Failed to load state: {e}")
        print("Delete the state file and re-run step 1.")
        sys.exit(1)
    _upgrade_plan_max_step(state)
    if not state.custom.get("plan_mode"):
        _, migrated = hydrate_legacy_mode(state.custom)
        if migrated:
            state.custom["mode_migrated_note"] = (
                "Legacy plan session: plan_mode was missing and was set to `default`. "
                "Continue without re-prompting for mode."
            )
    save_state(state, sp)
    return state, sp


def _finalize_plan_max_step(
    state: SkillState, sp: Path, body: str
) -> tuple[str, str | None, Path | None, str, str | None, bool]:
    """Handoff completion for final plan step.

    Returns body, menu, path, summary, next_cmd (same-step when incomplete),
    await_same_step.
    """
    plan_file = state.custom.get("plan_file")
    if not plan_file:
        sys.exit(
            "ERROR: state.custom['plan_file'] missing at handoff — "
            "re-run step 1 to initialize."
        )
    unfilled = find_unfilled_sections(Path(plan_file))
    if unfilled:
        warning = (
            "\n\n---\n\n"
            "**WORKFLOW NOT COMPLETE — unfilled plan sections detected.**\n\n"
            "The following sections still contain `<!-- FORGE_SKELETON: ... -->` "
            "markers and need to be filled in before the plan is ready:\n\n"
            + "\n".join(f"- {s}" for s in unfilled)
            + f"\n\nFile: `{plan_file}`\n\n"
            "Fill these sections, then re-run step 7."
        )
        body += warning
        save_state(state, sp)
        stay_cmd = build_next_command(
            SCRIPT_DIR / "plan.py",
            MAX_STEP,
            MAX_STEP,
            next_step=MAX_STEP,
            state=str(sp),
        )
        return (
            body,
            None,
            None,
            "Attempted final handoff but plan skeleton markers remain; "
            "session kept open.",
            stay_cmd,
            True,
        )

    state.mark_step_complete(MAX_STEP)
    state.completed_at = now_iso()
    save_state(state, sp)
    from scripts.shared.handoff_menu import resolve_handoff_commands
    from scripts.shared.skill_chain import SKILL_CHAIN

    chain = SKILL_CHAIN.get(SKILL_NAME)
    default_next, _alts = resolve_handoff_commands(
        SKILL_NAME,
        state,
        default_cmd=chain.default if chain else "evaluate --mode pre",
        alternatives=list(chain.alternatives) if chain else [],
    )
    handoff_path = write_handoff(
        skill_name=SKILL_NAME,
        state=state,
        context={
            "Plan location": plan_file,
            "Plan mode": state.custom.get("plan_mode", DEFAULT_MODE),
            "Task count": state.custom.get("task_count", "see plan"),
            "Dependencies": state.custom.get("dependencies_summary", "see plan"),
        },
        suggested_next=default_next or "evaluate --mode pre",
    )
    body += f"\n\n---\n\n{render_dashboard(state)}"
    body += f"\n\nHandoff written to: {handoff_path}"
    handoff_menu = build_skill_handoff_menu(SKILL_NAME, state, sp)
    clear_state_file(sp)
    return (
        body,
        handoff_menu,
        handoff_path,
        "Completed plan workflow, wrote handoff, and closed session state.",
        None,
        False,
    )


def handle_step_n(step: int, state_file: str | None = None, session_id: str | None = None) -> None:
    """Steps 2-6: Load state, render template, output prompt."""
    state, sp = _load_plan_step_state(step, state_file, session_id)

    template_map = {
        2: "plan/architecture",
        3: "plan/creation",
        4: "plan/review_loop",
        5: "plan/approval",
        6: "plan/documentation",
        7: "plan/handoff",
    }
    template_name = template_map.get(step)
    if not template_name:
        print(f"ERROR: Invalid step {step}")
        sys.exit(1)

    template = load_template(template_name)
    body = render_template(template, _build_variables(state))
    if step == 2:
        body = _inject_plan_architecture_probes(state, body, sp)

    state.current_step = step
    save_state(state, sp)

    handoff_menu = None
    handoff_path: Path | None = None
    run_summary = f"Completed step {step} ({PHASE_NAMES.get(step, f'Step {step}')})."
    await_same = False
    require_confirm: bool | None = None
    next_cmd = _next_command(step, state_path=str(sp)) if step < MAX_STEP else None
    if step == MAX_STEP:
        body, handoff_menu, handoff_path, run_summary, stay_cmd, await_same = (
            _finalize_plan_max_step(state, sp, body)
        )
        if stay_cmd:
            next_cmd = stay_cmd
            require_confirm = True
    else:
        state.mark_step_complete(step)
        save_state(state, sp)
        if step == 5:
            require_confirm = True

    append_skill_run_memory(
        SKILL_NAME,
        step,
        PHASE_NAMES.get(step, f"Step {step}"),
        run_summary,
        state=state,
        state_path=sp,
        handoff_path=handoff_path,
    )
    phase_name = PHASE_NAMES.get(step, f"Step {step}")
    print(format_step_output(
        SKILL_NAME, step, MAX_STEP, phase_name, body,
        next_cmd=next_cmd,
        phase_todos=PHASE_TODOS.get(step, []),
        handoff_menu=handoff_menu,
        all_phase_names=PHASE_NAMES,
        all_phase_todos=PHASE_TODOS,
        require_confirmation=require_confirm,
        await_same_step=await_same,
    ))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = build_base_parser(SKILL_NAME, MAX_STEP)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing plan file at step 1 even if it contains content.",
    )
    parser.add_argument(
        "--mode",
        choices=["default", "lite"],
        default=None,
        help="Plan mode: default (full governance) or lite (concise, same task rigor). "
        "If omitted on a new session, the agent must confirm mode with the user.",
    )
    parser.add_argument(
        "--save-mode-preference",
        action="store_true",
        help="When used with --mode, persist that mode as the default for future plan sessions.",
    )
    args = parser.parse_args()
    apply_resolved_workflow_step(args, SKILL_NAME, MAX_STEP)

    if validate_step_or_complete(args.step, MAX_STEP, SKILL_NAME):
        return

    if args.step == 1:
        handle_step_1(args)
    else:
        handle_step_n(args.step, state_file=args.state, session_id=getattr(args, "session", None))


if __name__ == "__main__":
    main()
