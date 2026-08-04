"""Sidecar file handling for the test-skill flows mode.

Mirrors evaluate's findings-sidecar pattern but with a different schema (single
object, not array) so the function is parallel — not a reuse of
_ingest_findings_sidecars.

Shape validation for ``.test-recommendation-step2.json`` goes through
``schema_gate`` (Wave 5); this module still owns exist/parse/delete lifecycle.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from scripts.shared.schema_gate import validate_sidecar_file

VALID_FLOW_TYPES = {"scenario", "bdd", "http-replay", "workflow-dryrun"}
RECOMMENDATION_SCHEMA = (
    "schemas/sidecars/test/test-recommendation-step2.schema.json"
)


def recommendation_sidecar_path(state_dir: Path) -> Path:
    """Return the path to the recommendation sidecar for the test skill."""
    return state_dir / ".test-recommendation-step2.json"


def write_recommendation_override(state_dir: Path, flow_type: str) -> Path:
    """Pre-write the sidecar when --flow-type was passed at CLI.

    Used by step 1/2 of test.py when the user has already chosen a type.

    Args:
        state_dir: Directory where state.json lives
        flow_type: One of VALID_FLOW_TYPES

    Returns:
        Path to the written sidecar file
    """
    path = recommendation_sidecar_path(state_dir)
    data = {
        "chosen": flow_type,
        "reasoning": "user override via --flow-type",
        "confidence": 1.0,
        "alternatives": [],
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def ingest_recommendation_sidecar(state_dir: Path) -> dict:
    """Read + validate + delete the sidecar.

    Validation:
    - File exists (else: sys.exit(1) with stderr message naming the file)
    - Shape via schema_gate (chosen / reasoning / confidence)

    NEVER falls back to a default. On any validation failure, exits with a
    clear stderr message naming the file + the specific issue.

    Args:
        state_dir: Directory where state.json lives

    Returns:
        The parsed sidecar dict on success.

    Deletes the sidecar file after successful validation (so re-runs don't
    re-ingest stale data).
    """
    path = recommendation_sidecar_path(state_dir)

    if not path.exists():
        print(f"ERROR: recommendation sidecar not found: {path}", file=sys.stderr)
        sys.exit(1)

    ok, msg = validate_sidecar_file(
        path,
        RECOMMENDATION_SCHEMA,
        require_file=True,
    )
    if not ok:
        print(f"ERROR: {msg}", file=sys.stderr)
        sys.exit(1)

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(
            f"ERROR: failed to read recommendation sidecar {path}: {e}",
            file=sys.stderr,
        )
        sys.exit(1)

    if not isinstance(data, dict):
        print(
            f"ERROR: recommendation sidecar {path} must be a JSON object",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        path.unlink()
    except OSError:
        pass

    return data


def scope_sidecar_path(state_dir: Path) -> Path:
    return state_dir / ".test-scope-step3.json"


def ingest_scope_sidecar(state_dir: Path) -> dict | None:
    """Load optional scope sidecar into a dict; return None if missing.

    Does not delete the file (scope may be re-read). Malformed JSON → stderr warning, None.
    """
    path = scope_sidecar_path(state_dir)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"WARNING: failed to read scope sidecar {path}: {e}", file=sys.stderr)
        return None
    return data if isinstance(data, dict) else None


def log_override_to_stderr(flow_type: str) -> None:
    """Single-line stderr log for adoption tracking.

    Args:
        flow_type: The flow type that was overridden
    """
    print(f"[flows] override: user passed --flow-type={flow_type}", file=sys.stderr)
