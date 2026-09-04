"""Tracked text files must use LF. CRLF makes every line look changed on WSL/Windows."""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

_SKIP_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".ico",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".zip",
    ".whl",
    ".pyc",
}


def test_gitattributes_declares_lf() -> None:
    text = (REPO_ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "eol=lf" in text
    assert "text=auto" in text


def test_tracked_text_files_use_lf() -> None:
    listed = subprocess.check_output(
        ["git", "ls-files", "-z"],
        cwd=REPO_ROOT,
        text=False,
    ).split(b"\0")
    offenders: list[str] = []
    for raw in listed:
        if not raw:
            continue
        rel = raw.decode("utf-8")
        path = REPO_ROOT / rel
        if not path.is_file() or path.suffix.lower() in _SKIP_SUFFIXES:
            continue
        data = path.read_bytes()
        if b"\0" in data:
            continue
        if b"\r" in data:
            offenders.append(rel)
    assert not offenders, (
        "CRLF/CR in tracked files (convert to LF; see .gitattributes):\n"
        + "\n".join(offenders[:40])
    )
