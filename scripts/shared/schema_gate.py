"""JSON Schema validation for design / evaluate / test workflow sidecars.

Wave 5: shape checks via ``jsonschema.Draft202012Validator``. Sidecar path
resolution reuses ``workflow_gate.gate_sidecar_path`` / ``load_gate_json``.

Evaluate findings: ingest remains warn-and-skip for malformed sidecars. Declared
``kind: schema`` gates for ``evaluate-findings-step`` are **soft** (missing →
pass; invalid → warn, do not exit) so the ingest contract is preserved. Design
and test recommendation schema gates hard-fail via ``exit_if_gate_fails``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from scripts.shared.skill_manifest import ManifestGate
from scripts.shared.workflow_gate import (
    exit_if_gate_fails,
    gate_sidecar_path,
    validate_override_bypass,
)

# Schema stems treated as soft/optional (evaluate findings ingest contract).
_SOFT_SCHEMA_STEMS = frozenset({"evaluate-findings-step"})

_LEGACY_SIDECAR_BY_STEM = {
    "design-spec-gate": ".develop-spec-gate.json",
}


def _packaged_schemas_root() -> Path | None:
    try:
        from importlib import resources

        root = resources.files("forge_next.assets").joinpath("schemas")
        as_path = Path(str(root))
        if as_path.is_dir():
            return as_path
    except (ModuleNotFoundError, TypeError, OSError, AttributeError):
        return None
    return None


def resolve_schema_path(schema_rel: str, repo_root: Path | None = None) -> Path:
    """Resolve schema file: checkout ``schemas/`` then packaged assets."""
    rel = schema_rel.replace("\\", "/").lstrip("./")
    if rel.startswith("schemas/"):
        under = rel[len("schemas/") :]
    else:
        under = rel

    roots: list[Path] = []
    if repo_root is not None:
        roots.append(Path(repo_root) / "schemas")
    # Walk up from this module for checkout layouts when repo_root omitted.
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "schemas"
        if candidate.is_dir() and candidate not in roots:
            roots.append(candidate)
            break

    for root in roots:
        path = root / under
        if path.is_file():
            return path

    packaged = _packaged_schemas_root()
    if packaged is not None:
        path = packaged / under
        if path.is_file():
            return path

    raise FileNotFoundError(
        f"Schema not found for {schema_rel!r} "
        f"(looked under checkout schemas/ and forge_next.assets.schemas)"
    )


def load_schema(schema_path: Path) -> dict[str, Any]:
    """Load a JSON Schema document from disk."""
    return json.loads(schema_path.read_text(encoding="utf-8"))


def schema_stem(schema_rel: str) -> str:
    """Return stem for ``design-spec-gate.schema.json`` → ``design-spec-gate``."""
    name = Path(schema_rel.replace("\\", "/")).name
    if name.endswith(".schema.json"):
        return name[: -len(".schema.json")]
    return Path(name).stem


def sidecar_filename_for_schema(schema_rel: str, step: int | None = None) -> str:
    """Map schema path to on-disk sidecar filename beside session state."""
    stem = schema_stem(schema_rel)
    if stem == "evaluate-findings-step":
        if step is None:
            raise ValueError("evaluate-findings-step schema requires step")
        return f".evaluate-findings-step{step}.json"
    return f".{stem}.json"


def legacy_sidecar_filename(schema_rel: str) -> str | None:
    return _LEGACY_SIDECAR_BY_STEM.get(schema_stem(schema_rel))


def is_soft_schema(schema_rel: str) -> bool:
    """True when schema gate must not hard-fail (evaluate findings ingest)."""
    return schema_stem(schema_rel) in _SOFT_SCHEMA_STEMS


def validate_data_against_schema(
    data: Any,
    schema: dict[str, Any],
    *,
    label: str = "sidecar",
) -> tuple[bool, str]:
    """Validate ``data`` with Draft 2020-12; return (ok, message)."""
    try:
        from jsonschema import Draft202012Validator
    except ImportError as e:  # pragma: no cover - dep required in Wave 5
        return False, f"jsonschema is required for schema gates: {e}"

    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.path))
    if not errors:
        return True, ""

    parts: list[str] = []
    for err in errors[:8]:
        path = ".".join(str(p) for p in err.path) or "(root)"
        parts.append(f"{path}: {err.message}")
    more = f" (+{len(errors) - 8} more)" if len(errors) > 8 else ""
    return False, f"{label} failed schema validation:{more}\n- " + "\n- ".join(parts)


def validate_sidecar_file(
    sidecar_path: Path,
    schema_rel: str,
    *,
    repo_root: Path | None = None,
    require_file: bool = True,
) -> tuple[bool, str]:
    """Load sidecar JSON and validate against the named schema."""
    if not sidecar_path.is_file():
        if require_file:
            return False, f"Missing schema sidecar `{sidecar_path.name}` ({sidecar_path})."
        return True, ""

    try:
        data = json.loads(sidecar_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        return False, f"Invalid JSON in `{sidecar_path.name}`: {e}"

    if not isinstance(data, (dict, list)):
        return False, f"`{sidecar_path.name}` must be a JSON object or array."

    schema_path = resolve_schema_path(schema_rel, repo_root)
    schema = load_schema(schema_path)
    return validate_data_against_schema(data, schema, label=sidecar_path.name)


def _repo_root_from_state(state_path: Path) -> Path:
    cur = state_path.resolve().parent
    for p in [cur, *cur.parents]:
        if (p / ".git").is_dir():
            return p
        if (p / "schemas").is_dir() and (p / "skills").is_dir():
            return p
    try:
        return state_path.resolve().parents[3]
    except IndexError:
        return Path.cwd().resolve()


def run_schema_gate(
    *,
    state: Any,
    step: int,
    state_path: Path,
    gate: ManifestGate,
) -> None:
    """Execute a declared ``kind: schema`` gate (hard or soft)."""
    if not gate.schema:
        raise SystemExit(f"ERROR: gate {gate.id!r} kind=schema missing schema path")

    schema_rel = gate.schema
    # Design shape gates mirror residual python: only when spec_required.
    if schema_stem(schema_rel).startswith("design-spec") and state is not None:
        custom = getattr(state, "custom", None) or {}
        if not bool(custom.get("spec_required")):
            return

    soft = is_soft_schema(schema_rel)
    repo_root = _repo_root_from_state(state_path)

    if soft:
        # Match ingest_findings_sidecars: prior steps only; warn, never hard-exit.
        for prior in range(1, step):
            filename = sidecar_filename_for_schema(schema_rel, step=prior)
            side = gate_sidecar_path(state_path, filename)
            if not side.is_file():
                continue
            ok, msg = validate_sidecar_file(
                side, schema_rel, repo_root=repo_root, require_file=False
            )
            if not ok:
                print(f"WARNING: schema gate {gate.id!r}: {msg}", file=sys.stderr)
        return

    filename = sidecar_filename_for_schema(schema_rel, step=step)
    legacy = legacy_sidecar_filename(schema_rel)
    side = gate_sidecar_path(state_path, filename, legacy_filename=legacy)

    ok, msg = validate_sidecar_file(
        side, schema_rel, repo_root=repo_root, require_file=True
    )
    exit_if_gate_fails(
        ok,
        msg,
        error_label=f"Schema gate {gate.id!r} failed — ",
    )


def validate_json_shape(
    data: Any,
    schema_rel: str,
    *,
    repo_root: Path | None = None,
    label: str = "payload",
) -> tuple[bool, str]:
    """Validate in-memory JSON against a schema (for residual wrappers / tests)."""
    schema_path = resolve_schema_path(schema_rel, repo_root)
    schema = load_schema(schema_path)
    return validate_data_against_schema(data, schema, label=label)


__all__ = [
    "resolve_schema_path",
    "load_schema",
    "schema_stem",
    "sidecar_filename_for_schema",
    "legacy_sidecar_filename",
    "is_soft_schema",
    "validate_data_against_schema",
    "validate_sidecar_file",
    "validate_json_shape",
    "run_schema_gate",
    "validate_override_bypass",
]
