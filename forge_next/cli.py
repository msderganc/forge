from __future__ import annotations

import argparse
import os
import sys

from forge_next.cli_inspect import (
    capture_human_output,
    run_doctor,
    run_status,
    summarize_orchestrator_output,
)
from forge_next.cli_install import run_install, run_uninstall
from forge_next.cli_runtime import repo_root_from_args, resolve_repo_root, run_module_main


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="forge", description="Forge Codex launcher CLI")
    sub = p.add_subparsers(dest="command", required=True)

    def add_common_repo_flag(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--repo", type=str, default=None, help="Target repo root (defaults to cwd auto-detected)")

    def add_common_output_flags(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--json", action="store_true", dest="json_output", help="Emit a JSON summary on stdout (human output on stderr)")
        sp.add_argument("--ascii", action="store_true", help="Prefer ASCII-only output")

    def add_session_flags(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--session", type=str, default=None, help="Session id to continue")
        sp.add_argument("--label", type=str, default=None, help="Label for a new session (step 1)")
        sp.add_argument(
            "--parallel",
            action="store_true",
            help="Deprecated: step 1 always creates a new session",
        )

    def add_workflow_phase_flags(sp: argparse.ArgumentParser) -> None:
        step_group = sp.add_mutually_exclusive_group(required=False)
        step_group.add_argument(
            "--step",
            type=int,
            default=None,
            help="Phase number (optional when --session or --state resumes a session)",
        )
        step_group.add_argument(
            "--phase",
            type=str,
            default=None,
            metavar="NAME",
            help="Named workflow phase (optional when resuming with --session or --state)",
        )

    def add_ceremony_flag(sp: argparse.ArgumentParser) -> None:
        sp.add_argument(
            "--ceremony",
            choices=["light", "medium", "detailed", "comprehensive"],
            default=None,
            help="Process depth band (overrides estimate).",
        )

    # evaluate
    ev = sub.add_parser("evaluate", help="Run the evaluate orchestrator")
    add_common_repo_flag(ev)
    add_common_output_flags(ev)
    add_session_flags(ev)
    add_workflow_phase_flags(ev)
    ev.add_argument("--plan", type=str)
    ev.add_argument("--state", type=str)
    ev.add_argument("--mode", choices=["pre", "post", "review"])
    ev.add_argument("--team", action="store_true")
    add_ceremony_flag(ev)
    ev.add_argument(
        "--quick",
        action="store_true",
        help="Small-ceremony evaluate: skip heavy pre/post phases",
    )
    ev.add_argument(
        "--effort",
        choices=["small", "medium", "large", "lite", "light", "standard", "thorough"],
        default=None,
        help="Override size/ceremony tier (small skips heavy phases)",
    )
    # sketch (pre-design intent organization)
    sk = sub.add_parser(
        "sketch",
        help="Organize intent and decisions before design (optional domain docs)",
    )
    add_common_repo_flag(sk)
    add_common_output_flags(sk)
    add_session_flags(sk)
    add_workflow_phase_flags(sk)
    sk.add_argument("--state", type=str)
    sk.add_argument(
        "--with-domain-docs",
        action="store_true",
        help="Allow CONTEXT.md glossary and sparse docs/adr/ updates",
    )

    # design (investigation + named design spec)
    dn = sub.add_parser(
        "design",
        help="Investigate, brainstorm, and write a named design spec (medium/large)",
    )
    add_common_repo_flag(dn)
    add_common_output_flags(dn)
    add_session_flags(dn)
    add_workflow_phase_flags(dn)
    dn.add_argument("--state", type=str)
    dn.add_argument("--quick", action="store_true")
    add_ceremony_flag(dn)
    dn.add_argument("--auto1", action="store_true")
    dn.add_argument("--auto2", action="store_true")
    dn.add_argument("--auto3", action="store_true")
    dn.add_argument(
        "--allow-spec-incomplete",
        action="store_true",
        help="Bypass design-spec gate on step 8 (requires override reason + follow-up)",
    )
    dn.add_argument("--spec-override-reason", type=str, default=None)
    dn.add_argument("--spec-override-follow-up", type=str, default=None)
    dn.add_argument("--spec-override-requested-by", type=str, default=None)
    dn.add_argument(
        "--allow-issues-incomplete",
        action="store_true",
        help="Bypass spec→issues gate on step 8 (requires override reason + follow-up)",
    )
    dn.add_argument("--issues-override-reason", type=str, default=None)
    dn.add_argument("--issues-override-follow-up", type=str, default=None)
    dn.add_argument("--issues-override-requested-by", type=str, default=None)

    # develop (deprecated alias for design)
    dv = sub.add_parser("develop", help="Deprecated alias for forge design")
    add_common_repo_flag(dv)
    add_common_output_flags(dv)
    add_session_flags(dv)
    add_workflow_phase_flags(dv)
    dv.add_argument("--state", type=str)
    dv.add_argument("--quick", action="store_true")
    add_ceremony_flag(dv)
    dv.add_argument("--auto1", action="store_true")
    dv.add_argument("--auto2", action="store_true")
    dv.add_argument("--auto3", action="store_true")
    dv.add_argument("--allow-spec-incomplete", action="store_true")
    dv.add_argument("--spec-override-reason", type=str, default=None)
    dv.add_argument("--spec-override-follow-up", type=str, default=None)
    dv.add_argument("--spec-override-requested-by", type=str, default=None)
    dv.add_argument("--allow-issues-incomplete", action="store_true")
    dv.add_argument("--issues-override-reason", type=str, default=None)
    dv.add_argument("--issues-override-follow-up", type=str, default=None)
    dv.add_argument("--issues-override-requested-by", type=str, default=None)

    # plan
    pl = sub.add_parser("plan", help="Run the plan orchestrator")
    add_common_repo_flag(pl)
    add_common_output_flags(pl)
    add_session_flags(pl)
    add_workflow_phase_flags(pl)
    pl.add_argument("--state", type=str)
    pl.add_argument("--quick", action="store_true")
    add_ceremony_flag(pl)
    pl.add_argument("--force", action="store_true")
    pl.add_argument(
        "--save-ceremony-preference",
        action="store_true",
        help="With --ceremony, persist that band as the default for future plan sessions",
    )

    # implement
    im = sub.add_parser("implement", help="Run the implement orchestrator")
    add_common_repo_flag(im)
    add_common_output_flags(im)
    add_session_flags(im)
    add_workflow_phase_flags(im)
    im.add_argument("--state", type=str)
    im.add_argument("--quick", action="store_true")
    add_ceremony_flag(im)
    im.add_argument("--plan", type=str, default=None, help="Path to plan file (implement step 1)")
    im.add_argument(
        "--branch-prefix",
        type=str,
        choices=("feat", "fix", "chore", "refactor", "docs", "hotfix"),
        default=None,
        help="Git branch prefix for feature/task branches (default: feat; stored in state on step 1)",
    )

    # ship (graphify preflight + ship skill handoff)
    sh = sub.add_parser(
        "ship",
        help="Ship preflight: refresh Graphify index before commit/PR (then follow ship skill)",
    )
    add_common_repo_flag(sh)
    add_common_output_flags(sh)
    add_workflow_phase_flags(sh)

    # code-review
    cr = sub.add_parser("code-review", help="Run the code-review orchestrator")
    add_common_repo_flag(cr)
    add_common_output_flags(cr)
    add_session_flags(cr)
    add_workflow_phase_flags(cr)
    cr.add_argument("--state", type=str)
    cr.add_argument("--quick", action="store_true")
    add_ceremony_flag(cr)
    cr.add_argument(
        "--effort",
        type=str,
        choices=["light", "standard", "thorough"],
        default=None,
        help="Review effort alias for --ceremony (light→light, standard→medium, thorough→comprehensive)",
    )
    cr_struct = cr.add_mutually_exclusive_group()
    cr_struct.add_argument(
        "--structural",
        dest="structural",
        action="store_true",
        default=None,
        help="Run structural probes + eight-agent Pass B at step 3",
    )
    cr_struct.add_argument(
        "--no-structural",
        dest="structural",
        action="store_false",
        help="Skip structural probes and eight-agents",
    )
    cr.add_argument(
        "--plan",
        type=str,
        default=None,
        help="Optional plan path or keywords (repo + native Cursor/Claude/Codex plan folders)",
    )
    cr.add_argument(
        "--mode", type=str, choices=["pr", "deep", "architecture"], default=None,
        help="Review mode (optional; auto-detected if omitted)",
    )
    cr.add_argument(
        "--target",
        nargs="+",
        default=None,
        help="PR number, branch name, or paths to review",
    )
    cr.add_argument(
        "--allow-structural-probes-incomplete",
        action="store_true",
        help="Bypass structural probes gate on steps 4+ (requires override reason + follow-up)",
    )
    cr.add_argument("--structural-probes-override-reason", type=str, default=None)
    cr.add_argument("--structural-probes-override-follow-up", type=str, default=None)

    # test
    ts = sub.add_parser("test", help="Run the test orchestrator")
    add_common_repo_flag(ts)
    add_common_output_flags(ts)
    add_session_flags(ts)
    add_workflow_phase_flags(ts)
    ts.add_argument("--state", type=str)
    ts.add_argument("--quick", action="store_true")
    add_ceremony_flag(ts)
    ts.add_argument("--mode", choices=["run", "flows", "ux"],
                    help="run|flows; 'ux' exits with redirect to forge ux-review")
    ts.add_argument(
        "--target",
        nargs="+",
        default=None,
        help="Test command, path, or pattern to run",
    )

    # ux-review (product UX audit in a real browser)
    ux = sub.add_parser(
        "ux-review",
        help="Real-browser product UX audit (pages, controls, states, prioritized report)",
    )
    add_common_repo_flag(ux)
    add_common_output_flags(ux)
    add_session_flags(ux)
    add_workflow_phase_flags(ux)
    ux.add_argument("--state", type=str)
    ux.add_argument("--quick", action="store_true")
    ux.add_argument(
        "--base-url",
        type=str,
        default=None,
        help="Application base URL to review",
    )

    # diagnose
    dg = sub.add_parser("diagnose", help="Run the diagnose orchestrator")
    add_common_repo_flag(dg)
    add_common_output_flags(dg)
    add_session_flags(dg)
    add_workflow_phase_flags(dg)
    dg.add_argument("--state", type=str)
    dg.add_argument("--quick", action="store_true")
    add_ceremony_flag(dg)

    # takeover (meta-workflow — replaces resume + iterate)
    to = sub.add_parser(
        "takeover",
        help="Infer epic and drive Forge skills until ship-ready",
    )
    add_common_repo_flag(to)
    add_common_output_flags(to)
    add_session_flags(to)
    add_workflow_phase_flags(to)
    to.add_argument("--state", type=str)
    to.add_argument("--issue", type=str)
    to.add_argument("--design", type=str)
    to.add_argument("--goal", type=str)
    to.add_argument("--cleanup", action="store_true")
    to.add_argument("--force", action="store_true")
    to.add_argument("--all-stale", action="store_true", dest="all_stale")

    # status
    st = sub.add_parser("status", help="Show workflow status (dashboard)")
    add_common_repo_flag(st)
    add_common_output_flags(st)

    # doctor
    doc = sub.add_parser("doctor", help="Diagnose installation and environment issues")
    add_common_repo_flag(doc)
    add_common_output_flags(doc)

    # session — manage parallel workflow sessions
    sess = sub.add_parser("session", help="Manage workflow sessions")
    add_common_repo_flag(sess)
    add_common_output_flags(sess)
    sess_sub = sess.add_subparsers(dest="session_cmd", required=True)
    sess_close = sess_sub.add_parser("close", help="Archive a session by id")
    sess_close.add_argument("session_id", type=str, help="Session id to archive")

    # graphify (optional codebase index + post-commit hook)
    gf = sub.add_parser("graphify", help="Optional Graphify index refresh and git post-commit hook")
    gf_sub = gf.add_subparsers(dest="graphify_cmd", required=True)
    gfr = gf_sub.add_parser("refresh", help="Run Graphify if available; write graphify-status.json")
    gfr.add_argument(
        "--foreground",
        action="store_true",
        help="Run refresh in this process and wait for completion (default: background)",
    )
    gfr.add_argument(
        "--background",
        action="store_true",
        help="Detached refresh (default; kept for scripts that pass it explicitly)",
    )
    gfr.add_argument(
        "--force",
        action="store_true",
        help="Background: spawn even when status looks fresh; foreground: always run update",
    )
    add_common_repo_flag(gfr)
    gfi = gf_sub.add_parser("install-hook", help="Add fail-soft Graphify block to .git/hooks/post-commit")
    add_common_repo_flag(gfi)
    gfu = gf_sub.add_parser("uninstall-hook", help="Remove Forge Graphify block from .git/hooks/post-commit")
    add_common_repo_flag(gfu)
    gfo = gf_sub.add_parser(
        "off",
        help="Disable Graphify banners, hooks, and auto-refresh for this repo (persisted)",
    )
    add_common_repo_flag(gfo)
    gfn = gf_sub.add_parser("on", help="Re-enable Graphify enforcement (clear repo off prefs)")
    add_common_repo_flag(gfn)
    gfs = gf_sub.add_parser("status", help="Show Graphify enforcement state for this repo")
    add_common_repo_flag(gfs)
    gfd = gf_sub.add_parser(
        "defer-waves",
        help="Defer GRAPHIFY banners during implement wave steps 3–5 (persisted)",
    )
    add_common_repo_flag(gfd)
    gfud = gf_sub.add_parser(
        "undefer-waves",
        help="Clear implement wave defer; GRAPHIFY shows on every implement step again",
    )
    add_common_repo_flag(gfud)

    # Studio is dispatched in main() before build_parser() so it never appears in `forge --help`.

    # install
    ins = sub.add_parser("install", help="Install integrations (Cursor/Claude/Codex) for this user")
    add_common_output_flags(ins)
    ins.add_argument("--ref", type=str, default="main", help="Git ref/branch for downloads (default: main)")
    ins.add_argument("--repo-url", type=str, default="https://github.com/msderganc/forge", help="Forge repo URL for integration downloads")
    ins.add_argument("--cursor", action="store_true", help="Install Cursor plugin")
    ins.add_argument("--claude", action="store_true", help="Install Claude command pack")
    ins.add_argument("--codex", action="store_true", help="Install Codex skill pack")
    ins.add_argument("--all", action="store_true", help="Install all integrations (default if none selected)")
    ins.add_argument("--cursor-dir", type=str, default=None, help="Override Cursor local plugins directory")
    ins.add_argument("--claude-dir", type=str, default=None, help="Override Claude commands install directory")
    ins.add_argument("--codex-dir", type=str, default=None, help="Override Codex skills install directory")
    ins.add_argument(
        "--skip-structural-tools",
        action="store_true",
        help="Skip installing knip, madge (npm), and pyscn (default: install with forge install)",
    )

    # structural-tools — knip, madge, pyscn for Pass B quality probes
    st_tools = sub.add_parser(
        "structural-tools",
        help="Install knip, madge, and pyscn for structural quality probes",
    )
    add_common_output_flags(st_tools)
    st_sub = st_tools.add_subparsers(dest="structural_tools_cmd", required=True)
    st_sub.add_parser("install", help="Install tools under the Forge-managed prefix")

    # structural-probes — run agent-selected knip/madge/pyscn/skylos after plan sidecar
    st_probes = sub.add_parser(
        "structural-probes",
        help="Run knip/madge/pyscn/skylos per .structural-probes-plan.json beside session state",
    )
    add_common_repo_flag(st_probes)
    add_common_output_flags(st_probes)
    st_probes_sub = st_probes.add_subparsers(dest="structural_probes_cmd", required=True)
    st_run = st_probes_sub.add_parser(
        "run",
        help="Execute tools listed in the probe plan; write .structural-probes.json",
    )
    st_run.add_argument(
        "--state-dir",
        type=str,
        required=True,
        help="Workflow state directory containing .structural-probes-plan.json",
    )
    st_run.add_argument(
        "--tools",
        type=str,
        default=None,
        help="Override plan: comma-separated knip,madge,jscn,pyscn,skylos",
    )

    # codex-agents — merge ~/.codex/config.toml delegation snippet for Forge skills
    ca = sub.add_parser(
        "codex-agents",
        help="Configure ~/.codex/config.toml so forge:* skills may use Codex sub-agents",
    )
    ca.add_argument("--config", type=str, default=None, help="Path to config.toml (default: ~/.codex/config.toml)")
    ca.add_argument("--force", action="store_true", help="Replace existing developer_instructions")
    ca.add_argument("--dry-run", action="store_true", help="Print actions without writing")

    # claude-graphify — merge Graphify hooks into ~/.claude/settings.json
    cg = sub.add_parser(
        "claude-graphify",
        help="Install Graphify hooks in Claude Code settings.json (all tools + forge prompts)",
    )
    cg.add_argument(
        "--settings",
        type=str,
        default=None,
        help="Path to settings.json (default: ~/.claude/settings.json)",
    )
    cg.add_argument("--dry-run", action="store_true", help="Print actions without writing")

    # claude-graphify-hook — Claude Code hook entrypoint (stdin JSON → stdout JSON)
    cgh = sub.add_parser(
        "claude-graphify-hook",
        help="Run a Claude Code Graphify hook event (used from ~/.claude/settings.json)",
    )
    cgh.add_argument(
        "event",
        nargs="?",
        default="SessionStart",
        choices=("SessionStart", "PreToolUse", "UserPromptSubmit"),
        help="Claude hook event name",
    )

    # cursor-subagent-hooks — merge lifecycle hooks into .cursor/hooks.json
    csh = sub.add_parser(
        "cursor-subagent-hooks",
        help="Install Cursor hooks to close unused sub-agents before each tool call",
    )
    csh.add_argument("--repo", type=str, default=None, help="Repo root (default: cwd)")
    csh.add_argument("--dry-run", action="store_true", help="Print merged hooks.json without writing")

    # cursor-subagent-hook — Cursor hook entrypoint (stdin JSON → stdout JSON)
    cshk = sub.add_parser(
        "cursor-subagent-hook",
        help="Run a Cursor sub-agent lifecycle hook event (used from .cursor/hooks.json)",
    )
    cshk.add_argument(
        "event",
        nargs="?",
        default="preToolUse",
        choices=("preToolUse", "subagentStart", "subagentStop", "postToolUse"),
        help="Cursor hook event name",
    )

    # uninstall
    un = sub.add_parser("uninstall", help="Uninstall integrations (Cursor/Claude/Codex) for this user")
    add_common_output_flags(un)
    un.add_argument("--cursor", action="store_true", help="Uninstall Cursor plugin")
    un.add_argument("--claude", action="store_true", help="Uninstall Claude command pack")
    un.add_argument("--codex", action="store_true", help="Uninstall Codex skill pack")
    un.add_argument("--all", action="store_true", help="Uninstall all integrations (default if none selected)")
    un.add_argument("--cursor-dir", type=str, default=None, help="Override Cursor local plugins directory")
    un.add_argument("--claude-dir", type=str, default=None, help="Override Claude commands install directory")
    un.add_argument("--codex-dir", type=str, default=None, help="Override Codex skills install directory")

    return p


def main(argv: list[str] | None = None) -> None:
    from forge_next import cli_dispatch

    os.environ.setdefault("FORGE_USE_LAUNCHER", "1")
    os.environ.setdefault("PYTHONUTF8", "1")
    try:
        # Ensure Unicode prompt output works on Windows terminals.
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    raw_argv = list(argv) if argv is not None else sys.argv[1:]
    studio_rc = cli_dispatch.try_studio_argv(raw_argv)
    if studio_rc is not None:
        raise SystemExit(studio_rc)

    parser = build_parser()
    args = parser.parse_args(raw_argv)

    cmd = args.command
    if getattr(args, "ascii", False):
        os.environ["FORGE_ASCII"] = "1"

    raise SystemExit(cli_dispatch.dispatch_command(cmd, args))


# Backward-compatible aliases for tests and studio
_repo_root_from_args = repo_root_from_args
_run_module_main = run_module_main
_run_status = run_status
_run_doctor = run_doctor


if __name__ == "__main__":
    main()
