"""Dispatch table for forge CLI integration commands (keeps cli.main thin)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from forge_next.cli_inspect import capture_human_output, run_doctor, run_status, summarize_orchestrator_output
from forge_next.cli_install import run_install, run_uninstall
from forge_next.cli_runtime import repo_root_from_args, run_module_main

_WORKFLOW_MODULES = {
    "evaluate": "scripts.evaluate.evaluate",
    "design": "scripts.design.design",
    "develop": "scripts.design.design",
    "plan": "scripts.plan.plan",
    "implement": "scripts.implement.implement",
    "code-review": "scripts.code_review.code_review",
    "test": "scripts.test.test",
    "ux-review": "scripts.ux_review.ux_review",
    "diagnose": "scripts.diagnose.orchestrate",
    "takeover": "scripts.takeover.takeover",
    "ship": "scripts.ship.ship",
    # Kill-switch FORGE_SKILL_ENGINE=0 is honored inside the skill shim
    # (scripts.sketch.sketch → sketch_legacy). Dispatch always targets the shim.
    "sketch": "scripts.sketch.sketch",
}


def try_studio_argv(raw_argv: list[str]) -> int | None:
    if not raw_argv or raw_argv[0] != "studio":
        return None
    from forge_next.studio.cli_commands import parse_studio_argv, run_studio_command

    return run_studio_command(parse_studio_argv(raw_argv[1:]))


def dispatch_codex_agents(args: Any) -> int:
    from forge_next.codex_agents import apply_codex_agents_config, default_codex_config_path

    cfg = (
        Path(getattr(args, "config", None)).expanduser()
        if getattr(args, "config", None)
        else default_codex_config_path()
    )
    return apply_codex_agents_config(
        cfg,
        force=bool(getattr(args, "force", False)),
        dry_run=bool(getattr(args, "dry_run", False)),
    )


def dispatch_claude_graphify(args: Any) -> int:
    from forge_next.claude_graphify import apply_claude_graphify_settings, default_claude_settings_path

    sp = (
        Path(getattr(args, "settings", None)).expanduser()
        if getattr(args, "settings", None)
        else default_claude_settings_path()
    )
    return apply_claude_graphify_settings(sp, dry_run=bool(getattr(args, "dry_run", False)))


def dispatch_claude_graphify_hook(args: Any) -> int:
    from forge_next.hooks import claude_graphify_hook

    event = getattr(args, "event", None) or "SessionStart"
    return claude_graphify_hook.main([event])


def dispatch_cursor_subagent_hooks(args: Any) -> int:
    from forge_next.cursor_subagent_hooks import apply_cursor_subagent_hooks

    root = Path(getattr(args, "repo", None)).expanduser() if getattr(args, "repo", None) else Path.cwd()
    return apply_cursor_subagent_hooks(root.resolve(), dry_run=bool(getattr(args, "dry_run", False)))


def dispatch_cursor_subagent_hook(args: Any) -> int:
    from forge_next.hooks import cursor_subagent_hook

    event = getattr(args, "event", None) or "preToolUse"
    return cursor_subagent_hook.main([event])


def dispatch_graphify(args: Any) -> int:
    from forge_next import graphify as forge_graphify

    rr = repo_root_from_args(getattr(args, "repo", None))
    subc = getattr(args, "graphify_cmd", None)
    handlers = {
        "refresh": lambda: forge_graphify.refresh(
            rr,
            background=not bool(getattr(args, "foreground", False)),
            force=bool(getattr(args, "force", False)),
        ),
        "install-hook": lambda: _graphify_msg(forge_graphify.install_post_commit_hook(rr)),
        "uninstall-hook": lambda: _graphify_msg(forge_graphify.uninstall_post_commit_hook(rr)),
        "off": lambda: _graphify_msg(forge_graphify.graphify_set_disabled(rr, disabled=True)),
        "on": lambda: _graphify_msg(forge_graphify.graphify_set_disabled(rr, disabled=False)),
        "status": lambda: _graphify_msg(forge_graphify.graphify_status_message(rr)),
        "defer-waves": lambda: _graphify_msg(forge_graphify.graphify_set_defer_implement_waves(rr, defer=True)),
        "undefer-waves": lambda: _graphify_msg(forge_graphify.graphify_set_defer_implement_waves(rr, defer=False)),
    }
    if subc not in handlers:
        print(f"Unknown graphify subcommand: {subc!r}", file=sys.stderr)
        return 1
    return handlers[subc]()


def _graphify_msg(pair: tuple[bool, str]) -> int:
    ok, msg = pair
    print(msg)
    return 0 if ok else 1


def dispatch_structural_tools(args: Any) -> int:
    from forge_next.structural_tools import install_structural_tools, structural_tools_install_notice_lines

    subc = getattr(args, "structural_tools_cmd", None)
    if subc != "install":
        print(f"Unknown structural-tools subcommand: {subc!r}", file=sys.stderr)
        return 1
    result = install_structural_tools()
    if getattr(args, "json_output", False):
        payload = {
            "command": "structural-tools.install",
            "result": result.to_dict(),
            "error": None if result.ok else "install incomplete",
        }
        print(json.dumps(payload, ensure_ascii=True))
    else:
        title = (
            "forge - structural-tools install"
            if os.environ.get("FORGE_ASCII") == "1"
            else "forge — structural-tools install"
        )
        print(title)
        print("=" * 60)
        for line in structural_tools_install_notice_lines(result):
            print(line.rstrip())
    return 0 if result.ok else 1


def dispatch_structural_probes(args: Any) -> int:
    from scripts.shared.structural_probes import (
        format_probe_results_banner,
        probe_payload_exit_code,
        run_probes_from_state_dir,
        sidecar_path,
    )

    subc = getattr(args, "structural_probes_cmd", None)
    if subc != "run":
        print(f"Unknown structural-probes subcommand: {subc!r}", file=sys.stderr)
        return 1
    repo_root = repo_root_from_args(getattr(args, "repo", None))
    state_dir = Path(getattr(args, "state_dir", "")).resolve()
    tools_arg = getattr(args, "tools", None)
    tools = None
    if tools_arg:
        tools = [t.strip().lower() for t in tools_arg.split(",") if t.strip()]
    payload = run_probes_from_state_dir(repo_root, state_dir, tools=tools)
    sc = sidecar_path(state_dir)
    banner = format_probe_results_banner(payload, sc)
    if getattr(args, "json_output", False):
        out = {
            "command": "structural-probes.run",
            "repo_root": str(repo_root),
            "state_dir": str(state_dir),
            "sidecar": str(sc) if sc else None,
            "payload": payload,
            "error": None,
        }
        exit_code = probe_payload_exit_code(payload)
        if exit_code != 0:
            out["error"] = "structural probes failed or did not execute"
        print(json.dumps(out, ensure_ascii=True))
        if banner.strip():
            print(banner, file=sys.stderr)
        return exit_code
    print(banner)
    return probe_payload_exit_code(payload)


_INTEGRATION_HANDLERS: dict[str, Any] = {
    "codex-agents": dispatch_codex_agents,
    "claude-graphify": dispatch_claude_graphify,
    "claude-graphify-hook": dispatch_claude_graphify_hook,
    "cursor-subagent-hooks": dispatch_cursor_subagent_hooks,
    "cursor-subagent-hook": dispatch_cursor_subagent_hook,
    "graphify": dispatch_graphify,
    "structural-tools": dispatch_structural_tools,
    "structural-probes": dispatch_structural_probes,
}


def _add_flag(out: list[str], flag: str, value: object) -> None:
    if value is None:
        return
    if isinstance(value, bool):
        if value:
            out.append(flag)
        return
    if isinstance(value, (list, tuple)):
        if not value:
            return
        out.append(flag)
        out.extend(str(v) for v in value)
        return
    out.extend([flag, str(value)])


def _passthrough_argv(args: Any) -> list[str]:
    passthrough: list[str] = []
    _add_flag(passthrough, "--step", getattr(args, "step", None))
    _add_flag(passthrough, "--phase", getattr(args, "phase", None))
    _add_flag(passthrough, "--plan", getattr(args, "plan", None))
    _add_flag(passthrough, "--branch-prefix", getattr(args, "branch_prefix", None))
    _add_flag(passthrough, "--state", getattr(args, "state", None))
    _add_flag(passthrough, "--session", getattr(args, "session", None))
    _add_flag(passthrough, "--label", getattr(args, "label", None))
    _add_flag(passthrough, "--parallel", getattr(args, "parallel", None))
    _add_flag(passthrough, "--mode", getattr(args, "mode", None))
    _add_flag(passthrough, "--ceremony", getattr(args, "ceremony", None))
    _add_flag(passthrough, "--base-url", getattr(args, "base_url", None))
    _add_flag(passthrough, "--save-mode-preference", getattr(args, "save_mode_preference", None))
    _add_flag(passthrough, "--team", getattr(args, "team", None))
    _add_flag(passthrough, "--quick", getattr(args, "quick", None))
    _add_flag(passthrough, "--effort", getattr(args, "effort", None))
    # Tri-state: None=default, True=--structural, False=--no-structural
    structural = getattr(args, "structural", None)
    if structural is True:
        passthrough.append("--structural")
    elif structural is False:
        passthrough.append("--no-structural")
    _add_flag(passthrough, "--force", getattr(args, "force", None))
    _add_flag(passthrough, "--cleanup", getattr(args, "cleanup", None))
    _add_flag(passthrough, "--all-stale", getattr(args, "all_stale", None))
    _add_flag(passthrough, "--auto1", getattr(args, "auto1", None))
    _add_flag(passthrough, "--auto2", getattr(args, "auto2", None))
    _add_flag(passthrough, "--auto3", getattr(args, "auto3", None))
    _add_flag(passthrough, "--with-domain-docs", getattr(args, "with_domain_docs", None))
    _add_flag(passthrough, "--goal", getattr(args, "goal", None))
    _add_flag(passthrough, "--issue", getattr(args, "issue", None))
    _add_flag(passthrough, "--design", getattr(args, "design", None))
    _add_flag(passthrough, "--target", getattr(args, "target", None))
    _add_flag(passthrough, "--max-loops", getattr(args, "max_loops", None))
    _add_flag(passthrough, "--metric-command", getattr(args, "metric_command", None))
    _add_flag(passthrough, "--harness", getattr(args, "harness", None))
    _add_flag(passthrough, "--text", getattr(args, "text", None))
    _add_flag(
        passthrough,
        "--allow-spec-incomplete",
        getattr(args, "allow_spec_incomplete", None),
    )
    _add_flag(passthrough, "--spec-override-reason", getattr(args, "spec_override_reason", None))
    _add_flag(
        passthrough,
        "--spec-override-follow-up",
        getattr(args, "spec_override_follow_up", None),
    )
    _add_flag(
        passthrough,
        "--spec-override-requested-by",
        getattr(args, "spec_override_requested_by", None),
    )
    _add_flag(
        passthrough,
        "--allow-issues-incomplete",
        getattr(args, "allow_issues_incomplete", None),
    )
    _add_flag(
        passthrough,
        "--issues-override-reason",
        getattr(args, "issues_override_reason", None),
    )
    _add_flag(
        passthrough,
        "--issues-override-follow-up",
        getattr(args, "issues_override_follow_up", None),
    )
    _add_flag(
        passthrough,
        "--issues-override-requested-by",
        getattr(args, "issues_override_requested_by", None),
    )
    _add_flag(
        passthrough,
        "--allow-structural-probes-incomplete",
        getattr(args, "allow_structural_probes_incomplete", None),
    )
    _add_flag(
        passthrough,
        "--structural-probes-override-reason",
        getattr(args, "structural_probes_override_reason", None),
    )
    _add_flag(
        passthrough,
        "--structural-probes-override-follow-up",
        getattr(args, "structural_probes_override_follow_up", None),
    )
    return passthrough


def dispatch_session(args: Any) -> int:
    from scripts.shared.session_store import archive_session_dir

    repo_root = repo_root_from_args(getattr(args, "repo", None))
    subc = getattr(args, "session_cmd", None)
    if subc == "close":
        sid = getattr(args, "session_id", None)
        if not sid:
            print("ERROR: session id required", file=sys.stderr)
            return 1
        dest = archive_session_dir(sid, repo_root)
        if dest is None:
            print(f"ERROR: session not found: {sid}", file=sys.stderr)
            return 1
        print(f"Archived session {sid} -> {dest}")
        return 0
    print(f"Unknown session subcommand: {subc!r}", file=sys.stderr)
    return 1


def dispatch_workflow(cmd: str, args: Any) -> int:
    if cmd == "develop":
        print(
            "Warning: 'forge develop' is deprecated; use 'forge design'.",
            file=sys.stderr,
        )
    module_name = _WORKFLOW_MODULES[cmd]
    repo_root = repo_root_from_args(getattr(args, "repo", None))
    passthrough = _passthrough_argv(args)
    if getattr(args, "json_output", False):
        human_out, rc = capture_human_output(module_name, passthrough, repo_root)
        summary = summarize_orchestrator_output(
            repo_root=repo_root,
            command=cmd,
            human_output=human_out,
        )
        summary["error"] = None if rc == 0 else summary.get("error") or f"exit_code={rc}"
        print(json.dumps(summary, ensure_ascii=True))
        if human_out.strip():
            print(human_out, file=sys.stderr)
        return rc
    return run_module_main(module_name, passthrough, repo_root)


def dispatch_command(cmd: str, args: Any) -> int:
    """Return exit code for a parsed forge subcommand."""
    if cmd in _INTEGRATION_HANDLERS:
        return _INTEGRATION_HANDLERS[cmd](args)
    if cmd == "install":
        run_install(
            json_output=getattr(args, "json_output", False),
            repo_url=getattr(args, "repo_url"),
            ref=getattr(args, "ref"),
            install_cursor=bool(getattr(args, "cursor", False)),
            install_claude=bool(getattr(args, "claude", False)),
            install_codex=bool(getattr(args, "codex", False)),
            install_all=bool(getattr(args, "all", False)),
            skip_structural_tools=bool(getattr(args, "skip_structural_tools", False)),
            cursor_dir=getattr(args, "cursor_dir", None),
            claude_dir=getattr(args, "claude_dir", None),
            codex_dir=getattr(args, "codex_dir", None),
        )
        return 0
    if cmd == "uninstall":
        run_uninstall(
            json_output=getattr(args, "json_output", False),
            uninstall_cursor=bool(getattr(args, "cursor", False)),
            uninstall_claude=bool(getattr(args, "claude", False)),
            uninstall_codex=bool(getattr(args, "codex", False)),
            uninstall_all=bool(getattr(args, "all", False)),
            cursor_dir=getattr(args, "cursor_dir", None),
            claude_dir=getattr(args, "claude_dir", None),
            codex_dir=getattr(args, "codex_dir", None),
        )
        return 0
    repo_root = repo_root_from_args(getattr(args, "repo", None))
    if cmd == "doctor":
        run_doctor(repo_root, json_output=getattr(args, "json_output", False))
        return 0
    if cmd == "status":
        run_status(repo_root, json_output=getattr(args, "json_output", False))
        return 0
    if cmd == "session":
        return dispatch_session(args)
    if cmd in _WORKFLOW_MODULES:
        return dispatch_workflow(cmd, args)
    print(f"Unknown command: {cmd!r}", file=sys.stderr)
    return 1
