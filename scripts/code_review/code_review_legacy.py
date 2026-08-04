#!/usr/bin/env python3
"""Code review skill orchestrator.

Script-driven workflow that outputs formatted prompts for Codex to follow.
Each --step invocation loads state, selects the appropriate prompt template,
substitutes variables, and prints the prompt for Codex to execute.

Steps:
  1. Target Detection — detect PR/branch/files/handoff, initialize state
  2. Mode Selection — auto-detect or use --mode flag, output mode-specific instructions
  3. Team Dispatch — dispatch all reviewers in parallel with mode-specific focus
  4. Deep Dive — Investigator deep-dives on critical findings
  5. Discussion — interactive review with user
  6. Report — write code review report, handoff, dashboard
"""

from __future__ import annotations

import sys
from pathlib import Path

# Auto-detect repo root so this works from any working directory
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent  # scripts/code-review/ -> scripts/ -> repo root

# Add repo root to sys.path so imports resolve without PYTHONPATH
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.evaluate.plan_resolver import (
    AmbiguousPlanError,
    extract_title,
    format_native_plan_hints,
    resolve_plan_file,
)
from scripts.shared.orchestrator import (
    SkillState,
    append_skill_run_memory,
    apply_resolved_workflow_step,
    build_base_parser,
    build_next_command,
    build_skill_handoff_menu,
    check_same_skill_clobber,
    clear_state_file,
    _detect_repo_root,
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
    validate_step,
    validate_step_or_complete,
    write_handoff,
)
from scripts.evaluate.template_engine import load_template, render_template

PROMPTS_DIR = REPO_ROOT / "prompts"
SKILL_NAME = "code-review"
MAX_STEP = 6

PHASE_NAMES = {
    1: "Target Detection",
    2: "Mode Selection",
    3: "Team Dispatch",
    4: "Deep Dive",
    5: "Discussion",
    6: "Report",
}

PHASE_TODOS = {
    1: [
        {"content": "Detect PR/branch/files target",
         "activeForm": "Detecting review target"},
        {"content": "Read handoff-implement.md",
         "activeForm": "Reading handoff"},
    ],
    2: [
        {"content": "Select review mode (pr/deep/architecture)",
         "activeForm": "Selecting mode"},
    ],
    3: [
        {"content": "Run forge step 3 (orchestrator runs pyscn/knip/madge; read .structural-probes.json)",
         "activeForm": "Running structural probes and team dispatch"},
        {"content": "Cite pyscn finding IDs in Pass B before dispatching reviewers",
         "activeForm": "Incorporating pyscn results"},
        {"content": "Write findings or advance when time-boxed (do not block on every subagent)",
         "activeForm": "Recording findings"},
    ],
    4: [
        {"content": "Dispatch Investigator for deep dive on critical findings",
         "activeForm": "Deep-diving critical findings"},
    ],
    5: [
        {"content": "Run interactive triage with user",
         "activeForm": "Running triage with user"},
        {"content": "Resolve or dismiss findings",
         "activeForm": "Resolving findings"},
    ],
    6: [
        {"content": "Write code review report",
         "activeForm": "Writing report"},
        {"content": "Write handoff and render dashboard",
         "activeForm": "Writing handoff"},
    ],
}

