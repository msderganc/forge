#!/usr/bin/env python3
"""Test skill orchestrator.

Script-driven workflow that outputs formatted prompts for Codex to follow.
Each --step invocation loads state, selects the appropriate prompt template,
substitutes variables, and prints the prompt for Codex to execute.

Steps:
  1. Context Detection — read handoff files, identify test targets, initialize state
  2. Test Discovery — QA Reviewer identifies test suites and coverage targets
  3. Test Execution — run test suites, collect results, follow verification-protocol.md
  4. Failure Analysis — for each failure, Investigator performs root-cause
  5. Coverage Gap Analysis — QA Reviewer + Critic identify untested paths
  6. Report — write test report, handoff, dashboard
"""

from __future__ import annotations

import sys
from pathlib import Path

# Auto-detect repo root so this works from any working directory
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent  # scripts/test/ -> scripts/ -> repo root

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
    runtime_state_path,
    save_state,
    validate_state_path,
    validate_step_or_complete,
    write_handoff,
)
from scripts.evaluate.template_engine import (
    default_prompts_root,
    load_template,
    render_template,
)
from scripts.test.test_flows import (
    FLOWS_MAX_STEP,
    FLOWS_PHASE_NAMES,
    handle_flow_step,
    initialize_flow_custom,
    prepare_flow_step_1,
    required_flow_prompts,
)

SKILL_NAME = "test"
MAX_STEP = 6

PHASE_NAMES = {
    1: "Context Detection",
    2: "Test Discovery",
    3: "Test Execution",
    4: "Failure Analysis",
    5: "Coverage Gap Analysis",
    6: "Report",
}

