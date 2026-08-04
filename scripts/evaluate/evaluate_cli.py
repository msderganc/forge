"""Evaluate CLI pre_run helpers (no skill_runner import)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


def reject_review_mode(*, args: Any, manifest: Any = None, repo_root: Path | None = None) -> None:
    """Deprecate evaluate --mode review in favor of forge code-review."""
    del manifest, repo_root
    if getattr(args, "mode", None) == "review":
        print(
            "ERROR: evaluate --mode review is deprecated. Use `forge code-review --step 1` "
            "for full-team review.",
            file=sys.stderr,
        )
        raise SystemExit(1)


def bind_plan_state_path(*, args: Any, manifest: Any = None, repo_root: Path | None = None) -> None:
    """Bind ``--state`` to plan-adjacent ``.evaluate-state.json`` (step 1) or resume it (2+).

    Evaluate keeps legacy plan-adjacent state (not always under ``.forge/sessions/``).
    Step 1 requires ``--plan``. Later steps reuse ``--state``, ``--plan``'s sibling
    state file, or ``find_state_file()`` — matching ``evaluate_legacy`` / ``evaluate_steps``.
    """
    del manifest
    if getattr(args, "state", None):
        return

    step = int(getattr(args, "step", 1) or 1)
    plan_arg = getattr(args, "plan", None)
    cwd = Path(repo_root) if repo_root else Path.cwd()

    from scripts.evaluate.state import state_path_for_plan

    if step == 1:
        if not plan_arg:
            print("ERROR: --plan is required for step 1. Provide a file path or keywords.")
            raise SystemExit(1)

        from scripts.evaluate.plan_resolver import extract_title, resolve_plan

        try:
            result = resolve_plan(plan_arg, cwd, return_matches=True)
        except FileNotFoundError as e:
            print(f"ERROR: {e}")
            raise SystemExit(1) from e

        if isinstance(result, list) and len(result) > 1:
            print("Multiple plans found. Present these to the user and ask which one to evaluate:\n")
            for i, p in enumerate(result, 1):
                title = extract_title(p)
                print(f"  {i}. {p} — {title}")
            print(
                "\nThen ask which plan to use and continue with "
                "`$forge:evaluate --step 1 --plan '<chosen path>'`."
            )
            raise SystemExit(0)

        plan_path = result[0] if isinstance(result, list) else result
        args.plan = str(plan_path.resolve())
        if not getattr(args, "parallel", False):
            args.state = str(state_path_for_plan(str(plan_path)))
        return

    # Steps 2+: prefer plan-adjacent state, else newest active evaluate state file.
    if plan_arg:
        from scripts.evaluate.plan_resolver import resolve_plan

        try:
            result = resolve_plan(plan_arg, cwd, return_matches=False)
        except FileNotFoundError:
            result = None
        if result is not None:
            plan_path = result[0] if isinstance(result, list) else result
            args.plan = str(Path(plan_path).resolve())
            candidate = state_path_for_plan(args.plan)
            if candidate.is_file():
                args.state = str(candidate)
                return

    from scripts.evaluate.evaluate_steps import find_state_file

    found = find_state_file(include_stale=False)
    if found is not None:
        args.state = str(found)


def pre_run(*, args: Any, manifest: Any = None, repo_root: Path | None = None) -> None:
    reject_review_mode(args=args, manifest=manifest, repo_root=repo_root)
    bind_plan_state_path(args=args, manifest=manifest, repo_root=repo_root)
