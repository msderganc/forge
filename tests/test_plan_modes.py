"""Tests for plan mode resolution, preference storage, and recommendations."""

from __future__ import annotations

import json

import pytest

from scripts.plan.plan_modes import (
    DEFAULT_MODE,
    format_mode_selection_block,
    hydrate_legacy_mode,
    load_persisted_preference,
    normalize_mode,
    recommend_mode,
    save_persisted_preference,
)


def test_normalize_mode():
    assert normalize_mode("lite") == "lite"
    assert normalize_mode("DEFAULT") == "default"
    assert normalize_mode(None) == DEFAULT_MODE
    assert normalize_mode("invalid") == DEFAULT_MODE


@pytest.mark.parametrize(
    "content,expected",
    [
        ("Quick fix for a typo in one file", "lite"),
        ("Large refactor across multi-module architecture", "default"),
        ("Please update the wording", "lite"),
        ("scope_tier: trivial\nSize: small", "lite"),
        ("minor patch with parallel wave work", "lite"),
    ],
)
def test_recommend_mode(content: str, expected: str):
    mode, _ = recommend_mode(handoff_content=content)
    assert mode == expected


def test_preference_roundtrip(monkeypatch, tmp_path):
    from scripts.plan import plan_modes

    monkeypatch.setattr(plan_modes, "runtime_memory_dir", lambda search_dir=None: tmp_path)
    save_persisted_preference("light")
    assert load_persisted_preference() == "lite"
    data = json.loads((tmp_path / "plan-preference.json").read_text())
    assert data["default_ceremony"] == "light"
    assert data["default_mode"] == "lite"


def test_preference_reads_legacy_default_mode(monkeypatch, tmp_path):
    from scripts.plan import plan_modes

    monkeypatch.setattr(plan_modes, "runtime_memory_dir", lambda search_dir=None: tmp_path)
    (tmp_path / "plan-preference.json").write_text(
        json.dumps({"default_mode": "default"}) + "\n", encoding="utf-8"
    )
    assert load_persisted_preference() == "default"
    assert plan_modes.load_persisted_ceremony() == "medium"


def test_hydrate_legacy_mode():
    custom: dict = {}
    mode, migrated = hydrate_legacy_mode(custom)
    assert mode == DEFAULT_MODE
    assert migrated is True
    assert custom["plan_mode"] == DEFAULT_MODE
    _, migrated2 = hydrate_legacy_mode(custom)
    assert migrated2 is False


def test_mode_selection_block_ceremony_cli_skips_prompt():
    block = format_mode_selection_block(
        recommended="lite",
        rationale="small scope",
        persisted=None,
        resolved_mode=None,
        resolution_source="prompt",
        ceremony="comprehensive",
        ceremony_source="cli",
    )
    assert "Ceremony selection" not in block
    assert "**Active:** `comprehensive`" in block
    assert "no confirmation needed" in block


def test_mode_selection_block_prompt():
    block = format_mode_selection_block(
        recommended="lite",
        rationale="small scope",
        persisted="default",
        resolved_mode=None,
        resolution_source="prompt",
    )
    assert "Ceremony selection" in block
    assert "light" in block
    assert "medium" in block
    assert "detailed" in block
    assert "comprehensive" in block
    assert "Do **not** offer only" in block
    assert "`light`" in block
    assert "`medium`" in block


def test_ensure_plan_initialized_syncs_plan_mode_from_ceremony_cli(tmp_path, monkeypatch):
    from scripts.plan import plan_vars
    from scripts.shared.orchestrator import SkillState

    monkeypatch.setattr(plan_vars, "consume_handoff", lambda _s: "")
    monkeypatch.setattr(plan_vars, "runtime_memory_dir", lambda _r: tmp_path)
    monkeypatch.setattr(plan_vars, "write_plan_skeleton", lambda *_a, **_k: None)
    monkeypatch.setattr(plan_vars, "generate_plan_filename", lambda _h: "x.md")
    monkeypatch.setattr(plan_vars, "save_state", lambda *_a, **_k: None)

    state = SkillState(skill_name="plan", max_step=7)
    state.custom["ceremony"] = "medium"
    state.custom["ceremony_source"] = "cli"
    plan_vars.ensure_plan_initialized(state, tmp_path, state_path=tmp_path / "s.json")
    assert state.custom["plan_mode"] == "default"
    assert state.custom["plan_mode_resolution"] == "cli"
    assert "Ceremony selection" not in state.custom["_mode_selection_block"]
    assert "`medium`" in state.custom["_mode_selection_block"]
