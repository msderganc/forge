#!/usr/bin/env python3
"""Legacy sketch orchestrator body (pre declarative skill engine).

Used when ``FORGE_SKILL_ENGINE=0``. Prefer ``scripts.sketch.sketch`` shim →
``run_skill`` when the engine is enabled.
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
    run_step1_session_hygiene,
    runtime_memory_dir,
    runtime_state_path,
    save_state,
    validate_state_path,
    validate_step_or_complete,
    write_handoff,
)
from scripts.sketch.sketch_vars import (
    build_handoff_context,
    build_variables as _build_variables,
)

SKILL_NAME = "sketch"
MAX_STEP = 3

PHASE_NAMES = {
    1: "Startup",
    2: "Sketch session",
    3: "Handoff",
}

PHASE_TODOS = {
    1: [
        {"content": "Confirm topic, destination, and domain-docs mode",
         "activeForm": "Confirming sketch setup"},
        {"content": "Initialize sketch-decisions.md (destination, fog, out-of-scope sections)",
         "activeForm": "Initializing sketch session"},
    ],
    2: [
        {"content": "Run conversation loop (reflect, confirm, ask)",
         "activeForm": "Running sketch dialogue"},
        {"content": "Synthesis checkpoint: destination + locked vs fog vs out-of-scope",
         "activeForm": "Synthesizing with user"},
        {"content": "Update sketch-decisions.md (name section on loop-back)",
         "activeForm": "Recording decisions"},
    ],
    3: [
        {"content": "Write handoff-sketch.md for design",
         "activeForm": "Writing sketch handoff"},
        {"content": "Present handoff menu (default design)",
         "activeForm": "Completing sketch handoff"},
    ],
}


def _memory_dir(repo_root: Path | None = None) -> Path:
    return runtime_memory_dir(repo_root)


def _ensure_sketch_custom(state: SkillState) -> None:
    defaults: dict[str, str | bool] = {
        "topic": "",
        "with_domain_docs": False,
    }
    for k, v in defaults.items():
        state.custom.setdefault(k, v)


def _state_path() -> Path:
    return runtime_state_path(SKILL_NAME)


def _next_command(
    step: int,
    state_path: str = "",
    *,
    with_domain_docs: bool = False,
    next_step: int | None = None,
) -> str:
    extra: dict[str, str] = {}
    if state_path:
        extra["state"] = state_path
    flags = ("with-domain-docs",) if with_domain_docs else ()
    return build_next_command(
        SCRIPT_DIR / "sketch.py",
        step,
        MAX_STEP,
        next_step=next_step,
        flags=flags,
        **extra,
    )


def _format(
    step: int,
    body: str,
    next_cmd: str | None = None,
    handoff_menu: str | None = None,
    *,
    require_confirmation: bool | None = None,
    await_same_step: bool = False,
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
        require_confirmation=require_confirmation,
        await_same_step=await_same_step,
    )


def _repo_root() -> Path:
    from scripts.shared.orchestrator import _detect_repo_root

    return _detect_repo_root(Path.cwd())


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
            loaded = load_state(existing)
            state = loaded
            sp = existing
        except Exception:
            state = None

    if state is None:
        state = SkillState(skill_name=SKILL_NAME, max_step=MAX_STEP)
        state.started_at = now_iso()

    _ensure_sketch_custom(state)
    state.custom["with_domain_docs"] = bool(getattr(args, "with_domain_docs", False))
    save_state(state, sp)
    print_remaining_session_warning(SKILL_NAME)
    print(f"STATE FILE: {sp}\n", file=sys.stderr)

    repo_root = _repo_root()
    mem = _memory_dir(repo_root)
    mem.mkdir(parents=True, exist_ok=True)

    template = load_template("sketch/startup")
    body = render_template(
        template,
        _build_variables(state, repo_root),
        search_dir=repo_root,
    )

    state.mark_step_complete(1)
    save_state(state, sp)
    append_skill_run_memory(
        SKILL_NAME,
        1,
        PHASE_NAMES[1],
        "Initialized sketch session.",
        state=state,
        state_path=sp,
    )

    print(
        _format(
            1,
            body,
            _next_command(
                1,
                state_path=str(sp),
                with_domain_docs=bool(state.custom.get("with_domain_docs")),
            ),
        )
    )


def _load_existing_state(
    step: int,
    state_file: str | None,
    session_id: str | None = None,
) -> tuple[SkillState, Path]:
    from scripts.shared.orchestrator import resolve_step_state_path

    sp = resolve_step_state_path(
        SKILL_NAME, step, state_file=state_file, session_id=session_id
    )
    if not sp.exists():
        print("ERROR: No sketch session in progress. Run step 1 first.")
        print("If the state file is elsewhere, pass --state <path>")
        sys.exit(1)
    try:
        state = load_state(sp)
    except (json.JSONDecodeError, KeyError, FileNotFoundError) as exc:
        print(f"ERROR: Cannot load state at {sp}: {exc}")
        sys.exit(1)
    return state, sp


def handle_step_n(
    step: int,
    state_file: str | None = None,
    session_id: str | None = None,
) -> None:
    state, sp = _load_existing_state(step, state_file, session_id=session_id)
    _ensure_sketch_custom(state)
    save_state(state, sp)

    template_map = {
        2: "sketch/session",
        3: "sketch/handoff",
    }
    template_name = template_map.get(step)
    if not template_name:
        print(f"ERROR: Invalid step {step}")
        sys.exit(1)

    repo_root = _repo_root()
    template = load_template(template_name)
    body = render_template(
        template,
        _build_variables(state, repo_root),
        search_dir=repo_root,
    )

    handoff_menu = None
    handoff_path: Path | None = None
    run_summary = f"Completed step {step} ({PHASE_NAMES.get(step, '')})."

    if step == MAX_STEP:
        state.mark_step_complete(step)
        state.completed_at = now_iso()
        save_state(state, sp)

        handoff_path = write_handoff(
            skill_name=SKILL_NAME,
            state=state,
            context=build_handoff_context(state, repo_root),
            suggested_next="design",
        )
        body += f"\n\nHandoff written to: {handoff_path}"
        handoff_menu = build_skill_handoff_menu(SKILL_NAME, state, sp)
        clear_state_file(sp)
        run_summary = "Completed sketch workflow and wrote handoff."
    elif step == 2:
        # Re-entrant: do not mark step 2 complete — user re-runs until ready for handoff
        state.custom["session_visits"] = int(state.custom.get("session_visits") or 0) + 1
        save_state(state, sp)
        body += (
            "\n\n---\n\n**Continue:** Re-run `forge sketch --step 2` to keep talking.\n"
            "**Handoff:** When the user confirms synthesis, run `forge sketch --step 3`."
        )
    else:
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

    next_cmd = None
    await_same = False
    require_confirm = None
    if step == 2:
        next_cmd = _next_command(
            2,
            state_path=str(sp),
            with_domain_docs=bool(state.custom.get("with_domain_docs")),
            next_step=2,
        )
        await_same = True
        require_confirm = True
    elif step < MAX_STEP:
        next_cmd = _next_command(
            step,
            state_path=str(sp),
            with_domain_docs=bool(state.custom.get("with_domain_docs")),
        )
    print(
        _format(
            step,
            body,
            next_cmd,
            handoff_menu=handoff_menu,
            require_confirmation=require_confirm,
            await_same_step=await_same,
        )
    )


def main() -> None:
    parser = build_base_parser(SKILL_NAME, MAX_STEP)
    parser.add_argument(
        "--with-domain-docs",
        action="store_true",
        help="Allow inline CONTEXT.md glossary and sparse docs/adr/ updates",
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
        )


if __name__ == "__main__":
    main()
