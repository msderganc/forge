"""Wave 5 schema_gate + design/evaluate/test sidecar schemas."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _repo_on_path():
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))


def _valid_spec_gate_payload() -> dict:
    return {
        "spec_path": "docs/forge/specs/2026-01-01-slug-design.md",
        "spec_written": True,
        "self_review_passed": True,
        "user_approved": True,
    }


def test_design_spec_gate_schema_valid_and_missing_field(tmp_path: Path):
    from scripts.shared.schema_gate import (
        validate_json_shape,
        validate_override_bypass,
        validate_sidecar_file,
    )

    schema = "schemas/sidecars/design/design-spec-gate.schema.json"
    ok, msg = validate_json_shape(
        _valid_spec_gate_payload(), schema, repo_root=REPO_ROOT
    )
    assert ok is True
    assert msg == ""

    bad = dict(_valid_spec_gate_payload())
    del bad["spec_path"]
    ok, msg = validate_json_shape(bad, schema, repo_root=REPO_ROOT)
    assert ok is False
    assert "spec_path" in msg
    # Message usable by exit_if_gate_fails
    assert "schema validation" in msg.lower() or "failed" in msg.lower()

    # Override bypass still works via workflow_gate helper re-export
    ok, msg = validate_override_bypass(
        True,
        "accepted risk",
        "track in plan",
        success_message="overridden",
    )
    assert ok is True
    assert "overridden" in msg

    side = tmp_path / ".design-spec-gate.json"
    side.write_text(json.dumps(bad), encoding="utf-8")
    ok, msg = validate_sidecar_file(side, schema, repo_root=REPO_ROOT)
    assert ok is False


def test_residual_schema_valid_but_missing_spec_file_still_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """TDD: schema-valid sidecar still fails when pointed-to spec_path is missing."""
    from scripts.design import spec_gate

    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    state_dir = repo / ".forge" / "sessions" / "x"
    state_dir.mkdir(parents=True)
    sp = state_dir / "session.json"
    sp.write_text("{}", encoding="utf-8")

    side = spec_gate.gate_sidecar_path(sp)
    # Schema-valid (booleans true, non-empty path) but file does not exist on disk.
    side.write_text(json.dumps(_valid_spec_gate_payload()), encoding="utf-8")

    monkeypatch.chdir(repo)
    ok, msg = spec_gate.validate_spec_gate(sp, True)
    assert ok is False
    assert "not found" in msg.lower() or "invalid" in msg.lower()


def test_residual_boolean_invariants_still_enforced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from scripts.design import spec_gate

    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    docs = repo / "docs" / "forge" / "specs"
    docs.mkdir(parents=True)
    (docs / "2026-01-01-slug-design.md").write_text("# ok\n", encoding="utf-8")

    state_dir = repo / ".forge" / "sessions" / "x"
    state_dir.mkdir(parents=True)
    sp = state_dir / "session.json"
    sp.write_text("{}", encoding="utf-8")

    payload = _valid_spec_gate_payload()
    payload["user_approved"] = False  # schema type ok; residual requires true
    side = spec_gate.gate_sidecar_path(sp)
    side.write_text(json.dumps(payload), encoding="utf-8")

    monkeypatch.chdir(repo)
    ok, msg = spec_gate.validate_spec_gate(sp, True)
    assert ok is False
    assert "user_approved" in msg


def test_recommendation_sidecar_schema():
    from scripts.shared.schema_gate import validate_json_shape

    schema = "schemas/sidecars/test/test-recommendation-step2.schema.json"
    ok, msg = validate_json_shape(
        {
            "chosen": "scenario",
            "reasoning": "fits journeys",
            "confidence": 0.8,
            "alternatives": [],
        },
        schema,
        repo_root=REPO_ROOT,
    )
    assert ok is True

    ok, msg = validate_json_shape(
        {"chosen": "nope", "reasoning": "x", "confidence": 0.5},
        schema,
        repo_root=REPO_ROOT,
    )
    assert ok is False
    assert "chosen" in msg.lower() or "schema" in msg.lower()

    ok, msg = validate_json_shape(
        {"chosen": "bdd", "reasoning": "", "confidence": 0.5},
        schema,
        repo_root=REPO_ROOT,
    )
    assert ok is False


def test_evaluate_findings_array_schema():
    from scripts.shared.schema_gate import validate_json_shape

    schema = "schemas/sidecars/evaluate/evaluate-findings-step.schema.json"
    ok, msg = validate_json_shape(
        [
            {
                "phase": "feasibility",
                "severity": "critical",
                "title": "F1",
                "detail": "stub",
            }
        ],
        schema,
        repo_root=REPO_ROOT,
    )
    assert ok is True

    ok, msg = validate_json_shape(
        [{"phase": "x", "severity": "warning"}],  # missing title/detail
        schema,
        repo_root=REPO_ROOT,
    )
    assert ok is False


def test_evaluate_findings_soft_gate_does_not_hard_fail(tmp_path: Path, capsys):
    """Soft schema must not break warn-and-skip ingest contract."""
    from scripts.shared.schema_gate import run_schema_gate
    from scripts.shared.skill_manifest import ManifestGate
    from scripts.shared.orchestrator import SkillState

    state = SkillState(skill_name="evaluate", max_step=7)
    sp = tmp_path / "session.json"
    sp.write_text("{}", encoding="utf-8")
    bad = tmp_path / ".evaluate-findings-step1.json"
    bad.write_text('{"not": "an array"}', encoding="utf-8")

    gate = ManifestGate(
        id="findings_shape",
        steps=(2,),
        kind="schema",
        schema="schemas/sidecars/evaluate/evaluate-findings-step.schema.json",
    )
    # Must not raise SystemExit
    run_schema_gate(state=state, step=2, state_path=sp, gate=gate)
    err = capsys.readouterr().err
    assert "WARNING" in err


def test_design_manifest_has_schema_and_residual_python():
    from scripts.shared.skill_manifest import load_manifest

    manifest = load_manifest("design", REPO_ROOT)
    kinds = {g.id: g.kind for g in manifest.gates}
    assert kinds["design_spec_shape"] == "schema"
    assert kinds["design_spec_gate"] == "python"
    assert kinds["design_spec_issues_shape"] == "schema"
    assert kinds["design_spec_issues_gate"] == "python"
    shape = next(g for g in manifest.gates if g.id == "design_spec_shape")
    assert shape.schema and "design-spec-gate.schema.json" in shape.schema


def test_is_soft_schema_only_for_evaluate_findings():
    from scripts.shared.schema_gate import is_soft_schema

    assert is_soft_schema(
        "schemas/sidecars/evaluate/evaluate-findings-step.schema.json"
    )
    assert not is_soft_schema(
        "schemas/sidecars/design/design-spec-gate.schema.json"
    )
    assert not is_soft_schema(
        "schemas/sidecars/test/test-recommendation-step2.schema.json"
    )
