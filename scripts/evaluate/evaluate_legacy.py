#!/usr/bin/env python3
"""Legacy evaluate orchestrator body (pre declarative skill engine).

Used when ``FORGE_SKILL_ENGINE=0``. Prefer ``scripts.evaluate.evaluate`` shim →
``run_skill`` when the engine is enabled.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# Auto-detect repo root so this works from any working directory
SCRIPT_DIR = Path(__file__).resolve().parent
PLUGIN_ROOT = SCRIPT_DIR.parent.parent  # scripts/evaluate/ -> scripts/ -> forge/

# Add repo root to sys.path so imports resolve without PYTHONPATH
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from scripts.evaluate.state import EvalState, load_state, save_state, STATE_FILENAME
from scripts.evaluate.state import clear_state
from scripts.evaluate.plan_resolver import extract_title, format_native_plan_hints, resolve_plan
from scripts.evaluate.mode_detector import extract_file_references, detect_mode
from scripts.evaluate.template_engine import load_template, render_template
from scripts.shared.orchestrator import (
    auto_parallel_on_conflict_enabled,
    append_skill_run_memory,
    build_next_command,
    build_skill_handoff_menu,
    _detect_repo_root,
    detect_active_sessions,
    format_active_session_warning,
    get_conflicting_sessions,
    is_evaluate_state_stale,
    validate_step_or_complete,
)
from scripts.shared.workflow_step import run_workflow_step

PROMPTS_DIR = PLUGIN_ROOT / "prompts"

PRE_PHASES = {
    2: "pre/feasibility",
    3: "pre/completeness",
    4: "pre/codebase_alignment",
    5: "pre/risk_dependencies",
    6: "shared/discussion",
    7: "report",
}

POST_PHASES = {
    2: "post/completeness_audit",
    3: "post/correctness",
    4: "post/code_quality",
    5: "post/performance",
    6: "post/operational_readiness",
    7: "shared/discussion",
    8: "report",
}

REVIEW_PHASES = {
    1: "review/team_dispatch",
    2: "review/findings_aggregation",
    3: "review/remediation",
    4: "shared/discussion",
    5: "report",
}

PHASE_NAMES = {
    "pre": {1: "Plan Parsing", 2: "Feasibility", 3: "Completeness", 4: "Codebase Alignment", 5: "Risk & Dependencies", 6: "Discussion", 7: "Report"},
    "post": {1: "Plan Parsing", 2: "Completeness Audit", 3: "Correctness", 4: "Code Quality", 5: "Performance", 6: "Operational Readiness", 7: "Discussion", 8: "Report"},
    "review": {1: "Team Dispatch", 2: "Findings Aggregation", 3: "Remediation", 4: "Discussion", 5: "Report"},
}

# Phase todos keyed by (mode, step)
PHASE_TODOS = {
    ("pre", 1): [
        {"content": "Parse plan and extract file references",
         "activeForm": "Parsing plan"},
        {"content": "Detect pre vs post implementation mode",
         "activeForm": "Detecting mode"},
    ],
    ("pre", 2): [
        {"content": "Assess feasibility of each plan step",
         "activeForm": "Assessing feasibility"},
    ],
    ("pre", 3): [
        {"content": "Check plan completeness (error handling, edge cases, tests)",
         "activeForm": "Checking completeness"},
    ],
    ("pre", 4): [
        {"content": "Check plan against existing code patterns and conventions",
         "activeForm": "Checking codebase alignment"},
    ],
    ("pre", 5): [
        {"content": "Analyze dependencies, risks, rollback strategies, and failure modes",
         "activeForm": "Analyzing risks and dependencies"},
    ],
    ("pre", 6): [
        {"content": "Present findings to user for triage",
         "activeForm": "Running triage with user"},
    ],
    ("pre", 7): [
        {"content": "Write evaluation report alongside plan",
         "activeForm": "Writing report"},
    ],
    ("post", 1): [
        {"content": "Parse plan and extract file references",
         "activeForm": "Parsing plan"},
    ],
    ("post", 2): [
        {"content": "Audit completeness (what was implemented vs planned)",
         "activeForm": "Auditing completeness"},
    ],
    ("post", 3): [
        {"content": "Verify correctness of implementation",
         "activeForm": "Verifying correctness"},
    ],
    ("post", 4): [
        {"content": "Review code quality and test quality",
         "activeForm": "Reviewing code quality"},
    ],
    ("post", 5): [
        {"content": "Review performance patterns and scalability concerns",
         "activeForm": "Reviewing performance"},
    ],
    ("post", 6): [
        {"content": "Check operational readiness (error handling, logging, resources, deployment)",
         "activeForm": "Checking operational readiness"},
    ],
    ("post", 7): [
        {"content": "Present findings to user for triage",
         "activeForm": "Running triage with user"},
    ],
    ("post", 8): [
        {"content": "Write evaluation report alongside plan",
         "activeForm": "Writing report"},
    ],
    ("review", 1): [
        {"content": "Dispatch full review team in parallel",
         "activeForm": "Dispatching review team"},
    ],
    ("review", 2): [
        {"content": "Aggregate findings from all reviewers",
         "activeForm": "Aggregating findings"},
    ],
    ("review", 3): [
        {"content": "Run remediation review loop",
         "activeForm": "Running remediation"},
    ],
    ("review", 4): [
        {"content": "Present findings to user for triage",
         "activeForm": "Running triage with user"},
    ],
    ("review", 5): [
        {"content": "Write review report",
         "activeForm": "Writing review report"},
    ],
}


def _findings_sidecar_path(state_dir: Path, step: int) -> Path:
    """Sidecar file where the LLM dumps findings emitted during step N."""
    return state_dir / f".evaluate-findings-step{step}.json"


def _ingest_findings_sidecars(state: EvalState, state_dir: Path, current_step: int) -> int:
    """Ingest any findings sidecars emitted by prior steps.

    Looks for `.evaluate-findings-stepN.json` at the same path as the state
    file for every step before `current_step`, parses each as a JSON array
    of `{phase, severity, title, detail}` objects, calls `state.add_finding`
    for each, then deletes the sidecar.

    Returns the number of findings ingested. Tolerant of malformed files —
    bad entries are skipped with a warning to stderr.
    """
    ingested = 0
    for step in range(1, current_step):
        sidecar = _findings_sidecar_path(state_dir, step)
        if not sidecar.exists():
            continue
        try:
            data = json.loads(sidecar.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            print(f"WARNING: skipping malformed findings sidecar {sidecar}: {e}", file=sys.stderr)
            continue
        if not isinstance(data, list):
            print(f"WARNING: findings sidecar {sidecar} is not a JSON array, skipping", file=sys.stderr)
            continue
        for entry in data:
            if not isinstance(entry, dict):
                continue
            try:
                state.add_finding(
                    phase=str(entry.get("phase", f"step{step}")),
                    severity=str(entry.get("severity", "warning")),
                    title=str(entry.get("title", "(untitled)")),
                    detail=str(entry.get("detail", "")),
                )
                ingested += 1
            except Exception as e:
                print(f"WARNING: failed to add finding from {sidecar}: {e}", file=sys.stderr)
        try:
            sidecar.unlink()
        except OSError:
            pass
    return ingested


def _build_variables(
    state: EvalState,
    plan_content: str,
    state_dir: Path | None = None,
    step: int | None = None,
) -> dict[str, str]:
    """Build template variable dict from state."""
    findings_text = ""
    if state.findings:
        for f in state.findings:
            status = f" [{f['status']}]" if f.get('status') != 'open' else ""
            note = f" — User: {f['user_note']}" if f.get('user_note') else ""
            findings_text += f"- **{f['id']}** ({f['severity']}): {f['title']}{status}{note}\n  {f['detail']}\n\n"
    else:
        findings_text = "(No findings yet)"

    sidecar_path = ""
    if state_dir is not None and step is not None:
        sidecar_path = str(_findings_sidecar_path(state_dir, step))

    native_hints = format_native_plan_hints(_detect_repo_root(Path.cwd()))

    probe_summary = "_Structural probes: not run (pre mode or no sidecar)._"
    if state.custom.get("structural_probes_sidecar") or state_dir:
        from scripts.shared.structural_probes import resolve_probe_summary_for_state

        probe_summary = resolve_probe_summary_for_state(
            state.custom,
            state_dir,
            style="full" if step == _max_step_for_mode(state.mode or "pre") else "brief",
        ).strip() or probe_summary

    return {
        "PLAN_CONTENT": plan_content,
        "PLAN_PATH": state.plan_path,
        "PLAN_NAME": state.plan_name,
        "MODE": state.mode or "unknown",
        "REFERENCED_FILES": ", ".join(state.referenced_files) if state.referenced_files else "(none extracted yet)",
        "PREVIOUS_FINDINGS": findings_text.strip(),
        "REVIEW_ROUND": str(state.review_round),
        "QUICK_MODE_NOTE": (
            "Quick/minimal-scope mode: heavy phases may be skipped "
            f"(eval_size={state.custom.get('eval_size', 'unknown')})."
            if state.custom.get("quick_mode")
            else ""
        ),
        "FINDINGS_SIDECAR": sidecar_path,
        "NATIVE_PLAN_HINTS": native_hints,
        "STRUCTURAL_PROBES_SUMMARY": probe_summary,
    }


def _max_step_for_mode(mode: str | None) -> int:
    """Return the maximum step number for the given evaluation mode."""
    if mode == "review":
        return 5
    if mode == "post":
        return 8
    return 7  # pre (default)


def _next_command(step: int, state_path: str = "", mode: str | None = None) -> str:
    """Build agent-facing continuation for the next step (``$forge-evaluate`` / slash)."""
    max_step = _max_step_for_mode(mode)
    extra = {}
    if state_path:
        extra["state"] = state_path
    if mode:
        extra["mode"] = mode
    return build_next_command(
        SCRIPT_DIR / "evaluate.py",
        step,
        max_step,
        phase_variant=mode,
        **extra,
    )


def _mode_phase_todos(mode: str) -> dict[int, list[dict]]:
    """Convert mode-keyed PHASE_TODOS to step-keyed dict for a given mode."""
    return {
        step: todos
        for (m, step), todos in PHASE_TODOS.items()
        if m == mode
    }


def _format_output(
    title: str,
    body: str,
    next_cmd: str,
    phase_todos: list[dict] | None = None,
    mode: str | None = None,
    step: int | None = None,
    handoff_menu: str | None = None,
    *,
    require_confirmation: bool | None = None,
) -> str:
    """Format step output with title, todos, and continuation directive."""
    max_step = _max_step_for_mode(mode) if mode else 1
    step_num = step if step is not None else 0
    phase_name = (
        PHASE_NAMES.get(mode, {}).get(step, f"Step {step}")
        if mode and step
        else (f"Step {step}" if step else "Step")
    )
    return run_workflow_step(
        "evaluate",
        step_num,
        max_step,
        phase_name,
        body,
        next_cmd=next_cmd or None,
        phase_todos=phase_todos,
        all_phase_names=PHASE_NAMES.get(mode) if mode else None,
        all_phase_todos=_mode_phase_todos(mode) if mode else None,
        handoff_menu=handoff_menu,
        title=title,
        require_confirmation=require_confirmation,
    )


def handle_step_1(args: argparse.Namespace) -> None:
    """Step 1: Plan resolution, parsing, and mode detection (or review dispatch)."""
    # Cross-session detection: only warn on fresh starts (no --state arg)
    if not getattr(args, "state", None):
        conflicting_sessions = get_conflicting_sessions(
            "evaluate",
            sessions=detect_active_sessions(),
        )
        if conflicting_sessions:
            print(format_active_session_warning(conflicting_sessions, "evaluate"), file=sys.stderr)

    # Review mode deprecated — use code-review
    if getattr(args, "mode", None) == "review":
        print(
            "ERROR: evaluate --mode review is deprecated. Use `forge code-review --step 1` "
            "for full-team review.",
            file=sys.stderr,
        )
        sys.exit(1)

    if not args.plan:
        print("ERROR: --plan is required for step 1. Provide a file path or keywords.")
        sys.exit(1)

    cwd = Path.cwd()
    try:
        result = resolve_plan(args.plan, cwd, return_matches=True)
    except FileNotFoundError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    if isinstance(result, list) and len(result) > 1:
        print("Multiple plans found. Present these to the user and ask which one to evaluate:\n")
        for i, p in enumerate(result, 1):
            title = extract_title(p)
            print(f"  {i}. {p} — {title}")
        print(
            "\nThen ask which plan to use and continue with "
            "`$forge:evaluate --step 1 --plan '<chosen path>'`."
        )
        return

    plan_path = result[0] if isinstance(result, list) else result
    plan_content = plan_path.read_text(encoding="utf-8")
    plan_name = plan_path.stem

    refs = extract_file_references(plan_content)

    plan_mtime = datetime.fromtimestamp(plan_path.stat().st_mtime, tz=timezone.utc).isoformat()
    forced_mode = getattr(args, "mode", None)
    if forced_mode in ("pre", "post"):
        mode = forced_mode
        matched, total = 0, 0
    else:
        mode, matched, total = detect_mode(refs, str(cwd), plan_mtime)

    sp = _resolve_evaluate_state_path(
        plan_path=plan_path,
        state_file=args.state,
        parallel=getattr(args, "parallel", False),
    )

    if sp.exists():
        try:
            state = load_state(sp)
        except Exception:
            state = EvalState(
                plan_path=str(plan_path.resolve()),
                plan_name=plan_name,
            )
    else:
        state = EvalState(
            plan_path=str(plan_path.resolve()),
            plan_name=plan_name,
        )
    state.plan_path = str(plan_path.resolve())
    state.plan_name = plan_name
    state.mode = mode
    state.current_step = 1
    state.referenced_files = refs
    from scripts.evaluate.evaluate_effort import (
        apply_size_to_custom,
        infer_size_from_plan,
        skipped_phase_summary,
    )

    quick = bool(getattr(args, "quick", False))
    size, size_rationale = infer_size_from_plan(
        plan_content,
        referenced_files=refs,
        cli_effort=getattr(args, "effort", None),
        quick=quick,
    )
    state.custom["mode"] = mode
    apply_size_to_custom(state.custom, size, size_rationale, quick)
    save_state(state, sp)

    # Print state path so user/Codex knows where it is
    print(f"STATE FILE: {sp}\n", file=sys.stderr)

    template = load_template("shared/plan_parsing")
    variables = _build_variables(state, plan_content)
    body = render_template(template, variables)

    body += f"\n\n---\n\n## Mode Detection\n\n"
    if forced_mode in ("pre", "post"):
        body += f"**Forced mode:** {mode.upper()}\n\n"
    else:
        body += f"**Detected mode:** {'POST-IMPLEMENTATION' if mode == 'post' else 'PRE-IMPLEMENTATION'}"
        body += f" ({matched}/{total} referenced files show matching changes)\n\n"
    body += f"Confirm this mode with the user. If they want to switch, update the mode.\n"
    body += f"Then proceed to the next step.\n"
    skipped = skipped_phase_summary(mode, size, bool(state.custom.get("quick_mode")))
    body += (
        f"\n## Size / ceremony\n\n"
        f"**Eval size:** `{size}` — {size_rationale}\n"
        f"**Quick mode:** `{bool(state.custom.get('quick_mode'))}`\n"
        f"**Skipped phases:** {skipped}\n\n"
        "Small/trivial/quick skips heavy phases "
        "(pre: codebase_alignment + risk_dependencies; "
        "post: performance + operational_readiness).\n"
    )

    # Mark step 1 complete
    state.mark_step_complete(1)
    save_state(state, sp)
    append_skill_run_memory(
        "evaluate",
        1,
        PHASE_NAMES.get(mode, PHASE_NAMES["pre"]).get(1, "Plan Parsing"),
        f"Initialized evaluate session ({mode} mode) and parsed plan context.",
        state=state,
        state_path=sp,
    )

    max_step = _max_step_for_mode(mode)
    title = f"EVALUATE — Plan Parsing (Step 1 of {max_step})"
    next_cmd = _next_command(1, state_path=str(sp), mode=mode)
    phase_todos = PHASE_TODOS.get((mode, 1), [])
    print(_format_output(title, body, next_cmd, phase_todos=phase_todos, mode=mode, step=1))


def handle_step_1_review(args: argparse.Namespace) -> None:
    """Step 1 for review mode: team dispatch (no plan needed)."""
    cwd = Path.cwd()

    sp = _resolve_evaluate_state_path(
        plan_path=None,
        state_file=args.state,
        parallel=getattr(args, "parallel", False),
    )

    if sp.exists():
        try:
            state = load_state(sp)
        except Exception:
            state = EvalState(
                plan_path="(review mode)",
                plan_name="review",
            )
    else:
        state = EvalState(
            plan_path="(review mode)",
            plan_name="review",
        )
    state.plan_path = "(review mode)"
    state.plan_name = "review"
    state.mode = "review"
    state.current_step = 1
    state.review_round = 0
    save_state(state, sp)

    print(f"STATE FILE: {sp}\n", file=sys.stderr)

    template = load_template("review/team_dispatch")
    variables = _build_variables(state, "(review mode — no plan)")
    body = render_template(template, variables)

    state.mark_step_complete(1)
    save_state(state, sp)
    append_skill_run_memory(
        "evaluate",
        1,
        PHASE_NAMES["review"][1],
        "Initialized evaluate session (review mode) and dispatched review team setup.",
        state=state,
        state_path=sp,
    )

    title = f"EVALUATE (REVIEW) — Team Dispatch (Step 1 of {_max_step_for_mode('review')})"
    next_cmd = _next_command(1, state_path=str(sp), mode="review")
    phase_todos = PHASE_TODOS.get(("review", 1), [])
    print(_format_output(title, body, next_cmd, phase_todos=phase_todos, mode="review", step=1))


def _is_evaluate_state_name(name: str) -> bool:
    return bool(re.match(r"^\.evaluate-state(?:-[^.\\/]+)?\.json$", name))


def _resolve_evaluate_state_path(
    *,
    plan_path: Path | None,
    state_file: str | None,
    parallel: bool,
) -> Path:
    """Resolve where evaluate step 1 should write state."""
    from scripts.evaluate.state import state_path_for_plan

    repo_root = _detect_repo_root().resolve()
    if state_file:
        sp = Path(state_file).resolve()
        try:
            sp.relative_to(repo_root)
        except ValueError:
            sys.exit(f"ERROR: --state path is outside the repository: {state_file}")
        if not _is_evaluate_state_name(sp.name):
            sys.exit(
                "ERROR: --state must look like `.evaluate-state.json` or "
                "`.evaluate-state-<id>.json`."
            )
        return sp

    plan_dir = (
        plan_path.resolve().parent
        if plan_path is not None
        else _detect_repo_root().resolve()
    )
    if not parallel:
        existing = _find_state_file(include_stale=False)
        if existing is not None and auto_parallel_on_conflict_enabled():
            parallel = True
        elif plan_path is not None:
            return state_path_for_plan(str(plan_path))
        else:
            return plan_dir / STATE_FILENAME

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    candidate = plan_dir / f".evaluate-state-{stamp}.json"
    idx = 2
    while candidate.exists():
        candidate = plan_dir / f".evaluate-state-{stamp}-{idx}.json"
        idx += 1
    return candidate


def _find_state_file(*, include_stale: bool = False) -> Path | None:
    from scripts.evaluate.evaluate_steps import find_state_file

    return find_state_file(include_stale=include_stale)


def handle_step_n(
    step: int,
    state_file: str | None = None,
    session_id: str | None = None,
) -> None:
    """Steps 2-6: Load state, render appropriate template, output prompt."""
    from scripts.evaluate.evaluate_steps import (
        load_evaluate_state,
        load_plan_content,
        render_step_body,
        resolve_state_path,
    )

    sp = resolve_state_path(state_file, session_id=session_id, step=step)
    state = load_evaluate_state(sp)

    ingested = _ingest_findings_sidecars(state, sp.parent, step)
    if ingested:
        save_state(state, sp)

    plan_content = load_plan_content(state)

    if state.mode == "review":
        phases = REVIEW_PHASES
    elif state.mode == "post":
        phases = POST_PHASES
    else:
        phases = PRE_PHASES
    max_step = _max_step_for_mode(state.mode)

    template_name = phases.get(step)
    if not template_name:
        print(f"ERROR: Invalid step {step} for mode {state.mode}")
        sys.exit(1)

    from scripts.evaluate.evaluate_effort import should_skip_phase, skip_note

    eval_size = str(state.custom.get("eval_size") or "medium")
    quick = bool(state.custom.get("quick_mode"))
    if should_skip_phase(state.mode, step, eval_size, quick):
        state.current_step = step
        state.mark_step_complete(step)
        save_state(state, sp)
        mode_label = state.mode.upper() if state.mode else "UNKNOWN"
        phase_name = PHASE_NAMES.get(state.mode or "pre", {}).get(step, f"Step {step}")
        title = f"EVALUATE ({mode_label}) — {phase_name} (Step {step} of {max_step}) [SKIPPED]"
        next_cmd = _next_command(step, state_path=str(sp), mode=state.mode)
        body = skip_note(state.mode, step)
        append_skill_run_memory(
            "evaluate",
            step,
            phase_name,
            f"Skipped {phase_name} for size={eval_size}",
            state=state,
            state_path=sp,
        )
        print(
            _format_output(
                title,
                body,
                next_cmd,
                phase_todos=PHASE_TODOS.get((state.mode or "pre", step), []),
                mode=state.mode or "pre",
                step=step,
            )
        )
        return

    template = load_template(template_name)
    variables = _build_variables(state, plan_content, state_dir=sp.parent, step=step)
    body, probe_gate_pending = render_step_body(template, variables, state, sp, step)

    state.current_step = step
    save_state(state, sp)

    # Mark this step complete
    state.mark_step_complete(step)
    save_state(state, sp)

    mode_label = state.mode.upper() if state.mode else "UNKNOWN"
    phase_name = PHASE_NAMES.get(state.mode or "pre", {}).get(step, f"Step {step}")
    title = f"EVALUATE ({mode_label}) — {phase_name} (Step {step} of {max_step})"

    next_cmd = _next_command(step, state_path=str(sp), mode=state.mode)
    phase_todos = PHASE_TODOS.get((state.mode or "pre", step), [])
    handoff_menu = None
    run_summary = f"Completed evaluate step {step} ({phase_name}) in mode {(state.mode or 'pre')}."
    if not next_cmd:
        from scripts.shared.structural_probes import resolve_probe_summary_for_state

        probe_brief = resolve_probe_summary_for_state(
            state.custom,
            sp.parent,
            style="brief",
        )
        body += f"\n\n---\n\n{probe_brief}"
        run_summary = f"Completed final evaluate step ({phase_name}) in mode {(state.mode or 'pre')} and closed state."
        handoff_menu = build_skill_handoff_menu("evaluate", state, sp)
        append_skill_run_memory(
            "evaluate",
            step,
            phase_name,
            run_summary,
            state=state,
            state_path=sp,
        )
        clear_state(sp)
    else:
        append_skill_run_memory(
            "evaluate",
            step,
            phase_name,
            run_summary,
            state=state,
            state_path=sp,
        )
    print(_format_output(title, body, next_cmd, phase_todos=phase_todos, mode=state.mode or "pre", step=step, handoff_menu=handoff_menu, require_confirmation=probe_gate_pending or None))


def main():
    parser = argparse.ArgumentParser(description="Evaluate skill orchestrator")
    step_group = parser.add_mutually_exclusive_group(required=False)
    step_group.add_argument(
        "--step", type=int, default=None,
        help="Phase number (1-7 pre, 1-8 post, 1-5 review); optional when resuming",
    )
    step_group.add_argument(
        "--phase", type=str, default=None, metavar="NAME",
        help="Named phase (e.g. pre-feasibility, post-correctness); optional when resuming",
    )
    parser.add_argument("--plan", type=str, help="Plan file path or keywords (step 1 only, pre/post modes)")
    parser.add_argument("--state", type=str, help="Path to .evaluate-state.json (auto-detected if omitted)")
    parser.add_argument("--session", type=str, default=None, help="Session id to continue")
    parser.add_argument(
        "--parallel",
        action="store_true",
        help="Start a parallel evaluate session using a suffixed .evaluate-state file.",
    )
    parser.add_argument("--mode", choices=["pre", "post", "review"], help="Force evaluation mode (pre or post)")
    parser.add_argument("--team", action="store_true", help="Enable team dispatch in pre/post modes")
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Small-ceremony evaluate: skip heavy pre/post phases (alignment/risk or perf/ops).",
    )
    parser.add_argument(
        "--effort",
        choices=["small", "medium", "large", "lite", "light", "standard", "thorough"],
        default=None,
        help="Override size/ceremony tier (small skips heavy phases).",
    )

    args = parser.parse_args()

    effective_mode = args.mode
    if effective_mode is None and (args.state or args.session):
        sp = Path(args.state).resolve() if args.state else None
        if sp is None and args.session:
            from scripts.shared.session_store import session_json_path
            from scripts.shared.orchestrator import _detect_repo_root

            sp = session_json_path(args.session, _detect_repo_root())
        if sp is not None and sp.exists():
            try:
                effective_mode = load_state(sp).mode
            except (json.JSONDecodeError, KeyError, FileNotFoundError):
                pass

    max_step = _max_step_for_mode(effective_mode)
    from scripts.shared.skill_phases import resolve_workflow_step

    args.step = resolve_workflow_step(
        skill_name="evaluate",
        max_step=max_step,
        step=args.step,
        phase=getattr(args, "phase", None),
        state_file=args.state,
        session_id=getattr(args, "session", None),
        variant=effective_mode,
    )

    if validate_step_or_complete(args.step, max_step, "evaluate"):
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
