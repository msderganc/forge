"""Skill handoff menu resolution and formatting."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from scripts.shared.skill_state import SkillState

HANDOFF_MULTISELECT_FILENAME = "handoff-multiselect.json"
FORGE_HANDOFF_MULTISELECT_PATH_PREFIX = "FORGE_HANDOFF_MULTISELECT_PATH="


def resolve_next_skill(
    skill_name: str,
    state: SkillState | None = None,
) -> tuple[str | None, list[str]]:
    """Single authority for default next skill + alternatives.

    ``SKILL_CHAIN`` provides base data; context overrides live here only.
    """
    from scripts.shared.skill_chain import SKILL_CHAIN

    chain = SKILL_CHAIN.get(skill_name)
    if chain is None:
        return None, []
    return resolve_handoff_commands(
        skill_name,
        state,
        default_cmd=chain.default or "",
        alternatives=list(chain.alternatives),
    )


def resolve_handoff_commands(
    skill_name: str,
    state: SkillState | None,
    *,
    default_cmd: str,
    alternatives: list[str],
) -> tuple[str | None, list[str]]:
    """Apply skill-specific overrides to default and alternative next commands."""
    from scripts.shared.handoff_resolvers import (
        resolve_diagnose_handoff,
        resolve_evaluate_handoff,
        resolve_test_handoff,
        resolve_ux_review_handoff,
    )

    default: str | None = default_cmd or None
    alts = list(alternatives)

    if state is None:
        return default, alts

    if skill_name == "diagnose":
        return resolve_diagnose_handoff(state, default, alts)
    if skill_name == "test":
        return resolve_test_handoff(state, default, alts)
    if skill_name == "evaluate":
        return resolve_evaluate_handoff(
            state, default, alts, alternatives=alternatives
        )
    if skill_name == "ux-review":
        return resolve_ux_review_handoff(state, default, alts)

    return default, alts


def _handoff_option_rows(
    *,
    default_cmd: str | None,
    alternatives: list[str],
) -> list[tuple[str, str, bool]]:
    """Return ``(chain_cmd, description, is_default)`` rows for menu + multiselect."""
    from scripts.shared.skill_chain import COMMAND_DESCRIPTIONS

    rows: list[tuple[str, str, bool]] = []
    if default_cmd:
        rows.append(
            (default_cmd, COMMAND_DESCRIPTIONS.get(default_cmd, ""), True),
        )
    for alt_cmd in alternatives:
        rows.append((alt_cmd, COMMAND_DESCRIPTIONS.get(alt_cmd, ""), False))
    return rows


def chain_command_slug(chain_cmd: str) -> str:
    """Stable AskQuestion id (no spaces)."""
    tokens = [t.lstrip("-").replace("_", "-") for t in chain_cmd.strip().split()]
    return "-".join(tokens)


def build_handoff_multiselect_payload(
    skill_name: str,
    *,
    default_cmd: str | None,
    alternatives: list[str],
    state_path: object | None = None,
) -> dict[str, Any]:
    """Machine-readable handoff for agent AskQuestion (``allow_multiple: true``)."""
    from scripts.shared.workflow_tokens import chain_command_to_agent_invocation

    options: list[dict[str, str]] = []
    default_ids: list[str] = []

    for chain_cmd, desc, is_default in _handoff_option_rows(
        default_cmd=default_cmd,
        alternatives=alternatives,
    ):
        inv = chain_command_to_agent_invocation(chain_cmd)
        label = inv if not desc else f"{inv} — {desc}"
        if is_default:
            label += " (default)"
            default_ids.append(chain_command_slug(chain_cmd))
        options.append(
            {
                "id": chain_command_slug(chain_cmd),
                "chain_cmd": chain_cmd,
                "label": label,
            }
        )

    options.append({"id": "stop", "label": "(stop) — exit the workflow here"})

    payload: dict[str, Any] = {
        "type": "forge_handoff_multiselect",
        "skill": skill_name,
        "allow_multiple": True,
        "title": f"What next after {skill_name}?",
        "prompt": "What should we do next? You can pick more than one.",
        "options": options,
        "default_option_ids": default_ids,
        "shortcuts": {
            "default": 'Reply "yes" or "1" for the default only.',
            "stop": 'Reply "stop" to exit without running another skill.',
        },
    }
    if state_path:
        payload["state_file"] = str(state_path)
    return payload


def format_handoff_multiselect_block(
    skill_name: str,
    *,
    default_cmd: str | None,
    alternatives: list[str],
    state_path: object | None = None,
) -> str:
    """Fenced JSON block for tests/tooling — not for user-facing footers."""
    payload = build_handoff_multiselect_payload(
        skill_name,
        default_cmd=default_cmd,
        alternatives=alternatives,
        state_path=state_path,
    )
    body = json.dumps(payload, indent=2, ensure_ascii=True)
    return f"```handoff-multiselect\n{body}\n```"


def handoff_multiselect_sidecar_path(state_path: Path | str) -> Path:
    """``<state-dir>/handoff-multiselect.json`` beside session.json or legacy state."""
    return Path(state_path).resolve().parent / HANDOFF_MULTISELECT_FILENAME


def write_handoff_multiselect_sidecar(
    state_path: Path | str,
    payload: dict[str, Any],
) -> Path:
    """Write machine payload next to the state file; return the written path."""
    path = handoff_multiselect_sidecar_path(state_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    return path


def locate_handoff_multiselect_sidecar(state_path: Path | str) -> Path | None:
    """Find sidecar at the live state dir or under ``sessions/_archive`` after clear."""
    path = Path(state_path)
    live = handoff_multiselect_sidecar_path(path)
    if live.is_file():
        return live

    from scripts.shared.session_store import (
        ARCHIVE_DIRNAME,
        SESSIONS_DIRNAME,
        is_session_state_path,
        session_id_from_state_path,
        sessions_archive_root,
    )

    if not is_session_state_path(path):
        return None
    sid = session_id_from_state_path(path)
    if not sid:
        return None

    # Prefer archive root derived from the original live path's sessions parent.
    try:
        sessions_parent = path.resolve().parent.parent
        if sessions_parent.name == SESSIONS_DIRNAME:
            archived = (
                sessions_parent / ARCHIVE_DIRNAME / sid / HANDOFF_MULTISELECT_FILENAME
            )
            if archived.is_file():
                return archived.resolve()
    except OSError:
        pass

    archived = sessions_archive_root() / sid / HANDOFF_MULTISELECT_FILENAME
    if archived.is_file():
        return archived.resolve()
    return None


def emit_handoff_multiselect_path(
    state_path: Path | str | None,
    *,
    path: Path | None = None,
) -> Path | None:
    """Print ``FORGE_HANDOFF_MULTISELECT_PATH=...`` on stderr when a sidecar exists."""
    if path is None:
        if state_path is None:
            return None
        path = locate_handoff_multiselect_sidecar(state_path)
    if path is None or not path.is_file():
        return None
    print(f"{FORGE_HANDOFF_MULTISELECT_PATH_PREFIX}{path}", file=sys.stderr)
    return path


def format_handoff_menu_lines(
    skill_name: str,
    *,
    default_cmd: str | None,
    alternatives: list[str],
    state_path: object | None = None,
) -> list[str]:
    """User-facing numbered handoff menu (no JSON / AskQuestion dump)."""
    from scripts.shared.workflow_tokens import (
        chain_command_to_agent_invocation,
        workflow_invocation_prefix,
    )

    prefix = workflow_invocation_prefix()
    lines = [
        "",
        f"WORKFLOW HANDOFF — {skill_name} complete",
        "=" * (len(skill_name) + 22),
        "",
    ]

    option_num = 1
    rows = _handoff_option_rows(default_cmd=default_cmd or None, alternatives=alternatives)

    if default_cmd:
        lines.append(
            f'Reply **"yes"** or **"1"** for the default, or pick numbers '
            f"(prefix `{prefix}`):"
        )
        lines.append("")
        inv = chain_command_to_agent_invocation(default_cmd)
        desc = rows[0][1] if rows else ""
        desc_text = f" — {desc}" if desc else ""
        lines.append(f"  {option_num}. `{inv}`{desc_text} **(default)**")
        option_num += 1
        for chain_cmd, desc, _ in rows[1:]:
            inv = chain_command_to_agent_invocation(chain_cmd)
            desc_text = f" — {desc}" if desc else ""
            lines.append(f"  {option_num}. `{inv}`{desc_text}")
            option_num += 1
    else:
        lines.append("**(none — workflow terminates here)**")
        lines.append("")
        for chain_cmd, desc, _ in rows:
            inv = chain_command_to_agent_invocation(chain_cmd)
            desc_text = f" — {desc}" if desc else ""
            lines.append(f"  {option_num}. `{inv}`{desc_text}")
            option_num += 1

    lines.extend(
        [
            f"  {option_num}. `(stop)` — exit the workflow here",
            "",
            f"Resume any time: `forge takeover` or `{chain_command_to_agent_invocation('takeover')}`",
        ]
    )
    if state_path:
        lines.append(f"**State file:** `{state_path}`")
    return lines
