"""Tests for named workflow phases and optional --step resolution."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.shared.skill_phases import (
    phase_for_step,
    phase_slug,
    resolve_workflow_step,
    step_for_phase,
)
from scripts.shared.orchestrator import build_next_command, parse_continuation_command


def test_phase_slug() -> None:
    assert phase_slug("Scope & Team") == "scope-team"
    assert phase_slug("Deepen (5 Whys)") == "deepen-5-whys"


def test_step_for_phase_plan() -> None:
    assert step_for_phase("plan", "architecture-dispatch") == 2
    assert step_for_phase("plan", "handoff") == 7


def test_evaluate_mode_prefixed_phase() -> None:
    assert step_for_phase("evaluate", "pre-feasibility", variant="pre") == 2
    assert phase_for_step("evaluate", 2, variant="pre") == "pre-orient-feasibility"


def test_resolve_defaults_to_step_1() -> None:
    assert resolve_workflow_step(
        skill_name="plan",
        max_step=7,
        step=None,
        phase=None,
    ) == 1


def test_resolve_from_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    session_dir = tmp_path / ".forge" / "sessions" / "abc123"
    session_dir.mkdir(parents=True)
    state = {
        "skill_name": "plan",
        "current_step": 2,
        "last_completed_step": 2,
        "max_step": 7,
    }
    (session_dir / "session.json").write_text(json.dumps(state), encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    step = resolve_workflow_step(
        skill_name="plan",
        max_step=7,
        step=None,
        phase=None,
        session_id="abc123",
    )
    assert step == 3


def test_build_next_command_uses_phase(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FORGE_WORKFLOW_INVOCATION", "slash")
    cmd = build_next_command(Path("scripts/plan/plan.py"), 1, 7)
    assert cmd == "/forge:plan --phase orient-architecture"


def test_evaluate_ambiguous_phase_requires_mode() -> None:
    with pytest.raises(SystemExit):
        step_for_phase("evaluate", "discussion")


def test_parse_continuation_command_accepts_phase() -> None:
    step, state = parse_continuation_command(
        "/forge:plan --phase plan-review-loop --session abc"
    )
    assert step == 4
    assert state is not None
    assert state.endswith("sessions\\abc\\session.json") or state.endswith("sessions/abc/session.json")


def test_phase_names_for_mixed_migrated_and_unmigrated() -> None:
    """Migrated skills via manifest; iterate remains on the Python map."""
    from scripts.shared.skill_phases import _SKILL_PHASE_NAMES, phase_names_for

    assert "sketch" not in _SKILL_PHASE_NAMES
    assert "plan" not in _SKILL_PHASE_NAMES
    assert "design" not in _SKILL_PHASE_NAMES
    assert "diagnose" not in _SKILL_PHASE_NAMES
    sketch_phases = phase_names_for("sketch")
    assert sketch_phases[1] == "Startup"
    assert sketch_phases[2] == "Sketch session"
    assert sketch_phases[3] == "Handoff"

    plan_phases = phase_names_for("plan")
    assert plan_phases[1] == "Frame"

    design_phases = phase_names_for("design")
    assert design_phases[1] == "Frame"

    diagnose_phases = phase_names_for("diagnose")
    assert diagnose_phases[1] == "Frame"

    # Non-CLI iterate skill remains on the Python map
    assert "iterate" in _SKILL_PHASE_NAMES
    iterate_phases = phase_names_for("iterate")
    assert iterate_phases[1] == "Initialize"
