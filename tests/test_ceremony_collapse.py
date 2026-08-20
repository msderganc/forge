"""Plan + light collapses the runner view from 7 steps to 3."""

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


@pytest.fixture
def forge_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FORGE_CODEX_ROOT", str(tmp_path / ".codex" / "forge"))
    (tmp_path / ".codex" / "forge").mkdir(parents=True)
    monkeypatch.chdir(REPO_ROOT)
    monkeypatch.delenv("FORGE_SKILL_ENGINE", raising=False)
    return tmp_path


def _run(argv: list[str]):
    from scripts.shared.skill_runner import run_skill

    return run_skill("plan", argv, repo_root=REPO_ROOT)


def _state_from_stderr(err: str) -> dict:
    match = re.search(r"STATE FILE:\s*(.+)", err)
    assert match, err
    path = Path(match.group(1).strip())
    assert path.is_file(), path
    return json.loads(path.read_text(encoding="utf-8"))


def test_plan_ceremony_light_collapses_to_three_steps(
    forge_runtime, capsys: pytest.CaptureFixture[str]
):
    code = _run(["--step", "1", "--ceremony", "light", "--force"])
    assert code == 0
    captured = capsys.readouterr()
    state = _state_from_stderr(captured.err)
    assert state["max_step"] == 3
    assert state["custom"]["plan_mode"] == "lite"
    assert state["custom"]["ceremony"] == "light"
    assert "Frame+Orient" in captured.out
    assert "Step 1 of 3" in captured.out or "step 1 of 3" in captured.out.lower()


def test_plan_ceremony_medium_keeps_seven_steps(
    forge_runtime, capsys: pytest.CaptureFixture[str]
):
    code = _run(["--step", "1", "--ceremony", "medium", "--force"])
    assert code == 0
    captured = capsys.readouterr()
    state = _state_from_stderr(captured.err)
    assert state["max_step"] == 7
    assert state["custom"]["plan_mode"] == "default"
    assert "Frame" in captured.out
    assert "Frame+Orient" not in captured.out


def test_plan_ceremony_light_mid_session_syncs_plan_mode(
    forge_runtime, capsys: pytest.CaptureFixture[str]
):
    code = _run(["--step", "1", "--ceremony", "medium", "--force"])
    assert code == 0
    captured = capsys.readouterr()
    match = re.search(r"STATE FILE:\s*(.+)", captured.err)
    assert match, captured.err
    state_path = match.group(1).strip()

    code2 = _run(
        ["--step", "2", "--state", state_path, "--ceremony", "light"]
    )
    assert code2 == 0
    captured2 = capsys.readouterr()
    state = json.loads(Path(state_path).read_text(encoding="utf-8"))
    assert state["custom"]["plan_mode"] == "lite"
    assert state["custom"]["ceremony"] == "light"
    # In-flight 7-step sessions do not collapse under a later --ceremony light.
    assert state["max_step"] == 7
    assert "Architect" in captured2.out or "Orient" in captured2.out


def test_plan_light_keep_mapping_matches_manifest():
    from scripts.shared.skill_manifest import load_manifest
    from scripts.shared.skill_runner import _PLAN_LIGHT_KEEP

    manifest = load_manifest("plan", REPO_ROOT)
    by_step = {s.step: s.prompt for s in manifest.steps}
    assert by_step[1] == "plan/context"
    assert by_step[3] == "plan/creation"
    assert by_step[7] == "plan/handoff"
    assert set(_PLAN_LIGHT_KEEP) == {1, 3, 7}


def test_plan_light_step2_notes_skipped_architect(
    forge_runtime, capsys: pytest.CaptureFixture[str]
):
    assert _run(["--step", "1", "--ceremony", "light", "--force"]) == 0
    captured = capsys.readouterr()
    match = re.search(r"STATE FILE:\s*(.+)", captured.err)
    assert match, captured.err
    state_path = match.group(1).strip()

    assert _run(["--step", "2", "--state", state_path, "--ceremony", "light"]) == 0
    out = capsys.readouterr().out
    assert "Act" in out
    assert "Architect dispatch was skipped" in out
    assert "Step 2 of 3" in out


def test_plan_light_step7_remaps_to_handoff(
    forge_runtime, capsys: pytest.CaptureFixture[str]
):
    assert _run(["--step", "1", "--ceremony", "light", "--force"]) == 0
    captured = capsys.readouterr()
    match = re.search(r"STATE FILE:\s*(.+)", captured.err)
    assert match, captured.err
    state_path = match.group(1).strip()

    code = _run(["--step", "7", "--state", state_path, "--ceremony", "light"])
    captured2 = capsys.readouterr()
    assert code == 0
    assert "remaps --step 7 to Handoff" in captured2.err
    assert "Handoff" in captured2.out
    assert "Step 3 of 3" in captured2.out


def test_plan_light_step4_is_skipped_not_complete(
    forge_runtime, capsys: pytest.CaptureFixture[str]
):
    assert _run(["--step", "1", "--ceremony", "light", "--force"]) == 0
    captured = capsys.readouterr()
    match = re.search(r"STATE FILE:\s*(.+)", captured.err)
    assert match, captured.err
    state_path = match.group(1).strip()

    code = _run(["--step", "4", "--state", state_path, "--ceremony", "light"])
    captured2 = capsys.readouterr()
    assert code == 1
    assert "Step 4 is skipped" in captured2.err
    assert "nothing left to do" not in captured2.err
