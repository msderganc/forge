"""Step-1 prompt lock: every skill, plus ceremony bands where they change jobs.

detailed/comprehensive share the medium spine except plan (collapse is light-only).
Run all four bands on plan; light+medium on the other ceremony skills.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# Skills that accept --ceremony. extra argv after --step 1 --ceremony <band> --label …
CEREMONY_SKILLS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("design", ()),
    ("plan", ("--force",)),
    ("implement", ("--plan", "README.md")),
    ("code-review", ("--target", ".", "--no-structural")),
    ("diagnose", ()),
    ("test", ("--mode", "run")),
    ("evaluate", ("--mode", "pre", "--plan", "README.md")),
)

NO_CEREMONY_SKILLS: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("sketch", (), "Startup"),
    ("ux-review", (), "Orient"),
    ("ship", (), "Graphify"),
    ("takeover", ("--goal", "ceremony-matrix ship-ready check"), "Initialize"),
)

REJECT_CEREMONY = ("sketch", "ux-review", "ship", "takeover")


def _cases() -> list[tuple[str, str, tuple[str, ...]]]:
    rows: list[tuple[str, str, tuple[str, ...]]] = []
    for skill, extra in CEREMONY_SKILLS:
        bands = ("light", "medium", "detailed", "comprehensive") if skill == "plan" else (
            "light",
            "medium",
        )
        for band in bands:
            rows.append((skill, band, extra))
    return rows


@pytest.fixture(autouse=True)
def _repo_on_path():
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture
def forge_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FORGE_CODEX_ROOT", str(tmp_path / ".codex" / "forge"))
    monkeypatch.setenv("FORGE_SKIP_SESSION_OPTIN", "1")
    monkeypatch.setenv("FORGE_SKIP_GRAPHIFY", "1")
    monkeypatch.setenv("FORGE_SKIP_GRAPHIFY_REFRESH", "1")
    (tmp_path / ".codex" / "forge").mkdir(parents=True)
    monkeypatch.chdir(REPO_ROOT)
    monkeypatch.delenv("FORGE_SKILL_ENGINE", raising=False)
    return tmp_path


def _run(skill: str, argv: list[str]) -> int:
    from scripts.shared.skill_runner import run_skill

    return run_skill(skill, argv, repo_root=REPO_ROOT)


def _state_from_stderr(err: str) -> dict:
    match = re.search(r"STATE FILE:\s*(.+)", err)
    assert match, err
    path = Path(match.group(1).strip())
    assert path.is_file(), path
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("skill,band,extra", _cases())
def test_ceremony_skill_step1_prompt(
    forge_runtime,
    capsys: pytest.CaptureFixture[str],
    skill: str,
    band: str,
    extra: tuple[str, ...],
):
    label = f"lvl-{skill}-{band}"
    argv = ["--step", "1", "--ceremony", band, "--label", label, *extra]
    code = _run(skill, argv)
    captured = capsys.readouterr()
    assert code == 0, captured.err
    state = _state_from_stderr(captured.err)
    assert state["custom"]["ceremony"] == band
    assert state["custom"]["ceremony_source"] == "cli"
    needle = skill.replace("-", " ")
    assert needle in captured.out.lower() or skill in captured.out.lower()
    assert f"Step 1 of {state['max_step']}" in captured.out
    if skill == "plan" and band == "light":
        assert state["max_step"] == 3
        assert "Frame+Orient" in captured.out
        assert state["custom"]["plan_mode"] == "lite"
    elif skill == "plan":
        assert state["max_step"] == 7
        assert "Frame+Orient" not in captured.out
        assert state["custom"]["plan_mode"] == "default"


@pytest.mark.parametrize("skill,extra,phase", NO_CEREMONY_SKILLS)
def test_non_ceremony_skill_step1_prompt(
    forge_runtime,
    capsys: pytest.CaptureFixture[str],
    skill: str,
    extra: tuple[str, ...],
    phase: str,
):
    argv = ["--step", "1", "--label", f"lvl-{skill}", *extra]
    code = _run(skill, argv)
    captured = capsys.readouterr()
    assert code == 0, captured.err
    assert phase in captured.out


@pytest.mark.parametrize("skill", REJECT_CEREMONY)
def test_non_ceremony_skill_rejects_ceremony_flag(forge_runtime, skill: str):
    with pytest.raises(SystemExit) as caught:
        _run(skill, ["--step", "1", "--ceremony", "light"])
    assert caught.value.code == 2


def test_evaluate_post_honors_ceremony(forge_runtime, capsys: pytest.CaptureFixture[str]):
    argv = [
        "--step",
        "1",
        "--mode",
        "post",
        "--plan",
        "README.md",
        "--ceremony",
        "light",
        "--label",
        "lvl-eval-post-light",
    ]
    code = _run("evaluate", argv)
    captured = capsys.readouterr()
    assert code == 0, captured.err
    state = _state_from_stderr(captured.err)
    assert state["custom"]["ceremony"] == "light"
    assert state["custom"].get("mode") == "post"


def test_test_flows_honors_ceremony(forge_runtime, capsys: pytest.CaptureFixture[str]):
    argv = [
        "--step",
        "1",
        "--mode",
        "flows",
        "--ceremony",
        "light",
        "--label",
        "lvl-test-flows-light",
    ]
    code = _run("test", argv)
    captured = capsys.readouterr()
    assert code == 0, captured.err
    state = _state_from_stderr(captured.err)
    assert state["custom"]["ceremony"] == "light"
    assert state["custom"].get("mode") == "flows"
