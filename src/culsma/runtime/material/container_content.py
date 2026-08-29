"""Container and content material operation implementations."""

from __future__ import annotations

from typing import Any

from culsma.pipeline.content_vocab import ContainerKind, normalize_content_classification
from culsma.pipeline.plan_nodes import PlanStep
from culsma.runtime.material.args import arg_bool, arg_quantity, arg_string
from culsma.runtime.material.contents_state import invalidate_contents_state
from culsma.runtime.material.diagnostics import diagnostic_result
from culsma.runtime.material.ledger import (
    check_capacity_guard,
    default_container_capacity_uL,
    ensure_container,
    normalize_capacity_uL,
    refresh_container_aggregates,
)
from culsma.runtime.material.refs import (
    bind_name,
    resolve_content_ref,
    resolve_or_create_container_ref,
)
from culsma.runtime.material.result import MaterialUpdateResult
from culsma.runtime.material.units import COUNT_TO_CELLS, MASS_TO_MG, VOLUME_TO_UL


def apply_alloc_container(step: PlanStep, state: dict[str, Any]) -> MaterialUpdateResult:
    kind = arg_string(step.args.get("kind"))
    label = arg_string(step.args.get("label"))
    barcode = arg_string(step.args.get("barcode"))
    bind_ref = arg_string(step.args.get("bind"))
    open_flag = arg_bool(step.args.get("open"))
    container_id = label or barcode or step.step_id
    container = ensure_container(state, container_id)
    metadata = container.setdefault("metadata", {})
    if isinstance(metadata, dict):
        if kind is not None:
            metadata["kind"] = kind
        if label is not None:
            metadata["label"] = label
        if barcode is not None:
            metadata["barcode"] = barcode
        if open_flag is not None:
            metadata["open"] = open_flag
        raw_capacity = step.args.get("capacity")
        if raw_capacity is not None:
            if kind == ContainerKind.SURFACE.value:
                return diagnostic_result(step, state, "MAT_INVALID_CAPACITY", "surface constructor does not support volume capacity")
            capacity_uL = normalize_capacity_uL(raw_capacity)
            if capacity_uL is None:
                qty = arg_quantity(raw_capacity)
                if qty is None:
                    return diagnostic_result(step, state, "MAT_INVALID_CAPACITY", "Container capacity must be a volume quantity")
                unit = str(qty["unit"])
                if unit not in VOLUME_TO_UL:
                    return diagnostic_result(step, state, "MAT_INVALID_CAPACITY", f"Unsupported capacity unit '{unit}'")
                return diagnostic_result(step, state, "MAT_INVALID_CAPACITY", "Container capacity must be > 0")
            metadata["capacity_uL"] = capacity_uL
        else:
            default_capacity_uL = default_container_capacity_uL(kind)
            if default_capacity_uL is not None:
                metadata["capacity_uL"] = default_capacity_uL
    if kind is not None:
        bind_name(state, kind + "::" + container_id, container_id, step.step_id)
    if label is not None:
        bind_name(state, label, container_id, step.step_id)
    if bind_ref is not None:
        bind_name(state, bind_ref, container_id, step.step_id)
    return MaterialUpdateResult(
        material_state=state,
        diagnostics=[],
        delta={"op": "AllocContainer", "container_id": container_id, "kind": kind, "bind": bind_ref},
    )


