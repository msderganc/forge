"""Declarative skill step runner (Wave 2+).

Loads ``skills/<skill>/manifest.yaml``, runs the shared control-plane loop
(state, prompts, handoff), and invokes declared gates.

Kill-switch: set ``FORGE_SKILL_ENGINE=0`` in the skill shim (authoritative) so
``*_legacy`` modules run instead of ``run_skill``. Escapes/vars must not import
this module (acyclic: runner → vars/gates, never reverse).
"""

from __future__ import annotations

import importlib
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from scripts.evaluate.template_engine import load_template, render_template
from scripts.shared.orchestrator import (
    SkillState,
    append_skill_run_memory,
    apply_resolved_workflow_step,
    build_base_parser,
    build_next_command,
    build_skill_handoff_menu,
    check_same_skill_clobber,
    clear_state_file,
    format_step_output,
    load_state,
    now_iso,
    print_remaining_session_warning,
    resolve_step1_state_path,
    resolve_step_state_path,
    run_step1_session_hygiene,
    runtime_memory_dir,
    save_state,
    validate_state_path,
    validate_step_or_complete,
    write_handoff,
    _detect_repo_root,
)
from scripts.shared.skill_chain import SKILL_CHAIN
from scripts.shared.skill_manifest import (
    CliFlag,
    Manifest,
    ManifestGate,
    ManifestStep,
    load_manifest,
)
from scripts.shared.ceremony import (
    Ceremony,
    estimate_ceremony,
    normalize_ceremony,
)

# Env value that forces legacy orchestrator bodies (shim / optional dispatch).
SKILL_ENGINE_KILL_SWITCH = "0"


def skill_engine_enabled() -> bool:
    """Return False when ``FORGE_SKILL_ENGINE=0`` (legacy path)."""
    return os.environ.get("FORGE_SKILL_ENGINE", "1").strip() != SKILL_ENGINE_KILL_SWITCH


def resolve_callable(spec: str) -> Callable[..., Any]:
    """Resolve ``module.path:function`` to a callable."""
    if ":" not in spec:
        raise ValueError(f"Invalid callable spec {spec!r}; expected module.path:function")
    mod_name, func_name = spec.split(":", 1)
    mod = importlib.import_module(mod_name)
    fn = getattr(mod, func_name, None)
    if not callable(fn):
        raise ValueError(f"Callable {spec!r} is missing or not callable")
    return fn


def run_declared_gates(
    manifest: Manifest,
    state: SkillState,
    step: int,
    *,
    state_path: Path,
) -> None:
    """Run gates whose ``steps`` contain ``step``. Empty list is a no-op.

    Supports ``kind: schema`` (``schema_gate.run_schema_gate``) and
    ``kind: python`` callables. Failures should exit via
    ``workflow_gate.exit_if_gate_fails`` (soft evaluate findings schemas warn).
    """
    run_declared_gates_for_view(
        _effective_view(manifest, None),
        state,
        step,
        state_path=state_path,
    )


