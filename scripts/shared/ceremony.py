"""Shared ceremony bands for Forge skill depth (light → comprehensive).

Wraps legacy depth knobs (`scope_tier`, plan `lite`, `--effort`, quick) into one
user-facing enum. Bias down when unsure.
"""

from __future__ import annotations

from typing import Any, Literal

Ceremony = Literal["light", "medium", "detailed", "comprehensive"]

CEREMONIES: tuple[Ceremony, ...] = ("light", "medium", "detailed", "comprehensive")

_RANK: dict[Ceremony, int] = {
    "light": 0,
    "medium": 1,
    "detailed": 2,
    "comprehensive": 3,
}

_ALIASES: dict[str, Ceremony] = {
    "light": "light",
    "lite": "light",
    "quick": "light",
    "small": "light",
    "trivial": "light",
    "medium": "medium",
    "standard": "medium",
    "default": "medium",
    "detailed": "detailed",
    "large": "detailed",
    "comprehensive": "comprehensive",
    "thorough": "comprehensive",
}


def normalize_ceremony(value: str | None) -> Ceremony | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    return _ALIASES.get(text)


def bias_down(a: Ceremony, b: Ceremony | None) -> Ceremony:
    """Return the lower of two bands (bias toward less ceremony)."""
    if b is None:
        return a
    return a if _RANK[a] <= _RANK[b] else b


def map_to_scope_tier(c: Ceremony) -> str:
    return {
        "light": "trivial",
        "medium": "medium",
        "detailed": "large",
        "comprehensive": "large",
    }[c]


def map_to_plan_mode(c: Ceremony) -> str:
    return "lite" if c == "light" else "default"


def map_to_effort(c: Ceremony) -> str:
    return {
        "light": "light",
        "medium": "standard",
        "detailed": "thorough",
        "comprehensive": "thorough",
    }[c]


def map_from_scope_tier(value: str | None) -> Ceremony | None:
    return normalize_ceremony(value)


def map_from_plan_mode(value: str | None) -> Ceremony | None:
    text = (value or "").strip().lower()
    if text == "lite":
        return "light"
    if text in ("default", "full", ""):
        return "medium" if text else None
    return normalize_ceremony(text)


def map_from_effort(value: str | None) -> Ceremony | None:
    return normalize_ceremony(value)


def estimate_ceremony(signals: dict[str, Any] | None = None) -> tuple[Ceremony, str]:
    """Estimate ceremony from CLI / handoff / legacy knobs. Bias down when unsure."""
    signals = signals or {}

    if signals.get("cli_ceremony") is not None:
        cli = normalize_ceremony(_as_str(signals.get("cli_ceremony")))
        if cli:
            return cli, "CLI --ceremony"

    inherited = normalize_ceremony(_as_str(signals.get("inherited_ceremony")))
    if inherited:
        return inherited, "Inherited from handoff/session"

    if signals.get("quick") or signals.get("quick_mode"):
        return "light", "Quick mode → light ceremony"

    if signals.get("effort") is not None or signals.get("cli_effort") is not None:
        raw = signals.get("effort") if signals.get("effort") is not None else signals.get("cli_effort")
        from_effort = map_from_effort(_as_str(raw))
        if from_effort:
            return from_effort, f"Mapped from effort `{raw}`"

    if signals.get("plan_mode") is not None:
        from_plan = map_from_plan_mode(_as_str(signals.get("plan_mode")))
        if from_plan:
            return from_plan, f"Mapped from plan_mode `{signals.get('plan_mode')}`"

    if signals.get("scope_tier") is not None or signals.get("size") is not None:
        raw = signals.get("scope_tier") if signals.get("scope_tier") is not None else signals.get("size")
        from_tier = map_from_scope_tier(_as_str(raw))
        if from_tier:
            band = from_tier
            severity = _as_str(signals.get("severity")).lower()
            if severity in ("low", "info") and band in ("detailed", "comprehensive"):
                band = bias_down(band, "medium")
                return band, f"Mapped from scope_tier with low-severity bias-down → {band}"
            return band, f"Mapped from scope_tier/size → {band}"

    explicit = normalize_ceremony(_as_str(signals.get("ceremony")))
    if explicit:
        return explicit, "ceremony field"

    return "medium", "Default medium ceremony (bias-down when unsure)"


def _as_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
