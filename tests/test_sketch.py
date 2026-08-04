"""Tests for forge sketch orchestrator."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SKETCH_SCRIPT = REPO_ROOT / "scripts" / "sketch" / "sketch.py"


def _run_sketch(
    step: int,
    *,
    state_dir: Path | None = None,
    with_domain_docs: bool = False,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, str(SKETCH_SCRIPT), "--step", str(step)]
    if state_dir is not None:
        state = state_dir / "sketch.json"
        if step > 1:
            cmd.extend(["--state", str(state)])
    if with_domain_docs and step == 1:
        cmd.append("--with-domain-docs")
    return subprocess.run(
        cmd,
        cwd=cwd or REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def test_sketch_step1_outputs_startup(tmp_path, monkeypatch):
    monkeypatch.setenv("FORGE_CODEX_ROOT", str(tmp_path / ".codex" / "forge-codex"))
    (tmp_path / ".codex" / "forge-codex").mkdir(parents=True)
    proc = _run_sketch(1, with_domain_docs=True)
    assert proc.returncode == 0, proc.stderr
    assert "forge sketch" in proc.stdout.lower() or "Sketch" in proc.stdout
    assert "sketch-decisions" in proc.stdout or "sketch" in proc.stdout.lower()
    assert "design spec" in proc.stdout.lower() or "docs/forge/specs" in proc.stdout
    assert ".forge/memory/sketch-decisions.md" in proc.stdout or "sketch-decisions.md" in proc.stdout
    assert not re.search(r"[A-Za-z]:\\.*memory", proc.stdout)


def test_sketch_paths_use_repo_relative_memory_dir(tmp_path, monkeypatch):
    from scripts.shared import repo_paths as rp
    from scripts.sketch import sketch_vars as sketch_vars_mod

    (tmp_path / ".git").mkdir()
    (tmp_path / ".codex").mkdir()
    codex = (tmp_path / ".codex").resolve()

    real_is_writable = rp.is_writable_dir

    def selective_writable(path: Path) -> bool:
        if path.resolve() == codex:
            return False
        return real_is_writable(path)

    monkeypatch.setattr("scripts.shared.repo_paths.is_writable_dir", selective_writable)

    from scripts.shared.orchestrator import SkillState

    state = SkillState(skill_name="sketch", max_step=3)
    vars_ = sketch_vars_mod.build_variables(state, tmp_path)
    assert vars_["SKETCH_DECISIONS_PATH"] == ".forge/memory/sketch-decisions.md"
    assert vars_["SKETCH_DECISIONS_REL"] == ".forge/memory/sketch-decisions.md"
    assert ".codex/forge/memory" not in vars_["SKETCH_NO_EDIT_POLICY"]


def test_sketch_handoff_menu_defaults_to_design(tmp_path, monkeypatch):
    from scripts.shared.orchestrator import SkillState, build_skill_handoff_menu, runtime_state_path

    monkeypatch.setenv("FORGE_CODEX_ROOT", str(tmp_path / ".codex" / "forge-codex"))
    monkeypatch.setenv("FORGE_WORKFLOW_INVOCATION", "dollar")
    sp = runtime_state_path("sketch", tmp_path)
    state = SkillState(skill_name="sketch", max_step=3)
    menu = build_skill_handoff_menu("sketch", state, sp)
    assert "$forge:design" in menu
    assert "handoff-multiselect" in menu
    assert "WORKFLOW HANDOFF — sketch complete" in menu


def test_skill_chain_sketch_entry():
    from scripts.shared.skill_chain import SKILL_CHAIN

    assert "sketch" in SKILL_CHAIN
    assert SKILL_CHAIN["sketch"].default == "design"
    assert "sketch" in SKILL_CHAIN["design"].alternatives


@pytest.mark.parametrize("prompt", ["sketch/startup", "sketch/session", "sketch/handoff"])
def test_sketch_prompt_templates_exist(prompt: str):
    path = REPO_ROOT / "prompts" / f"{prompt}.md"
    assert path.is_file(), path
    packaged = REPO_ROOT / "forge_next" / "assets" / "prompts" / f"{prompt}.md"
    assert packaged.is_file(), packaged


def test_sketch_step2_reentrant_hint(tmp_path, monkeypatch):
    monkeypatch.setenv("FORGE_CODEX_ROOT", str(tmp_path / ".codex" / "forge"))
    (tmp_path / ".codex" / "forge").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    r1 = _run_sketch(1)
    assert r1.returncode == 0, r1.stderr
    import re

    m = re.search(r"STATE FILE:\s*(.+)", r1.stderr)
    assert m, r1.stderr
    state_path = m.group(1).strip()
    cmd = [sys.executable, str(SKETCH_SCRIPT), "--step", "2", "--state", state_path]
    r2 = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert r2.returncode == 0, r2.stderr
    assert "forge sketch --step 2" in r2.stdout or "step 2" in r2.stdout.lower()
    assert "synthesis" in r2.stdout.lower() or "reflect" in r2.stdout.lower()


def test_sketch_session_prompt_in_repo():
    text = (REPO_ROOT / "prompts" / "sketch" / "session.md").read_text(encoding="utf-8")
    assert "synthesis" in text.lower()
    assert "loop-back" in text.lower() or "loop back" in text.lower()


def test_integration_spec_includes_sketch():
    spec = json.loads(
        (REPO_ROOT / "integrations" / "spec" / "commands.json").read_text(encoding="utf-8")
    )
    ids = [c["id"] for c in spec["commands"]]
    assert "forge:sketch" in ids
