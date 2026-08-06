"""Handoff markdown files and per-skill run-memory jsonl under the runtime memory dir."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.shared.runtime_layout import (
    RUN_HISTORY_MAX_ENTRIES,
    legacy_memory_dir,
    runtime_memory_dir,
)
from scripts.shared.skill_state import SkillState
from scripts.shared.state_lifecycle import now_iso


def handoff_paths(name: str, search_dir: Path | None = None) -> tuple[Path, Path]:
    """Return canonical and legacy handoff paths for a skill name."""
    return (
        runtime_memory_dir(search_dir) / f"handoff-{name}.md",
        legacy_memory_dir(search_dir) / f"handoff-{name}.md",
    )


_handoff_paths = handoff_paths


def _handoff_lookup_names(name: str) -> tuple[str, ...]:
    from scripts.shared.skill_aliases import skill_name_variants

    slug = name.strip().lower().replace("_", "-")
    variants = skill_name_variants(slug)
    ordered: list[str] = []
    if slug in variants:
        ordered.append(slug)
    for alt in sorted(variants):
        if alt not in ordered:
            ordered.append(alt)
    return tuple(ordered) or (name,)


def _resolve_handoff_body(raw: str, search_dir: Path | None = None) -> str:
    """If ``raw`` is a pointer document, load the session handoff; else return raw."""
    if "forge_handoff_pointer:" not in raw[:200]:
        return raw
    path_m = re.search(r"(?m)^path:\s*(.+)\s*$", raw)
    if not path_m:
        return raw
    rel = path_m.group(1).strip().strip("`")
    from scripts.shared.runtime_layout import detect_repo_root

    root = Path(search_dir) if search_dir else detect_repo_root()
    target = (root / rel).resolve() if not Path(rel).is_absolute() else Path(rel)
    try:
        if target.is_file():
            return target.read_text(encoding="utf-8")
    except OSError:
        pass
    # Fall back to archived session handoff when live path is gone
    sid_m = re.search(r"(?m)^session_id:\s*(.+)\s*$", raw)
    if sid_m:
        sid = sid_m.group(1).strip()
        from scripts.shared.session_store import sessions_archive_root

        archived = sessions_archive_root(root) / sid / "handoff.md"
        try:
            if archived.is_file():
                return archived.read_text(encoding="utf-8")
        except OSError:
            pass
    # Rewrite relative path sessions/X → sessions/_archive/X
    if "/sessions/" in rel.replace("\\", "/") and "/_archive/" not in rel.replace("\\", "/"):
        alt = rel.replace("\\", "/")
        alt = alt.replace("/sessions/", "/sessions/_archive/", 1)
        alt_path = (root / alt).resolve()
        try:
            if alt_path.is_file():
                return alt_path.read_text(encoding="utf-8")
        except OSError:
            pass
    return raw


def handoff_exists(name: str, search_dir: Path | None = None) -> bool:
    """True if a ``handoff-{name}.md`` (or a skill-alias variant) exists."""
    for skill_name in _handoff_lookup_names(name):
        for handoff in handoff_paths(skill_name, search_dir):
            if handoff.exists():
                return True
    return False


def read_handoff(name: str, search_dir: Path | None = None) -> str:
    """Read a handoff file from the runtime memory directory if it exists."""
    for skill_name in _handoff_lookup_names(name):
        for handoff in handoff_paths(skill_name, search_dir):
            if handoff.exists():
                raw = handoff.read_text(encoding="utf-8")
                return _resolve_handoff_body(raw, search_dir)
    return ""


def close_handoff(name: str, search_dir: Path | None = None) -> bool:
    """Delete canonical + legacy *global* handoff pointers (not session handoffs)."""
    removed = False
    for skill_name in _handoff_lookup_names(name):
        for handoff in handoff_paths(skill_name, search_dir):
            if handoff.exists():
                handoff.unlink()
                removed = True
    return removed


def consume_handoff(name: str, search_dir: Path | None = None) -> str:
    """Read handoff (resolving pointers) and clear the global pointer only."""
    content = read_handoff(name, search_dir=search_dir)
    if content:
        close_handoff(name, search_dir=search_dir)
    return content


def write_handoff(
    skill_name: str,
    state: SkillState,
    context: dict[str, str],
    suggested_next: str,
    memory_dir: Path | None = None,
    *,
    state_path: Path | None = None,
) -> Path:
    """Write full handoff under the session dir; global file is a thin pointer."""
    if memory_dir is None:
        memory_dir = runtime_memory_dir()
    memory_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc).isoformat()

    lines = [
        f"# Handoff: {skill_name} → {suggested_next.split()[0] if suggested_next else 'next'}",
        "",
        "## Completed",
        f"- **Skill:** {skill_name}",
        f"- **Timestamp:** {now}",
        f"- **Status:** complete",
        f"- **Quick mode:** {state.quick_mode}",
    ]
    if state.session_id:
        lines.append(f"- **Session:** {state.session_id}")

    lines.extend([
        "",
        "## Context for Next Skill",
    ])

    for key, val in context.items():
        lines.append(f"- **{key}:** {val}")

    lines.extend([
        "",
        "## Beads State",
        f"- **Epic:** {state.epic_id or 'N/A'}",
        f"- **Open issues:** {', '.join(k for k, v in state.issue_ids.items()) or 'none'}",
        "",
        "## Suggested Next",
        f"`{suggested_next}`" if suggested_next else "(end of flow)",
        "",
    ])

    content = "\n".join(lines)

    from scripts.shared.session_store import (
        is_session_state_path,
        session_handoff_path,
        session_id_from_state_path,
    )
    from scripts.shared.runtime_layout import repo_relative_path

    sid = state.session_id or (session_id_from_state_path(state_path) if state_path else None)
    session_hp: Path | None = None
    if sid:
        session_hp = session_handoff_path(sid)
        session_hp.parent.mkdir(parents=True, exist_ok=True)
        session_hp.write_text(content, encoding="utf-8")
    elif state_path and is_session_state_path(state_path):
        session_hp = state_path.parent / "handoff.md"
        session_hp.write_text(content, encoding="utf-8")
        sid = session_id_from_state_path(state_path)

    # Global file: thin pointer when we have a session handoff; else full content (legacy).
    handoff_path = memory_dir / f"handoff-{skill_name}.md"
    if session_hp is not None and sid:
        try:
            rel = repo_relative_path(session_hp)
        except Exception:
            rel = str(session_hp).replace("\\", "/")
        pointer = "\n".join(
            [
                "---",
                "forge_handoff_pointer: 1",
                f"skill: {skill_name}",
                f"session_id: {sid}",
                f"path: {rel}",
                f"updated_at: {now}",
                "---",
                "",
                f"# Handoff pointer: {skill_name}",
                "",
                f"Full handoff: `{rel}`",
                "",
            ]
        )
        handoff_path.write_text(pointer, encoding="utf-8")
    else:
        handoff_path.write_text(content, encoding="utf-8")

    return handoff_path


def skill_run_memory_path(
    skill_name: str,
    search_dir: Path | None = None,
    memory_dir: Path | None = None,
) -> Path:
    """Path to per-skill run-memory jsonl file."""
    md = memory_dir or runtime_memory_dir(search_dir)
    return md / f"{skill_name}-runs.jsonl"


def append_skill_run_memory(
    skill_name: str,
    step: int,
    phase: str,
    summary: str,
    *,
    state: Any | None = None,
    state_path: Path | None = None,
    handoff_path: Path | None = None,
    max_entries: int = RUN_HISTORY_MAX_ENTRIES,
    search_dir: Path | None = None,
    memory_dir: Path | None = None,
) -> Path:
    """Append an auditable run entry and cap history to the most recent entries."""
    md = memory_dir or runtime_memory_dir(search_dir)
    md.mkdir(parents=True, exist_ok=True)
    history_path = skill_run_memory_path(skill_name, search_dir=search_dir, memory_dir=md)
    timestamp = now_iso()

    state_path_str = str(state_path.resolve()) if isinstance(state_path, Path) else (
        str(Path(state_path).resolve()) if state_path else ""
    )
    handoff_path_str = str(handoff_path.resolve()) if isinstance(handoff_path, Path) else (
        str(Path(handoff_path).resolve()) if handoff_path else ""
    )

    started_at = getattr(state, "started_at", None) if state is not None else None
    session_ref = f"{skill_name}:{state_path_str or '(no-state)'}:{started_at or '(unknown-start)'}"
    handoff_ref = handoff_path_str or "(none)"

    entry: dict[str, Any] = {
        "timestamp": timestamp,
        "skill": skill_name,
        "step": int(step),
        "phase": phase,
        "summary": summary.strip(),
        "session_ref": session_ref,
        "state_path": state_path_str,
        "session_started_at": started_at,
        "handoff_ref": handoff_ref,
        "handoff_path": handoff_path_str,
    }
    if state is not None:
        entry["current_step"] = getattr(state, "current_step", None)
        entry["last_completed_step"] = getattr(state, "last_completed_step", None)
        entry["max_step"] = getattr(state, "max_step", None)
        entry["completed_at"] = getattr(state, "completed_at", None)
        entry["quick_mode"] = bool(getattr(state, "quick_mode", False))

    records: list[dict[str, Any]] = []
    if history_path.exists():
        for line in history_path.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s:
                continue
            try:
                obj = json.loads(s)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                records.append(obj)

    records.append(entry)
    keep = max(1, int(max_entries))
    records = records[-keep:]

    history_path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=True, separators=(",", ":")) for r in records) + "\n",
        encoding="utf-8",
    )
    return history_path


def build_skill_handoff_menu(
    skill_name: str,
    state: SkillState | None = None,
    state_path: Path | None = None,
) -> str:
    """Build a numbered handoff menu for skill-chain transitions.

    User-facing stdout is text-only. When ``state_path`` is set, the AskQuestion
    payload is written to ``<state-dir>/handoff-multiselect.json`` and announced
    on stderr as ``FORGE_HANDOFF_MULTISELECT_PATH=...``.
    """
    from scripts.shared.handoff_menu import (
        build_handoff_multiselect_payload,
        emit_handoff_multiselect_path,
        format_handoff_menu_lines,
        resolve_handoff_commands,
        write_handoff_multiselect_sidecar,
    )
    from scripts.shared.skill_chain import SKILL_CHAIN

    transition = SKILL_CHAIN.get(skill_name)
    if not transition:
        return f"\nWORKFLOW HANDOFF — {skill_name} complete\n\nNo configured next skill."

    default_cmd, alternatives = resolve_handoff_commands(
        skill_name,
        state,
        default_cmd=transition.default,
        alternatives=list(transition.alternatives) or [],
    )

    if state_path is not None:
        payload = build_handoff_multiselect_payload(
            skill_name,
            default_cmd=default_cmd,
            alternatives=alternatives,
            state_path=state_path,
        )
        write_handoff_multiselect_sidecar(state_path, payload)
        # Do not emit path here — clear_state_file archives the session dir;
        # skill_runner re-emits FORGE_HANDOFF_MULTISELECT_PATH after archive.

    return "\n".join(
        format_handoff_menu_lines(
            skill_name,
            default_cmd=default_cmd,
            alternatives=alternatives,
            state_path=state_path,
        )
    )
