"""Declarative skill manifest types and loader (Wave 1 foundation).

Hook surface is capped: ``cli_flags``, ``gates``, ``pre_run``, and per-step
``variables_callable``. No undeclared plugin hooks.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

ALLOWED_TOP_LEVEL_KEYS = frozenset(
    {
        "manifest_version",
        "skill",
        "max_step",
        "variants",
        "steps",
        "gates",
        "cli_flags",
        "pre_run",
        "handoff_skill",
    }
)
ALLOWED_GATE_KINDS = frozenset({"schema", "python"})
ALLOWED_STEP_KEYS = frozenset(
    {"step", "phase", "prompt", "todos", "variables_callable", "await_same_step"}
)
ALLOWED_VARIANT_KEYS = frozenset({"max_step", "steps", "gates", "todos_by_step"})


class SkillManifestError(ValueError):
    """Invalid or missing skill manifest."""


@dataclass(frozen=True)
class CliFlag:
    name: str
    type: str
    default: Any = None
    choices: tuple[str, ...] | None = None
    help: str = ""


@dataclass(frozen=True)
class ManifestGate:
    id: str
    steps: tuple[int, ...]
    kind: str
    schema: str | None = None
    callable: str | None = None
    override_key: str | None = None


@dataclass(frozen=True)
class ManifestStep:
    step: int
    phase: str
    prompt: str
    todos: tuple[dict[str, str], ...] = ()
    variables_callable: str | None = None
    await_same_step: bool = False


@dataclass(frozen=True)
class ManifestVariant:
    """Non-recursive variant view (evaluate/test modes). Not a nested Manifest."""

    max_step: int
    steps: tuple[ManifestStep, ...]
    gates: tuple[ManifestGate, ...] = ()
    todos_by_step: tuple[tuple[int, tuple[dict[str, str], ...]], ...] = ()


@dataclass(frozen=True)
class Manifest:
    manifest_version: int
    skill: str
    max_step: int | None
    variants: dict[str, ManifestVariant] | None
    steps: tuple[ManifestStep, ...]
    gates: tuple[ManifestGate, ...] = ()
    cli_flags: tuple[CliFlag, ...] = ()
    pre_run: str | None = None
    handoff_skill: str | None = None


def _packaged_skills_root() -> Path | None:
    """Return packaged skills root when importable, else None."""
    try:
        from importlib import resources

        root = resources.files("forge_next.assets").joinpath("skills")
        # Traversable may not be a Path; normalize when on disk.
        as_path = Path(str(root))
        if as_path.is_dir():
            return as_path
    except (ModuleNotFoundError, TypeError, OSError, AttributeError):
        return None
    return None


def _resolve_manifest_path(skill: str, repo_root: Path) -> Path:
    checkout = repo_root / "skills" / skill / "manifest.yaml"
    if checkout.is_file():
        return checkout
    packaged_root = _packaged_skills_root()
    if packaged_root is not None:
        packaged = packaged_root / skill / "manifest.yaml"
        if packaged.is_file():
            return packaged
    raise SkillManifestError(
        f"Missing skill manifest for {skill!r}: "
        f"expected {checkout} or packaged forge_next/assets/skills/{skill}/manifest.yaml"
    )


def _parse_cli_flag(raw: dict[str, Any]) -> CliFlag:
    if not isinstance(raw, dict) or "name" not in raw or "type" not in raw:
        raise SkillManifestError("cli_flags entries require name and type")
    choices = raw.get("choices")
    return CliFlag(
        name=str(raw["name"]),
        type=str(raw["type"]),
        default=raw.get("default"),
        choices=tuple(str(c) for c in choices) if choices is not None else None,
        help=str(raw.get("help") or ""),
    )


def _parse_gate(raw: dict[str, Any]) -> ManifestGate:
    if not isinstance(raw, dict):
        raise SkillManifestError("gate entries must be mappings")
    kind = str(raw.get("kind") or "")
    if kind not in ALLOWED_GATE_KINDS:
        raise SkillManifestError(
            f"Unsupported gate kind {kind!r}; allowed: {sorted(ALLOWED_GATE_KINDS)}"
        )
    steps_raw = raw.get("steps")
    if not isinstance(steps_raw, list) or not steps_raw:
        raise SkillManifestError(f"gate {raw.get('id')!r} requires non-empty steps list")
    gate_id = raw.get("id")
    if not gate_id:
        raise SkillManifestError("gate entries require id")
    return ManifestGate(
        id=str(gate_id),
        steps=tuple(int(s) for s in steps_raw),
        kind=kind,
        schema=str(raw["schema"]) if raw.get("schema") is not None else None,
        callable=str(raw["callable"]) if raw.get("callable") is not None else None,
        override_key=(
            str(raw["override_key"]) if raw.get("override_key") is not None else None
        ),
    )


def _parse_step(raw: dict[str, Any]) -> ManifestStep:
    if not isinstance(raw, dict):
        raise SkillManifestError("step entries must be mappings")
    unknown = set(raw) - ALLOWED_STEP_KEYS
    if unknown:
        raise SkillManifestError(
            f"Unknown step keys {sorted(unknown)}; "
            "only variables_callable is allowed as a per-step hook"
        )
    for required in ("step", "phase", "prompt"):
        if required not in raw:
            raise SkillManifestError(f"step entry missing required field {required!r}")
    todos_raw = raw.get("todos") or []
    if not isinstance(todos_raw, list):
        raise SkillManifestError("step todos must be a list")
    todos: list[dict[str, str]] = []
    for item in todos_raw:
        if not isinstance(item, dict):
            raise SkillManifestError("todo entries must be mappings")
        todos.append({str(k): str(v) for k, v in item.items()})
    return ManifestStep(
        step=int(raw["step"]),
        phase=str(raw["phase"]),
        prompt=str(raw["prompt"]),
        todos=tuple(todos),
        variables_callable=(
            str(raw["variables_callable"])
            if raw.get("variables_callable") is not None
            else None
        ),
        await_same_step=bool(raw.get("await_same_step", False)),
    )


def _parse_todos_by_step(
    raw: Any,
) -> tuple[tuple[int, tuple[dict[str, str], ...]], ...]:
    if raw is None:
        return ()
    if not isinstance(raw, dict):
        raise SkillManifestError("todos_by_step must be a mapping of step -> todos")
    out: list[tuple[int, tuple[dict[str, str], ...]]] = []
    for step_key, todos_raw in raw.items():
        if not isinstance(todos_raw, list):
            raise SkillManifestError("todos_by_step values must be lists")
        todos = tuple(
            {str(k): str(v) for k, v in item.items()}
            for item in todos_raw
            if isinstance(item, dict)
        )
        out.append((int(step_key), todos))
    return tuple(out)


def _parse_variant(raw: dict[str, Any]) -> ManifestVariant:
    if not isinstance(raw, dict):
        raise SkillManifestError("variant entries must be mappings")
    unknown = set(raw) - ALLOWED_VARIANT_KEYS
    if unknown:
        raise SkillManifestError(
            f"Unknown variant keys {sorted(unknown)}; ManifestVariant is non-recursive"
        )
    if "max_step" not in raw or "steps" not in raw:
        raise SkillManifestError("variants require max_step and steps")
    steps_raw = raw.get("steps")
    if not isinstance(steps_raw, list) or not steps_raw:
        raise SkillManifestError("variant steps must be a non-empty list")
    gates_raw = raw.get("gates") or []
    if not isinstance(gates_raw, list):
        raise SkillManifestError("variant gates must be a list")
    return ManifestVariant(
        max_step=int(raw["max_step"]),
        steps=tuple(_parse_step(s) for s in steps_raw),
        gates=tuple(_parse_gate(g) for g in gates_raw),
        todos_by_step=_parse_todos_by_step(raw.get("todos_by_step")),
    )


def _parse_manifest(data: dict[str, Any], *, expected_skill: str | None = None) -> Manifest:
    if not isinstance(data, dict):
        raise SkillManifestError("manifest root must be a mapping")

    unknown = set(data) - ALLOWED_TOP_LEVEL_KEYS
    if unknown:
        raise SkillManifestError(
            f"Unknown manifest keys/hooks {sorted(unknown)}; "
            "allowed hooks: cli_flags, gates, pre_run, variables_callable"
        )

    version = data.get("manifest_version")
    if version != 1:
        raise SkillManifestError(f"manifest_version must be 1, got {version!r}")

    skill = data.get("skill")
    if not skill or not isinstance(skill, str):
        raise SkillManifestError("manifest requires skill name")
    if expected_skill is not None and skill != expected_skill:
        raise SkillManifestError(
            f"manifest skill {skill!r} does not match requested {expected_skill!r}"
        )

    variants_raw = data.get("variants")
    variants: dict[str, ManifestVariant] | None = None
    if variants_raw is not None:
        if not isinstance(variants_raw, dict):
            raise SkillManifestError("variants must be a mapping")
        variants = {
            str(name): _parse_variant(body) for name, body in variants_raw.items()
        }

    steps_raw = data.get("steps")
    if steps_raw is None:
        raise SkillManifestError("manifest requires steps")
    if not isinstance(steps_raw, list):
        raise SkillManifestError("steps must be a list")
    if variants is None and not steps_raw:
        raise SkillManifestError("manifest requires non-empty steps when variants absent")

    gates_raw = data.get("gates") or []
    if not isinstance(gates_raw, list):
        raise SkillManifestError("gates must be a list")
    flags_raw = data.get("cli_flags") or []
    if not isinstance(flags_raw, list):
        raise SkillManifestError("cli_flags must be a list")

    max_step = data.get("max_step")
    if max_step is not None:
        max_step = int(max_step)
    elif variants is None:
        raise SkillManifestError("manifest requires max_step when variants absent")

    pre_run = data.get("pre_run")
    if pre_run is not None:
        pre_run = str(pre_run)

    handoff = data.get("handoff_skill")
    if handoff is not None:
        handoff = str(handoff)

    return Manifest(
        manifest_version=1,
        skill=skill,
        max_step=max_step,
        variants=variants,
        steps=tuple(_parse_step(s) for s in steps_raw),
        gates=tuple(_parse_gate(g) for g in gates_raw),
        cli_flags=tuple(_parse_cli_flag(f) for f in flags_raw),
        pre_run=pre_run,
        handoff_skill=handoff,
    )


def load_manifest(skill: str, repo_root: Path) -> Manifest:
    """Load skills/<skill>/manifest.yaml (checkout) or packaged assets mirror."""
    path = _resolve_manifest_path(skill, Path(repo_root))
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise SkillManifestError(f"Invalid YAML in {path}: {exc}") from exc
    if raw is None:
        raise SkillManifestError(f"Empty manifest at {path}")
    return _parse_manifest(raw, expected_skill=skill)
