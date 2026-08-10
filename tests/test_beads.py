"""Tests for forge_next.beads availability / install notice."""

from __future__ import annotations

from pathlib import Path

import pytest

from forge_next import beads


def test_beads_unavailable_when_bd_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FORGE_BD_COMMAND", raising=False)
    monkeypatch.setattr(beads.shutil, "which", lambda name: None)
    available, summary, details = beads.beads_availability()
    assert available is False
    assert "not available" in summary
    assert details["bd_path"] is None
    text = "\n".join(beads.beads_install_notice_lines())
    assert "not available" in text
    assert "steveyegge/beads" in text


def test_beads_available_on_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("FORGE_BD_COMMAND", raising=False)
    monkeypatch.setattr(beads.shutil, "which", lambda name: "/usr/bin/bd" if name == "bd" else None)
    monkeypatch.setattr(beads, "_probe_bd_version", lambda _cmd: "bd 0.9.0")
    available, summary, details = beads.beads_availability(tmp_path)
    assert available is True
    assert details["bd_path"] == "/usr/bin/bd"
    assert details["bd_version"] == "bd 0.9.0"
    assert details["beads_dir_exists"] is False
    assert "available" in summary
    monkeypatch.setenv("FORGE_ASCII", "1")
    text = "\n".join(beads.beads_install_notice_lines(tmp_path))
    assert "[OK] Beads: available" in text
    assert "bd init" in text


def test_beads_override_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FORGE_BD_COMMAND", "/custom/bd")
    monkeypatch.setattr(beads, "_probe_bd_version", lambda _cmd: None)
    available, _summary, details = beads.beads_availability()
    assert available is True
    assert details["via"] == "FORGE_BD_COMMAND"
    assert details["bd_path"] == "/custom/bd"


def test_beads_multiword_override_keeps_full_command(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FORGE_BD_COMMAND", "uv run bd")
    monkeypatch.setattr(beads, "_probe_bd_version", lambda cmd: "ok" if cmd == "uv run bd" else None)
    available, summary, details = beads.beads_availability()
    assert available is True
    assert details["bd_path"] == "uv run bd"
    assert "`uv run bd`" in summary


def test_probe_bd_version_swallows_unicode_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a, **_k):
        raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "bad")

    monkeypatch.setattr(beads.subprocess, "run", boom)
    assert beads._probe_bd_version("bd") is None


def test_doctor_warns_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FORGE_BD_COMMAND", raising=False)
    monkeypatch.setattr(beads.shutil, "which", lambda name: None)
    warnings = beads.beads_warnings_for_doctor()
    assert len(warnings) == 1
    assert "steveyegge/beads" in warnings[0]
