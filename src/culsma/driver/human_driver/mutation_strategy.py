"""Human-driver mutation strategy selection."""

from __future__ import annotations

from typing import Any

from .models import HumanMappingRecord


def resolve_mutation_strategy(record: HumanMappingRecord) -> dict[str, Any]:
    quantities_uL = _collect_source_quantities_uL(record.semantic_args.get("sources"))
    max_volume_uL = max(quantities_uL) if quantities_uL else None
    pipette_label, tip_label = _select_pipette_setup(max_volume_uL)
    multi_aspirate = max_volume_uL is not None and max_volume_uL > 1000

    notes: list[str] = [
        f"Use {pipette_label}.",
        f"Use {tip_label}.",
    ]
    if multi_aspirate:
        notes.append("Volume exceeds a single micropipette stroke; split into repeated pipette transfers.")

    return {
        "strategy_kind": "pipette_transfer",
        "pipette_label": pipette_label,
        "tip_label": tip_label,
        "max_volume_uL": max_volume_uL,
        "quantified_transfer": bool(quantities_uL),
        "multi_aspirate": multi_aspirate,
        "strategy_notes": tuple(notes),
    }


def _collect_source_quantities_uL(sources: Any) -> list[float]:
    if not isinstance(sources, list):
        return []
    quantities: list[float] = []
    for item in sources:
        if not isinstance(item, dict) or item.get("kind") != "IRPair":
            continue
        right = item.get("right")
        volume = _quantity_to_uL(right)
        if volume is not None:
            quantities.append(volume)
    return quantities


def _quantity_to_uL(value: Any) -> float | None:
    if not isinstance(value, dict) or value.get("kind") != "IRQuantity":
        return None
    unit = value.get("unit")
    raw_value = value.get("value")
    if not isinstance(raw_value, (int, float)):
        return None
    amount = float(raw_value)
    if unit in {"uL", "ul"}:
        return amount
    if unit in {"mL", "ml"}:
        return amount * 1000.0
    return None


def _select_pipette_setup(max_volume_uL: float | None) -> tuple[str, str]:
    if max_volume_uL is None:
        return "single-channel micropipette", "filtered pipette tip"
    if max_volume_uL <= 20:
        return "P20 single-channel pipette", "filtered clear tip"
    if max_volume_uL <= 200:
        return "P200 single-channel pipette", "filtered yellow tip"
    return "P1000 single-channel pipette", "filtered blue tip"
