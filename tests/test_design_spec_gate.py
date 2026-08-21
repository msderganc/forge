"""Design spec gate sidecar (.design-spec-gate.json + legacy compat)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.develop import spec_gate


def test_gate_sidecar_prefers_design_filename(tmp_path: Path) -> None:
    state = tmp_path / "session.json"
    state.write_text("{}", encoding="utf-8")
    primary = tmp_path / spec_gate.SPEC_GATE_FILE
    primary.write_text(json.dumps({"spec_path": "x.md"}), encoding="utf-8")
    assert spec_gate.gate_sidecar_path(state) == primary


def test_gate_sidecar_reads_legacy_develop_file(tmp_path: Path) -> None:
    state = tmp_path / "session.json"
    state.write_text("{}", encoding="utf-8")
    legacy = tmp_path / spec_gate.LEGACY_SPEC_GATE_FILE
    legacy.write_text(
        json.dumps(
            {
                "spec_path": "docs/forge/specs/2026-01-01-slug-design.md",
                "spec_written": True,
                "self_review_passed": True,
                "user_approved": True,
            }
        ),
        encoding="utf-8",
    )
    assert spec_gate.gate_sidecar_path(state) == legacy
    data = spec_gate.load_gate_json(legacy)
    assert data is not None
    assert data["user_approved"] is True


def test_validate_spec_gate_not_required() -> None:
    sp = Path("/tmp/fake/state/design.json")
    ok, msg = spec_gate.validate_spec_gate(sp, False)
    assert ok is True
    assert msg == ""


def test_validate_spec_gate_missing_sidecar(tmp_path: Path) -> None:
    sp = tmp_path / "session.json"
    sp.write_text('{"skill_name":"design"}', encoding="utf-8")
    ok, msg = spec_gate.validate_spec_gate(sp, True)
    assert ok is False
    assert "Missing" in msg or "invalid" in msg.lower()


def test_validate_spec_gate_happy_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    docs = repo / "docs" / "forge" / "specs"
    docs.mkdir(parents=True)
    (docs / "2026-01-01-test-design.md").write_text("# Design\n", encoding="utf-8")

    sp = repo / ".forge" / "sessions" / "x" / "session.json"
    sp.parent.mkdir(parents=True)
    sp.write_text("{}", encoding="utf-8")
    spec_gate.gate_sidecar_path(sp).write_text(
        json.dumps(
            {
                "spec_path": "docs/forge/specs/2026-01-01-test-design.md",
                "spec_written": True,
                "self_review_passed": True,
                "user_approved": True,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(repo)
    ok, msg = spec_gate.validate_spec_gate(sp, True)
    assert ok is True
    assert msg == ""


def test_validate_spec_gate_override_requires_reason(tmp_path: Path) -> None:
    sp = tmp_path / "session.json"
    ok, msg = spec_gate.validate_spec_gate(
        sp,
        True,
        allow_incomplete=True,
        override_reason="",
        override_follow_up="do it later",
    )
    assert ok is False