def run_skill(skill: str, argv: list[str], *, repo_root: Path | None = None) -> int:
    """CLI entry for one skill. Returns process exit code."""
    root = Path(repo_root) if repo_root is not None else _detect_repo_root(Path.cwd())
    root = root.resolve()
    manifest = load_manifest(skill, root)
    # Parser max_step: largest variant (or top-level) so --step choices cover all modes.
    parser_max = _parser_max_step(manifest)
    if parser_max < 1:
        print(f"ERROR: skill {skill!r} has invalid max_step", file=sys.stderr)
        return 1

    parser = build_base_parser(skill, parser_max)
    _apply_cli_flags(parser, manifest.cli_flags)
    args = parser.parse_args(list(argv))

    variant_name = _select_variant_name(manifest, args, state=None)
    view = _effective_view(manifest, variant_name)
    max_step = view.max_step
    apply_resolved_workflow_step(args, skill, max_step, variant=variant_name)

    if manifest.pre_run:
        resolve_callable(manifest.pre_run)(args=args, manifest=manifest, repo_root=root)

    if validate_step_or_complete(args.step, max_step, skill):
        return 0

    step = int(args.step)

    if step == 1:
        state, state_path = _bootstrap_step1(skill, max_step, args, root)
    else:
        state, state_path = _load_step_state(skill, step, args)
        guard_code = _resume_mode_guards(skill, state, args)
        if guard_code:
            return guard_code

    # Re-select variant from persisted mode once state is loaded.
    variant_name = _select_variant_name(manifest, args, state=state)
    view = _effective_view(manifest, variant_name)
    max_step = view.max_step
    state.max_step = max_step

    step_spec = _step_spec_from_view(view, step, skill)
    phase_names = {s.step: s.phase for s in view.steps}
    phase_todos = {s.step: [dict(t) for t in s.todos] for s in view.steps}

    _apply_flag_values_to_state(state, manifest.cli_flags, args, step=step)
    # Persist CLI overrides that gates/vars read (docs override, etc.).
    _apply_override_args_to_state(state, args)
    if variant_name:
        state.custom.setdefault("mode", variant_name)
    # Dual-axis: mode selects the variant view; ceremony overlays depth/gates.
    resolve_and_persist_ceremony(state, args, step=step)
    state.current_step = step
    save_state(state, state_path)

    variables = _build_step_variables(
        step_spec, state, root, manifest, step=step, state_path=state_path
    )
    # Step-1 vars often set plan_mode / scope_tier after first estimate — refresh
    # when ceremony was only estimated (CLI/inherited stay locked).
    if step == 1 and str(state.custom.get("ceremony_source") or "") == "estimated":
        state.custom.pop("ceremony", None)
        state.custom.pop("ceremony_source", None)
        state.custom.pop("ceremony_rationale", None)
        resolve_and_persist_ceremony(state, args, step=1)
        # Plan narrative mode must track the refreshed ceremony band.
        if skill == "plan":
            band = normalize_ceremony(
                str(state.custom.get("ceremony"))
                if state.custom.get("ceremony") is not None
                else None
            )
            if band:
                from scripts.shared.ceremony import map_to_plan_mode

                state.custom["plan_mode"] = map_to_plan_mode(band)
        save_state(state, state_path)
    append_body = str(variables.pop("__APPEND__", "") or "")
    phase_label = str(variables.pop("__PHASE_LABEL__", "") or "") or step_spec.phase
    # Vars may re-select mode (evaluate detect_mode); refresh view if needed.
    refreshed = str(state.custom.get("mode") or "") or variant_name
    if refreshed and refreshed != variant_name and manifest.variants and refreshed in manifest.variants:
        variant_name = refreshed
        view = _effective_view(manifest, variant_name)
        max_step = view.max_step
        state.max_step = max_step
        step_spec = _step_spec_from_view(view, step, skill)
        phase_names = {s.step: s.phase for s in view.steps}
        phase_todos = {s.step: [dict(t) for t in s.todos] for s in view.steps}
        phase_label = step_spec.phase
        save_state(state, state_path)

    template = load_template(step_spec.prompt)
    body = render_template(template, variables, search_dir=root)
    if append_body:
        body += append_body

    run_declared_gates_for_view(view, state, step, state_path=state_path)
    # Gates/vars may stash dynamic control flags on state.custom.
    prepend_after_gates = str(state.custom.pop("_prepend_body", "") or "")
    if prepend_after_gates:
        body = prepend_after_gates + body
    append_after_gates = str(state.custom.pop("_append_body", "") or "")
    if append_after_gates:
        body += append_after_gates

    handoff_menu: str | None = None
    handoff_path: Path | None = None
    await_same = bool(step_spec.await_same_step) or bool(
        state.custom.pop("_await_same_step", False)
    )
    skip_completion = bool(state.custom.pop("_skip_completion", False))
    custom_next = state.custom.pop("_next_step", None)
    exit_code = int(state.custom.pop("_exit_code", 0) or 0)
    run_summary = f"Completed step {step} ({phase_label})."

    if step == max_step and not skip_completion and not await_same:
        state.mark_step_complete(step)
        state.completed_at = now_iso()
        save_state(state, state_path)
        context = _build_handoff_context(step_spec, state, root, manifest)
        suggested = _suggested_next(skill, manifest, state=state)
        handoff_path = write_handoff(
            skill_name=skill,
            state=state,
            context=context,
            suggested_next=suggested,
            state_path=state_path,
        )
        body += f"\n\nHandoff written to: {handoff_path}"
        handoff_menu = build_skill_handoff_menu(skill, state, state_path)
        clear_state_file(state_path)
        # Sidecar moves with the session under _archive; re-emit post-archive path.
        from scripts.shared.handoff_menu import emit_handoff_multiselect_path

        emit_handoff_multiselect_path(state_path)
        run_summary = f"Completed {skill} workflow and wrote handoff."
    elif await_same:
        state.custom["session_visits"] = int(state.custom.get("session_visits") or 0) + 1
        save_state(state, state_path)
    else:
        state.mark_step_complete(step)
        save_state(state, state_path)

    append_skill_run_memory(
        skill,
        step,
        phase_label,
        run_summary,
        state=state,
        state_path=state_path,
        handoff_path=handoff_path,
    )

    next_cmd = None
    require_confirm = None
    if await_same:
        next_cmd = _next_command(
            skill,
            step,
            max_step,
            state_path=str(state_path),
            flags=_active_flag_tokens(manifest, state),
            next_step=int(custom_next) if custom_next is not None else step,
        )
        require_confirm = True
    elif step < max_step or custom_next is not None:
        next_target = int(custom_next) if custom_next is not None else None
        if next_target is None or next_target <= max_step:
            next_cmd = _next_command(
                skill,
                step,
                max_step,
                state_path=str(state_path),
                flags=_active_flag_tokens(manifest, state),
                next_step=next_target,
            )

    print(
        format_step_output(
            skill,
            step,
            max_step,
            phase_label,
            body,
            next_cmd=next_cmd,
            phase_todos=list(step_spec.todos),
            handoff_menu=handoff_menu,
            all_phase_names=phase_names,
            all_phase_todos=phase_todos,
            require_confirmation=require_confirm,
            await_same_step=await_same,
        )
    )
    return int(exit_code) if exit_code else 0


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _resume_mode_guards(skill: str, state: SkillState, args: Any) -> int:
    """Legacy parity for test: stale ux sessions and explicit --mode conflicts.

    Returns a process exit code when the resume must abort, else 0.
    """
    saved = str(state.custom.get("mode") or "")
    if skill == "test" and saved == "ux":
        print(
            "ERROR: This session used removed `test --mode ux`.\n"
            "       Start a new session with: forge ux-review --step 1 [--base-url URL]\n"
            "       Or delete the state file and use --mode run / --mode flows.",
            file=sys.stderr,
        )
        return 2

    cli_mode = getattr(args, "mode", None)
    if (
        skill == "test"
        and cli_mode is not None
        and saved
        and str(cli_mode) != saved
    ):
        print(
            f"ERROR: Cannot resume — saved mode is '{saved}' but --mode '{cli_mode}' "
            f"was passed.\n"
            "       Either re-run without --mode (resume preserves saved mode) or "
            "delete the state file.",
            file=sys.stderr,
        )
        return 1
    return 0



