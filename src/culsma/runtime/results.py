"""Compact run results, independent of the legacy lab-report JSON shape."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterator
from copy import deepcopy
from math import isfinite
from typing import Any

from culsma.runtime.material.accounting import MaterialAccounting, MaterialQuantity
from culsma.runtime.material.roles import collect_container_roles
from culsma.runtime.state import RuntimeState


def build_results(
    *,
    state: RuntimeState,
    returns: dict[str, Any],
    plan: Any,
    material_accounting: MaterialAccounting | None,
) -> dict[str, Any]:
    """Project material use, physical resources, and full protocol returns."""
    material_state = state.artifacts.get("material_state", {})
    roles = collect_container_roles(
        plan=plan,
        final_material_state=material_state,
        step_status=state.step_status,
    )
    materials = _material_rows(accounting=material_accounting, roles=roles)
    resources = _resource_rows(
        state=state,
        material_state=material_state,
        accounting=material_accounting,
        roles=roles,
        returns=returns,
        plan=plan,
    )
    return {"materials": materials, "resources": resources, "returns": deepcopy(returns)}


def _material_rows(
    *, accounting: MaterialAccounting | None, roles: dict[str, set[str]]
) -> list[dict[str, Any]]:
    if accounting is None:
        return []
    consumed = accounting.consumption_by_input()
    totals: dict[tuple[str, str], float] = {}
    for lot in accounting.list_input_lots():
        quantity = (
            lot.initial
            if "sample" in roles.get(lot.container_id, set())
            else consumed.get(lot.lot_id)
        )
        if quantity is None:
            continue
        for unit, amount in _quantity_axes(quantity):
            key = (lot.name, unit)
            totals[key] = totals.get(key, 0.0) + amount
    return [
        {"name": name, "amount": round(amount, 6), "unit": unit}
        for (name, unit), amount in sorted(
            totals.items(), key=lambda item: (-item[1], item[0][0], item[0][1])
        )
    ]


def _quantity_axes(quantity: MaterialQuantity) -> Iterator[tuple[str, float]]:
    if quantity.volume_uL > 1e-9:
        yield "uL", quantity.volume_uL
    if quantity.mass_mg > 1e-9:
        yield "mg", quantity.mass_mg
    if quantity.count_cells > 1e-9:
        yield "cells", quantity.count_cells


def _resource_rows(
    *,
    state: RuntimeState,
    material_state: Any,
    accounting: MaterialAccounting | None,
    roles: dict[str, set[str]],
    returns: dict[str, Any],
    plan: Any,
) -> list[dict[str, Any]]:
    counts: Counter[tuple[str, float | None]] = Counter()
    carrier_by_step, carrier_ids = _physical_carriers(plan=plan, state=state)
    material_state = material_state if isinstance(material_state, dict) else {}
    containers = material_state.get("containers", {})
    containers = containers if isinstance(containers, dict) else {}
    referenced = set(roles) | _returned_container_ids(returns)
    if accounting is not None:
        consumed = accounting.consumption_by_input()
        for lot in accounting.list_input_lots():
            quantity = consumed.get(lot.lot_id)
            if quantity is not None and any(_quantity_axes(quantity)):
                referenced.add(lot.container_id)

    for container_id, container in containers.items():
        # Separation slots are material fractions, not additional labware.
        if "::" in container_id or not isinstance(container, dict):
            continue
        metadata = container.get("metadata")
        metadata = metadata if isinstance(metadata, dict) else {}
        allocation_step = metadata.get("allocation_step_id")
        if allocation_step in state.step_status:
            if state.step_status[allocation_step] != "completed":
                continue
        elif container_id not in referenced:
            continue
        if allocation_step in carrier_by_step:
            # A well is a position in its carrier, not a separate consumable.
            continue
        kind = metadata.get("kind") or "unknown"
        # Imported state may carry string-valued capacity or no metadata.
        try:
            capacity = float(metadata["capacity_uL"])
            if not isfinite(capacity) or capacity <= 0:
                capacity = None
        except (KeyError, TypeError, ValueError):
            capacity = None
        counts[(kind, capacity)] += 1
    for kind, ids in carrier_ids.items():
        counts[(kind, None)] += len(ids)
    resources = [
        {"kind": kind, "capacity_uL": capacity, "count": count}
        for (kind, capacity), count in sorted(
            counts.items(), key=lambda item: (item[0][0], item[0][1] is None, item[0][1] or 0)
        )
    ]
    resources.extend(_instrument_rows(plan=plan, state=state))
    return resources


def _physical_carriers(
    *, plan: Any, state: RuntimeState
) -> tuple[dict[str, tuple[str, str]], dict[str, set[str]]]:
    """Map completed positional allocations to their shared physical carrier."""

    by_step: dict[str, tuple[str, str]] = {}
    ids_by_kind: dict[str, set[str]] = {}
    for protocol in getattr(plan, "plans", []):
        for step in getattr(protocol, "steps", []):
            step_id = getattr(step, "step_id", "")
            if state.step_status.get(step_id) != "completed" or getattr(step, "op", "") != "AllocContainer":
                continue
            args = getattr(step, "args", {})
            if not isinstance(args, dict):
                continue
            carrier_kind = _arg_string(args.get("carrier_kind"))
            carrier_id = _arg_string(args.get("carrier_id"))
            if not carrier_kind or not carrier_id:
                continue
            by_step[step_id] = (carrier_kind, carrier_id)
            ids_by_kind.setdefault(carrier_kind, set()).add(carrier_id)
    return by_step, ids_by_kind


def _instrument_rows(*, plan: Any, state: RuntimeState) -> list[dict[str, Any]]:
    """Project unique, explicitly bound devices from completed steps."""

    names: set[str] = set()
    for protocol in getattr(plan, "plans", []):
        for step in getattr(protocol, "steps", []):
            if state.step_status.get(getattr(step, "step_id", "")) != "completed":
                continue
            args = getattr(step, "args", {})
            if not isinstance(args, dict):
                continue
            direct = _arg_string(args.get("device"))
            if direct:
                names.add(direct)
            nested = _call_arg_string(args.get("program"), "device")
            if nested:
                names.add(nested)
    return [{"kind": "device", "name": name, "count": 1} for name in sorted(names)]


def _call_arg_string(call: Any, name: str) -> str | None:
    if not isinstance(call, dict) or call.get("kind") != "IRCall":
        return None
    args = call.get("args")
    if not isinstance(args, list):
        return None
    for arg in args:
        if isinstance(arg, dict) and arg.get("name") == name:
            return _arg_string(arg.get("value"))
    return None


def _arg_string(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict) and value.get("kind") == "IRIdentifier":
        name = value.get("name")
        return name if isinstance(name, str) else None
    if isinstance(value, dict) and value.get("kind") == "IRString":
        text = value.get("value")
        return text if isinstance(text, str) else None
    return None


def _returned_container_ids(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        if value.get("kind") == "container_ref" and isinstance(value.get("id"), str):
            found.add(value["id"])
        for nested in value.values():
            found.update(_returned_container_ids(nested))
    elif isinstance(value, list):
        for nested in value:
            found.update(_returned_container_ids(nested))
    return found
