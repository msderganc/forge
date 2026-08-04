#!/usr/bin/env python3
"""Diagnose skill orchestrator (legacy body).

Used when ``FORGE_SKILL_ENGINE=0``. Default path is the declarative runner via
``scripts.diagnose.orchestrate`` → ``run_skill("diagnose")``.

See ``prompts/diagnose/technique_catalog.md`` for toolbox + use-case routing rules.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Auto-detect repo root so this works from any working directory
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent  # scripts/diagnose/ -> scripts/ -> repo root

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
    ensure_runtime_dirs,
    find_state_file,
    format_step_output,
    print_remaining_session_warning,
    run_step1_session_hygiene,
    load_state,
    now_iso,
    resolve_step1_state_path,
    runtime_state_path,
    save_state,
    validate_state_path,
    validate_step,
    validate_step_or_complete,
    write_handoff,
    render_dashboard,
)
from scripts.diagnose import diagnose_gates
from scripts.diagnose.five_whys_register import load_register as load_five_whys
from scripts.diagnose.five_whys_register import register_path as five_whys_register_path
from scripts.diagnose.five_whys_register import summarize_chains
from scripts.diagnose.first_principles_register import load_register as load_fp_register
from scripts.diagnose.first_principles_register import register_path as fp_register_path
from scripts.diagnose.first_principles_register import summarize as summarize_fp
from scripts.diagnose.hypothesis_register import (
    load_register,
    register_path,
    summarize_register,
)
from scripts.diagnose.mece_tree_register import load_register as load_mece_register
from scripts.diagnose.mece_tree_register import register_path as mece_register_path
from scripts.diagnose.mece_tree_register import summarize as summarize_mece
from scripts.diagnose.problem_spec_register import load_register as load_problem_spec_register
from scripts.diagnose.problem_spec_register import register_path as problem_spec_register_path
from scripts.diagnose.problem_spec_register import summarize as summarize_problem_spec
from scripts.diagnose.repro_loop_register import load_register as load_repro_loop_register
from scripts.diagnose.repro_loop_register import register_path as repro_loop_register_path
from scripts.diagnose.repro_loop_register import summarize as summarize_repro_loop
from scripts.diagnose.technique_coverage import coverage_path
from scripts.diagnose.technique_coverage import load_sidecar as load_coverage
from scripts.diagnose.technique_coverage import summarize_coverage
from scripts.evaluate.template_engine import load_template, render_template

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SKILL_NAME = "diagnose"
MAX_STEP = 7

PROMPTS_DIR = REPO_ROOT / "prompts"

PHASE_TEMPLATES = {
    1: "diagnose/define",
    2: "diagnose/evidence",
    3: "diagnose/decompose",
    4: "diagnose/analyze",
    5: "diagnose/solutions",
    6: "diagnose/quick_fix",
    7: "diagnose/report",
}

PHASE_NAMES = {
    1: "Frame the Problem",
    2: "Reproduce & Observe",
    3: "Deepen (5 Whys)",
    4: "Analyze & Rank",
    5: "Solution Generation",
    6: "Implement & Validate",
    7: "Report & Prevention",
}

PHASE_TODOS = {
    1: [
        {"content": "Pick ONE entry framing technique (KT, Cynefin, first-principles, evidence, or MECE sketch)",
         "activeForm": "Choosing entry framing"},
        {"content": "Write problem_statement + .diagnose-problem-spec.json (framing_entry, routing)",
         "activeForm": "Writing problem spec"},
        {"content": "List activated_techniques (always includes 5 Whys; add others only when needed)",
         "activeForm": "Routing follow-on techniques"},
    ],
    2: [
        {"content": "Build feedback loop — write .diagnose-feedback-loop.json (loop_type, command_or_path)",
         "activeForm": "Building feedback loop"},
        {"content": "Run loop; capture symptom; confirm matches_user_report",
         "activeForm": "Running feedback loop"},
        {"content": "Document minimal_repro_steps and artifact paths",
         "activeForm": "Documenting minimal repro"},
        {"content": "Gather remaining evidence (logs, metrics, git hotspots, tests)",
         "activeForm": "Gathering evidence"},
    ],
    3: [
        {"content": "Draft 5 Whys chains in .diagnose-five-whys.json (primary deepen step)",
         "activeForm": "Drafting 5 Whys chains"},
        {"content": "Activate MECE / hypothesis register only if routing_preferred requires them",
         "activeForm": "Optional MECE or hypotheses"},
        {"content": "Update technique coverage rows for activated techniques only",
         "activeForm": "Updating coverage rows"},
    ],
    4: [
        {"content": "If hypothesis register active: eliminate all candidates via falsification",
         "activeForm": "Eliminating hypotheses"},
        {"content": "Finalize 5 Whys to root_cause + but_for; persist sidecars",
         "activeForm": "Finalizing 5 Whys"},
        {"content": "Run FMEA scoring on full candidate list",
         "activeForm": "Running FMEA scoring"},
        {"content": "Apply counterfactual validation on plausible hypotheses",
         "activeForm": "Running counterfactual validation"},
        {"content": "Confirm root cause with evidence; persist register",
         "activeForm": "Confirming root cause"},
    ],
    5: [
        {"content": "Generate solutions only for confirmed root causes",
         "activeForm": "Generating solutions"},
        {"content": "Run pre-mortem on each proposed fix",
         "activeForm": "Running pre-mortem"},
    ],
    6: [
        {"content": "Apply fix (if simple complexity)",
         "activeForm": "Applying fix"},
        {"content": "Validate fix addresses root cause",
         "activeForm": "Validating fix"},
    ],
    7: [
        {"content": "Finalize coverage matrix for activated techniques (not all 20 by default)",
         "activeForm": "Technique matrix"},
        {"content": "Write diagnostic report with prevention measures",
         "activeForm": "Writing diagnostic report"},
        {"content": "Write handoff and render dashboard",
         "activeForm": "Writing handoff"},
    ],
}

# Phases where each autonomy mode pauses for user approval
AUTONOMY_GATES = {
    "guided": {2, 4, 6},       # After evidence, after ranking, before fix
    "autonomous": set(),        # No pauses
    "interactive": {1, 2, 3, 4, 5, 6, 7},  # Every phase
}


# ---------------------------------------------------------------------------
# State helpers
# ---------------------------------------------------------------------------

def _init_state(mode: str, quick: bool) -> SkillState:
    """Create a fresh diagnose state."""
    state = SkillState(skill_name=SKILL_NAME)
    state.max_step = MAX_STEP
    state.current_step = 1
    state.quick_mode = quick
    state.started_at = now_iso()
    state.custom["autonomy_mode"] = mode
    state.custom["fix_complexity"] = "unknown"  # set in phase 5/6
    state.custom.setdefault("hypothesis_min", 5)
    state.custom.setdefault("hypothesis_regen_attempts", 0)
    state.custom.setdefault("hypothesis_validation_attempts", 0)
    state.custom.setdefault("problem_spec_regen_attempts", 0)
    state.custom.setdefault("quartet_regen_attempts", 0)
    state.custom.setdefault("step5_bundle_attempts", 0)
    state.custom.setdefault("step7_closure_attempts", 0)
    return state


def _state_path() -> Path:
    """Return default state file location."""
    return runtime_state_path(SKILL_NAME)


def _load_or_fail(
    step: int,
    state_file: str | None,
    session_id: str | None = None,
) -> tuple[SkillState, Path]:
    """Load state or exit with error."""
    from scripts.shared.orchestrator import resolve_step_state_path

    sp = resolve_step_state_path(
        SKILL_NAME, step, state_file=state_file, session_id=session_id
    )

    if not sp.exists():
        print("ERROR: No diagnosis in progress. Run step 1 first.")
        print("If the state file is elsewhere, pass --state <path>")
        sys.exit(1)

    try:
        state = load_state(sp)
    except json.JSONDecodeError:
        print(f"ERROR: State file is corrupted: {sp}")
        print("Delete it and re-run step 1.")
        sys.exit(1)
    except (KeyError, FileNotFoundError) as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    return state, sp


# ---------------------------------------------------------------------------
# Template rendering
# ---------------------------------------------------------------------------

def _build_variables(
    state: SkillState,
    *,
    state_path: Path | None = None,
    step: int | None = None,
) -> dict[str, str]:
    """Build template variable dict from state."""
    mode = state.custom.get("autonomy_mode", "guided")
    complexity = state.custom.get("fix_complexity", "unknown")
    hypothesis_min = int(state.custom.get("hypothesis_min", 5))
    hypothesis_gate = ""
    hypothesis_summary = "(Not evaluated yet)"
    five_whys_summary = "(Not evaluated yet)"
    technique_coverage_summary = "(Not evaluated yet)"
    first_principles_summary = "(Not evaluated yet)"
    mece_summary = "(Not evaluated yet)"
    problem_spec_summary = "(Not evaluated yet)"
    repro_loop_summary = "(Not evaluated yet)"
    diagnose_artifact_gate = ""

    state_dir_rel = ""
    if state_path is not None:
        from scripts.diagnose.diagnose_registers import state_dir_from_state_path
        from scripts.shared.runtime_layout import repo_relative_path

        sd = state_dir_from_state_path(state_path)
        state_dir_rel = repo_relative_path(sd)
        reg_file = register_path(sd)
        reg_data = load_register(reg_file)
        hypothesis_summary = summarize_register(reg_data)
        five_whys_summary = summarize_chains(load_five_whys(five_whys_register_path(sd)))
        technique_coverage_summary = summarize_coverage(load_coverage(coverage_path(sd)))
        first_principles_summary = summarize_fp(load_fp_register(fp_register_path(sd)))
        mece_summary = summarize_mece(load_mece_register(mece_register_path(sd)))
        problem_spec_summary = summarize_problem_spec(
            load_problem_spec_register(problem_spec_register_path(sd))
        )
        repro_loop_summary = summarize_repro_loop(
            load_repro_loop_register(repro_loop_register_path(sd))
        )
        active_step = step if step is not None else state.current_step
        if active_step >= 4 and reg_data:
            state.custom["hypothesis_register_summary"] = hypothesis_summary

    # Build findings summary
    findings_text = ""
    if state.findings:
        for f in state.findings:
            status = f" [{f['status']}]" if f.get("status") != "open" else ""
            findings_text += (
                f"- **{f['id']}** ({f['severity']}): {f['title']}{status}\n"
                f"  {f['detail']}\n\n"
            )
    else:
        findings_text = "(No findings yet)"

    # Build dispatch history
    dispatch_text = ""
    if state.dispatches:
        for d in state.dispatches:
            agent = d.agent if hasattr(d, "agent") else d.get("agent", "?")
            step = d.step if hasattr(d, "step") else d.get("step", "?")
            done = d.completed if hasattr(d, "completed") else d.get("completed", False)
            mark = "done" if done else "pending"
            dispatch_text += f"- {agent} (step {step}): {mark}\n"
    else:
        dispatch_text = "(None yet)"

    # Autonomy gate message
    gates = AUTONOMY_GATES.get(mode, AUTONOMY_GATES["guided"])
    if state.current_step in gates:
        autonomy_gate = (
            f"**AUTONOMY GATE ({mode} mode):** Pause here. Present findings to "
            f"the user and wait for approval before proceeding to the next phase."
        )
    else:
        autonomy_gate = (
            f"**Mode: {mode}** — No pause required at this phase. "
            f"Proceed directly to the next step."
        )

    # Complexity check for phase 6
    if complexity == "simple":
        complexity_check = (
            "Complexity assessment: **SIMPLE** (<=2 files, no architectural changes).\n"
            "Proceed with implementation below."
        )
    elif complexity == "complex":
        complexity_check = (
            "Complexity assessment: **COMPLEX** (multi-file or architectural, but a single "
            "dominant implementation path is clear).\n"
            "Skip this phase. Hand off to **`plan`** then `implement`.\n"
            "Write the handoff file with root causes and recommended solution."
        )
    elif complexity == "large":
        complexity_check = (
            "Complexity assessment: **LARGE / SYSTEMIC** (under-specified solution space, "
            "major cross-subsystem trade-offs, or multiple viable architectures).\n"
            "Skip quick implementation in this phase. Hand off to **`design`** first for "
            "design/brainstorming, then **`plan`**.\n"
            "Write the handoff file with root causes, constraints, and known unknowns."
        )
    else:
        complexity_check = (
            "Complexity not yet assessed. Before proceeding, evaluate:\n"
            "- How many files does the fix touch?\n"
            "- Does it require architectural changes?\n"
            "- Is there one clear implementation shape, or are major design choices still open?\n\n"
            "If <=2 files and no architectural changes → set `fix_complexity` to `simple` and proceed.\n"
            "If multi-file / architectural **and** one dominant fix path → set to `complex` and hand off to `plan`.\n"
            "If systemic / multi-strategy / unclear best shape → set to `large` and hand off to `design` first."
        )

    return {
        "AUTONOMY_MODE": mode,
        "AUTONOMY_GATE": autonomy_gate,
        "FIX_COMPLEXITY": complexity,
        "COMPLEXITY_CHECK": complexity_check,
        "PREVIOUS_FINDINGS": findings_text.strip(),
        "DISPATCH_HISTORY": dispatch_text.strip(),
        "PLUGIN_ROOT": str(REPO_ROOT),
        "SCRIPT_DIR": str(SCRIPT_DIR),
        "STATE_DIR": state_dir_rel or ".forge/sessions/<id>",
        "HYPOTHESIS_MIN": str(hypothesis_min),
        "HYPOTHESIS_GATE": hypothesis_gate,
        "HYPOTHESIS_REGISTER_SUMMARY": hypothesis_summary,
        "FIVE_WHYS_SUMMARY": five_whys_summary,
        "TECHNIQUE_COVERAGE_SUMMARY": technique_coverage_summary,
        "FIRST_PRINCIPLES_SUMMARY": first_principles_summary,
        "MECE_SUMMARY": mece_summary,
        "PROBLEM_SPEC_SUMMARY": problem_spec_summary,
        "REPRO_LOOP_SUMMARY": repro_loop_summary,
        "DIAGNOSE_ARTIFACT_GATE": diagnose_artifact_gate,
        "FIVE_WHYS_GATE": diagnose_artifact_gate,
        "TECHNIQUE_COVERAGE_GATE": diagnose_artifact_gate,
        "QUARTET_GATE": diagnose_artifact_gate,
    }


diagnose_gates.PHASE_NAMES = PHASE_NAMES


# ---------------------------------------------------------------------------
# Step handlers
# ---------------------------------------------------------------------------

def handle_step_1(args) -> None:
    """Step 1: Initialize state, render Define & Classify prompt."""
    sp = resolve_step1_state_path(
        SKILL_NAME,
        args.state,
        parallel=getattr(args, "parallel", False),
        label=getattr(args, "label", None),
        session_id=getattr(args, "session", None),
    )
    # Same-skill abort: refuse to silently overwrite an in-progress session.
    check_same_skill_clobber(
        SKILL_NAME,
        allow_parallel=bool(getattr(args, "parallel", False) or args.state),
        target_state_path=sp,
    )

    run_step1_session_hygiene(SKILL_NAME, sp)
    print_remaining_session_warning(SKILL_NAME)

    mode = getattr(args, "mode", "guided") or "guided"
    quick = getattr(args, "quick", False)

    if sp.exists():
        try:
            state = load_state(sp)
        except Exception:
            state = _init_state(mode, quick)
    else:
        state = _init_state(mode, quick)

    from scripts.shared.session_store import session_id_from_state_path

    sid = session_id_from_state_path(sp)
    if sid:
        state.session_id = sid

    ensure_runtime_dirs()
    session_label = getattr(args, "label", None)
    save_state(state, sp, label=session_label)

    from scripts.diagnose.diagnose_registers import state_dir_from_state_path

    print(f"STATE FILE: {sp}", file=sys.stderr)
    print(
        f"STATE DIR: {state_dir_from_state_path(sp)}  (write .diagnose-*.json here)\n",
        file=sys.stderr,
    )

    template = load_template(PHASE_TEMPLATES[1])
    variables = _build_variables(state, state_path=sp, step=1)
    body = render_template(template, variables)

    if quick:
        body += (
            "\n\n---\n\n"
            "**QUICK MODE:** Investigator-only. Skip full team dispatch.\n"
            "Phase 2 still requires a feedback loop (`.diagnose-feedback-loop.json`) "
            "before step 3; the step-3 gate applies in quick mode.\n"
            "Then abbreviated analyze, fix, and report.\n"
        )

    state.mark_step_complete(1)
    save_state(state, sp, label=session_label)
    append_skill_run_memory(
        SKILL_NAME,
        1,
        PHASE_NAMES[1],
        "Initialized diagnose session and framed the problem (adaptive entry).",
        state=state,
        state_path=sp,
    )

    next_cmd = build_next_command(
        SCRIPT_DIR / "orchestrate.py", 1, MAX_STEP,
        mode=mode,
        state=str(sp),
    )
    print(format_step_output(
        SKILL_NAME, 1, MAX_STEP, PHASE_NAMES[1], body,
        next_cmd=next_cmd,
        phase_todos=PHASE_TODOS.get(1, []),
        all_phase_names=PHASE_NAMES,
        all_phase_todos=PHASE_TODOS,
    ))


def handle_step_n(
    step: int,
    state_file: str | None = None,
    mode: str | None = None,
    session_id: str | None = None,
) -> None:
    """Steps 2-7: Load state, render template, output prompt."""
    from scripts.diagnose.diagnose_step_output import print_diagnose_step
    from scripts.diagnose.diagnose_steps import (
        append_complexity_gate_notes,
        apply_gate_template_variables,
        resolve_step_gate,
    )

    state, sp = _load_or_fail(step, state_file, session_id=session_id)

    template_name = PHASE_TEMPLATES.get(step)
    if not template_name:
        print(f"ERROR: No template for step {step}")
        sys.exit(1)

    template = load_template(template_name)
    gate_result, step2_warning = resolve_step_gate(step, state, sp)

    variables = _build_variables(state, state_path=sp, step=step)
    apply_gate_template_variables(variables, gate_result)
    body = render_template(template, variables)
    if step2_warning:
        body += step2_warning
    body = append_complexity_gate_notes(step, body, state)

    print_diagnose_step(
        skill_name=SKILL_NAME,
        step=step,
        max_step=MAX_STEP,
        phase_name=PHASE_NAMES.get(step, f"Step {step}"),
        body=body,
        state=state,
        sp=sp,
        gate_result=gate_result,
        mode=mode,
        is_last=step >= MAX_STEP,
        script_dir=SCRIPT_DIR,
        phase_names=PHASE_NAMES,
        phase_todos=PHASE_TODOS,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = build_base_parser(SKILL_NAME, MAX_STEP)
    parser.add_argument(
        "--mode", type=str, default=None,
        choices=["guided", "autonomous", "interactive"],
        help="Autonomy mode (default: guided)"
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
            mode=args.mode,
            session_id=getattr(args, "session", None),
        )


if __name__ == "__main__":
    main()