@dataclass(frozen=True)
class _EffectiveView:
    max_step: int
    steps: tuple[ManifestStep, ...]
    gates: tuple[ManifestGate, ...]


def _gates_for_step(gates: tuple[ManifestGate, ...] | list[ManifestGate], step: int) -> list[ManifestGate]:
    return [g for g in gates if step in g.steps]


def run_declared_gates_for_view(
    view: _EffectiveView,
    state: SkillState,
    step: int,
    *,
    state_path: Path,
) -> None:
    """Run gates from an effective (possibly variant) view."""
    from scripts.shared.ceremony import normalize_ceremony

    gates = _gates_for_step(view.gates, step)
    if not gates:
        return
    ceremony = normalize_ceremony(
        str(state.custom.get("ceremony"))
        if state.custom.get("ceremony") is not None
        else None
    )
    for gate in gates:
        soft = bool(ceremony and ceremony in (gate.soft_when or ()))
        if gate.kind == "python":
            if not gate.callable:
                raise SystemExit(f"ERROR: gate {gate.id!r} kind=python missing callable")
            if soft:
                print(
                    f"NOTE: soft_when skipped gate {gate.id!r} at ceremony={ceremony}",
                    file=sys.stderr,
                )
                continue
            fn = resolve_callable(gate.callable)
            fn(state=state, step=step, state_path=state_path, gate=gate)
        elif gate.kind == "schema":
            from scripts.shared.schema_gate import run_schema_gate

            run_schema_gate(
                state=state, step=step, state_path=state_path, gate=gate
            )
        else:
            raise SystemExit(f"ERROR: unsupported gate kind {gate.kind!r} for {gate.id!r}")


