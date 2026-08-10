"""Shared pytest helpers for handoff and CLI passthrough tests."""

from __future__ import annotations


class PassthroughArgs:
    """Minimal namespace for ``cli_dispatch._passthrough_argv`` tests."""

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


def empty_passthrough_args(**overrides) -> PassthroughArgs:
    """Baseline args object with None defaults for optional CLI flags."""
    defaults = {
        "effort": None,
        "structural": None,
        "quick": None,
        "step": None,
        "state": None,
        "session": None,
        "label": None,
        "parallel": None,
        "mode": None,
        "target": None,
        "plan": None,
        "allow_structural_probes_incomplete": None,
        "structural_probes_override_reason": None,
        "structural_probes_override_follow_up": None,
        "phase": None,
        "branch_prefix": None,
        "base_url": None,
        "save_ceremony_preference": None,
        "ceremony": None,
        "team": None,
        "force": None,
        "cleanup": None,
        "all_stale": None,
        "auto1": None,
        "auto2": None,
        "auto3": None,
        "with_domain_docs": None,
        "goal": None,
        "issue": None,
        "design": None,
        "max_loops": None,
        "metric_command": None,
        "harness": None,
        "text": None,
        "allow_spec_incomplete": None,
        "spec_override_reason": None,
        "spec_override_follow_up": None,
        "spec_override_requested_by": None,
        "allow_issues_incomplete": None,
        "issues_override_reason": None,
        "issues_override_follow_up": None,
        "issues_override_requested_by": None,
    }
    defaults.update(overrides)
    return PassthroughArgs(**defaults)
