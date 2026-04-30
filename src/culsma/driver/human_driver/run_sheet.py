"""Human run-sheet grouping utilities."""

from __future__ import annotations

from dataclasses import dataclass
import re

from culsma.driver.framework.models import DriverProjection

_SECTION_BY_CATEGORY = {
    "setup": "Setup",
    "internal_setup": "Setup",
    "material": "Material Transfer",
    "separation": "Separation",
    "environment": "Condition Hold",
    "thermal_control": "Thermal Cycling",
    "condition_hold": "Condition Hold",
    "observation": "Observation",
    "instruction": "General",
}


@dataclass(frozen=True)
class HumanRunSheetItem:
    step_id: str
    title: str
    summary: str
    details: tuple[str, ...] = ()
    category: str = "instruction"
    step_ids: tuple[str, ...] = ()
    repeat_count: int = 1


@dataclass(frozen=True)
class HumanRunSheetSection:
    key: str
    title: str
    step_ids: tuple[str, ...] = ()
    items: tuple[HumanRunSheetItem, ...] = ()


@dataclass(frozen=True)
class HumanRunSheet:
    items: tuple[HumanRunSheetItem, ...] = ()
    sections: tuple[HumanRunSheetSection, ...] = ()


def projection_to_packet(projection: DriverProjection) -> dict[str, object]:
    section_key = projection.category
    section_title = _SECTION_BY_CATEGORY.get(section_key, "General")
    return {
        "section": {
            "key": section_key,
            "title": section_title,
        },
        "item": {
            "step_id": projection.step_id,
            "title": projection.label,
            "summary": projection.summary,
            "details": list(projection.details),
            "category": projection.category,
        },
    }


def build_run_sheet(projections: list[DriverProjection]) -> HumanRunSheet:
    alias_map = _build_alias_map(projections)
    items: list[HumanRunSheetItem] = []

    for projection in projections:
        key = projection.category
        if key == "internal_setup":
            continue
        summary = projection.summary
        details = tuple(projection.details)
        if key != "setup":
            summary = _apply_aliases(summary, alias_map)
            details = tuple(_apply_aliases(line, alias_map) for line in details)
        item = HumanRunSheetItem(
            step_id=projection.step_id,
            title=projection.label,
            summary=summary,
            details=details,
            category=projection.category,
            step_ids=(projection.step_id,),
            repeat_count=1,
        )
        if not items:
            items.append(item)
            continue
        prior = items[-1]
        if _can_merge(prior, item):
            merged_ids = prior.step_ids + item.step_ids
            items[-1] = HumanRunSheetItem(
                step_id=prior.step_id,
                title=prior.title,
                summary=_normalize_repeat_summary(prior.summary, len(merged_ids)),
                details=prior.details,
                category=prior.category,
                step_ids=merged_ids,
                repeat_count=len(merged_ids),
            )
            continue
        items.append(item)

    return HumanRunSheet(items=tuple(items), sections=())


def _can_merge(left: HumanRunSheetItem, right: HumanRunSheetItem) -> bool:
    return (
        left.category == right.category
        and left.title == right.title
        and left.details == right.details
        and _strip_repeat_prefix(left.summary).casefold() == _strip_repeat_prefix(right.summary).casefold()
    )


def _normalize_repeat_summary(summary: str, repeat_count: int) -> str:
    base = _strip_repeat_prefix(summary)
    if repeat_count <= 1:
        return base
    return f"Repeat {repeat_count} times: {base[0].lower() + base[1:] if len(base) > 1 else base.lower()}"


def _strip_repeat_prefix(summary: str) -> str:
    prefix = "Repeat "
    if not summary.startswith(prefix):
        return summary
    parts = summary.split(": ", 1)
    if len(parts) == 2:
        return parts[1]
    return summary


def _build_alias_map(projections: list[DriverProjection]) -> dict[str, str]:
    alias_map: dict[str, str] = {}
    for projection in projections:
        if projection.semantic_op != "AllocContainer":
            continue
        bind_name = projection.payload.get("bind")
        label = projection.payload.get("label")
        if isinstance(bind_name, str) and bind_name and isinstance(label, str) and label:
            alias_map[bind_name] = label
    return alias_map


def _apply_aliases(text: str, alias_map: dict[str, str]) -> str:
    rewritten = text
    for source, target in alias_map.items():
        rewritten = re.sub(rf"\b{re.escape(source)}\b", target, rewritten)
    return rewritten
