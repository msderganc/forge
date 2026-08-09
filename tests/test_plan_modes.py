"""Tests for plan mode resolution, preference storage, and recommendations."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

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


def test_recommend_lite_for_small_scope():
    mode, _ = recommend_mode(handoff_content="Quick fix for a typo in one file")
    assert mode == "lite"


def test_recommend_default_for_refactor():
    mode, _ = recommend_mode(handoff_content="Large refactor across multi-module architecture")
    assert mode == "default"


def test_recommend_mode_insufficient_signals_prefers_lite():
    mode, rationale = recommend_mode(handoff_content="Please update the wording")
    assert mode == "lite"
    assert "lite" in rationale.lower() or "insufficient" in rationale.lower()


def test_recommend_mode_trivial_scope_prefers_lite():
    mode, _ = recommend_mode(handoff_content="scope_tier: trivial\nSize: small")
    assert mode == "lite"


def test_recommend_mode_tied_prefers_lite():
    # one lite + one default signal → tie → lite
    mode, _ = recommend_mode(handoff_content="minor patch with parallel wave work")
    assert mode == "lite"


def test_preference_roundtrip(monkeypatch, tmp_path):
    from scripts.plan import plan_modes

    monkeypatch.setattr(plan_modes, "runtime_memory_dir", lambda search_dir=None: tmp_path)
    save_persisted_preference("lite")
    assert load_persisted_preference() == "lite"
    data = json.loads((tmp_path / "plan-preference.json").read_text())
    assert data["default_mode"] == "lite"


def test_hydrate_legacy_mode():
    custom: dict = {}
    mode, migrated = hydrate_legacy_mode(custom)
    assert mode == DEFAULT_MODE
    assert migrated is True
    assert custom["plan_mode"] == DEFAULT_MODE
    _, migrated2 = hydrate_legacy_mode(custom)
    assert migrated2 is False


def test_mode_selection_block_cli():
    block = format_mode_selection_block(
        recommended="lite",
        rationale="small scope",
        persisted=None,
        resolved_mode="lite",
        resolution_source="cli",
    )
    assert "no confirmation needed" in block
    assert "light" in block


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
    assert "legacy `lite`" in block
