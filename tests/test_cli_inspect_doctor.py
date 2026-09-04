"""Human-readable forge doctor CLI output."""

from __future__ import annotations

from forge_next.cli_inspect import format_doctor_check_lines


def test_format_doctor_check_lines_humanizes_nested_dump() -> None:
    lines = format_doctor_check_lines(
        {
            "repo_root": "/mnt/h/code/ssapro",
            "pythonutf8": "1",
            "forge_ascii": None,
            "codex_anchor_exists": True,
            "forge_path_shadowed": False,
            "structural_tools": {
                "knip": "5.88.1",
                "knip_command": ["/home/matt/.local/share/forge/structural-tools/node_modules/.bin/knip"],
                "pyscn": "1.2.3",
            },
            "beads": {
                "available": True,
                "summary": "available (`/home/matt/.local/bin/bd`)",
            },
            "structural_probe_gates": [],
            "runtime_adaptation": {
                "writable_repo_root": "/mnt/h/code/ssapro",
                "cwd_aliases": ["/mnt/h/code/ssapro"],
                "mount_class": "wsl_bind",
            },
        }
    )
    text = "\n".join(lines)

    assert "repo root: /mnt/h/code/ssapro" in text
    assert "PYTHONUTF8: 1" in text
    assert "FORGE_ASCII: (unset)" in text
    assert "codex anchor exists: yes" in text
    assert "forge path shadowed: no" in text
    assert "structural tools:" in text
    assert "  knip: 5.88.1" in text
    assert "  knip command: /home/matt/.local/share/forge/structural-tools/node_modules/.bin/knip" in text
    assert "beads:" in text
    assert "  available: yes" in text
    assert "structural probe gates: (none)" in text
    assert "runtime adaptation:" in text
    assert "  cwd aliases: /mnt/h/code/ssapro" in text
    assert "{" not in text
    assert "}" not in text
    assert "True" not in text
    assert "False" not in text
    assert "None" not in text
    assert "[]" not in text
    assert "['/" not in text


def test_format_doctor_check_lines_lists_dict_items() -> None:
    lines = format_doctor_check_lines(
        {
            "structural_probe_gates": [
                {"status": "pending", "skill": "implement"},
            ]
        }
    )
    text = "\n".join(lines)
    assert "structural probe gates:" in text
    assert "    status: pending" in text
    assert "    skill: implement" in text