def _parser_max_step(manifest: Manifest) -> int:
    """Largest max_step across variants (or top-level) for argparse --step range."""
    values: list[int] = []
    if manifest.max_step is not None:
        values.append(int(manifest.max_step))
    if manifest.variants:
        values.extend(int(v.max_step) for v in manifest.variants.values())
    return max(values) if values else 0


def _resolve_max_step(manifest: Manifest, variant_name: str | None = None) -> int:
    view = _effective_view(manifest, variant_name)
    return view.max_step


def _select_variant_name(
    manifest: Manifest,
    args: Any,
    *,
    state: SkillState | None,
) -> str | None:
    """Select mode variant only (evaluate pre/post, test run/flows, …).

    Dual-axis overlay: ceremony is resolved separately via
    ``resolve_and_persist_ceremony`` and must NOT drive variant selection.
    Ceremony softens gates / collapses depth on the mode-selected view.
    """
    if not manifest.variants:
        return None
    candidates: list[str] = []
    mode = getattr(args, "mode", None)
    if mode:
        candidates.append(str(mode))
    if state is not None:
        custom_mode = state.custom.get("mode")
        if custom_mode:
            candidates.append(str(custom_mode))
    for name in candidates:
        if name in manifest.variants:
            return name
    for preferred in ("pre", "run"):
        if preferred in manifest.variants:
            return preferred
    return next(iter(manifest.variants))


def resolve_and_persist_ceremony(
    state: SkillState,
    args: Any,
    *,
    step: int,
) -> Ceremony:
    """Resolve ceremony band and persist onto ``state.custom``.

    Priority: CLI ``--ceremony`` → ``inherited_ceremony`` → estimate from
    effort / plan_mode / scope_tier / quick. ``--effort`` is an alias that
    maps to ceremony when ceremony is not from CLI.
    """
    cli_raw = getattr(args, "ceremony", None)
    if cli_raw is not None and str(cli_raw).strip():
        band = normalize_ceremony(str(cli_raw))
        if band:
            state.custom["ceremony"] = band
            state.custom["ceremony_rationale"] = "CLI --ceremony"
            state.custom["ceremony_source"] = "cli"
            return band

    # Resume: keep a previously resolved ceremony unless CLI overrides.
    existing = normalize_ceremony(
        str(state.custom.get("ceremony"))
        if state.custom.get("ceremony") is not None
        else None
    )
    existing_source = str(state.custom.get("ceremony_source") or "")
    if step > 1 and existing and existing_source in (
        "cli",
        "inherited",
        "estimated",
        "escalated",
    ):
        return existing

    if existing_source == "cli" and existing:
        return existing

    effort_raw = getattr(args, "effort", None)
    if effort_raw is None:
        effort_raw = state.custom.get("effort")

    plan_mode = state.custom.get("plan_mode")
    mode_val = state.custom.get("mode")
    if plan_mode is None and mode_val in ("lite", "default"):
        plan_mode = mode_val

    inherited_raw = state.custom.get("inherited_ceremony")
    signals = {
        "inherited_ceremony": inherited_raw,
        # --effort aliases ceremony when --ceremony was not passed.
        "effort": effort_raw,
        "cli_effort": effort_raw,
        "plan_mode": plan_mode,
        "scope_tier": state.custom.get("scope_tier") or state.custom.get("size"),
        "quick": bool(
            getattr(state, "quick_mode", False)
            or state.custom.get("quick_mode")
            or getattr(args, "quick", False)
        ),
        "severity": state.custom.get("severity"),
    }
    band, rationale = estimate_ceremony(signals)

    inherited = normalize_ceremony(
        str(inherited_raw) if inherited_raw is not None else None
    )
    if inherited and band == inherited:
        source = "inherited"
    else:
        source = "estimated"

    state.custom["ceremony"] = band
    state.custom["ceremony_rationale"] = rationale
    state.custom["ceremony_source"] = source
    return band


