"""Code-review template variables and gate adapters (no skill_runner import)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.code_review.code_review_legacy import (
    MODE_TEMPLATES,
    _build_variables as _legacy_build_variables,
    _code_review_state_dir,
    _detect_mode,
    _normalize_target,
    _prompt_archive_dir,
)
from scripts.code_review.structural_probes_gate import (
    exit_if_structural_probes_gate_fails as _exit_structural,
)
from scripts.evaluate.plan_resolver import (
    AmbiguousPlanError,
    extract_title,
    resolve_plan_file,
)
from scripts.shared.orchestrator import SkillState, consume_handoff, save_state


def ensure_code_review_initialized(
    state: SkillState,
    repo_root: Path,
    *,
    state_path: Path | None = None,
) -> None:
    """Idempotent step-1 target/mode/effort setup."""
    if state.custom.get("_cr_initialized"):
        return

    handoff_content = state.custom.get("handoff_content")
    if handoff_content is None:
        handoff_content = consume_handoff("implement")
        state.custom["handoff_content"] = handoff_content

    plan_path = str(state.custom.get("plan_path") or "")
    plan_arg = (state.custom.get("plan") or "").strip()
    if plan_arg and not plan_path:
        try:
            plan_path = str(resolve_plan_file(plan_arg, repo_root))
        except AmbiguousPlanError as e:
            import sys

            print("Multiple plans matched. Choose one:\n", file=sys.stderr)
            for i, p in enumerate(e.matches, 1):
                print(f"  {i}. {p} — {extract_title(p)}", file=sys.stderr)
            raise SystemExit(1) from e
        except FileNotFoundError as e:
            import sys

            print(f"ERROR: {e}", file=sys.stderr)
            raise SystemExit(1) from e
        state.custom["plan_path"] = plan_path

    target_arg = state.custom.get("target")
    if not state.custom.get("target_tokens"):
        target, target_tokens = _normalize_target(target_arg)
        state.custom["target"] = target
        state.custom["target_tokens"] = target_tokens
    else:
        target = str(state.custom.get("target") or "")
        target_tokens = list(state.custom.get("target_tokens") or [])

    mode = str(state.custom.get("mode") or "")
    if not mode:
        mode = _detect_mode(target, str(handoff_content or ""))
        state.custom["mode"] = mode

    from scripts.code_review.effort_recommendation import (
        format_effort_config_section,
        recommend_effort_structural,
        resolve_applied_config,
    )
    import argparse

    # Reconstruct a minimal namespace for resolve_applied_config
    ns = argparse.Namespace(
        effort=state.custom.get("effort"),
        structural=False if state.custom.get("no_structural") else None,
        quick=state.quick_mode,
    )
    # Prefer explicit effort from CLI custom; structural defaults on unless no_structural
    recommendation = recommend_effort_structural(
        mode=mode,
        target=target,
        target_tokens=target_tokens,
        handoff_content=str(handoff_content or ""),
        plan_path=plan_path,
        quick=bool(state.quick_mode),
    )
    effort, structural_enabled, effort_overridden, structural_overridden = (
        resolve_applied_config(ns, recommendation)
    )
    if state.custom.get("no_structural"):
        structural_enabled = False
    if state.custom.get("effort"):
        effort = str(state.custom["effort"])

    state.quick_mode = effort == "light" or bool(state.quick_mode)
    state.custom["effort"] = effort
    state.custom["structural_enabled"] = structural_enabled
    state.custom["effort_recommendation"] = recommendation.to_dict()
    state.custom["effort_config_section"] = format_effort_config_section(
        recommendation,
        applied_effort=effort,
        applied_structural=structural_enabled,
        effort_overridden=effort_overridden,
        structural_overridden=structural_overridden or bool(
            state.custom.get("no_structural")
        ),
    )
    state.custom["_cr_initialized"] = True
    if state_path is not None:
        save_state(state, state_path)


def build_variables(
    state: SkillState,
    repo_root: Path,
    step: int = 1,
    state_path: Path | None = None,
) -> dict[str, str]:
    if step == 1 or not state.custom.get("_cr_initialized"):
        ensure_code_review_initialized(state, repo_root, state_path=state_path)

    prompts_style = "full" if step >= 6 else "brief"
    variables = _legacy_build_variables(
        state,
        state_path=state_path,
        repo_root=repo_root,
        prompts_style=prompts_style,
    )

    # Step 3: request structural inject via gate flag
    if step == 3 and bool(state.custom.get("structural_enabled", True)):
        state.custom["_needs_structural_inject"] = True
    elif step == 3:
        variables["__APPEND__"] = (
            "\n\n---\n\n**Structural Pass B:** skipped (`--no-structural`). "
            "Core reviewers only — no probes / eight-agents.\n"
        )

    # Light effort: after team dispatch skip to report when no pending probes
    if step == 3:
        effort = str(state.custom.get("effort") or "standard")
        if effort == "light":
            state.custom["_pending_light_skip"] = True

    return variables


def build_handoff_context(state: SkillState, repo_root: Path) -> dict[str, str]:
    mode = state.custom.get("mode", "pr")
    open_count = len(state.open_findings())
    total_count = len(state.findings)
    return {
        "Review mode": str(mode),
        "Target": str(state.custom.get("target", "N/A")),
        "Findings": (
            f"{open_count} open, {total_count - open_count} resolved of {total_count} total"
        ),
        "Critical findings": str(
            sum(1 for f in state.open_findings() if f.get("severity") == "critical")
        ),
    }


def exit_if_structural_probes_gate_fails(
    *, state: SkillState, step: int, state_path: Path, gate: Any
) -> None:
    """Manifest python gate for steps >= 4 when structural probes enabled."""
    if not bool(state.custom.get("structural_enabled", True)):
        return
    from scripts.shared.orchestrator import _detect_repo_root

    scan_root = _detect_repo_root(Path.cwd())
    state_dir = _code_review_state_dir(state_path, scan_root)
    _exit_structural(
        state_dir,
        scan_root,
        allow_incomplete=bool(state.custom.get("allow_structural_probes_incomplete")),
        override_reason=str(state.custom.get("structural_probes_override_reason") or ""),
        override_follow_up=str(
            state.custom.get("structural_probes_override_follow_up") or ""
        ),
    )


def maybe_inject_structural_probes(
    *, state: SkillState, step: int, state_path: Path, gate: Any
) -> None:
    if not state.custom.pop("_needs_structural_inject", False):
        if state.custom.pop("_pending_light_skip", False):
            state.custom["_next_step"] = 6
        return

    from scripts.shared.orchestrator import _detect_repo_root
    from scripts.shared.structural_probes import inject_structural_probes_section
    from scripts.shared.structural_probes_gate import probe_gate_is_pending

    scan_root = _detect_repo_root(Path.cwd())
    state_dir = _code_review_state_dir(state_path, scan_root)
    scope = state.custom.get("target_tokens") or []
    effort = str(state.custom.get("effort") or ("light" if state.quick_mode else "standard"))
    body, sidecar, _payload = inject_structural_probes_section(
        "",
        skill_name="code-review",
        step=step,
        repo_root=scan_root,
        state_dir=state_dir,
        mode=state.custom.get("mode"),
        scope_paths=scope if scope else None,
        quick_mode=effort != "thorough",
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
    state.custom["_append_body"] = body

    pending = probe_gate_is_pending(state_dir)
    if pending:
        state.custom["_await_same_step"] = True
    elif state.custom.pop("_pending_light_skip", False):
        state.custom["_next_step"] = 6
    save_state(state, state_path)


# Re-exports used by tests
__all__ = [
    "MODE_TEMPLATES",
    "build_handoff_context",
    "build_variables",
    "exit_if_structural_probes_gate_fails",
    "maybe_inject_structural_probes",
]
