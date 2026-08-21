"""Tests for implement documentation gate (content + MAX_STEP locks)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def add_repo_to_path():
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))


def test_validate_documentation_gate_requires_marker_cleared(tmp_path: Path):
    from scripts.implement.docs_gate import validate_documentation_gate

    state_p = tmp_path / "implement.json"
    state_p.write_text("{}", encoding="utf-8")
    plan_p = tmp_path / "plan.md"
    plan_p.write_text(
        "## Documentation\n\n<!-- FORGE_SKELETON: DOCUMENTATION -->\n",
        encoding="utf-8",
    )
    ok, msg = validate_documentation_gate(state_p, plan_p)
    assert ok is False
    assert "Documentation skeleton" in msg


def test_validate_documentation_gate_passes_with_sidecar(tmp_path: Path):
    from scripts.implement.docs_gate import gate_sidecar_path, validate_documentation_gate

    state_p = tmp_path / "implement.json"
    state_p.write_text("{}", encoding="utf-8")
    plan_p = tmp_path / "plan.md"
    plan_p.write_text("## Documentation\n\nFilled.\n", encoding="utf-8")

    gate = {
        "complete": True,
        "audience_matrix": [
            {
                "audience_level": "architect_expert",
                "applicable": False,
                "justification": "no arch change",
                "delivery_evidence": "",
            },
            {
                "audience_level": "technical_operator",
                "applicable": True,
                "justification": "ops impact",
                "delivery_evidence": "docs/runbook.md",
            },
            {
                "audience_level": "user",
                "applicable": False,
                "justification": "internal only",
                "delivery_evidence": "",
            },
        ],
        "external_wiki_checklist": [],
    }
    gate_sidecar_path(state_p).write_text(json.dumps(gate), encoding="utf-8")

    ok, msg = validate_documentation_gate(state_p, plan_p)
    assert ok is True
    assert msg == ""


def test_override_requires_follow_up(tmp_path: Path):
    from scripts.implement.docs_gate import validate_documentation_gate

    state_p = tmp_path / "implement.json"
    ok, msg = validate_documentation_gate(
        state_p,
        None,
        allow_incomplete=True,
        override_reason="urgent",
        override_follow_up="",
    )
    assert ok is False
    assert "follow-up" in msg.lower()


def test_diagnose_report_prompt_lists_technique_matrix():
    text = (REPO_ROOT / "prompts" / "diagnose" / "report.md").read_text(encoding="utf-8")
    assert "activated" in text.lower()
    assert "technique-coverage" in text.lower() or "technique coverage" in text.lower()


def test_orchestrator_max_steps_match_plan_implement_diagnose():
    from scripts.plan.plan import MAX_STEP as PLAN_MAX
    from scripts.implement.implement import MAX_STEP as IMPL_MAX
    from scripts.diagnose.orchestrate import MAX_STEP as DG_MAX

    assert PLAN_MAX == 7
    assert IMPL_MAX == 8
    assert DG_MAX == 7