def select_mode_and_ceremony(
    manifest: Manifest,
    args: Any,
    state: SkillState,
) -> tuple[str | None, str]:
    """Return ``(mode_variant_name, ceremony)`` for dual-axis selection tests."""
    mode = _select_variant_name(manifest, args, state=state)
    ceremony = normalize_ceremony(
        str(state.custom.get("ceremony"))
        if state.custom.get("ceremony") is not None
        else None
    )
    if ceremony is None:
        ceremony = resolve_and_persist_ceremony(
            state, args, step=int(state.current_step or 1)
        )
    return mode, str(ceremony)


def _effective_view(manifest: Manifest, variant_name: str | None) -> _EffectiveView:
    if variant_name and manifest.variants and variant_name in manifest.variants:
        variant = manifest.variants[variant_name]
        gates = variant.gates if variant.gates else manifest.gates
        return _EffectiveView(
            max_step=int(variant.max_step),
            steps=variant.steps,
            gates=gates,
        )
    if manifest.steps:
        return _EffectiveView(
            max_step=int(manifest.max_step or 0),
            steps=manifest.steps,
            gates=manifest.gates,
        )
    if manifest.variants:
        # Fallback: first variant
        name = next(iter(manifest.variants))
        return _effective_view(manifest, name)
    return _EffectiveView(max_step=0, steps=(), gates=())


def _step_spec_from_view(view: _EffectiveView, step: int, skill: str) -> ManifestStep:
    for s in view.steps:
        if s.step == step:
            return s
    print(f"ERROR: Invalid step {step} for skill {skill}", file=sys.stderr)
    raise SystemExit(1)


def _step_spec(manifest: Manifest, step: int) -> ManifestStep:
    return _step_spec_from_view(_effective_view(manifest, None), step, manifest.skill)


def _phase_names(manifest: Manifest) -> dict[int, str]:
    return {s.step: s.phase for s in manifest.steps}


def _phase_todos(manifest: Manifest) -> dict[int, list[dict]]:
    return {s.step: [dict(t) for t in s.todos] for s in manifest.steps}


def _apply_cli_flags(parser: Any, flags: tuple[CliFlag, ...]) -> None:
    for flag in flags:
        kwargs: dict[str, Any] = {"help": flag.help or None}
        dest = _flag_dest(flag.name)
        if flag.type == "bool":
            parser.add_argument(
                flag.name,
                dest=dest,
                action="store_true",
                default=bool(flag.default) if flag.default is not None else False,
                help=flag.help or None,
            )
        elif flag.type == "int":
            parser.add_argument(
                flag.name,
                dest=dest,
                type=int,
                default=flag.default,
                choices=list(flag.choices) if flag.choices else None,
                help=flag.help or None,
            )
        elif flag.type == "list":
            parser.add_argument(
                flag.name,
                dest=dest,
                nargs="+",
                default=flag.default,
                help=flag.help or None,
            )
        else:
            parser.add_argument(
                flag.name,
                dest=dest,
                type=str,
                default=flag.default,
                choices=list(flag.choices) if flag.choices else None,
                help=flag.help or None,
            )


