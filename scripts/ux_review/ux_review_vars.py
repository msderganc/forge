"""UX-review template variables and gate adapters (no skill_runner import)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.shared.orchestrator import SkillState


def ensure_custom(state: SkillState) -> None:
    defaults: dict = {
        "base_url": "",
        "roles": ["anonymous"],
        "orientation": {},
        "review_plan": {},
        "coverage": {
            "pages": [],
            "controls": [],
            "workflows": [],
            "states": [],
            "viewports": [],
            "skips": [],
        },
        "findings": [],
        "report_path": "",
    }
    for key, value in defaults.items():
        state.custom.setdefault(key, value)


def check_plan_gate(state: SkillState) -> list[str]:
    plan = state.custom.get("review_plan") or {}
    missing: list[str] = []
    if not plan.get("journeys") and not plan.get("pages"):
        missing.append("review_plan needs journeys and/or pages before walkthrough")
    if not (state.custom.get("base_url") or "").strip():
        missing.append("base_url is empty — set it before browser walkthrough")
    return missing


def check_findings_gate(state: SkillState) -> list[str]:
    findings = state.custom.get("findings") or []
    coverage = state.custom.get("coverage") or {}
    missing: list[str] = []
    required = ("title", "severity", "location", "impact", "steps", "recommendation")
    for i, finding in enumerate(findings):
        if not isinstance(finding, dict):
            missing.append(f"findings[{i}] must be an object")
            continue
        for key in required:
            if not finding.get(key):
                missing.append(f"findings[{i}] missing '{key}'")
    if not findings and not coverage.get("clean_review"):
        missing.append(
            "findings is empty but coverage.clean_review is not true — "
            "document findings or set coverage.clean_review=true for a clean pass"
        )
    pages = coverage.get("pages") or []
    controls = coverage.get("controls") or []
    workflows = coverage.get("workflows") or []
    if not (pages or controls or workflows):
        missing.append(
            "coverage has no pages/controls/workflows — record what was reviewed before report"
        )
    return missing


def build_variables(
    state: SkillState,
    repo_root: Path,
    step: int = 1,
    state_path: Path | None = None,
) -> dict[str, str]:
    ensure_custom(state)
    if state.custom.get("base_url") is None:
        state.custom["base_url"] = ""
    orientation = state.custom.get("orientation") or {}
    plan = state.custom.get("review_plan") or {}
    coverage = state.custom.get("coverage") or {}
    findings = state.custom.get("findings") or []
    sp = state_path or Path(".")
    return {
        "BASE_URL": str(state.custom.get("base_url") or "(ask user)"),
        "ROLES": ", ".join(state.custom.get("roles") or ["anonymous"]),
        "ORIENTATION_JSON": (
            json.dumps(orientation, indent=2) if orientation else "(empty — fill this step)"
        ),
        "REVIEW_PLAN_JSON": (
            json.dumps(plan, indent=2) if plan else "(empty — fill this step)"
        ),
        "COVERAGE_JSON": json.dumps(coverage, indent=2),
        "FINDINGS_COUNT": str(len(findings)),
        "FINDINGS_JSON": json.dumps(findings, indent=2) if findings else "[]",
        "STATE_PATH": str(sp),
        "STATE_DIR": str(sp.parent if sp != Path(".") else sp),
        "REPORT_PATH": str(
            state.custom.get("report_path") or "memory/ux-review-report.md"
        ),
        "QUICK": "yes" if state.custom.get("quick") or state.quick_mode else "no",
        "PLAN_GATE_FAILURES": "",
        "FINDINGS_GATE_FAILURES": "",
    }


def build_handoff_context(state: SkillState, repo_root: Path) -> dict[str, str]:
    findings = state.custom.get("findings") or []
    high = [
        f
        for f in findings
        if str(f.get("severity", "")).lower() in ("blocker", "critical", "high")
    ]
    return {
        "Base URL": str(state.custom.get("base_url", "")),
        "Findings": str(len(findings)),
        "High/blocker": str(len(high)),
        "Report": str(state.custom.get("report_path") or "memory/ux-review-report.md"),
        "Suggested action": (
            "diagnose high-severity UX issues" if high else "UX review complete"
        ),
    }


def exit_if_plan_gate_fails(
    *, state: SkillState, step: int, state_path: Path, gate: Any
) -> None:
    """Soft gate (legacy parity): print prompt with banner, next→step 2, exit 1."""
    del step, state_path, gate
    missing = check_plan_gate(state)
    if not missing:
        return
    failures = "\n".join(f"- {m}" for m in missing)
    state.custom["_prepend_body"] = (
        "## PLAN GATE — incomplete\n\n"
        "Finish orientation/plan (steps 1–2) before walkthrough:\n\n"
        f"{failures}\n\n---\n\n"
    )
    state.custom["_next_step"] = 2
    state.custom["_skip_completion"] = True
    state.custom["_exit_code"] = 1


def exit_if_findings_gate_fails(
    *, state: SkillState, step: int, state_path: Path, gate: Any
) -> None:
    """Soft gate (legacy parity): print prompt with banner, next→step 5, exit 1."""
    del step, state_path, gate
    missing = check_findings_gate(state)
    if not missing:
        return
    failures = "\n".join(f"- {m}" for m in missing)
    state.custom["_prepend_body"] = (
        "## FINDINGS GATE — incomplete\n\n"
        "Complete structured findings (step 5) before handoff:\n\n"
        f"{failures}\n\n---\n\n"
    )
    state.custom["_next_step"] = 5
    state.custom["_skip_completion"] = True
    state.custom["_exit_code"] = 1


# Aliases for tests that imported private helpers
_check_findings_gate = check_findings_gate
_check_plan_gate = check_plan_gate
_ensure_custom = ensure_custom
_build_variables = build_variables
