"""Gate payload helpers for plan lowering."""

from __future__ import annotations

from typing import Any


def merge_gate(base: dict[str, Any] | None, **extra: Any) -> dict[str, Any] | None:
    merged = dict(base or {})
    for key, value in extra.items():
        merged[key] = value
    return merged or None


def append_runtime_condition(base: dict[str, Any] | None, expr: Any, *, negate: bool) -> dict[str, Any] | None:
    merged = dict(base or {})
    existing = merged.get("runtime_conditions")
    conditions = list(existing) if isinstance(existing, list) else []
    conditions.append({"expr": expr, "negate": negate})
    merged["runtime_conditions"] = conditions
    return merged


def append_constraints(
    base: dict[str, Any] | None,
    *,
    requirements: list[str],
    options: dict[str, Any],
) -> dict[str, Any] | None:
    merged = dict(base or {})
    existing = merged.get("constraint")
    merged_requirements: list[str] = []
    merged_options: dict[str, Any] = {}
    if isinstance(existing, dict):
        existing_requirements = existing.get("requirements")
        if isinstance(existing_requirements, list):
            for item in existing_requirements:
                if isinstance(item, str) and item not in merged_requirements:
                    merged_requirements.append(item)
        existing_options = existing.get("options")
        if isinstance(existing_options, dict):
            merged_options.update(existing_options)
    for item in requirements:
        if item not in merged_requirements:
            merged_requirements.append(item)
    merged_options.update(options)
    merged["constraint"] = {
        "requirements": merged_requirements,
        "options": merged_options,
    }
    return merged
