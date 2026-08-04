"""Design spec completion gate for develop/design handoff.

Shape of ``.design-spec-gate.json`` is validated via ``schema_gate`` (JSON Schema).
This module keeps residual checks: on-disk ``spec_path`` existence and boolean
invariants (``spec_written`` / ``self_review_passed`` / ``user_approved``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.shared.schema_gate import validate_json_shape
from scripts.shared.workflow_gate import (
    exit_if_gate_fails as _exit_if_gate_fails,
    gate_sidecar_path as _gate_sidecar_path,
    load_gate_json,
    validate_override_bypass,
)

SPEC_GATE_FILE = ".design-spec-gate.json"
LEGACY_SPEC_GATE_FILE = ".develop-spec-gate.json"
SPEC_GATE_SCHEMA = "schemas/sidecars/design/design-spec-gate.schema.json"

__all__ = [
    "SPEC_GATE_FILE",
    "LEGACY_SPEC_GATE_FILE",
    "SPEC_GATE_SCHEMA",
    "gate_sidecar_path",
    "load_gate_json",
    "validate_spec_gate",
    "exit_if_gate_fails",
    "handoff_spec_summary",
]


def gate_sidecar_path(state_path: Path) -> Path:
    return _gate_sidecar_path(
        state_path,
        SPEC_GATE_FILE,
        legacy_filename=LEGACY_SPEC_GATE_FILE,
    )


def _repo_root_from_state(state_path: Path) -> Path:
    """Walk up from the state file until a `.git` directory is found."""
    cur = state_path.resolve().parent
    for p in [cur, *cur.parents]:
        if (p / ".git").is_dir():
            return p
    try:
        return state_path.resolve().parents[3]
    except IndexError:
        return Path.cwd().resolve()


def _resolve_spec_path(repo_root: Path, raw: str) -> Path | None:
    s = (raw or "").strip()
    if not s:
        return None
    p = Path(s).expanduser()
    if p.is_absolute():
        return p if p.is_file() else None
    cand = (repo_root / p).resolve()
    return cand if cand.is_file() else None


def _validate_shape(data: dict[str, Any], repo_root: Path) -> tuple[bool, str]:
    return validate_json_shape(
        data, SPEC_GATE_SCHEMA, repo_root=repo_root, label=SPEC_GATE_FILE
    )


def _validate_residual(
    data: dict[str, Any], state_path: Path, repo_root: Path
) -> tuple[bool, str]:
    """On-disk spec_path + boolean invariants (not covered by schema alone)."""
    spec_raw = str(data.get("spec_path", "")).strip()
    spec_path = _resolve_spec_path(repo_root, spec_raw)
    if spec_path is None:
        return (
            False,
            f"Design spec file not found or path invalid: `{spec_raw!r}` "
            f"(resolved from repo root `{repo_root}`).",
        )

    for key in ("spec_written", "self_review_passed", "user_approved"):
        if not data.get(key):
            return (
                False,
                f"Spec gate: `{key}` must be true in `{SPEC_GATE_FILE}`.",
            )
    return True, ""


def validate_spec_gate(
    state_path: Path | None = None,
    spec_required: bool | None = None,
    *,
    allow_incomplete: bool = False,
    override_reason: str = "",
    override_requested_by: str = "",
    override_follow_up: str = "",
    override_timestamp: str = "",
    # skill_runner gate-adapter kwargs (Wave 4+)
    state: Any = None,
    step: int | None = None,
    gate: Any = None,
) -> tuple[bool, str] | None:
    """Return (ok, message), or exit via gate adapter when ``state``/``gate`` set.

    When ``spec_required`` is false, always ok. Manifest python gates call this
    as ``validate_spec_gate(state=..., step=..., state_path=..., gate=...)``.
    Residual path/boolean checks still fail when the pointed-to file is missing.
    """
    del override_requested_by  # recorded by CLI/state; not required for bypass UX
    # Adapter path used by declarative skill_runner gates.
    if state is not None and gate is not None:
        from scripts.shared.orchestrator import now_iso

        sp = state_path if state_path is not None else Path(".")
        if step is not None and step >= 6:
            tier = str(state.custom.get("scope_tier", "unknown"))
            if tier == "unknown":
                side = gate_sidecar_path(sp)
                if side.is_file():
                    state.custom["scope_tier"] = "medium"
                    state.custom["spec_required"] = True
        required = bool(state.custom.get("spec_required"))
        # Step 6 only prepares the sidecar; do not fail yet.
        if step == 6:
            return None
        allow = False
        reason = ""
        follow_up = ""
        ts = ""
        if step == 8:
            allow = bool(state.custom.get("allow_spec_incomplete"))
            reason = str(state.custom.get("spec_override_reason") or "")
            follow_up = str(state.custom.get("spec_override_follow_up") or "")
            ts = now_iso()
        ok, msg = validate_spec_gate(
            sp,
            required,
            allow_incomplete=allow,
            override_reason=reason,
            override_follow_up=follow_up,
            override_timestamp=ts,
        )
        exit_if_gate_fails(ok, msg)
        return None

    if state_path is None or spec_required is None:
        raise TypeError("validate_spec_gate requires state_path and spec_required")

    if not spec_required:
        return True, ""

    ok, msg = validate_override_bypass(
        allow_incomplete,
        override_reason,
        override_follow_up,
        reason_field_label="--spec-override-reason (non-empty)",
        follow_up_field_label="--spec-override-follow-up (non-empty)",
        success_message=f"Spec gate overridden — reason recorded (timestamp={override_timestamp}).",
        override_timestamp=override_timestamp,
    )
    if allow_incomplete:
        return ok, msg

    side = gate_sidecar_path(state_path)
    data = load_gate_json(side)
    if not data:
        return (
            False,
            f"Missing or invalid `{SPEC_GATE_FILE}` next to the design state file "
            f"({side}). Complete the spec workflow from step 6 before running step 7.",
        )

    repo = _repo_root_from_state(state_path)
    ok, msg = _validate_shape(data, repo)
    if not ok:
        return False, msg

    return _validate_residual(data, state_path, repo)


def exit_if_gate_fails(ok: bool, msg: str) -> None:
    _exit_if_gate_fails(ok, msg, error_label="Design spec gate failed — ")


def handoff_spec_summary(gate_data: dict[str, Any] | None) -> dict[str, str]:
    """Flatten spec gate fields for handoff context."""
    if not gate_data:
        return {"Spec path": "(n/a)", "Spec approved": "(n/a)"}
    return {
        "Spec path": str(gate_data.get("spec_path", "")).strip() or "(unknown)",
        "Spec approved": "yes" if gate_data.get("user_approved") else "no",
    }
