"""Implement docs-gate escape adapter for skill_runner (no skill_runner import)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.implement.docs_gate import (
    exit_if_gate_fails,
    validate_documentation_gate,
)
from scripts.shared.orchestrator import SkillState, now_iso


def _resolve_plan_path(state: SkillState) -> Path | None:
    raw = (state.custom.get("plan_path") or "").strip()
    if not raw:
        return None
    p = Path(raw)
    return p if p.is_file() else p


def exit_if_documentation_gate_fails(
    *, state: SkillState, step: int, state_path: Path, gate: Any
) -> None:
    """Manifest python gate — wraps validate_documentation_gate + exit_if_gate_fails."""
    ts = now_iso()
    ok, msg = validate_documentation_gate(
        state_path,
        _resolve_plan_path(state),
        allow_incomplete=bool(state.custom.get("allow_docs_incomplete")),
        override_reason=str(state.custom.get("docs_override_reason") or ""),
        override_requested_by=str(state.custom.get("docs_override_requested_by") or ""),
        override_follow_up=str(state.custom.get("docs_override_follow_up") or ""),
        override_timestamp=ts,
    )
    exit_if_gate_fails(ok, msg)
