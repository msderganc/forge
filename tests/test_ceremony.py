"""Tests for shared ceremony band helpers."""

from __future__ import annotations

import pytest

from scripts.shared.ceremony import (
    CEREMONIES,
    bias_down,
    estimate_ceremony,
    map_from_effort,
    map_from_plan_mode,
    map_from_scope_tier,
    map_to_effort,
    map_to_plan_mode,
    map_to_scope_tier,
    normalize_ceremony,
)


def test_normalize_aliases() -> None:
    assert normalize_ceremony("LIGHT") == "light"
    assert normalize_ceremony("lite") == "light"
    assert normalize_ceremony("quick") == "light"
    assert normalize_ceremony("standard") == "medium"
    assert normalize_ceremony("default") == "medium"
    assert normalize_ceremony("thorough") == "comprehensive"
    assert normalize_ceremony("large") == "detailed"
    assert normalize_ceremony("bogus") is None
    assert normalize_ceremony(None) is None


def test_bias_down() -> None:
    assert bias_down("comprehensive", "detailed") == "detailed"
    assert bias_down("light", "detailed") == "light"
    assert bias_down("medium", None) == "medium"


def test_legacy_maps() -> None:
    assert map_to_scope_tier("light") == "trivial"
    assert map_to_scope_tier("medium") == "medium"
    assert map_to_scope_tier("detailed") == "large"
    assert map_to_scope_tier("comprehensive") == "large"
    assert map_to_plan_mode("light") == "lite"
    assert map_to_plan_mode("medium") == "default"
    assert map_to_effort("light") == "light"
    assert map_to_effort("medium") == "standard"
    assert map_to_effort("detailed") == "thorough"
    assert map_to_effort("comprehensive") == "thorough"


def test_maps_from_legacy() -> None:
    assert map_from_scope_tier("trivial") == "light"
    assert map_from_scope_tier("small") == "light"
    assert map_from_scope_tier("medium") == "medium"
    assert map_from_scope_tier("large") == "detailed"
    assert map_from_plan_mode("lite") == "light"
    assert map_from_plan_mode("default") == "medium"
    assert map_from_effort("light") == "light"
    assert map_from_effort("standard") == "medium"
    assert map_from_effort("thorough") == "comprehensive"
    assert map_from_effort("quick") == "light"


def test_estimate_ceremony_cli_wins_via_signals() -> None:
    band, rationale = estimate_ceremony({"cli_ceremony": "light"})
    assert band == "light"
    assert "cli" in rationale.lower()


def test_estimate_ceremony_bias_down_from_severity() -> None:
    band, rationale = estimate_ceremony(
        {
            "scope_tier": "large",
            "severity": "low",
        }
    )
    # large → detailed, but low severity biases down toward medium
    assert band in CEREMONIES
    assert band in ("medium", "detailed")
    assert rationale


def test_estimate_inherits_handoff() -> None:
    band, rationale = estimate_ceremony({"inherited_ceremony": "comprehensive"})
    assert band == "comprehensive"
    assert "inherit" in rationale.lower()


@pytest.mark.parametrize(
    "signals,expected",
    [
        ({"plan_mode": "lite"}, "light"),
        ({"effort": "thorough"}, "comprehensive"),
        ({"quick": True}, "light"),
        ({}, "medium"),
    ],
)
def test_estimate_common_signals(signals: dict, expected: str) -> None:
    band, _ = estimate_ceremony(signals)
    assert band == expected
