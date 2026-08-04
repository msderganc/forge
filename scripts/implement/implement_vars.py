"""Implement template variables (must not import skill_runner)."""

from __future__ import annotations

from pathlib import Path

from scripts.evaluate.plan_resolver import AmbiguousPlanError, resolve_plan_file
from scripts.implement.implement_legacy import (
    DEFAULT_BRANCH_PREFIX,
    TEAM_ROLES,
    _build_doc_variables,
    _build_handoff_variables,
    _build_step1_variables,
    _build_step2_variables,
    _build_team_composition,
    _build_wave_variables,
    _feature_branch_placeholder,
    _studio_template_vars,
    _sync_waves_from_plan,
)
from scripts.shared.orchestrator import SkillState, save_state


def _ensure_defaults(state: SkillState) -> None:
    defaults = {
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
    for key, value in defaults.items():
        state.custom.setdefault(key, value)


def build_variables(
    state: SkillState,
    repo_root: Path,
    step: int = 1,
    state_path: Path | None = None,
) -> dict[str, str]:
    """Unified variables builder for all implement steps."""
    _ensure_defaults(state)
    # Apply CLI plan / branch / defer from state.custom (set by runner)
    plan_arg = state.custom.get("plan")
    if plan_arg and not state.custom.get("plan_path"):
        try:
            state.custom["plan_path"] = str(resolve_plan_file(str(plan_arg), repo_root))
        except AmbiguousPlanError as e:
            import sys

            print("Multiple plans matched. Choose one:\n", file=sys.stderr)
            for i, p in enumerate(e.matches, 1):
                print(f"  {i}. {p}", file=sys.stderr)
            raise SystemExit(1) from e
        except FileNotFoundError as e:
            import sys

            print(f"ERROR: {e}", file=sys.stderr)
            raise SystemExit(1) from e

    if state.custom.get("branch_prefix"):
        pass  # already on state
    if state.custom.get("defer_graphify_waves") and step == 1:
        from forge_next.graphify_enforcement import set_graphify_defer_implement_waves
        import sys

        set_graphify_defer_implement_waves(repo_root, defer=True)
        print(
            "forge implement: Graphify deferred for wave steps 3–5 "
            "(clear with `forge graphify undefer-waves`).",
            file=sys.stderr,
        )

    if step <= 2:
        _sync_waves_from_plan(state)

    if step == 1:
        variables = _build_step1_variables(state)
        append = ""
        if plan_arg:
            append = (
                f"\n\n---\n\n**Plan argument provided:** `{plan_arg}`\n"
                "Use this path directly (skip detection order steps 2-4).\n"
            )
            variables["__APPEND__"] = append
        if state_path is not None:
            save_state(state, state_path)
        return variables

    if step == 2:
        return _build_step2_variables(state)

    if step in (3, 4, 5):
        variables = _build_wave_variables(state)
        if step == 5:
            current_wave = int(state.custom.get("current_wave", 1) or 1)
            total_waves = int(state.custom.get("total_waves", 0) or 0)
            waves_completed = int(state.custom.get("waves_completed", 0) or 0) + 1
            state.custom["waves_completed"] = waves_completed
            if waves_completed < total_waves:
                state.custom["current_wave"] = current_wave + 1
                state.custom["_next_step"] = 3
                variables["__PHASE_LABEL__"] = (
                    f"Wave Completion (Wave {current_wave} done, "
                    f"{total_waves - waves_completed} remaining)"
                )
            else:
                state.custom["_next_step"] = 6
                variables["__PHASE_LABEL__"] = "Wave Completion (All waves done)"
            if state_path is not None:
                save_state(state, state_path)
        return variables

    if step == 6:
        return {
            **_studio_template_vars(),
            "TEAM_COMPOSITION": _build_team_composition(),
        }

    if step == 7:
        return _build_doc_variables(state, state_path)

    if step == 8:
        return _build_handoff_variables(state)

    return _studio_template_vars()


def build_handoff_context(state: SkillState, repo_root: Path) -> dict[str, str]:
    doc_gate = (
        "overridden" if state.custom.get("allow_docs_incomplete") else "passed"
    )
    return {
        "Feature branch": str(
            state.custom.get("feature_branch") or _feature_branch_placeholder(state)
        ),
        "Waves completed": str(state.custom.get("waves_completed", 0)),
        "Total waves": str(state.custom.get("total_waves", 0)),
        "Plan path": str(state.custom.get("plan_path", "")),
        "Documentation gate": doc_gate,
        "Docs Completed": "",
        "Docs Deferred": (
            f"override — follow-up: {state.custom.get('docs_override_follow_up', '')}"
            if state.custom.get("allow_docs_incomplete")
            else "(none)"
        ),
        "External Wiki Evidence": "",
        "Override Used (if any)": (
            "yes" if state.custom.get("allow_docs_incomplete") else "no"
        ),
    }


# Re-export helpers tests may need via implement shim
__all__ = [
    "DEFAULT_BRANCH_PREFIX",
    "TEAM_ROLES",
    "build_handoff_context",
    "build_variables",
]
