"""Skill manifest loader: types, validation, checkout-then-assets resolution."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "skill_manifests"


@pytest.fixture(autouse=True)
def add_repo_to_path():
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))


def _write_yaml(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_load_manifest_valid_sketch_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts.shared.skill_manifest import Manifest, ManifestVariant, load_manifest

    skill_dir = tmp_path / "skills" / "sketch"
    _write_yaml(skill_dir / "manifest.yaml", (FIXTURES / "valid_sketch.yaml").read_text(encoding="utf-8"))
    monkeypatch.chdir(tmp_path)

    manifest = load_manifest("sketch", tmp_path)
    assert isinstance(manifest, Manifest)
    assert manifest.manifest_version == 1
    assert manifest.skill == "sketch"
    assert manifest.max_step == 3
    assert len(manifest.steps) == 3
    assert manifest.steps[0].phase == "Startup"
    assert manifest.pre_run is None or isinstance(manifest.pre_run, str)
    # Variants must be ManifestVariant (non-recursive), not nested Manifest
    assert manifest.variants is None or all(
        isinstance(v, ManifestVariant) for v in manifest.variants.values()
    )
    assert not isinstance(getattr(manifest, "variants", None), Manifest)


def test_load_manifest_invalid_missing_steps_raises(tmp_path: Path) -> None:
    from scripts.shared.skill_manifest import SkillManifestError, load_manifest

    skill_dir = tmp_path / "skills" / "sketch"
    _write_yaml(
        skill_dir / "manifest.yaml",
        (FIXTURES / "invalid_missing_steps.yaml").read_text(encoding="utf-8"),
    )
    with pytest.raises(SkillManifestError, match=r"steps"):
        load_manifest("sketch", tmp_path)


def test_load_manifest_prefers_checkout_over_packaged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts.shared import skill_manifest as sm

    checkout = tmp_path / "skills" / "sketch" / "manifest.yaml"
    _write_yaml(
        checkout,
        """
manifest_version: 1
skill: sketch
max_step: 3
steps:
  - step: 1
    phase: CheckoutStartup
    prompt: sketch/startup
  - step: 2
    phase: Session
    prompt: sketch/session
  - step: 3
    phase: Handoff
    prompt: sketch/handoff
""".strip()
        + "\n",
    )
    packaged = tmp_path / "packaged" / "sketch" / "manifest.yaml"
    _write_yaml(
        packaged,
        """
manifest_version: 1
skill: sketch
max_step: 3
steps:
  - step: 1
    phase: PackagedStartup
    prompt: sketch/startup
  - step: 2
    phase: Session
    prompt: sketch/session
  - step: 3
    phase: Handoff
    prompt: sketch/handoff
""".strip()
        + "\n",
    )
    monkeypatch.setattr(sm, "_packaged_skills_root", lambda: tmp_path / "packaged")
    manifest = sm.load_manifest("sketch", tmp_path)
    assert manifest.steps[0].phase == "CheckoutStartup"


def test_load_manifest_falls_back_to_packaged_assets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts.shared import skill_manifest as sm

    packaged = tmp_path / "packaged" / "sketch" / "manifest.yaml"
    _write_yaml(
        packaged,
        """
manifest_version: 1
skill: sketch
max_step: 3
steps:
  - step: 1
    phase: PackagedStartup
    prompt: sketch/startup
  - step: 2
    phase: Session
    prompt: sketch/session
  - step: 3
    phase: Handoff
    prompt: sketch/handoff
""".strip()
        + "\n",
    )
    monkeypatch.setattr(sm, "_packaged_skills_root", lambda: tmp_path / "packaged")
    # No checkout skills/sketch/manifest.yaml
    manifest = sm.load_manifest("sketch", tmp_path)
    assert manifest.steps[0].phase == "PackagedStartup"


def test_manifest_pre_run_and_variant_types(tmp_path: Path) -> None:
    from scripts.shared.skill_manifest import ManifestVariant, load_manifest

    _write_yaml(
        tmp_path / "skills" / "test" / "manifest.yaml",
        """
manifest_version: 1
skill: test
pre_run: "scripts.test.test_cli:reject_ux_mode"
cli_flags:
  - name: "--mode"
    type: str
    default: "run"
    choices: ["run", "flows"]
variants:
  run:
    max_step: 6
    steps:
      - step: 1
        phase: Discovery
        prompt: test/discovery
  flows:
    max_step: 7
    steps:
      - step: 1
        phase: Context
        prompt: test/flow_context
steps: []
gates: []
""".strip()
        + "\n",
    )
    manifest = load_manifest("test", tmp_path)
    assert manifest.pre_run == "scripts.test.test_cli:reject_ux_mode"
    assert manifest.variants is not None
    assert set(manifest.variants) == {"run", "flows"}
    assert isinstance(manifest.variants["run"], ManifestVariant)
    assert manifest.variants["run"].max_step == 6
    assert manifest.variants["flows"].max_step == 7
    # Non-recursive: variant is not a Manifest
    from scripts.shared.skill_manifest import Manifest

    assert not isinstance(manifest.variants["run"], Manifest)


def test_load_manifest_rejects_unknown_gate_kind(tmp_path: Path) -> None:
    from scripts.shared.skill_manifest import SkillManifestError, load_manifest

    _write_yaml(
        tmp_path / "skills" / "sketch" / "manifest.yaml",
        """
manifest_version: 1
skill: sketch
max_step: 1
steps:
  - step: 1
    phase: Startup
    prompt: sketch/startup
gates:
  - id: bad
    steps: [1]
    kind: plugin
""".strip()
        + "\n",
    )
    with pytest.raises(SkillManifestError, match=r"kind|plugin|gate"):
        load_manifest("sketch", tmp_path)


def test_load_manifest_rejects_undeclared_top_level_hooks(tmp_path: Path) -> None:
    from scripts.shared.skill_manifest import SkillManifestError, load_manifest

    _write_yaml(
        tmp_path / "skills" / "sketch" / "manifest.yaml",
        """
manifest_version: 1
skill: sketch
max_step: 1
steps:
  - step: 1
    phase: Startup
    prompt: sketch/startup
post_run: "scripts.evil:hook"
""".strip()
        + "\n",
    )
    with pytest.raises(SkillManifestError, match=r"post_run|hook|unknown"):
        load_manifest("sketch", tmp_path)
