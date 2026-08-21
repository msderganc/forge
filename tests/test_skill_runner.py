"""Tests for declarative skill_runner + sketch prototype."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _repo_on_path():
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))


def _run_skill_sketch(argv: list[str], *, repo_root: Path, monkeypatch: pytest.MonkeyPatch):
    from scripts.shared.skill_runner import run_skill

    monkeypatch.chdir(repo_root)
    return run_skill("sketch", argv, repo_root=repo_root)


def test_run_skill_sketch_steps_1_2_3_and_handoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
):
    monkeypatch.setenv("FORGE_CODEX_ROOT", str(tmp_path / ".codex" / "forge"))
    (tmp_path / ".codex" / "forge").mkdir(parents=True)
    monkeypatch.chdir(REPO_ROOT)

    code1 = _run_skill_sketch(["--step", "1"], repo_root=REPO_ROOT, monkeypatch=monkeypatch)
    assert code1 == 0
    err1 = capsys.readouterr()
    m = re.search(r"STATE FILE:\s*(.+)", err1.err)
    assert m, err1.err
    state_path = m.group(1).strip()

    code2 = _run_skill_sketch(
        ["--step", "2", "--state", state_path],
        repo_root=REPO_ROOT,
        monkeypatch=monkeypatch,
    )
    assert code2 == 0
    out2 = capsys.readouterr().out
    assert "Sketch session" in out2
    assert "forge sketch --step 2" in out2 or "step 2" in out2.lower()

    code3 = _run_skill_sketch(
        ["--step", "3", "--state", state_path],
        repo_root=REPO_ROOT,
        monkeypatch=monkeypatch,
    )
    assert code3 == 0
    out3 = capsys.readouterr().out
    assert "Handoff" in out3
    assert "Handoff written to:" in out3
    assert not Path(state_path).exists()


def test_run_skill_with_domain_docs_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys):
    monkeypatch.setenv("FORGE_CODEX_ROOT", str(tmp_path / ".codex" / "forge"))
    (tmp_path / ".codex" / "forge").mkdir(parents=True)
    monkeypatch.chdir(REPO_ROOT)

    code = _run_skill_sketch(
        ["--step", "1", "--with-domain-docs"],
        repo_root=REPO_ROOT,
        monkeypatch=monkeypatch,
    )
    assert code == 0
    err = capsys.readouterr().err
    m = re.search(r"STATE FILE:\s*(.+)", err)
    assert m
    state_path = Path(m.group(1).strip())
    data = json.loads(state_path.read_text(encoding="utf-8"))
    custom = data.get("custom") or {}
    assert custom.get("with_domain_docs") is True


def test_run_declared_gates_empty_noop(tmp_path: Path):
    from scripts.shared.orchestrator import SkillState
    from scripts.shared.skill_manifest import Manifest, ManifestStep
    from scripts.shared.skill_runner import run_declared_gates

    manifest = Manifest(
        manifest_version=1,
        skill="sketch",
        max_step=3,
        variants=None,
        steps=(
            ManifestStep(step=1, phase="Startup", prompt="sketch/startup"),
        ),
        gates=(),
    )
    state = SkillState(skill_name="sketch", max_step=3)
    # Must not raise
    run_declared_gates(manifest, state, 1, state_path=tmp_path / "session.json")


def test_kill_switch_uses_legacy_not_runner(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FORGE_SKILL_ENGINE", "0")
    calls: list[str] = []

    def fake_legacy_main() -> None:
        calls.append("legacy")

    def boom_run_skill(*_a, **_k):
        calls.append("runner")
        raise AssertionError("run_skill must not be called when kill-switch is set")

    monkeypatch.setattr(
        "scripts.sketch.sketch_legacy.main",
        fake_legacy_main,
    )
    # Import after env set; patch run_skill on skill_runner module
    import scripts.shared.skill_runner as sr

    monkeypatch.setattr(sr, "run_skill", boom_run_skill)

    from scripts.sketch import sketch as sketch_shim

    sketch_shim.main()
    assert calls == ["legacy"]


def test_vars_module_does_not_import_skill_runner():
    import ast

    import scripts.sketch.sketch_vars as vars_mod

    tree = ast.parse(Path(vars_mod.__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "skill_runner" not in alias.name
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            assert "skill_runner" not in mod


def test_evaluate_mode_pre_and_ceremony_light_dual_axis():
    """Mode variants stay orthogonal to ceremony overlay."""
    from types import SimpleNamespace

    from scripts.shared.orchestrator import SkillState
    from scripts.shared.skill_manifest import load_manifest
    from scripts.shared.skill_runner import (
        resolve_and_persist_ceremony,
        select_mode_and_ceremony,
    )

    manifest = load_manifest("evaluate", REPO_ROOT)
    state = SkillState(skill_name="evaluate", max_step=7)
    args = SimpleNamespace(mode="pre", ceremony="light", effort=None, quick=False)
    resolve_and_persist_ceremony(state, args, step=1)
    mode, ceremony = select_mode_and_ceremony(manifest, args, state)
    assert mode == "pre"
    assert ceremony == "light"
    assert state.custom["ceremony"] == "light"
    assert state.custom["ceremony_source"] == "cli"
    assert state.custom.get("mode") in (None, "pre")  # mode set by runner separately


def test_test_mode_flows_and_ceremony_medium_dual_axis():
    from types import SimpleNamespace

    from scripts.shared.orchestrator import SkillState
    from scripts.shared.skill_manifest import load_manifest
    from scripts.shared.skill_runner import (
        resolve_and_persist_ceremony,
        select_mode_and_ceremony,
    )

    manifest = load_manifest("test", REPO_ROOT)
    state = SkillState(skill_name="test", max_step=7)
    args = SimpleNamespace(mode="flows", ceremony="medium", effort=None, quick=False)
    resolve_and_persist_ceremony(state, args, step=1)
    state.custom["mode"] = "flows"
    mode, ceremony = select_mode_and_ceremony(manifest, args, state)
    assert mode == "flows"
    assert ceremony == "medium"
    assert state.custom["ceremony_source"] == "cli"


def test_effort_aliases_to_ceremony_when_not_cli():
    from types import SimpleNamespace

    from scripts.shared.orchestrator import SkillState
    from scripts.shared.skill_runner import resolve_and_persist_ceremony

    state = SkillState(skill_name="evaluate", max_step=7)
    args = SimpleNamespace(mode="pre", ceremony=None, effort="light", quick=False)
    band = resolve_and_persist_ceremony(state, args, step=1)
    assert band == "light"
    assert state.custom["ceremony_source"] == "estimated"
    assert "effort" in str(state.custom["ceremony_rationale"]).lower()


def test_soft_when_gate_is_soft_only_for_listed_ceremony():
    from scripts.shared.orchestrator import SkillState
    from scripts.shared.schema_gate import gate_is_soft
    from scripts.shared.skill_manifest import ManifestGate

    gate = ManifestGate(
        id="optional_on_light",
        steps=(1,),
        kind="schema",
        schema="schemas/sidecars/design/design-spec-gate.schema.json",
        soft_when=("light",),
    )
    state = SkillState(skill_name="design", max_step=8)
    state.custom["ceremony"] = "light"
    assert gate_is_soft(gate, state) is True

    state.custom["ceremony"] = "medium"
    assert gate_is_soft(gate, state) is False

    # Deny-by-default: empty soft_when never softens via this field
    hard = ManifestGate(
        id="always_hard",
        steps=(1,),
        kind="schema",
        schema="schemas/sidecars/design/design-spec-gate.schema.json",
        soft_when=(),
    )
    state.custom["ceremony"] = "light"
    assert gate_is_soft(hard, state) is False


def test_select_variant_name_ignores_ceremony():
    """Ceremony must not select mode variants (dual-axis overlay)."""
    from types import SimpleNamespace

    from scripts.shared.orchestrator import SkillState
    from scripts.shared.skill_manifest import load_manifest
    from scripts.shared.skill_runner import _select_variant_name

    manifest = load_manifest("evaluate", REPO_ROOT)
    state = SkillState(skill_name="evaluate", max_step=7)
    state.custom["ceremony"] = "light"
    args = SimpleNamespace(mode="pre", ceremony="light")
    assert _select_variant_name(manifest, args, state=state) == "pre"
    # No accidental compound key like pre-light
    assert "pre-light" not in (manifest.variants or {})