PHASE_TODOS = {
    1: [
        {"content": "Read handoff-code-review.md and handoff-implement.md",
         "activeForm": "Reading handoffs"},
        {"content": "Initialize test state",
         "activeForm": "Initializing state"},
    ],
    2: [
        {"content": "Dispatch QA Reviewer to discover test suites",
         "activeForm": "Discovering test suites"},
        {"content": "Identify coverage targets",
         "activeForm": "Identifying coverage targets"},
    ],
    3: [
        {"content": "Run test suites via verification ladder",
         "activeForm": "Running test suites"},
        {"content": "Collect results and coverage data",
         "activeForm": "Collecting results"},
    ],
    4: [
        {"content": "Dispatch Investigator for failure root-cause analysis",
         "activeForm": "Investigating failures"},
    ],
    5: [
        {"content": "Dispatch QA + Critic for coverage gap analysis",
         "activeForm": "Analyzing coverage gaps"},
        {"content": "Run mutation audit on critical paths",
         "activeForm": "Running mutation audit"},
    ],
    6: [
        {"content": "Write test report",
         "activeForm": "Writing test report"},
        {"content": "Write handoff and render dashboard",
         "activeForm": "Writing handoff"},
    ],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _state_path() -> Path:
    """Return the default state file path."""
    return runtime_state_path(SKILL_NAME)


def _normalize_target(target_arg: str | list[str] | None) -> tuple[str, list[str]]:
    """Normalize target CLI input into canonical string and raw tokens."""
    if target_arg is None:
        return "", []
    if isinstance(target_arg, list):
        tokens = [tok for tok in target_arg if tok]
        return " ".join(tokens), tokens
    return target_arg, [target_arg] if target_arg else []




def _build_variables(
    state: SkillState,
    state_path: Path | None = None,
    *,
    prompts_style: str = "brief",
) -> dict[str, str]:
    """Build template variable dict from state."""
    mode = state.custom.get("mode", "run")
    target = state.custom.get("target", "")
    handoff_cr = state.custom.get("handoff_code_review", "")
    handoff_impl = state.custom.get("handoff_implement", "")

    # Build handoff section
    handoff_parts = []
    if handoff_cr:
        handoff_parts.append(
            "## Handoff from Code Review\n\n"
            "<handoff>\n"
            f"{handoff_cr}\n"
            "</handoff>"
        )
    if handoff_impl:
        handoff_parts.append(
            "## Handoff from Implement\n\n"
            "<handoff>\n"
            f"{handoff_impl}\n"
            "</handoff>"
        )
    if not handoff_parts:
        handoff_parts.append(
            "## No Handoff Found\n\n"
            "No handoff files found. Discovering test targets from the project."
        )
    handoff_section = "\n\n".join(handoff_parts)

    # Build test results summary
    test_results = state.custom.get("test_results", {})
    passed = test_results.get("passed", 0)
    failed = test_results.get("failed", 0)
    skipped = test_results.get("skipped", 0)
    total = test_results.get("total", 0)
    coverage = test_results.get("coverage_pct", "N/A")

    if total > 0:
        results_section = (
            f"**Total:** {total} | **Passed:** {passed} | "
            f"**Failed:** {failed} | **Skipped:** {skipped}\n"
            f"**Coverage:** {coverage}%"
        )
    else:
        results_section = "(Tests not yet executed)"

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

    # Team assignments based on quick mode
    if state.quick_mode:
        team_section = (
            "**Quick mode active** -- abbreviated team:\n\n"
            "| Agent | Focus |\n"
            "|-------|-------|\n"
            "| QA Reviewer | Test execution and coverage analysis |\n"
            "| Investigator | Failure root-cause (if needed) |\n"
        )
    else:
        team_section = (
            "| Agent | Focus |\n"
            "|-------|-------|\n"
            "| QA Reviewer (lead) | Test discovery, execution, coverage analysis |\n"
            "| Investigator | Failure root-cause analysis |\n"
            "| Critic | Coverage gap identification, untested assumptions |\n"
            "| Doc-writer | Test report documentation |\n"
        )

    # Discovered test suites
    test_suites = state.custom.get("test_suites", [])
    if test_suites:
        suites_text = "\n".join(f"- {s}" for s in test_suites)
    else:
        suites_text = "(Not yet discovered)"

    # New flow-mode variables
    flow_type = state.custom.get("flow_type", "")
    flow_type_override = flow_type or ""
    framework = state.custom.get("framework", "")
    framework_confidence = state.custom.get("framework_confidence", 0.0)
    entry_point = state.custom.get("entry_point", "")
    entry_point_confidence = state.custom.get("entry_point_confidence", 0.0)
    test_db = state.custom.get("test_db", "")
    roles = state.custom.get("roles", [])
    layout_confidence_warning = state.custom.get("layout_confidence_warning", "")

    execution_log = state.custom.get("test_execution_log") or (
        "(Orchestrator has not run pytest yet — step 3 runs `python -m pytest` unless "
        "`FORGE_SKIP_TEST_AUTO_RUN=1`.)"
    )

    workflow_prompts = ""
    if state_path is not None:
        from scripts.shared.workflow_prompt_archive import format_workflow_prompts_markdown

        workflow_prompts = format_workflow_prompts_markdown(
            state_path.parent,
            style=prompts_style,
        )

    return {
        "TARGET": target or "(auto-detected from handoff or project)",
        "HANDOFF_CONTENT": handoff_section,
        "TEST_RESULTS": results_section,
        "TEST_SUITES": suites_text,
        "FINDINGS": findings_text.strip(),
        "TEAM_ASSIGNMENTS": team_section,
        "QUICK_MODE": "yes" if state.quick_mode else "no",
        "SKILL_NAME": SKILL_NAME,
        "PASSED": str(passed),
        "FAILED": str(failed),
        "SKIPPED": str(skipped),
        "TOTAL": str(total),
        "COVERAGE": str(coverage),
        # Flow-mode variables
        "MODE": mode,
        "FLOW_TYPE": flow_type,
        "FLOW_TYPE_OVERRIDE": flow_type_override,
        "FRAMEWORK": framework,
        "FRAMEWORK_CONFIDENCE": f"{framework_confidence:.0%}",
        "ENTRY_POINT": entry_point,
        "ENTRY_POINT_CONFIDENCE": f"{entry_point_confidence:.0%}",
        "TEST_DB": test_db,
        "ROLES": ", ".join(roles) if roles else "",
        "LAYOUT_CONFIDENCE_WARNING": layout_confidence_warning,
        "TEST_EXECUTION_LOG": execution_log.strip(),
        "WORKFLOW_PROMPTS_APPENDIX": workflow_prompts.strip(),
    }


def _max_step_for_mode(mode: str | None) -> int:
    """Return max step count for a test skill mode."""
    if mode == "flows":
        return FLOWS_MAX_STEP
    return MAX_STEP


def _next_command(step: int, state_path: str = "", mode: str | None = "run") -> str:
    """Build the command for the next step."""
    extra = {}
    if state_path:
        extra["state"] = state_path
    if mode and mode != "run":
        extra["mode"] = mode
    variant = mode or "run"
    return build_next_command(
        SCRIPT_DIR / "test.py",
        step,
        _max_step_for_mode(variant),
        phase_variant=variant,
        **extra,
    )


# ---------------------------------------------------------------------------
# Step handlers
# ---------------------------------------------------------------------------

def handle_step_1(args) -> None:
    """Step 1: Context Detection -- read handoffs, identify targets, init state."""
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

    # Read handoffs
    handoff_cr = consume_handoff("code-review")
    handoff_impl = consume_handoff("implement")
    project_md = read_memory_file("project.md")

    # Determine target
    target, target_tokens = _normalize_target(getattr(args, "target", None))

    # Determine mode and set max_step
    mode = getattr(args, "mode", "run")
    max_step = _max_step_for_mode(mode)

    if sp.exists():
        try:
            state = load_state(sp)
        except Exception:
            state = SkillState(skill_name=SKILL_NAME, max_step=max_step)
    else:
        state = SkillState(skill_name=SKILL_NAME, max_step=max_step)
    state.max_step = max_step
    state.current_step = 1
    state.quick_mode = args.quick
    state.started_at = state.started_at or now_iso()
    state.custom["mode"] = mode
    state.custom["target"] = target
    state.custom["target_tokens"] = target_tokens
    state.custom["handoff_code_review"] = handoff_cr
    state.custom["handoff_implement"] = handoff_impl
    state.custom["project_context"] = project_md
    state.custom["test_results"] = {
        "passed": 0,
        "failed": 0,
        "skipped": 0,
        "total": 0,
        "coverage_pct": "N/A",
    }
    state.custom["test_suites"] = []

    if mode == "flows":
        initialize_flow_custom(state, args)

    save_state(state, sp)

    # Print state path so Codex knows where it is
    print(f"STATE FILE: {sp}\n", file=sys.stderr)

    if mode == "flows":
        prepare_flow_step_1(sp, getattr(args, "flow_type", None))
        handle_flow_step(1, state, sp)
    else:
        # Run mode: original flow
        template = load_template("test/context")
        variables = _build_variables(state, state_path=sp)
        body = render_template(template, variables)

        from scripts.shared.workflow_prompt_archive import record_step_prompt

        record_step_prompt(
            sp.parent,
            skill=SKILL_NAME,
            step=1,
            phase_name=PHASE_NAMES[1],
            body=body,
            template_name="test/context",
        )

        state.mark_step_complete(1)
        save_state(state, sp)
        append_skill_run_memory(
            SKILL_NAME,
            1,
            PHASE_NAMES[1],
            "Initialized test session (run mode) and loaded handoff context.",
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


def handle_step_n(
    step: int,
    state_file: str | None = None,
    session_id: str | None = None,
) -> None:
    """Steps 2-7: Load state, render template, output prompt."""
    from scripts.shared.orchestrator import resolve_step_state_path

    sp = resolve_step_state_path(
        SKILL_NAME, step, state_file=state_file, session_id=session_id
    )

    if not sp.exists():
        print("ERROR: No test session in progress. Run step 1 first.")
        print(f"Expected state file at: {_state_path()}")
        sys.exit(1)

    try:
        state = load_state(sp)
    except Exception as e:
        print(f"ERROR: Failed to load state: {e}")
        print("Delete the state file and re-run step 1.")
        sys.exit(1)

    # Dispatch based on mode
    mode = state.custom.get("mode", "run")
    if mode == "ux":
        print(
            "ERROR: This session used removed `test --mode ux`.\n"
            "       Start a new session with: forge ux-review --step 1 [--base-url URL]\n"
            "       Or delete the state file and use --mode run / --mode flows.",
            file=sys.stderr,
        )
        sys.exit(2)
    if mode == "flows":
        handle_flow_step(step, state, sp)
        return

    # Run-mode path (unchanged)
    # Map steps to template names
    template_map = {
        2: "test/discovery",
        3: "test/execution",
        4: "test/failure_analysis",
        5: "test/coverage_gaps",
        6: "test/report",
    }

    template_name = template_map.get(step)
    if not template_name:
        print(f"ERROR: Invalid step {step}")
        sys.exit(1)

    from scripts.shared.orchestrator import _detect_repo_root

    repo_root = _detect_repo_root(Path.cwd())

    if step == 2 and not state.custom.get("test_suites"):
        from scripts.test.pytest_runner import discover_pytest_command

        tokens = state.custom.get("target_tokens") or []
        state.custom["test_suites"] = [discover_pytest_command(repo_root, tokens)]

    if step == 3:
        from scripts.test.pytest_runner import (
            apply_results_to_state_custom,
            discover_pytest_command,
            run_pytest,
            should_run_pytest,
            skip_test_auto_run,
        )

        if should_run_pytest(state.custom):
            tokens = state.custom.get("target_tokens") or []
            suites = state.custom.get("test_suites") or []
            cmd = suites[0] if suites else discover_pytest_command(repo_root, tokens)
            print(
                "forge: test step 3 — running pytest (Pass B execution)...",
                file=sys.stderr,
                flush=True,
            )
            result = run_pytest(repo_root, cmd)
            apply_results_to_state_custom(state.custom, result)
            print(
                f"forge: pytest finished — exit {result.get('exit_code')} "
                f"({result.get('passed', 0)} passed, {result.get('failed', 0)} failed)",
                file=sys.stderr,
                flush=True,
            )
        elif not skip_test_auto_run():
            print(
                "forge: test step 3 — skipping pytest (results already in state; "
                "set FORGE_TEST_FORCE_RERUN=1 to re-run)",
                file=sys.stderr,
                flush=True,
            )

    # Load template before mutating state — a missing template must not leave
    # state half-written.
    template = load_template(template_name)
    prompts_style = "full" if step == MAX_STEP else "brief"
    variables = _build_variables(state, state_path=sp, prompts_style=prompts_style)
    body = render_template(template, variables)

    from scripts.shared.workflow_prompt_archive import record_step_prompt

    record_step_prompt(
        sp.parent,
        skill=SKILL_NAME,
        step=step,
        phase_name=PHASE_NAMES.get(step, f"Step {step}"),
        body=body,
        template_name=template_name,
    )

    state.current_step = step
    save_state(state, sp)

    # Step 6: mark completion and write handoff
    handoff_menu = None
    handoff_path: Path | None = None
    run_summary = f"Completed step {step} ({PHASE_NAMES.get(step, f'Step {step}')})."
    if step == MAX_STEP:
        state.mark_step_complete(step)
        state.completed_at = now_iso()
        save_state(state, sp)

        test_results = state.custom.get("test_results", {})
        passed = test_results.get("passed", 0)
        failed = test_results.get("failed", 0)
        total = test_results.get("total", 0)
        coverage = test_results.get("coverage_pct", "N/A")

        # Suggest diagnose if there are failures, otherwise end of flow
        suggested_next = "diagnose" if failed > 0 else "(end of flow)"

        handoff_path = write_handoff(
            skill_name=SKILL_NAME,
            state=state,
            context={
                "Test results": f"{passed}/{total} passed, {failed} failed",
                "Coverage": f"{coverage}%",
                "Failures": str(failed),
                "Open findings": str(len(state.open_findings())),
                "Suggested action": "diagnose failures" if failed > 0 else "all tests passing",
            },
            suggested_next=suggested_next,
        )

        dashboard = render_dashboard(state)
        body += f"\n\n---\n\n{dashboard}"
        body += f"\n\nHandoff written to: {handoff_path}"
        clear_state_file(sp)
        handoff_menu = build_skill_handoff_menu(SKILL_NAME, state, sp)
        run_summary = "Completed test workflow (run mode), wrote handoff, and closed session state."

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

    phase_name = PHASE_NAMES.get(step, f"Step {step}")
    mode = state.custom.get("mode", "run")
    effective_max = _max_step_for_mode(mode)
    next_cmd = _next_command(step, state_path=str(sp), mode=mode) if step < effective_max else None
    print(format_step_output(
        SKILL_NAME, step, MAX_STEP, phase_name, body,
        next_cmd=next_cmd,
        phase_todos=PHASE_TODOS.get(step, []),
        handoff_menu=handoff_menu,
        all_phase_names=PHASE_NAMES,
        all_phase_todos=PHASE_TODOS,
    ))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = build_base_parser(SKILL_NAME, MAX_STEP)
    parser.add_argument(
        "--target", nargs="+", default=None,
        help="Test command, path, or pattern to run"
    )
    # Flow-mode flags (Fix 1)
    parser.add_argument(
        "--mode", type=str, choices=["run", "flows", "ux"], default="run",
        help="Skill mode: run (default) or flows (author mock flows). "
             "'ux' redirects to forge ux-review"
    )
    parser.add_argument(
        "--flow-type", type=str,
        choices=["scenario", "bdd", "http-replay", "workflow-dryrun"],
        default=None,
        help="Override flow type recommendation"
    )
    parser.add_argument(
        "--re-record", action="store_true",
        help="Refresh HTTP-replay cassettes (flows mode only)"
    )
    parser.add_argument(
        "--framework", type=str, default=None,
        help="Manual override for test framework detection"
    )
    parser.add_argument(
        "--entry-point", type=str,
        choices=["ui", "http", "cli", "module", "none"],
        default=None,
        help="Manual override for test entry point"
    )
    parser.add_argument(
        "--no-db", action="store_true",
        help="Override test-DB detection as 'none'"
    )
    parser.add_argument(
        "--roles", type=str, default=None,
        help="Comma-separated role list override (e.g., 'admin,member,viewer')"
    )
    args = parser.parse_args()

    # Real-browser product UX lives in forge ux-review (not test --mode ux).
    if args.mode == "ux":
        print(
            "ERROR: `forge test --mode ux` was removed to avoid overlapping "
            "`forge ux-review`.\n"
            "       Use: forge ux-review --step 1 [--base-url URL]\n"
            "       (suite runs: --mode run; mock flows: --mode flows)",
            file=sys.stderr,
        )
        sys.exit(2)

    # Atomic-delivery feature-check: if flows mode, verify prompts exist
    if args.mode == "flows":
        missing = []
        for p in required_flow_prompts():
            try:
                load_template(f"test/{p}")
            except FileNotFoundError:
                missing.append(p)
        if missing:
            prompts_root = default_prompts_root()
            print(
                f"ERROR: flows mode unavailable — missing prompts in active template root ({prompts_root}): {missing}",
                file=sys.stderr
            )
            sys.exit(1)
    apply_resolved_workflow_step(args, SKILL_NAME, _max_step_for_mode(args.mode), variant=args.mode)

    # Resume-conflict guard: if state exists and mode differs, abort
    if args.step > 1 and args.state:
        sp = validate_state_path(args.state, SKILL_NAME)
        if sp and sp.exists():
            try:
                saved_state = load_state(sp)
                saved_mode = saved_state.custom.get("mode", "run")
                # Only abort if --mode was explicitly passed (not default)
                if args.mode != "run" and saved_mode != args.mode:
                    print(
                        f"ERROR: Cannot resume — saved mode is '{saved_mode}' but --mode '{args.mode}' was passed.\n"
                        f"       Either re-run without --mode (resume preserves saved mode) or delete the state file.",
                        file=sys.stderr
                    )
                    sys.exit(1)
            except Exception:
                # If we can't load, let validate_step_or_complete handle it
                pass

    # Determine the max step based on mode (if step > 1, try to load state first to check)
    mode = getattr(args, "mode", "run")
    if args.step > 1 and args.state:
        sp = validate_state_path(args.state, SKILL_NAME)
        if sp and sp.exists():
            try:
                saved_state = load_state(sp)
                mode = saved_state.custom.get("mode", "run")
            except Exception:
                pass

    effective_max_step = _max_step_for_mode(mode)

    # Allow over-cap if not a step request
    if validate_step_or_complete(args.step, effective_max_step, SKILL_NAME):
        return

    if args.step == 1:
        handle_step_1(args)
    else:
        handle_step_n(
            args.step,
            state_file=args.state,
            session_id=getattr(args, "session", None),
        )


if __name__ == "__main__":
    main()
