"""Read-only reconciliation of completed-run consumption with external inventory."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


INVENTORY_SNAPSHOT_SCHEMA = "culsma_inventory_snapshot_v1"
INVENTORY_RECONCILIATION_SCHEMA = "culsma_inventory_reconciliation_v1"
_AXES = ("volume_uL", "mass_mg", "count_cells")
_CONSUMPTION_KEYS = {
    "volume_uL": "consumed_uL",
    "mass_mg": "consumed_mg",
    "count_cells": "consumed_cells",
}


def unchecked_inventory_result(*, reason: str = "inventory_not_supplied") -> dict[str, Any]:
    return {
        "schema": INVENTORY_RECONCILIATION_SCHEMA,
        "checked": False,
        "sufficient": None,
        "reason": reason,
        "items": [],
        "shortages": [],
    }


def reconcile_external_inventory(
    *,
    report: dict[str, Any],
    snapshot: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return a report copy with an optional, read-only inventory result."""
    updated = deepcopy(report)
    if snapshot is None:
        updated["external_inventory"] = unchecked_inventory_result()
        return updated

    execution = report.get("execution")
    if not isinstance(execution, dict) or not bool(execution.get("ok")):
        updated["external_inventory"] = unchecked_inventory_result(reason="runtime_incomplete")
        return updated

    available_by_name = _normalize_snapshot(snapshot)
    consumption = _reagent_consumption(report)
    items: list[dict[str, Any]] = []
    shortages: list[dict[str, Any]] = []

    for row in consumption:
        name = row.get("name")
        if not isinstance(name, str) or not name:
            continue
        available = available_by_name.get(name, {})
        required_values: dict[str, float | None] = {}
        available_values: dict[str, float | None] = {}
        shortage_values: dict[str, float | None] = {}
        remaining_values: dict[str, float | None] = {}
        has_shortage = False

        for axis in _AXES:
            required = _optional_quantity(row.get(_CONSUMPTION_KEYS[axis]))
            if required is None:
                required_values[axis] = None
                available_values[axis] = None
                shortage_values[axis] = None
                remaining_values[axis] = None
                continue
            available_quantity = available.get(axis, 0.0)
            shortage = max(0.0, required - available_quantity)
            remaining = max(0.0, available_quantity - required)
            required_values[axis] = _rounded(required)
            available_values[axis] = _rounded(available_quantity)
            shortage_values[axis] = _rounded(shortage)
            remaining_values[axis] = _rounded(remaining)
            has_shortage = has_shortage or shortage > 1e-9

        item = {
            "name": name,
            "sufficient": not has_shortage,
            "required": required_values,
            "available": available_values,
            "shortage": shortage_values,
            "remaining": remaining_values,
        }
        items.append(item)
        if has_shortage:
            shortages.append({"name": name, "shortage": shortage_values})

    updated["external_inventory"] = {
        "schema": INVENTORY_RECONCILIATION_SCHEMA,
        "checked": True,
        "sufficient": not shortages,
        "reason": None,
        "items": items,
        "shortages": shortages,
    }
    return updated


def _normalize_snapshot(snapshot: dict[str, Any]) -> dict[str, dict[str, float]]:
    schema = snapshot.get("schema")
    if schema is not None and schema != INVENTORY_SNAPSHOT_SCHEMA:
        raise ValueError(
            f"INVENTORY_SNAPSHOT_SCHEMA_INVALID: expected '{INVENTORY_SNAPSHOT_SCHEMA}'"
        )
    raw_items = snapshot.get("items")
    if not isinstance(raw_items, list):
        raise ValueError("INVENTORY_SNAPSHOT_INVALID: 'items' must be a list")

    normalized: dict[str, dict[str, float]] = {}
    for index, raw_item in enumerate(raw_items):
        if not isinstance(raw_item, dict):
            raise ValueError(f"INVENTORY_SNAPSHOT_INVALID: item {index} must be an object")
        name = raw_item.get("name")
        available = raw_item.get("available")
        if not isinstance(name, str) or not name:
            raise ValueError(f"INVENTORY_SNAPSHOT_INVALID: item {index} requires a name")
        if not isinstance(available, dict):
            raise ValueError(
                f"INVENTORY_SNAPSHOT_INVALID: item '{name}' requires an available object"
            )
        totals = normalized.setdefault(name, {})
        for axis in _AXES:
            raw_value = available.get(axis)
            if raw_value is None:
                continue
            if not isinstance(raw_value, (int, float)) or isinstance(raw_value, bool):
                raise ValueError(
                    f"INVENTORY_SNAPSHOT_INVALID: item '{name}' axis '{axis}' must be numeric"
                )
            value = float(raw_value)
            if value < 0:
                raise ValueError(
                    f"INVENTORY_SNAPSHOT_INVALID: item '{name}' axis '{axis}' must be non-negative"
                )
            totals[axis] = totals.get(axis, 0.0) + value
    return normalized


def _reagent_consumption(report: dict[str, Any]) -> list[dict[str, Any]]:
    materials = report.get("materials")
    if not isinstance(materials, dict):
        return []
    rows = materials.get("reagent_consumption")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _optional_quantity(value: Any) -> float | None:
    if value is None:
        return None
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    return max(0.0, float(value))


def _rounded(value: float) -> float:
    return round(value, 6)
