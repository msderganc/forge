"""Passthrough of launcher flags to orchestrator modules."""

from __future__ import annotations

from types import SimpleNamespace

from forge_next.cli_dispatch import _passthrough_argv


def test_passthrough_includes_ceremony() -> None:
    args = SimpleNamespace(ceremony="medium", mode="lite", step=1)
    out = _passthrough_argv(args)
    assert out[out.index("--ceremony") + 1] == "medium"
    assert out[out.index("--mode") + 1] == "lite"
    assert out[out.index("--step") + 1] == "1"

    args = SimpleNamespace(
        step=1,
        issue="42",
        design="docs/forge/specs/x-design.md",
        goal="ship-ready",
    )
    out = _passthrough_argv(args)
    assert out[out.index("--issue") + 1] == "42"
    assert out[out.index("--design") + 1] == "docs/forge/specs/x-design.md"
    assert out[out.index("--goal") + 1] == "ship-ready"


def test_passthrough_includes_design_and_code_review_gate_bypasses() -> None:
    args = SimpleNamespace(
        allow_spec_incomplete=True,
        spec_override_reason="blocked",
        spec_override_follow_up="fill later",
        allow_issues_incomplete=True,
        issues_override_reason="blocked",
        issues_override_follow_up="fill later",
        allow_structural_probes_incomplete=True,
        structural_probes_override_reason="ci",
        structural_probes_override_follow_up="re-run probes",
    )
    out = _passthrough_argv(args)
    assert "--allow-spec-incomplete" in out
    assert out[out.index("--spec-override-reason") + 1] == "blocked"
    assert "--allow-issues-incomplete" in out
    assert "--allow-structural-probes-incomplete" in out
    assert out[out.index("--structural-probes-override-follow-up") + 1] == "re-run probes"