# Maps mode -> template name for step 3
MODE_TEMPLATES = {
    "pr": "code-review/diff_analysis",
    "deep": "code-review/security_scan",
    "architecture": "code-review/architecture_check",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _state_path() -> Path:
    """Return the default state file path."""
    return runtime_state_path(SKILL_NAME)




def _detect_mode(target: str, handoff_content: str) -> str:
    """Auto-detect review mode from target and handoff content.

    Returns 'pr', 'deep', or 'architecture'.
    """
    if not target and not handoff_content:
        return "pr"

    combined = (target + " " + handoff_content).lower()

    # If target looks like a PR number
    if target and target.strip().isdigit():
        return "pr"

    # If target starts with # (PR reference)
    if target and target.strip().startswith("#"):
        return "pr"

    # Deep mode indicators
    deep_keywords = ["bug", "issue", "error", "fail", "crash", "troubleshoot",
                     "investigate", "trace", "debug", "security", "vulnerability"]
    if any(kw in combined for kw in deep_keywords):
        return "deep"

    # Architecture mode indicators
    arch_keywords = ["architecture", "design", "pattern", "coupling", "solid",
                     "refactor", "structure", "dependency", "module"]
    if any(kw in combined for kw in arch_keywords):
        return "architecture"

    return "pr"


def _normalize_target(target_arg: str | list[str] | None) -> tuple[str, list[str]]:
    """Normalize target CLI input into canonical string and raw tokens."""
    if target_arg is None:
        return "", []
    if isinstance(target_arg, list):
        tokens = [tok for tok in target_arg if tok]
        return " ".join(tokens), tokens
    return target_arg, [target_arg] if target_arg else []


def _code_review_state_dir(state_path: Path, repo_root: Path) -> Path:
    from scripts.shared.repo_paths import equivalent_path_in_repo

    return equivalent_path_in_repo(state_path.parent, repo_root)


def _prompt_archive_dir(state_path: Path, repo_root: Path) -> Path:
    return _code_review_state_dir(state_path, repo_root)


def _build_variables(
    state: SkillState,
    *,
    state_path: Path | None = None,
    repo_root: Path | None = None,
    prompts_style: str = "brief",
) -> dict[str, str]:
    """Build template variable dict from state."""
    mode = state.custom.get("mode", "pr")
    target = state.custom.get("target", "(auto-detected)")
    handoff_content = state.custom.get("handoff_content", "")
    plan_path = (state.custom.get("plan_path") or "").strip()
    repo_root = _detect_repo_root(Path.cwd())
    native_plan_hints = format_native_plan_hints(repo_root)
    if plan_path:
        plan_link_section = (
            "## Plan reference\n\n"
            f"Compare the review target against this plan (intent vs code): `{plan_path}`\n"
        )
    else:
        plan_link_section = ""

    # Build handoff section
    if handoff_content:
        handoff_section = (
            "## Handoff from Implement\n\n"
            "<handoff>\n"
            f"{handoff_content}\n"
            "</handoff>"
        )
    else:
        handoff_section = (
            "## No Handoff Found\n\n"
            "No handoff-implement.md was found. Using target from arguments or git state."
        )

    # Build findings summary
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

    # Mode display
    mode_display = {
        "pr": "PR Review -- analyze diff and changes",
        "deep": "Deep Troubleshooting Review -- trace code paths, investigate issues",
        "architecture": "Architecture Review -- design patterns, coupling, SOLID principles",
    }

    # Team assignments based on effort / quick mode
    # light → Architect + QA; standard → Architect + QA (+ Security if auth/data);
    # thorough → full six-agent team.
    effort = str(state.custom.get("effort") or ("light" if state.quick_mode else "standard"))
    handoff_blob = str(state.custom.get("handoff_content") or "")
    target_blob = str(state.custom.get("target") or "")
    include_security = False
    try:
        from scripts.code_review.effort_recommendation import mentions_auth_or_data

        include_security = mentions_auth_or_data(f"{handoff_blob} {target_blob}") or mode in (
            "deep",
            "architecture",
        )
    except Exception:
        include_security = mode in ("deep", "architecture")

    if state.quick_mode or effort == "light":
        team_section = (
            f"**Effort: {effort}** — abbreviated review:\n\n"
            "| Agent | Focus |\n"
            "|-------|-------|\n"
            "| Architect | Design and structure review |\n"
            "| QA Reviewer | Correctness and test coverage |\n"
            "\nStructural probes **on** (S3/S4/S8 quick subset); diff-scoped; "
            "unrelated findings advisory.\n"
        )
    elif effort == "thorough":
        team_section = (
            f"**Effort: {effort}** — full team:\n\n"
            "| Agent | Focus |\n"
            "|-------|-------|\n"
            "| Architect | Design patterns, structure, coupling |\n"
            "| Security Reviewer | Auth, data flow, injection, secrets |\n"
            "| QA Reviewer | Correctness, edge cases, test coverage |\n"
            "| Critic | Assumptions, missed cases, over-engineering |\n"
            "| Investigator | Deep code path tracing, dependency analysis |\n"
            "| Doc-writer | Documentation completeness, API docs |\n"
            "\nStructural probes **on** with broader fan-out (full S1–S8); "
            "diff-scoped; unrelated findings advisory.\n"
        )
    else:
        # standard — trimmed team
        rows = [
            "| Agent | Focus |",
            "|-------|-------|",
            "| Architect | Design patterns, structure, coupling |",
            "| QA Reviewer | Correctness, edge cases, test coverage |",
        ]
        if include_security:
            rows.insert(
                3,
                "| Security Reviewer | Auth, data flow, injection, secrets |",
            )
            security_note = "Security Reviewer included (auth/data signals)."
        else:
            security_note = "Security Reviewer skipped (no auth/data signals)."
        team_section = (
            f"**Effort: {effort}** — trimmed team:\n\n"
            + "\n".join(rows)
            + f"\n\n{security_note}\n"
            "Structural probes **on** (S3/S4/S8 quick subset); diff-scoped; "
            "unrelated findings advisory.\n"
        )

    probe_summary = ""
    workflow_prompts = ""
    rr = repo_root or _detect_repo_root(Path.cwd())
    if state_path is not None:
        from scripts.shared.structural_probes import resolve_probe_summary_for_state
        from scripts.shared.workflow_prompt_archive import format_workflow_prompts_markdown

        archive_dir = _prompt_archive_dir(state_path, rr)
        probe_summary = resolve_probe_summary_for_state(
            state.custom,
            archive_dir,
            style="full",
        )
        workflow_prompts = format_workflow_prompts_markdown(
            archive_dir,
            style=prompts_style,
        )

    return {
        "MODE": mode,
        "MODE_DISPLAY": mode_display.get(mode, mode),
        "TARGET": target,
        "HANDOFF_CONTENT": handoff_section,
        "FINDINGS": findings_text.strip(),
        "TEAM_ASSIGNMENTS": team_section,
        "QUICK_MODE": "yes" if state.quick_mode else "no",
        "EFFORT": str(state.custom.get("effort") or ("light" if state.quick_mode else "standard")),
        "STRUCTURAL_ENABLED": (
            "yes" if state.custom.get("structural_enabled", True) else "no"
        ),
        "EFFORT_CONFIG_SECTION": state.custom.get("effort_config_section", ""),
        "SKILL_NAME": SKILL_NAME,
        "PLAN_PATH": plan_path or "(none)",
        "PLAN_LINK_SECTION": plan_link_section,
        "NATIVE_PLAN_HINTS": native_plan_hints,
        "STRUCTURAL_PROBES_SUMMARY": probe_summary.strip()
        or "_Structural probes: not run (no sidecar)._",
        "WORKFLOW_PROMPTS_APPENDIX": workflow_prompts.strip(),
    }


def _next_command(step: int, state_path: str = "") -> str:
    """Build the command for the next step."""
    extra = {}
    if state_path:
        extra["state"] = state_path
    return build_next_command(SCRIPT_DIR / "code_review.py", step, MAX_STEP, **extra)


# ---------------------------------------------------------------------------
# Step handlers
# ---------------------------------------------------------------------------

def handle_step_1(args) -> None:
    """Step 1: Target Detection -- detect PR/branch/files/handoff, init state."""
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

    # Read handoff from implement
    handoff_content = consume_handoff("implement")

    # Optional plan: path or keywords (includes native Cursor/Claude/Codex plan dirs)
    plan_path = ""
    plan_arg = (getattr(args, "plan", None) or "").strip()
    if plan_arg:
        try:
            plan_path = str(resolve_plan_file(plan_arg, Path.cwd()))
        except AmbiguousPlanError as e:
            print("Multiple plans matched. Choose one:\n", file=sys.stderr)
            for i, p in enumerate(e.matches, 1):
                print(f"  {i}. {p} — {extract_title(p)}", file=sys.stderr)
            sys.exit(1)
        except FileNotFoundError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)

    # Determine target
    target, target_tokens = _normalize_target(getattr(args, "target", None))

    # Determine mode
    mode = getattr(args, "mode", None) or ""
    if not mode:
        mode = _detect_mode(target, handoff_content)

    if sp.exists():
        try:
            state = load_state(sp)
        except Exception:
            state = SkillState(skill_name=SKILL_NAME, max_step=MAX_STEP)
    else:
        state = SkillState(skill_name=SKILL_NAME, max_step=MAX_STEP)
    state.current_step = 1

    from scripts.code_review.effort_recommendation import (
        format_effort_config_section,
        recommend_effort_structural,
        resolve_applied_config,
    )

    recommendation = recommend_effort_structural(
        mode=mode,
        target=target,
        target_tokens=target_tokens,
        handoff_content=handoff_content,
        plan_path=plan_path,
        quick=bool(getattr(args, "quick", False)),
    )
    effort, structural_enabled, effort_overridden, structural_overridden = resolve_applied_config(
        args, recommendation
    )
    state.quick_mode = effort == "light" or bool(args.quick)
    state.started_at = state.started_at or now_iso()
    state.custom["mode"] = mode
    state.custom["target"] = target
    state.custom["target_tokens"] = target_tokens
    state.custom["handoff_content"] = handoff_content
    state.custom["plan_path"] = plan_path
    state.custom["effort"] = effort
    state.custom["structural_enabled"] = structural_enabled
    state.custom["effort_recommendation"] = recommendation.to_dict()
    state.custom["effort_config_section"] = format_effort_config_section(
        recommendation,
        applied_effort=effort,
        applied_structural=structural_enabled,
        effort_overridden=effort_overridden,
        structural_overridden=structural_overridden,
    )

    save_state(state, sp)

    # Print state path so Codex knows where it is
    print(f"STATE FILE: {sp}\n", file=sys.stderr)

    template = load_template("code-review/target_detection")
    scan_root = _detect_repo_root(Path.cwd())
    variables = _build_variables(state, state_path=sp, repo_root=scan_root)
    body = render_template(template, variables)

    from scripts.shared.workflow_prompt_archive import record_step_prompt

    record_step_prompt(
        _prompt_archive_dir(sp, scan_root),
        skill=SKILL_NAME,
        step=1,
        phase_name=PHASE_NAMES[1],
        body=body,
        template_name="code-review/target_detection",
    )

    state.mark_step_complete(1)
    save_state(state, sp)
    append_skill_run_memory(
        SKILL_NAME,
        1,
        PHASE_NAMES[1],
        "Initialized code-review session and detected target/mode.",
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


def _probe_status_one_liner(probe_markdown: str) -> str:
    """Single-line probe status for run_summary / memory."""
    for line in probe_markdown.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("_") and stripped.endswith("_"):
            return stripped.strip("_")
        if stripped.startswith("- **") and "finding" in stripped.lower():
            return stripped.lstrip("- ")
        if "not run" in stripped.lower() or "suppressed" in stripped.lower():
            return stripped.strip("_")
    return "see step output for structural probe details"


def handle_step_n(
    step: int,
    state_file: str | None = None,
    session_id: str | None = None,
    *,
    allow_structural_probes_incomplete: bool = False,
    structural_probes_override_reason: str = "",
    structural_probes_override_follow_up: str = "",
) -> None:
    """Steps 2-6: Load state, render template, output prompt."""
    from scripts.shared.orchestrator import resolve_step_state_path

    sp = resolve_step_state_path(
        SKILL_NAME, step, state_file=state_file, session_id=session_id
    )

    if not sp.exists():
        print("ERROR: No code-review session in progress. Run step 1 first.")
        print(f"Expected state file at: {_state_path()}")
        sys.exit(1)

    try:
        state = load_state(sp)
    except Exception as e:
        print(f"ERROR: Failed to load state: {e}")
        print("Delete the state file and re-run step 1.")
        sys.exit(1)

    scan_root = _detect_repo_root(Path.cwd())

    if step >= 4 and bool(state.custom.get("structural_enabled", True)):
        from scripts.code_review.structural_probes_gate import exit_if_structural_probes_gate_fails

        state_dir = _code_review_state_dir(sp, scan_root)
        exit_if_structural_probes_gate_fails(
            state_dir,
            scan_root,
            allow_incomplete=allow_structural_probes_incomplete,
            override_reason=structural_probes_override_reason,
            override_follow_up=structural_probes_override_follow_up,
        )

    # Map steps to template names
    mode = state.custom.get("mode", "pr")

    template_map = {
        2: "code-review/mode_selection",
        3: MODE_TEMPLATES.get(mode, "code-review/diff_analysis"),
        4: "code-review/deep_dive",
        5: "code-review/discussion",
        6: "code-review/report",
    }

    template_name = template_map.get(step)
    if not template_name:
        print(f"ERROR: Invalid step {step}")
        sys.exit(1)

    # Load template before mutating state — a missing template must not leave
    # state half-written.
    template = load_template(template_name)
    prompts_style = "full" if step == MAX_STEP else "brief"
    variables = _build_variables(
        state,
        state_path=sp,
        repo_root=scan_root,
        prompts_style=prompts_style,
    )
    body = render_template(template, variables)

    probe_gate_pending = False
    # Structural defaults on; only --no-structural disables.
    structural_enabled = bool(state.custom.get("structural_enabled", True))
    effort = str(state.custom.get("effort") or ("light" if state.quick_mode else "standard"))
    if step == 3 and structural_enabled:
        print(
            "forge: code-review step 3 — loading template and structural Pass B…",
            file=sys.stderr,
            flush=True,
        )
        from scripts.shared.structural_probes import inject_structural_probes_section

        scope = state.custom.get("target_tokens") or []
        from scripts.shared.repo_paths import resolve_repo_root

        scan_root = resolve_repo_root(Path.cwd())
        state_dir = _code_review_state_dir(sp, scan_root)
        # Scale fan-out: light/standard → S3/S4/S8; thorough → full eight.
        structural_quick = effort != "thorough"
        body, sidecar, _payload = inject_structural_probes_section(
            body,
            skill_name=SKILL_NAME,
            step=step,
            repo_root=scan_root,
            state_dir=state_dir,
            mode=state.custom.get("mode"),
            scope_paths=scope if scope else None,
            quick_mode=structural_quick,
            force_full_eight=(effort == "thorough"),
            # Gate on DEFERRED/FAIL (unlike plan step 2 advisory baseline).
            advisory=False,
        )
        body += (
            "\n\n**Structural scope:** prefer diff / target paths. Findings outside "
            "the changed surface are **advisory** unless this change caused them.\n"
        )
        if sidecar:
            state.custom["structural_probes_sidecar"] = str(sidecar)

        from scripts.shared.structural_probes_gate import probe_gate_is_pending

        probe_gate_pending = probe_gate_is_pending(
            _code_review_state_dir(sp, scan_root)
        )
    elif step == 3 and not structural_enabled:
        body += (
            "\n\n---\n\n**Structural Pass B:** skipped (`--no-structural`). "
            "Core reviewers only — no probes / eight-agents.\n"
        )
        probe_gate_pending = False

    from scripts.shared.workflow_prompt_archive import record_step_prompt

    record_step_prompt(
        _prompt_archive_dir(sp, scan_root),
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

        open_count = len(state.open_findings())
        total_count = len(state.findings)

        handoff_path = write_handoff(
            skill_name=SKILL_NAME,
            state=state,
            context={
                "Review mode": mode,
                "Target": state.custom.get("target", "N/A"),
                "Findings": f"{open_count} open, {total_count - open_count} resolved of {total_count} total",
                "Critical findings": str(sum(
                    1 for f in state.open_findings() if f.get("severity") == "critical"
                )),
            },
            suggested_next="test",
        )

        from scripts.shared.structural_probes import resolve_probe_summary_for_state

        probe_brief = resolve_probe_summary_for_state(
            state.custom,
            _code_review_state_dir(sp, scan_root),
            style="brief",
        )
        dashboard = render_dashboard(state)
        body += f"\n\n---\n\n{probe_brief}\n\n---\n\n{dashboard}"
        body += f"\n\nHandoff written to: {handoff_path}"
        handoff_menu = build_skill_handoff_menu(SKILL_NAME, state, sp)
        clear_state_file(sp)
        probe_status = _probe_status_one_liner(probe_brief)
        run_summary = (
            "Completed code-review workflow, wrote handoff, and closed session state. "
            f"Structural probes: {probe_status}"
        )

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
    next_cmd = None
    if step < MAX_STEP:
        effort = str(state.custom.get("effort") or "standard")
        # Light effort: after team dispatch (3), skip deep-dive + discussion → report
        if step == 3 and effort == "light" and not probe_gate_pending:
            next_cmd = build_next_command(
                SCRIPT_DIR / "code_review.py",
                step,
                MAX_STEP,
                next_step=6,
                state=str(sp),
            )
        else:
            next_cmd = _next_command(step, state_path=str(sp))
    output = format_step_output(
        SKILL_NAME, step, MAX_STEP, phase_name, body,
        next_cmd=next_cmd,
        phase_todos=PHASE_TODOS.get(step, []),
        handoff_menu=handoff_menu,
        all_phase_names=PHASE_NAMES,
        all_phase_todos=PHASE_TODOS,
        require_confirmation=True if probe_gate_pending else None,
        await_same_step=probe_gate_pending,
    )
    # Flush before large step bodies so terminals show output immediately.
    print(output, flush=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = build_base_parser(SKILL_NAME, MAX_STEP)
    parser.add_argument(
        "--mode", type=str, choices=["pr", "deep", "architecture"],
        default=None,
        help="Review focus: pr (diff), deep (troubleshooting), architecture (design patterns)",
    )
    parser.add_argument(
        "--effort",
        type=str,
        choices=["light", "standard", "thorough"],
        default=None,
        help=(
            "Review effort (replaces --quick). light=Architect+QA; "
            "standard=Architect+QA(+Security if auth/data); thorough=full six. "
            "Structural probes are always on unless --no-structural."
        ),
    )
    struct = parser.add_mutually_exclusive_group()
    struct.add_argument(
        "--structural",
        dest="structural",
        action="store_true",
        default=None,
        help="Force structural probes on (default already on; use to override --no-structural in scripts)",
    )
    struct.add_argument(
        "--no-structural",
        dest="structural",
        action="store_false",
        help="Skip structural probes and eight-agents (opt-out; structural is on by default)",
    )
    parser.add_argument(
        "--target", nargs="+", default=None,
        help="PR number, branch name, or file paths to review"
    )
    parser.add_argument(
        "--plan", type=str, default=None,
        help="Optional plan file path or keywords (searches repo + native .cursor/.claude/.codex plans)",
    )
    parser.add_argument(
        "--allow-structural-probes-incomplete",
        action="store_true",
        help="Bypass structural probes gate on steps 4+ (requires override reason and follow-up)",
    )
    parser.add_argument("--structural-probes-override-reason", type=str, default="")
    parser.add_argument("--structural-probes-override-follow-up", type=str, default="")
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
            allow_structural_probes_incomplete=getattr(
                args, "allow_structural_probes_incomplete", False
            ),
            structural_probes_override_reason=getattr(
                args, "structural_probes_override_reason", ""
            ),
            structural_probes_override_follow_up=getattr(
                args, "structural_probes_override_follow_up", ""
            ),
        )


if __name__ == "__main__":
    main()
