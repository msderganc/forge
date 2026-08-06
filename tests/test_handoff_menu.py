"""Handoff menu: text-only footer + multiselect sidecar."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.shared.handoff_menu import (
    FORGE_HANDOFF_MULTISELECT_PATH_PREFIX,
    HANDOFF_MULTISELECT_FILENAME,
    build_handoff_multiselect_payload,
    emit_handoff_multiselect_path,
    format_handoff_menu_lines,
    format_handoff_multiselect_block,
    locate_handoff_multiselect_sidecar,
    write_handoff_multiselect_sidecar,
)
from scripts.shared.orchestrator import build_skill_handoff_menu


def test_format_handoff_menu_lines_excludes_json_fence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FORGE_WORKFLOW_INVOCATION", "slash")
    text = "\n".join(
        format_handoff_menu_lines(
            "plan",
            default_cmd="evaluate --mode pre",
            alternatives=["implement"],
        )
    )
    assert "1." in text
    assert "/forge:evaluate --mode pre" in text
    assert "/forge:implement" in text
    assert "(stop)" in text
    assert "handoff-multiselect" not in text
    assert "forge_handoff_multiselect" not in text
    assert "AskQuestion" not in text


def test_format_handoff_multiselect_block_still_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FORGE_WORKFLOW_INVOCATION", "slash")
    block = format_handoff_multiselect_block(
        "plan",
        default_cmd="implement",
        alternatives=["ship"],
    )
    assert "```handoff-multiselect" in block
    assert "forge_handoff_multiselect" in block


def test_build_skill_handoff_menu_writes_sidecar(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("FORGE_WORKFLOW_INVOCATION", "dollar")
    state_path = tmp_path / "sessions" / "abc123" / "session.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text("{}", encoding="utf-8")

    menu = build_skill_handoff_menu("design", state_path=state_path)
    assert "WORKFLOW HANDOFF — design complete" in menu
    assert "1." in menu
    assert "(stop)" in menu
    assert "handoff-multiselect" not in menu
    assert "forge_handoff_multiselect" not in menu

    sidecar = state_path.parent / HANDOFF_MULTISELECT_FILENAME
    assert sidecar.is_file()
    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    assert payload["type"] == "forge_handoff_multiselect"
    assert payload["allow_multiple"] is True
    assert payload["state_file"] == str(state_path)

    # Path is emitted after archive by skill_runner, not during menu build.
    assert FORGE_HANDOFF_MULTISELECT_PATH_PREFIX not in capsys.readouterr().err


def test_locate_sidecar_after_archive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FORGE_RUNTIME_ROOT", str(tmp_path / ".forge"))
    sessions = tmp_path / ".forge" / "sessions"
    sid = "sess-archive-1"
    live_dir = sessions / sid
    live_dir.mkdir(parents=True)
    state_path = live_dir / "session.json"
    state_path.write_text("{}", encoding="utf-8")

    payload = build_handoff_multiselect_payload(
        "plan",
        default_cmd="implement",
        alternatives=["ship"],
        state_path=state_path,
    )
    write_handoff_multiselect_sidecar(state_path, payload)

    archive_dir = sessions / "_archive" / sid
    archive_dir.mkdir(parents=True)
    # Simulate clear_state_file archive move
    (live_dir / HANDOFF_MULTISELECT_FILENAME).rename(
        archive_dir / HANDOFF_MULTISELECT_FILENAME
    )
    state_path.unlink()
    live_dir.rmdir()

    found = locate_handoff_multiselect_sidecar(state_path)
    assert found is not None
    assert found == (archive_dir / HANDOFF_MULTISELECT_FILENAME).resolve()

    emitted = emit_handoff_multiselect_path(state_path)
    assert emitted == found


def test_build_skill_handoff_menu_skips_sidecar_without_state_path(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("FORGE_WORKFLOW_INVOCATION", "dollar")
    menu = build_skill_handoff_menu("plan")
    assert "WORKFLOW HANDOFF" in menu
    err = capsys.readouterr().err
    assert FORGE_HANDOFF_MULTISELECT_PATH_PREFIX not in err
