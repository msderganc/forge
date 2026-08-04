"""Takeover step variables — route init (no skill_runner import)."""

from __future__ import annotations

from pathlib import Path

from scripts.shared.orchestrator import SkillState, save_state
from scripts.takeover.deviations import empty_deviations, record_assumption, record_inference
from scripts.takeover.router import build_route_plan
from scripts.takeover.takeover_legacy import (
    DEFAULT_MAX_INNER,
    _ensure_gates_dir,
    _route_plan_to_dict,
    gates_dir_relative,
)


def build_variables(
    state: SkillState,
    repo_root: Path,
    step: int = 1,
    state_path: Path | None = None,
) -> dict[str, str]:
    if step == 1:
        _ensure_gates_dir(repo_root)
        if not state.custom.get("goal"):
            state.custom.setdefault("goal", "ship-ready")
            state.custom.setdefault("route_plan", None)
            state.custom.setdefault("deviations", empty_deviations())
            state.custom.setdefault("max_inner", DEFAULT_MAX_INNER)
            state.custom.setdefault("inner_eval_pre", 0)
            state.custom.setdefault("inner_eval_post", 0)
            state.custom.setdefault("inner_cr", 0)
            state.custom.setdefault("ship_ready", False)

        goal = (str(state.custom.get("goal") or "")).strip() or "ship-ready"
        plan, inferences = build_route_plan(
            repo_root=repo_root,
            issue=state.custom.get("issue"),
            design=state.custom.get("design"),
            goal=goal,
        )
        dev = state.custom.setdefault("deviations", empty_deviations())
        for inf in inferences:
            record_inference(dev, inf["field"], inf["chosen"], inf["reason"])
        record_assumption(dev, f"Default goal: {goal}")

        state.custom["goal"] = plan.goal
        state.custom["route_plan"] = _route_plan_to_dict(plan)
        if state_path is not None:
            save_state(state, state_path)

        body_parts = [
            "# Takeover — routed",
            "",
            f"**Goal:** {plan.goal}",
            f"**Entry skill:** `{plan.entry_skill}` — {plan.entry_reason}",
            f"**Scope tier:** `{plan.scope_tier}` (evaluate skip={plan.skip_evaluate}; "
            f"code-review effort=`{plan.code_review_effort}`)",
        ]
        if plan.short_circuit_to_test:
            body_parts.append(
                "**Short-circuit:** diagnose `simple` fix detected — prefer test/ship "
                "path; skip evaluate when small."
            )
        if plan.upstream_skills:
            body_parts.append(f"**Upstream:** {', '.join(plan.upstream_skills)}")
        if plan.design_path:
            body_parts.append(f"**Design:** `{plan.design_path}`")
        if plan.issue_ref:
            body_parts.append(f"**Issue:** `{plan.issue_ref}`")
        body_parts.extend(
            [
                "",
                "Run the child skill commands emitted on subsequent steps until "
                "ship-ready gates pass.",
                "Gate findings: only **critical** + **warning** block; suggestions "
                "are advisory.",
                f"Gate directory: `{gates_dir_relative(repo_root)}/`",
            ]
        )
        return {"BODY": "\n".join(body_parts)}

    # Later steps: BODY filled by gate escape
    return {"BODY": state.custom.pop("_takeover_body", "") or ""}


def build_handoff_context(state: SkillState, repo_root: Path) -> dict[str, str]:
    del repo_root
    plan = state.custom.get("route_plan") or {}
    return {
        "Goal": str(state.custom.get("goal") or "ship-ready"),
        "Entry skill": str(plan.get("entry_skill") or ""),
        "Ship ready": "yes" if state.custom.get("ship_ready") else "no",
    }
