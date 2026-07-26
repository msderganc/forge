"""Shared orchestrator base for all Forge skill scripts.

Provides common patterns for state management, step progression,
review loop enforcement, agent dispatch tracking, beads state,
session resume, and handoff file generation.

Skill orchestrators use :class:`SkillState` and shared helpers in this module.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.shared import handoff_io as _handoff_io
from scripts.shared import runtime_layout as _runtime_layout
from scripts.shared import session_hygiene as _session_hygiene
from scripts.shared import state_lifecycle as _state_lifecycle
from scripts.shared.pipeline import (
    PIPELINE_FLOW,
    PIPELINE_SKILL_INDEX,
    PIPELINE_SKILL_ORDER,
    next_pipeline_skill,
)
from scripts.shared.skill_state import AgentDispatch, ReviewLoopState, SkillState
from scripts.shared.workflow_tokens import (
    chain_command_to_agent_invocation,
    skill_token_from_script,
)

# ---------------------------------------------------------------------------
# Re-exports — keep ``from scripts.shared.orchestrator import …`` stable
# ---------------------------------------------------------------------------

_detect_repo_root = _runtime_layout.detect_repo_root
REPO_ROOT = _runtime_layout.REPO_ROOT
CANONICAL_RUNTIME_PARTS = _runtime_layout.CANONICAL_RUNTIME_PARTS
LEGACY_FORGE_CODEX_RUNTIME_PARTS = _runtime_layout.LEGACY_FORGE_CODEX_RUNTIME_PARTS
LEGACY_RUNTIME_DIRNAME = _runtime_layout.LEGACY_RUNTIME_DIRNAME
EVALUATE_STATE_FILENAME = _runtime_layout.EVALUATE_STATE_FILENAME
RUN_HISTORY_MAX_ENTRIES = _runtime_layout.RUN_HISTORY_MAX_ENTRIES
_blocked_runtime_anchor = _runtime_layout.blocked_runtime_anchor
runtime_root = _runtime_layout.runtime_root
legacy_runtime_root = _runtime_layout.legacy_runtime_root
runtime_memory_dir = _runtime_layout.runtime_memory_dir
runtime_memory_dir_relative = _runtime_layout.runtime_memory_dir_relative
runtime_dir_relative = _runtime_layout.runtime_dir_relative
template_runtime_variables = _runtime_layout.template_runtime_variables
legacy_memory_dir = _runtime_layout.legacy_memory_dir
runtime_state_dir = _runtime_layout.runtime_state_dir
legacy_state_dir = _runtime_layout.legacy_state_dir
runtime_adr_dir = _runtime_layout.runtime_adr_dir
runtime_backlog_path = _runtime_layout.runtime_backlog_path
ensure_runtime_dirs = _runtime_layout.ensure_runtime_dirs
state_filename = _runtime_layout.state_filename
legacy_state_filename = _runtime_layout.legacy_state_filename
runtime_state_path = _runtime_layout.runtime_state_path
_is_skill_state_filename = _runtime_layout.is_skill_state_filename
_state_path_candidates = _runtime_layout.state_path_candidates
save_state = _runtime_layout.save_state
load_state = _runtime_layout.load_state
clear_state_file = _runtime_layout.clear_state_file
find_state_file = _runtime_layout.find_state_file

KNOWN_SKILLS = _session_hygiene.KNOWN_SKILLS
PIPELINE_SKILLS = _session_hygiene.PIPELINE_SKILLS
detect_active_sessions = _session_hygiene.detect_active_sessions
skip_forge_auto_close = _session_hygiene.skip_forge_auto_close
step1_abandon_threshold_seconds = _session_hygiene.step1_abandon_threshold_seconds
has_matching_handoff = _session_hygiene.has_matching_handoff
is_step1_abandoned = _session_hygiene.is_step1_abandoned
auto_close_superseded_sessions = _session_hygiene.auto_close_superseded_sessions
print_auto_closed_audit = _session_hygiene.print_auto_closed_audit
resume_invocation_hint = _session_hygiene.resume_invocation_hint
takeover_invocation_hint = _session_hygiene.takeover_invocation_hint
hint_cleanup_if_still_active = _session_hygiene.hint_cleanup_if_still_active
run_step1_session_hygiene = _session_hygiene.run_step1_session_hygiene
collect_session_leak_hints = _session_hygiene.collect_session_leak_hints
collect_unreadable_state_files = _session_hygiene.collect_unreadable_state_files
print_remaining_session_warning = _session_hygiene.print_remaining_session_warning
get_conflicting_sessions = _session_hygiene.get_conflicting_sessions
format_active_session_warning = _session_hygiene.format_active_session_warning
next_skill_command = _session_hygiene.next_skill_command
_iter_skill_state_paths = _session_hygiene._iter_skill_state_paths

_handoff_paths = _handoff_io.handoff_paths
read_handoff = _handoff_io.read_handoff
close_handoff = _handoff_io.close_handoff
consume_handoff = _handoff_io.consume_handoff
write_handoff = _handoff_io.write_handoff
skill_run_memory_path = _handoff_io.skill_run_memory_path
append_skill_run_memory = _handoff_io.append_skill_run_memory
build_skill_handoff_menu = _handoff_io.build_skill_handoff_menu

is_state_effectively_complete = _state_lifecycle.is_state_effectively_complete
stale_session_threshold_seconds = _state_lifecycle.stale_session_threshold_seconds
_parse_iso_timestamp = _state_lifecycle.parse_iso_timestamp
is_state_stale = _state_lifecycle.is_state_stale
is_evaluate_state_stale = _state_lifecycle.is_evaluate_state_stale
now_iso = _state_lifecycle.now_iso

# Ensure Unicode prompt output works on Windows terminals when running scripts
# directly (not via the `forge` launcher).
os.environ.setdefault("PYTHONUTF8", "1")
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


def skip_forge_session_opt_in() -> bool:
    """Return True when step-1 session opt-in banner should be suppressed."""
    v = os.environ.get("FORGE_SKIP_SESSION_OPTIN", "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _spawn_graphify_refresh_if_needed(repo_root: Path) -> None:
    """Kick off a debounced background refresh when a graph index exists (never blocks)."""
    try:
        from forge_next.graphify import spawn_refresh_background
        from scripts.shared.graphify_contract import graph_index_present

        if graph_index_present(repo_root):
            spawn_refresh_background(repo_root)
    except Exception:
        pass


def forge_graphify_context_block(skill_name: str, step: int) -> str:
    """Graphify banner (ship skill only). Also spawns background refresh when index exists."""
    repo_root = _detect_repo_root()
    _spawn_graphify_refresh_if_needed(repo_root)
    from scripts.shared.graphify_contract import forge_graphify_banner

    return forge_graphify_banner(skill_name, step, repo_root)


def forge_session_opt_in_banner(skill_name: str, step: int) -> str:
    """Prompt agents to offer structured Forge workflows vs ad-hoc help (step 1 only).

    Shown at the start of any skill when ``step == 1``, unless
    ``FORGE_SKIP_SESSION_OPTIN`` is set (automation / CI).
    """
    if step != 1 or skip_forge_session_opt_in() or skill_name.strip().lower() == "ship":
        return ""
    bar = ("=" * 60) if os.environ.get("FORGE_ASCII") == "1" else ("━" * 60)
    slug = skill_name.strip().lower()
    return (
        f"{bar}\n"
        "SESSION OPT-IN — Forge structured workflows\n"
        f"{bar}\n\n"
        "**Before creating phase todos or driving the workflow,** ask once "
        "(unless they already answered in this chat).\n\n"
        f"You are starting **`{slug}`** (step 1) — a guided multi-step Forge skill.\n\n"
        "Ask in plain English, for example:\n\n"
        "**Do you want the full Forge workflow for this, or just informal help?**\n\n"
        "- **Full Forge** — follow each step, run suggested `/forge:…` / `$forge:…` / "
        "`forge …` lines, and honor handoffs.\n"
        "- **Informal help** — answer in chat only; do not drive the full workflow or "
        "touch Forge state unless they ask.\n\n"
        "If they already opted in earlier in this conversation, skip repeating the "
        "question; add a line under `## Forge session` in `project.md`: "
        "`forge_skills: opted_in` (optional short note).\n\n"
        "_To hide this block (e.g. CI): set `FORGE_SKIP_SESSION_OPTIN=1`._\n\n"
    )


def validate_state_path(state_file: str, skill_name: str) -> Path | None:
    """Validate and resolve a --state CLI argument.

    Returns the resolved Path if valid, or None if the argument should be
    ignored (doesn't exist, outside project).
    """
    from scripts.shared.repo_paths import equivalent_path_in_repo, same_git_repo

    repo_root = _detect_repo_root().resolve()
    sp = equivalent_path_in_repo(Path(state_file), repo_root)

    try:
        sp.relative_to(repo_root)
    except ValueError:
        if not same_git_repo(sp, repo_root):
            print(
                f"WARNING: --state path is outside the repository, ignoring: {state_file}",
                file=sys.stderr,
            )
            return None
        sp = equivalent_path_in_repo(sp, repo_root)

    # Accept legacy skill json names and session.json under sessions/{id}/
    from scripts.shared.session_store import is_session_state_path

    looks_like_state = _is_skill_state_filename(sp.name, skill_name) or (
        is_session_state_path(sp) and sp.is_file()
    )
    if not looks_like_state:
        print(f"WARNING: --state path doesn't look like a state file, ignoring: {state_file}",
              file=sys.stderr)
        return None

    if not sp.exists():
        return None

    return sp


def resolve_step1_state_path(
    skill_name: str,
    state_file: str | None = None,
    *,
    parallel: bool = False,
    search_dir: Path | None = None,
    label: str | None = None,
    session_id: str | None = None,
) -> Path:
    """Resolve where a step-1 invocation should write state.

    Step 1 **always creates a new session directory** unless ``--state`` or
    ``--session`` points at an existing file (legacy resume paths only).
    """
    from scripts.shared.session_store import (
        create_session,
        migrate_legacy_state_files,
        run_session_cleanup,
        session_json_path,
    )

    from scripts.shared.runtime_adaptation import adapt_runtime, writable_repo_root

    repo_root = writable_repo_root(search_dir)
    adapt_runtime(repo_root)

    run_session_cleanup(search_dir=repo_root)
    migrate_legacy_state_files(repo_root)

    if session_id:
        path = session_json_path(session_id, repo_root)
        if not path.is_file():
            sys.exit(f"ERROR: session not found: {session_id}")
        return path

    if state_file:
        from scripts.shared.repo_paths import equivalent_path_in_repo, same_git_repo

        sp = equivalent_path_in_repo(Path(state_file), repo_root)
        try:
            sp.relative_to(repo_root)
        except ValueError:
            if not same_git_repo(sp, repo_root):
                sys.exit(f"ERROR: --state path is outside the repository: {state_file}")
            sp = equivalent_path_in_repo(sp, repo_root)
        from scripts.shared.session_store import is_session_state_path

        if not _is_skill_state_filename(sp.name, skill_name) and not is_session_state_path(sp):
            sys.exit(
                f"ERROR: --state must be session.json or `{skill_name}.json` "
                f"(got `{sp.name}`)"
            )
        if sp.is_file():
            return sp
        # Explicit legacy path: create/write at the given location (parallel tests).
        if _is_skill_state_filename(sp.name, skill_name):
            sp.parent.mkdir(parents=True, exist_ok=True)
            return sp
        sys.exit(f"ERROR: state file not found: {state_file}")

    # Always allocate a new parallel session (--parallel is a no-op alias).
    _ = parallel
    sid, path = create_session(skill_name, label=label, search_dir=repo_root)
    return path


def resolve_state_path(
    skill_name: str,
    step: int,
    state_file: str | None = None,
    *,
    session_id: str | None = None,
    search_dir: Path | None = None,
) -> Path:
    """Resolve state path for any step (step 1 uses ``resolve_step1_state_path``)."""
    from scripts.shared.session_store import resolve_session_for_step

    if step == 1:
        return resolve_step1_state_path(skill_name, state_file, search_dir=search_dir)
    return resolve_session_for_step(
        skill_name,
        step,
        session_id=session_id,
        state_file=state_file,
        search_dir=search_dir,
    )


def _next_parallel_state_path(skill_name: str, repo_root: Path) -> Path:
    """Legacy parallel path helper (deprecated — use session directories)."""
    state_dir = runtime_state_dir(repo_root)
    state_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    candidate = state_dir / f"{skill_name}-{stamp}.json"
    idx = 2
    while candidate.exists():
        candidate = state_dir / f"{skill_name}-{stamp}-{idx}.json"
        idx += 1
    return candidate


def auto_parallel_on_conflict_enabled() -> bool:
    """Whether step-1 should auto-allocate parallel state on same-skill conflicts."""
    v = os.environ.get("FORGE_AUTO_PARALLEL_ON_CONFLICT", "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def resolve_skill_state_path(
    skill_name: str,
    step: int,
    args: Any,
) -> Path:
    """Resolve state path from CLI args (session-first, legacy fallback)."""
    state_file = getattr(args, "state", None)
    session_id = getattr(args, "session", None)
    label = getattr(args, "label", None)
    parallel = getattr(args, "parallel", False)
    if step == 1:
        return resolve_step1_state_path(
            skill_name,
            state_file,
            parallel=parallel,
            label=label,
            session_id=session_id,
        )
    sp = validate_state_path(state_file, skill_name) if state_file else None
    if sp is not None:
        return sp
    from scripts.shared.session_store import resolve_session_for_step

    return resolve_session_for_step(
        skill_name,
        step,
        session_id=session_id,
        state_file=None,
    )


def resolve_step_state_path(
    skill_name: str,
    step: int,
    *,
    state_file: str | None = None,
    session_id: str | None = None,
) -> Path:
    """Resolve session/state path for steps 2+ using CLI ``--state`` / ``--session``."""

    class _StepArgs:
        pass

    args = _StepArgs()
    args.state = state_file
    args.session = session_id
    args.label = None
    args.parallel = False
    return resolve_skill_state_path(skill_name, step, args)


def read_memory_file(name: str) -> str:
    """Read a file from the runtime memory directory if it exists.

    Args:
        name: The filename (e.g. "project.md").

    Returns:
        File content as string, or empty string if not found.
    """
    for path in (
        runtime_memory_dir() / name,
        legacy_memory_dir() / name,
    ):
        if path.exists():
            return path.read_text(encoding="utf-8")
    return ""


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def format_phase_todos(phase_todos: list[dict]) -> str:
    """Render a Codex plan-tracking block for the current phase.

    Uses json.dumps() for proper escaping of quotes, backslashes, newlines,
    and other special characters in todo content.
    """
    if not phase_todos:
        return ""

    # Build a list of safe todo dicts (only the three expected keys)
    safe_todos = [
        {
            "content": todo.get("content", ""),
            "activeForm": todo.get("activeForm", ""),
            "status": todo.get("status", "pending"),
        }
        for todo in phase_todos
    ]

    # json.dumps handles all escaping correctly
    todos_json = json.dumps(safe_todos, indent=2)

    return "\n".join([
        "## Create Phase Todos",
        "",
        "**IMMEDIATELY mirror these todos in Codex progress tracking before any other work.**",
        "Prefer `update_plan` by translating each item into a plan step with the same status.",
        "When work changes, keep the plan updated and add new steps for important sub-tasks.",
        "",
        "```json",
        todos_json,
        "```",
        "",
    ])


def build_skill_todos(
    phase_names: dict[int, str],
    phase_todos: dict[int, list[dict]],
    current_step: int,
    last_completed_step: int = 0,
) -> list[dict]:
    """Build a complete skill-level todo list covering all phases.

    Completed phases are marked 'completed', the current phase is
    'in_progress', and future phases are 'pending'.  Sub-tasks for the
    current phase are appended as 'pending' items.
    """
    todos: list[dict] = []
    for step_num in sorted(phase_names.keys()):
        name = phase_names[step_num]
        if step_num <= last_completed_step:
            status = "completed"
        elif step_num == current_step:
            status = "in_progress"
        else:
            status = "pending"

        todos.append({
            "content": name,
            "activeForm": f"Running {name}",
            "status": status,
        })

        # Add sub-tasks for the current phase only
        if step_num == current_step:
            for sub_todo in phase_todos.get(step_num, []):
                todos.append({
                    "content": f"  {sub_todo['content']}",
                    "activeForm": sub_todo["activeForm"],
                    "status": "pending",
                })

    return todos


def parse_continuation_command(cmd: str) -> tuple[int | None, str | None]:
    """Extract step (from ``--step`` or ``--phase``) and ``--state`` from a continuation line."""
    from scripts.shared.continuation_parser import parse_continuation_command as _parse

    return _parse(cmd)


def format_same_skill_continuation(
    next_step: int,
    state_path: str | None = None,
    *,
    require_confirmation: bool = False,
    phase_label: str | None = None,
    await_same_step: bool = False,
) -> str:
    """Render same-skill continuation guidance.

    By default, deterministic next steps should auto-continue and avoid a
    confirmation prompt. Ask for confirmation only when the continuation target
    could not be parsed unambiguously, a gate is pending, or the step is
    re-entrant (``await_same_step``).
    """
    target = phase_label or f"step {next_step}"
    bar = ("-" * 60) if os.environ.get("FORGE_ASCII") == "1" else ("━" * 60)
    if await_same_step:
        lines = [
            f"\n\n{bar}",
            "CONTINUATION",
            bar,
            "",
            f"**Re-run this step** ({target}) after completing the work / gate above.",
            "",
            "Do **not** advance to a later phase until this step's requirements pass.",
        ]
    elif require_confirmation:
        lines = [
            f"\n\n{bar}",
            "CONTINUATION",
            bar,
            "",
            f"This phase is complete. **Should I continue into {target}?**",
            "",
            "Reply yes to move on, or say no / pause if you want to stop here.",
        ]
    else:
        lines = [
            f"\n\n{bar}",
            "CONTINUATION",
            bar,
            "",
            f"Next step is clear: continue directly to **{target}**.",
            "",
            "Only pause if the user asked to stop or change direction.",
        ]
    if state_path:
        lines.extend(["", f"Resume context is saved at `{state_path}`."])
        # Prefer an explicit --session hint when the path is a session.json
        try:
            from scripts.shared.session_store import (
                is_session_state_path,
                session_id_from_state_path,
            )

            p = Path(state_path)
            if is_session_state_path(p):
                sid = session_id_from_state_path(p)
                if sid:
                    lines.append(
                        f"Continue with `--session {sid}` (required when multiple "
                        f"sessions are active)."
                    )
        except Exception:
            pass
    return "\n".join(lines)


def format_workflow_transition(cross_skill_next: str) -> str:
    """Render a short cross-skill transition prompt.

    `cross_skill_next` is a skill name like "plan". Suggested invocation uses
    ``$forge:<skill>`` for IDE/agent routing.
    """
    bar = ("=" * 60) if os.environ.get("FORGE_ASCII") == "1" else ("═" * 60)
    slug = cross_skill_next.strip().replace("_", "-")
    suggestion = f"$forge:{slug}"
    return (
        f"\n\n{bar}\n"
        f"WORKFLOW TRANSITION\n"
        f"{bar}\n"
        f"This skill is finished. **Suggested next:** `{suggestion}` (starts at step 1).\n"
        f"\n"
        f"Pause here unless the user asks to continue — confirm before switching skills.\n"
    )


def format_step_output(
    skill_name: str,
    step: int,
    max_step: int,
    phase_name: str,
    body: str,
    next_cmd: str | None = None,
    phase_todos: list[dict] | None = None,
    cross_skill_next: str | None = None,
    all_phase_names: dict[int, str] | None = None,
    all_phase_todos: dict[int, list[dict]] | None = None,
    handoff_menu: str | None = None,
    *,
    require_confirmation: bool | None = None,
    await_same_step: bool = False,
    title: str | None = None,
) -> str:
    """Format step output with title, todos, body, and continuation directive.

    Args:
        skill_name: Name of the skill (e.g. "develop").
        step: Current step number.
        max_step: Maximum step number for this skill.
        phase_name: Human-readable phase name.
        body: The rendered prompt body.
        next_cmd: Command to run for the next step (None if final step).
        phase_todos: Optional list of todo dicts for current phase only (legacy).
        cross_skill_next: Optional next-skill command when at skill boundary.
        all_phase_names: Full dict of {step: phase_name} for the skill.
            When provided, a skill-level todo list is generated showing
            all phases with their completion status.
        all_phase_todos: Full dict of {step: [todo_dicts]} for the skill.
            Used alongside all_phase_names for sub-task detail.
        handoff_menu: Optional numbered handoff menu for final-step transitions.
        require_confirmation: When set, overrides auto-continue for same-skill
            continuation (e.g. workflow gates that must wait for user approval).
        await_same_step: When True, footer tells the agent to re-run this step
            (gate pending / re-entrant dialogue) instead of auto-advancing.
        title: Optional full title override (default: SKILL — Phase (Step N of M)).
    """
    if title is None:
        title = f"{skill_name.upper()} — {phase_name} (Step {step} of {max_step})"
    header = f"{title}\n{'=' * len(title)}\n\n"
    opt_in_section = forge_session_opt_in_banner(skill_name, step)
    graphify_section = forge_graphify_context_block(skill_name, step)

    # Step 1 may insert a session opt-in block, then phase todos (for Codex plan
    # mirroring), then body.
    if all_phase_names:
        # If caller provided a per-step phase_todos override (e.g. implement's
        # wave-scoped todos), use it for the current step's sub-tasks instead
        # of the generic all_phase_todos entry.
        effective_phase_todos = dict(all_phase_todos or {})
        if phase_todos is not None:
            effective_phase_todos[step] = phase_todos
        skill_todos = build_skill_todos(
            all_phase_names,
            effective_phase_todos,
            current_step=step,
            last_completed_step=step - 1,
        )
        todos_section = format_phase_todos(skill_todos)
    elif phase_todos:
        todos_section = format_phase_todos(phase_todos)
    else:
        todos_section = ""
    output = header + opt_in_section + graphify_section + todos_section + body

    if handoff_menu:
        output += "\n\n" + handoff_menu
    elif next_cmd:
        ns, sp_ = parse_continuation_command(next_cmd)
        parsed_ok = ns is not None
        if ns is None:
            ns = step + 1
        same = bool(await_same_step or (parsed_ok and ns == step))
        if same:
            confirm = True
        elif require_confirmation is not None:
            confirm = require_confirmation
        else:
            confirm = not parsed_ok
        phase_label: str | None = None
        try:
            parts = shlex.split(next_cmd)
        except ValueError:
            parts = []
        for i, token in enumerate(parts):
            if token == "--phase" and i + 1 < len(parts):
                phase_label = f"phase `{parts[i + 1]}`"
                break
        if phase_label is None and ns is not None:
            from scripts.shared.skill_phases import phase_for_step

            try:
                phase_label = f"phase `{phase_for_step(skill_name, ns)}`"
            except Exception:
                phase_label = None
        output += format_same_skill_continuation(
            ns,
            sp_,
            require_confirmation=confirm,
            phase_label=phase_label,
            await_same_step=same,
        )
    elif cross_skill_next:
        output += "\n\nWORKFLOW COMPLETE — this skill has finished."
        output += format_workflow_transition(cross_skill_next)
    else:
        output += "\n\nWORKFLOW COMPLETE — return results to the user."

    return output


def build_next_command(
    script_path: Path,
    step: int,
    max_step: int,
    *,
    next_step: int | None = None,
    flags: tuple[str, ...] = (),
    phase_variant: str | None = None,
    **extra_args: str,
) -> str:
    """Build a compact continuation token line (``$forge:<skill> --phase …``).

    Shown to tooling parsers; same-step prompts use plain language via
    ``format_same_skill_continuation`` instead of echoing this string to users.
    """
    if step >= max_step and next_step is None:
        return ""
    target_step = next_step if next_step is not None else step + 1
    if target_step > max_step:
        return ""
    if target_step < 1:
        return ""
    from scripts.shared.skill_phases import agent_skill_token, phase_for_step
    from scripts.shared.workflow_tokens import workflow_invocation_prefix

    script_token = skill_token_from_script(script_path)
    skill = agent_skill_token(script_token)
    phase = phase_for_step(skill, target_step, variant=phase_variant)
    parts: list[str] = [
        f"{workflow_invocation_prefix()}{skill}",
        f"--phase {phase}",
    ]
    for flag in flags:
        parts.append(f"--{flag}")
    for key, val in extra_args.items():
        if key == "state":
            from scripts.shared.session_store import session_id_from_state_path

            sid = session_id_from_state_path(Path(val))
            if sid:
                parts.append(f"--session {shlex.quote(sid)}")
                continue
        parts.append(f"--{key} {shlex.quote(val)}")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Handoff file generation
# ---------------------------------------------------------------------------

def render_dashboard(state: SkillState) -> str:
    """Render a skill completion dashboard."""
    open_count = len(state.open_findings())
    resolved_count = len(state.findings) - open_count
    agents = set()
    for d in state.dispatches:
        name = d.agent if isinstance(d, AgentDispatch) else d.get("agent", "unknown")
        agents.add(name)

    lines = [
        "## forge — Skill Summary",
        f"**Skill:** {state.skill_name}",
        f"**Status:** {'COMPLETE' if state.completed_at else 'IN_PROGRESS'}",
        f"**Started:** {state.started_at or 'N/A'}",
        f"**Completed:** {state.completed_at or 'N/A'}",
        f"**Agents dispatched:** {', '.join(sorted(agents)) or 'none'}",
        f"**Findings:** {open_count} open, {resolved_count} resolved",
        f"**Beads:** {state.epic_id or 'N/A'}",
        f"**Quick mode:** {state.quick_mode}",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI helpers
# ---------------------------------------------------------------------------

def build_base_parser(skill_name: str, max_step: int) -> argparse.ArgumentParser:
    """Build the base argument parser for a skill orchestrator."""
    from scripts.shared.skill_phases import format_phase_list

    parser = argparse.ArgumentParser(
        description=f"forge {skill_name} skill orchestrator"
    )
    phase_help = format_phase_list(skill_name)
    step_group = parser.add_mutually_exclusive_group(required=False)
    step_group.add_argument(
        "--step", type=int, default=None,
        help=f"Phase number (1-{max_step}); optional when --session or --state resumes a session",
    )
    step_group.add_argument(
        "--phase", type=str, default=None, metavar="NAME",
        help=f"Named phase ({phase_help}); optional when resuming with --session or --state",
    )
    parser.add_argument(
        "--state", type=str, default=None,
        help="Path to session.json or legacy state file (resume)"
    )
    parser.add_argument(
        "--session", type=str, default=None,
        help="Session id to continue (from forge status / forge takeover)",
    )
    parser.add_argument(
        "--label", type=str, default=None,
        help="Human-readable label for a new session (step 1 only)",
    )
    parser.add_argument(
        "--parallel", action="store_true",
        help="Deprecated: step 1 always creates a new session (same as default)",
    )
    parser.add_argument(
        "--quick", action="store_true",
        help="Quick mode: minimal review loops, lead agents only"
    )
    return parser


def apply_resolved_workflow_step(
    args: Any,
    skill_name: str,
    max_step: int,
    *,
    variant: str | None = None,
) -> int:
    """Resolve ``--step`` / ``--phase`` / session inference and set ``args.step``."""
    from scripts.shared.skill_phases import resolve_workflow_step

    resolved = resolve_workflow_step(
        skill_name=skill_name,
        max_step=max_step,
        step=getattr(args, "step", None),
        phase=getattr(args, "phase", None),
        state_file=getattr(args, "state", None),
        session_id=getattr(args, "session", None),
        variant=variant,
    )
    args.step = resolved
    return resolved


def validate_step(step: int, max_step: int) -> None:
    """Validate step number is in range."""
    if step < 1 or step > max_step:
        sys.exit(f"ERROR: --step must be 1-{max_step}")


def check_same_skill_clobber(
    skill_name: str,
    *,
    allow_parallel: bool = False,
    target_state_path: Path | None = None,
) -> None:
    """No-op: step 1 always creates a new session directory (parallel-first)."""
    _ = (skill_name, allow_parallel, target_state_path)
    return


def validate_step_or_complete(step: int, max_step: int, skill_name: str) -> bool:
    """Soft step validator: tolerates over-cap steps as 'already complete'.

    Returns True when the requested step is past the skill's final step —
    caller should print a friendly 'workflow complete' message and exit 0
    without mutating state. Returns False for in-range steps. Hard-errors
    (sys.exit) for negative or zero steps.

    Use this at skill entry points where the LLM may overshoot after the
    final step; keep `validate_step` for code paths that depend on its
    sys.exit contract (e.g. existing tests).
    """
    if step < 1:
        sys.exit(f"ERROR: --step must be >= 1 (got {step})")
    if step > max_step:
        print(
            f"`{skill_name}` ends at step {max_step}; nothing left to do.\n"
            f"Run `{resume_invocation_hint()}` to continue the next pipeline skill, "
            f"or start a new workflow.",
            file=sys.stderr,
        )
        return True
    return False