def _flag_dest(name: str) -> str:
    return name.lstrip("-").replace("-", "_")


def _apply_flag_values_to_state(
    state: SkillState,
    flags: tuple[CliFlag, ...],
    args: Any,
    *,
    step: int,
) -> None:
    """Persist declared CLI flags onto ``state.custom`` (step 1 sets; later preserves)."""
    for flag in flags:
        dest = _flag_dest(flag.name)
        if not hasattr(args, dest):
            continue
        value = getattr(args, dest)
        if flag.type == "bool":
            # Step 1: honor CLI. Later steps: keep prior custom unless flag is True again.
            if step == 1:
                state.custom[dest] = bool(value)
            elif value:
                state.custom[dest] = True
            else:
                state.custom.setdefault(dest, False)
        elif dest == "mode":
            # Do not clobber a persisted mode with a missing CLI default.
            if value is None:
                continue
            if step == 1 or not state.custom.get("mode"):
                state.custom[dest] = value
            else:
                state.custom[dest] = value
        else:
            if step == 1 or value is not None:
                if value is not None or step == 1:
                    state.custom[dest] = value


def _active_flag_tokens(manifest: Manifest, state: SkillState) -> tuple[str, ...]:
    tokens: list[str] = []
    for flag in manifest.cli_flags:
        if flag.type != "bool":
            continue
        dest = _flag_dest(flag.name)
        if state.custom.get(dest):
            tokens.append(dest.replace("_", "-"))
    return tuple(tokens)


def _bootstrap_step1(
    skill: str,
    max_step: int,
    args: Any,
    repo_root: Path,
) -> tuple[SkillState, Path]:
    sp = resolve_step1_state_path(
        skill,
        args.state,
        parallel=getattr(args, "parallel", False),
        label=getattr(args, "label", None),
        session_id=getattr(args, "session", None),
    )
    sp.parent.mkdir(parents=True, exist_ok=True)
    check_same_skill_clobber(
        skill,
        allow_parallel=bool(getattr(args, "parallel", False) or args.state),
        target_state_path=sp,
    )
    run_step1_session_hygiene(skill, sp)

    existing = None
    if args.state:
        existing = validate_state_path(args.state, skill)
    elif sp.exists():
        existing = sp

    state: SkillState | None = None
    if existing is not None:
        try:
            state = load_state(existing)
            sp = existing
        except Exception:
            state = None

    if state is None:
        state = SkillState(skill_name=skill, max_step=max_step)
        state.started_at = now_iso()

    state.max_step = max_step
    save_state(state, sp)
    print_remaining_session_warning(skill)
    print(f"STATE FILE: {sp}\n", file=sys.stderr)

    mem = runtime_memory_dir(repo_root)
    mem.mkdir(parents=True, exist_ok=True)
    return state, sp


def _load_step_state(
    skill: str,
    step: int,
    args: Any,
) -> tuple[SkillState, Path]:
    sp = resolve_step_state_path(
        skill,
        step,
        state_file=args.state,
        session_id=getattr(args, "session", None),
    )
    if not sp.exists():
        print(f"ERROR: No {skill} session in progress. Run step 1 first.")
        print("If the state file is elsewhere, pass --state <path>")
        raise SystemExit(1)
    try:
        state = load_state(sp)
    except Exception as exc:
        print(f"ERROR: Cannot load state at {sp}: {exc}")
        raise SystemExit(1) from exc
    return state, sp


def _vars_callable_spec(step_spec: ManifestStep, manifest: Manifest) -> str | None:
    if step_spec.variables_callable:
        return step_spec.variables_callable
    for s in manifest.steps:
        if s.variables_callable:
            return s.variables_callable
    return None