def apply_define_content(step: PlanStep, state: dict[str, Any]) -> MaterialUpdateResult:
    kind = arg_string(step.args.get("kind"))
    ctype = arg_string(step.args.get("type"))
    code = arg_string(step.args.get("code"))
    name = arg_string(step.args.get("name"))
    explicit_attrs = _arg_string_map(step.args.get("attrs"))
    normalized = normalize_content_classification(kind, ctype) if kind is not None and ctype is not None else None
    stored_kind = normalized.kind if normalized is not None else kind
    stored_type = normalized.type if normalized is not None else ctype
    content_id = code or name or step.step_id
    registry = state.setdefault("content_registry", {})
    if not isinstance(registry, dict):
        state["content_registry"] = {}
        registry = state["content_registry"]
    existing = registry.get(content_id)
    candidate = {
        "content_kind": stored_kind,
        "content_type": stored_type,
        "content_code": code,
        "content_name": name,
    }
    if normalized is not None and normalized.changed:
        candidate["content_original_kind"] = normalized.original_kind
        candidate["content_original_type"] = normalized.original_type
    merged_candidate_attrs: dict[str, Any] = {}
    if normalized is not None and normalized.attrs:
        merged_candidate_attrs.update(normalized.attrs)
    if explicit_attrs:
        merged_candidate_attrs.update(explicit_attrs)
    if merged_candidate_attrs:
        candidate["content_attrs"] = merged_candidate_attrs
    if isinstance(existing, dict):
        for key in ("content_kind", "content_type", "content_code"):
            old_v = existing.get(key)
            new_v = candidate.get(key)
            if old_v is not None and new_v is not None and old_v != new_v:
                return diagnostic_result(
                    step,
                    state,
                    "MAT_CONTENT_METADATA_CONFLICT",
                    f"Conflicting immutable metadata for content '{content_id}'",
                )
        if isinstance(existing.get("content_attrs"), dict) and isinstance(candidate.get("content_attrs"), dict):
            merged_attrs = dict(existing["content_attrs"])
            merged_attrs.update(candidate["content_attrs"])
            candidate["content_attrs"] = merged_attrs
        existing.update({k: v for k, v in candidate.items() if v is not None})
    else:
        registry[content_id] = candidate

    bindings = state.setdefault("content_bindings", {})
    if not isinstance(bindings, dict):
        state["content_bindings"] = {}
        bindings = state["content_bindings"]
    bindings[content_id] = content_id
    if code:
        bindings[code] = content_id
    if name:
        bindings[name] = content_id

    return MaterialUpdateResult(
        material_state=state,
        diagnostics=[],
        delta={"op": "DefineContent", "content_id": content_id},
    )


