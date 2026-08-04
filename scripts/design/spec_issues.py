"""Design spec → issues gate for design step 8 (handoff).

Shape of ``.design-spec-issues.json`` is validated via ``schema_gate``.
Residual checks: ``spec_path`` match vs design-spec-gate sidecar and boolean
invariants (``issues_written`` / ``user_confirmed``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.develop import spec_gate
from scripts.shared.schema_gate import validate_json_shape
from scripts.shared.workflow_gate import (
    exit_if_gate_fails as _exit_if_gate_fails,
    gate_sidecar_path as _gate_sidecar_path,
    load_gate_json,
    validate_override_bypass,
)

SPEC_ISSUES_FILE = ".design-spec-issues.json"
SPEC_ISSUES_SCHEMA = "schemas/sidecars/design/design-spec-issues.schema.json"

__all__ = [
    "SPEC_ISSUES_FILE",
    "SPEC_ISSUES_SCHEMA",
    "gate_sidecar_path",
    "load_gate_json",
    "validate_spec_issues_gate",
    "exit_if_gate_fails",
    "handoff_issues_summary",
    "issues_status_block",
]


def gate_sidecar_path(state_path: Path) -> Path:
    return _gate_sidecar_path(state_path, SPEC_ISSUES_FILE)


def _repo_root_from_state(state_path: Path) -> Path:
    cur = state_path.resolve().parent
    for p in [cur, *cur.parents]:
        if (p / ".git").is_dir():
            return p
    try:
        return state_path.resolve().parents[3]
    except IndexError:
        return Path.cwd().resolve()


def _validate_residual(
    data: dict[str, Any], state_path: Path
) -> tuple[bool, str]:
    """Path match vs design-spec-gate + boolean invariants."""
    spec_gate_data = load_gate_json(spec_gate.gate_sidecar_path(state_path))
    expected_spec = ""
    if spec_gate_data:
        expected_spec = str(spec_gate_data.get("spec_path", "")).strip()

    spec_raw = str(data.get("spec_path", "")).strip()
    if not spec_raw:
        return False, f"Spec issues gate: `spec_path` must be set in `{SPEC_ISSUES_FILE}`."
    if expected_spec and spec_raw != expected_spec:
        return (
            False,
            f"Spec issues gate: `spec_path` ({spec_raw!r}) must match "
            f"`.design-spec-gate.json` ({expected_spec!r}).",
        )

    for key in ("issues_written", "user_confirmed"):
        if not data.get(key):
            return (
                False,
                f"Spec issues gate: `{key}` must be true in `{SPEC_ISSUES_FILE}`.",
            )
    return True, ""


def validate_spec_issues_gate(
    state_path: Path | None = None,
    spec_required: bool | None = None,
    *,
    allow_incomplete: bool = False,
    override_reason: str = "",
    override_requested_by: str = "",
    override_follow_up: str = "",
    override_timestamp: str = "",
    state: Any = None,
    step: int | None = None,
    gate: Any = None,
) -> tuple[bool, str] | None:
    """Return (ok, message), or exit via gate adapter when ``state``/``gate`` set."""
    del override_requested_by
    if state is not None and gate is not None:
        from scripts.shared.orchestrator import now_iso

        sp = state_path if state_path is not None else Path(".")
        required = bool(state.custom.get("spec_required"))
        if step is not None and step < 8:
            return None
        allow = bool(state.custom.get("allow_issues_incomplete"))
        ok, msg = validate_spec_issues_gate(
            sp,
            required,
            allow_incomplete=allow,
            override_reason=str(state.custom.get("issues_override_reason") or ""),
            override_follow_up=str(state.custom.get("issues_override_follow_up") or ""),
            override_timestamp=now_iso(),
        )
        exit_if_gate_fails(ok, msg)
        return None

    if state_path is None or spec_required is None:
        raise TypeError(
            "validate_spec_issues_gate requires state_path and spec_required"
        )

    if not spec_required:
        return True, ""

    ok, msg = validate_override_bypass(
        allow_incomplete,
        override_reason,
        override_follow_up,
        reason_field_label="--issues-override-reason (non-empty)",
        follow_up_field_label="--issues-override-follow-up (non-empty)",
        success_message=(
            f"Spec issues gate overridden — reason recorded "
            f"(timestamp={override_timestamp})."
        ),
        override_timestamp=override_timestamp,
    )
    if allow_incomplete:
        return ok, msg

    side = gate_sidecar_path(state_path)
    data = load_gate_json(side)
    if not data:
        return (
            False,
            f"Missing or invalid `{SPEC_ISSUES_FILE}` next to the design state file "
            f"({side}). Complete spec → issues decomposition on step 7 before step 8.",
        )

    repo = _repo_root_from_state(state_path)
    ok, msg = validate_json_shape(
        data, SPEC_ISSUES_SCHEMA, repo_root=repo, label=SPEC_ISSUES_FILE
    )
    if not ok:
        return False, msg

    return _validate_residual(data, state_path)


def exit_if_gate_fails(ok: bool, msg: str) -> None:
    _exit_if_gate_fails(ok, msg, error_label="Design spec issues gate failed — ")


def handoff_issues_summary(gate_data: dict[str, Any] | None) -> dict[str, str]:
    """Flatten spec issues fields for handoff context."""
    if not gate_data:
        return {
            "Issues sidecar": "(n/a)",
            "Issue count": "(n/a)",
            "Beads mode": "(n/a)",
            "Epic": "(n/a)",
        }
    issues = gate_data.get("issues") or []
    count = len(issues) if isinstance(issues, list) else 0
    return {
        "Issues sidecar": SPEC_ISSUES_FILE,
        "Issue count": str(count),
        "Beads mode": str(gate_data.get("beads_mode", "")).strip() or "(unknown)",
        "Epic": str(gate_data.get("epic_id", "")).strip() or "none",
    }


def issues_status_block(state_path: Path) -> str:
    """Human-readable spec issues gate status for templates."""
    side = gate_sidecar_path(state_path)
    data = load_gate_json(side)
    if not data:
        return (
            f"**Spec issues gate:** required — sidecar missing or invalid "
            f"(`{side.name}`).\n"
        )
    issues = data.get("issues") or []
    count = len(issues) if isinstance(issues, list) else 0
    parts = [
        "**Spec issues gate:** required",
        f"- `spec_path`: {data.get('spec_path', '')}",
        f"- `issues_written`: {data.get('issues_written', False)}",
        f"- `user_confirmed`: {data.get('user_confirmed', False)}",
        f"- `beads_mode`: {data.get('beads_mode', '')}",
        f"- `issue_count`: {count}",
        f"- `epic_id`: {data.get('epic_id', 'none')}",
    ]
    return "\n".join(parts) + "\n"