def _apply_override_args_to_state(state: SkillState, args: Any) -> None:
    """Copy common override/flag attrs onto state.custom for gate adapters."""
    for key in (
        "allow_docs_incomplete",
        "docs_override_reason",
        "docs_override_requested_by",
        "docs_override_follow_up",
        "allow_structural_probes_incomplete",
        "structural_probes_override_reason",
        "structural_probes_override_follow_up",
        "plan",
        "branch_prefix",
        "target",
        "mode",
        "base_url",
        "force",
        "save_ceremony_preference",
        "defer_graphify_waves",
        "no_structural",
        "effort",
        "ceremony",
        "allow_spec_incomplete",
        "spec_override_reason",
        "spec_override_requested_by",
        "spec_override_follow_up",
        "allow_issues_incomplete",
        "issues_override_reason",
        "issues_override_requested_by",
        "issues_override_follow_up",
        "flow_type",
        "re_record",
        "framework",
        "entry_point",
        "no_db",
        "roles",
        "plan",
        "goal",
        "issue",
        "design",
        "team",
        "cleanup",
        "all_stale",
        "auto1",
        "auto2",
        "auto3",
    ):
        if hasattr(args, key):
            value = getattr(args, key)
            if value is not None:
                state.custom[key] = value
    if hasattr(args, "quick") and args.quick:
        state.quick_mode = True
        state.custom["quick_mode"] = True
    # --target may be nargs='+' list
    if hasattr(args, "target") and args.target is not None:
        t = args.target
        if isinstance(t, list):
            state.custom["target"] = " ".join(str(x) for x in t if x)
            state.custom["target_tokens"] = [str(x) for x in t if x]
        else:
            state.custom["target"] = str(t)


def _build_step_variables(
    step_spec: ManifestStep,
    state: SkillState,
    repo_root: Path,
    manifest: Manifest,
    *,
    step: int | None = None,
    state_path: Path | None = None,
) -> dict[str, str]:
    spec = _vars_callable_spec(step_spec, manifest)
    if not spec:
        return {}
    fn = resolve_callable(spec)
    step_n = int(step if step is not None else step_spec.step)
    kwargs: dict[str, Any] = {"step": step_n}
    if state_path is not None:
        kwargs["state_path"] = state_path
    try:
        result = fn(state, repo_root, **kwargs)
    except TypeError:
        try:
            result = fn(state, repo_root, step=step_n)
        except TypeError:
            result = fn(state, repo_root)
    return {str(k): str(v) for k, v in dict(result).items()}


def _build_handoff_context(
    step_spec: ManifestStep,
    state: SkillState,
    repo_root: Path,
    manifest: Manifest,
) -> dict[str, str]:
    spec = _vars_callable_spec(step_spec, manifest)
    if spec and ":" in spec:
        mod_name = spec.split(":", 1)[0]
        mod = importlib.import_module(mod_name)
        fn = getattr(mod, "build_handoff_context", None)
        if callable(fn):
            return {str(k): str(v) for k, v in dict(fn(state, repo_root)).items()}
    return {
        str(k): str(v)
        for k, v in state.custom.items()
        if not str(k).startswith("_")
    }


def _suggested_next(
    skill: str,
    manifest: Manifest,
    *,
    state: SkillState | None = None,
) -> str:
    if manifest.handoff_skill:
        return manifest.handoff_skill
    try:
        from scripts.shared.handoff_menu import resolve_next_skill

        default, _alts = resolve_next_skill(skill, state)
        if default:
            return str(default)
    except Exception:
        pass
    transition = SKILL_CHAIN.get(skill)
    if transition is not None and transition.default:
        return str(transition.default)
    return "next"


def _script_path_for(skill: str) -> Path:
    # scripts/<skill with underscores>/<skill>.py
    token = skill.replace("-", "_")
    return Path("scripts") / token / f"{token}.py"


def _next_command(
    skill: str,
    step: int,
    max_step: int,
    *,
    state_path: str = "",
    flags: tuple[str, ...] = (),
    next_step: int | None = None,
) -> str:
    extra: dict[str, str] = {}
    if state_path:
        extra["state"] = state_path
    return build_next_command(
        _script_path_for(skill),
        step,
        max_step,
        next_step=next_step,
        flags=flags,
        **extra,
    )