def apply_load_content(step: PlanStep, state: dict[str, Any]) -> MaterialUpdateResult:
    container_name = arg_string(step.args.get("container"))
    content_ref = arg_string(step.args.get("content"))
    amount = arg_quantity(step.args.get("amount"))
    if container_name is None or content_ref is None or amount is None:
        return diagnostic_result(step, state, "MAT_CONTENT_LOAD_AXIS_MISMATCH", "LoadContent args are invalid")

    content_id = resolve_content_ref(state, content_ref)
    if content_id is None:
        return diagnostic_result(step, state, "MAT_CONTENT_NOT_FOUND", f"Unknown content '{content_ref}'")
    registry = state.setdefault("content_registry", {})
    if not isinstance(registry, dict) or not isinstance(registry.get(content_id), dict):
        return diagnostic_result(step, state, "MAT_CONTENT_NOT_FOUND", f"Unknown content '{content_ref}'")

    container_id = resolve_or_create_container_ref(state, container_name)
    container = ensure_container(state, container_id)
    index = state.setdefault("container_content_index", {})
    if not isinstance(index, dict):
        state["container_content_index"] = {}
        index = state["container_content_index"]
    container_contents = index.setdefault(container_id, {})
    if not isinstance(container_contents, dict):
        index[container_id] = {}
        container_contents = index[container_id]
    slot = container_contents.setdefault(
        content_id,
        {"volume_uL": 0.0, "mass_mg": 0.0, "count_cells": 0.0, "axis": None, "unit": None},
    )
    if not isinstance(slot, dict):
        container_contents[content_id] = {
            "volume_uL": 0.0,
            "mass_mg": 0.0,
            "count_cells": 0.0,
            "axis": None,
            "unit": None,
        }
        slot = container_contents[content_id]

    unit = str(amount["unit"])
    value = float(amount["value"])
    if unit in VOLUME_TO_UL:
        axis = "volume"
        moved_uL = value * VOLUME_TO_UL[unit]
        moved_mg = moved_uL
        moved_cells = 0.0
        canonical_value = moved_uL
        canonical_unit = "uL"
    elif unit in MASS_TO_MG:
        axis = "mass"
        moved_mg = value * MASS_TO_MG[unit]
        moved_uL = moved_mg
        moved_cells = 0.0
        canonical_value = moved_mg
        canonical_unit = "mg"
    elif unit in COUNT_TO_CELLS:
        axis = "count"
        content = registry[content_id]
        if content.get("content_kind") != "bio_cellular":
            return diagnostic_result(
                step,
                state,
                "MAT_CONTENT_LOAD_AXIS_MISMATCH",
                f"Cell-count unit '{unit}' requires bio_cellular content, got '{content.get('content_kind')}'",
            )
        if value < 0 or not value.is_integer():
            return diagnostic_result(
                step,
                state,
                "MAT_CELL_COUNT_VALUE_INVALID",
                "Loaded cell count must be a non-negative integer",
            )
        moved_uL = 0.0
        moved_mg = 0.0
        moved_cells = value * COUNT_TO_CELLS[unit]
        canonical_value = moved_cells
        canonical_unit = "cells"
    else:
        return diagnostic_result(step, state, "MAT_CONTENT_LOAD_AXIS_MISMATCH", f"Unsupported amount unit '{unit}'")
    cap_diag = check_capacity_guard(step=step, state=state, container_id=container_id, added_uL=moved_uL)
    if cap_diag is not None:
        return cap_diag

    existing_axis = slot.get("axis")
    if existing_axis is not None and existing_axis != axis:
        return diagnostic_result(
            step,
            state,
            "MAT_CONTENT_LOAD_AXIS_MISMATCH",
            f"Content '{content_id}' in container '{container_id}' has axis '{existing_axis}', got '{axis}'",
        )
    slot["axis"] = axis
    slot["unit"] = canonical_unit
    slot["volume_uL"] = float(slot.get("volume_uL", 0.0)) + moved_uL
    slot["mass_mg"] = float(slot.get("mass_mg", 0.0)) + moved_mg
    slot["count_cells"] = float(slot.get("count_cells", 0.0)) + moved_cells

    comps = container.setdefault("components", {})
    if isinstance(comps, dict):
        comps[content_id] = float(comps.get(content_id, 0.0)) + canonical_value
    component_quantities = container.setdefault("component_quantities", {})
    if isinstance(component_quantities, dict):
        existing_quantity = component_quantities.get(content_id)
        if not isinstance(existing_quantity, dict):
            existing_quantity = {"dimension": axis, "unit": canonical_unit, "value": 0.0}
            component_quantities[content_id] = existing_quantity
        existing_quantity["value"] = float(existing_quantity.get("value", 0.0)) + canonical_value
    refresh_container_aggregates(container)
    invalidate_contents_state(state, container_id, reason="content_load")

    return MaterialUpdateResult(
        material_state=state,
        diagnostics=[],
        delta={
            "op": "LoadContent",
            "container": container_id,
            "content_id": content_id,
            "axis": axis,
            "amount": value,
            "unit": unit,
        },
    )


def apply_annotate_content(step: PlanStep, state: dict[str, Any]) -> MaterialUpdateResult:
    content_ref = arg_string(step.args.get("content"))
    if content_ref is None:
        return diagnostic_result(step, state, "MAT_CONTENT_NOT_FOUND", "AnnotateContent requires content")
    content_id = resolve_content_ref(state, content_ref)
    registry = state.setdefault("content_registry", {})
    if content_id is None or not isinstance(registry, dict) or not isinstance(registry.get(content_id), dict):
        return diagnostic_result(step, state, "MAT_CONTENT_NOT_FOUND", f"Unknown content '{content_ref}'")
    return MaterialUpdateResult(
        material_state=state,
        diagnostics=[],
        delta={"op": "AnnotateContent", "content_id": content_id},
    )


def _arg_string_map(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    attrs: dict[str, Any] = {}
    for key, raw in value.items():
        if not isinstance(key, str):
            continue
        text = arg_string(raw)
        if text is not None:
            attrs[key] = text
            continue
        boolean = arg_bool(raw)
        if boolean is not None:
            attrs[key] = boolean
    return attrs
