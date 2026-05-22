"""Material operation handlers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from copy import deepcopy
from typing import Any

from culsma.common.diagnostics import Diagnostic
from culsma.pipeline.content_vocab import ContainerKind, normalize_content_classification
from culsma.pipeline.plan_nodes import PlanStep
from culsma.runtime.material.partition import partition_sep_material
from culsma.runtime.material.support import (
    MaterialUpdateResult,
    _MASS_TO_MG,
    _VOLUME_TO_UL,
    _arg_bool,
    _arg_call,
    _arg_quantity,
    _arg_string,
    _bind_indexed_group,
    _bind_name,
    _call_arg_int,
    _call_arg_string,
    _check_capacity_guard,
    _collect_unit_into_container,
    _container,
    _default_container_capacity_uL,
    _density_mg_per_uL,
    _diag_result,
    _ensure_container,
    _inventory_check_enabled,
    _is_serialized_pair,
    _is_unit_ref,
    _move_explicit,
    _move_ratio,
    _normalize_capacity_uL,
    _ref_display,
    _resolve_content_ref,
    _resolve_or_create_container_ref,
    _resolve_source_ref,
    _resolve_structured_ref,
    _resolve_target_ref,
    _top_up_source_for_estimate,
)


class MaterialOpHandler(ABC):
    ops: frozenset[str] = frozenset()

    def handles(self, op: str) -> bool:
        return op in self.ops

    @abstractmethod
    def apply(self, step: PlanStep, state: dict[str, Any]) -> MaterialUpdateResult:
        raise NotImplementedError


class ContainerContentHandler(MaterialOpHandler):
    ops = frozenset({"AllocContainer", "DefineContent", "LoadContent", "AnnotateContent"})

    def apply(self, step: PlanStep, state: dict[str, Any]) -> MaterialUpdateResult:
        if step.op == "AllocContainer":
            return _apply_alloc_container(step, state)
        if step.op == "DefineContent":
            return _apply_define_content(step, state)
        if step.op == "LoadContent":
            return _apply_load_content(step, state)
        if step.op == "AnnotateContent":
            return _apply_annotate_content(step, state)
        return MaterialUpdateResult(material_state=state, diagnostics=[], delta={})


class MutationHandler(MaterialOpHandler):
    ops = frozenset({"Mutation"})

    def apply(self, step: PlanStep, state: dict[str, Any]) -> MaterialUpdateResult:
        return _apply_mutation(step, state)


class SeparationHandler(MaterialOpHandler):
    ops = frozenset({"sep", "frac"})

    def apply(self, step: PlanStep, state: dict[str, Any]) -> MaterialUpdateResult:
        if step.op == "sep":
            return _apply_sep(step, state)
        if step.op == "frac":
            return _apply_frac(step, state)
        return MaterialUpdateResult(material_state=state, diagnostics=[], delta={})


class NoopMaterialOpHandler(MaterialOpHandler):
    ops = frozenset()

    def handles(self, op: str) -> bool:
        return True

    def apply(self, step: PlanStep, state: dict[str, Any]) -> MaterialUpdateResult:
        return MaterialUpdateResult(material_state=state, diagnostics=[], delta={})


def _apply_alloc_container(step: PlanStep, state: dict[str, Any]) -> MaterialUpdateResult:
    kind = _arg_string(step.args.get("kind"))
    label = _arg_string(step.args.get("label"))
    barcode = _arg_string(step.args.get("barcode"))
    bind_name = _arg_string(step.args.get("bind"))
    open_flag = _arg_bool(step.args.get("open"))
    container_id = label or barcode or step.step_id
    container = _ensure_container(state, container_id)
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
                return _diag_result(step, state, "MAT_INVALID_CAPACITY", "surface constructor does not support volume capacity")
            capacity_uL = _normalize_capacity_uL(raw_capacity)
            if capacity_uL is None:
                qty = _arg_quantity(raw_capacity)
                if qty is None:
                    return _diag_result(step, state, "MAT_INVALID_CAPACITY", "Container capacity must be a volume quantity")
                unit = str(qty["unit"])
                if unit not in _VOLUME_TO_UL:
                    return _diag_result(step, state, "MAT_INVALID_CAPACITY", f"Unsupported capacity unit '{unit}'")
                return _diag_result(step, state, "MAT_INVALID_CAPACITY", "Container capacity must be > 0")
            metadata["capacity_uL"] = capacity_uL
        else:
            default_capacity_uL = _default_container_capacity_uL(kind)
            if default_capacity_uL is not None:
                metadata["capacity_uL"] = default_capacity_uL
    if kind is not None:
        _bind_name(state, kind + "::" + container_id, container_id, step.step_id)
    if label is not None:
        _bind_name(state, label, container_id, step.step_id)
    if bind_name is not None:
        _bind_name(state, bind_name, container_id, step.step_id)
    return MaterialUpdateResult(
        material_state=state,
        diagnostics=[],
        delta={"op": "AllocContainer", "container_id": container_id, "kind": kind, "bind": bind_name},
    )


def _apply_define_content(step: PlanStep, state: dict[str, Any]) -> MaterialUpdateResult:
    kind = _arg_string(step.args.get("kind"))
    ctype = _arg_string(step.args.get("type"))
    code = _arg_string(step.args.get("code"))
    name = _arg_string(step.args.get("name"))
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
    merged_candidate_attrs: dict[str, str] = {}
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
                return _diag_result(
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


def _arg_string_map(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    attrs: dict[str, str] = {}
    for key, raw in value.items():
        if not isinstance(key, str):
            continue
        text = _arg_string(raw)
        if text is not None:
            attrs[key] = text
    return attrs


def _apply_load_content(step: PlanStep, state: dict[str, Any]) -> MaterialUpdateResult:
    container_name = _arg_string(step.args.get("container"))
    content_ref = _arg_string(step.args.get("content"))
    amount = _arg_quantity(step.args.get("amount"))
    if container_name is None or content_ref is None or amount is None:
        return _diag_result(step, state, "MAT_CONTENT_LOAD_AXIS_MISMATCH", "LoadContent args are invalid")

    content_id = _resolve_content_ref(state, content_ref)
    if content_id is None:
        return _diag_result(step, state, "MAT_CONTENT_NOT_FOUND", f"Unknown content '{content_ref}'")
    registry = state.setdefault("content_registry", {})
    if not isinstance(registry, dict) or not isinstance(registry.get(content_id), dict):
        return _diag_result(step, state, "MAT_CONTENT_NOT_FOUND", f"Unknown content '{content_ref}'")

    container_id = _resolve_or_create_container_ref(state, container_name)
    container = _ensure_container(state, container_id)
    index = state.setdefault("container_content_index", {})
    if not isinstance(index, dict):
        state["container_content_index"] = {}
        index = state["container_content_index"]
    container_contents = index.setdefault(container_id, {})
    if not isinstance(container_contents, dict):
        index[container_id] = {}
        container_contents = index[container_id]
    slot = container_contents.setdefault(content_id, {"volume_uL": 0.0, "mass_mg": 0.0, "axis": None})
    if not isinstance(slot, dict):
        container_contents[content_id] = {"volume_uL": 0.0, "mass_mg": 0.0, "axis": None}
        slot = container_contents[content_id]

    unit = str(amount["unit"])
    value = float(amount["value"])
    if unit in _VOLUME_TO_UL:
        axis = "volume"
        moved_uL = value * _VOLUME_TO_UL[unit]
        moved_mg = moved_uL
    elif unit in _MASS_TO_MG:
        axis = "mass"
        moved_mg = value * _MASS_TO_MG[unit]
        moved_uL = moved_mg
    else:
        return _diag_result(step, state, "MAT_CONTENT_LOAD_AXIS_MISMATCH", f"Unsupported amount unit '{unit}'")
    cap_diag = _check_capacity_guard(step=step, state=state, container_id=container_id, added_uL=moved_uL)
    if cap_diag is not None:
        return cap_diag

    existing_axis = slot.get("axis")
    if existing_axis is not None and existing_axis != axis:
        return _diag_result(
            step,
            state,
            "MAT_CONTENT_LOAD_AXIS_MISMATCH",
            f"Content '{content_id}' in container '{container_id}' has axis '{existing_axis}', got '{axis}'",
        )
    slot["axis"] = axis
    slot["volume_uL"] = float(slot.get("volume_uL", 0.0)) + moved_uL
    slot["mass_mg"] = float(slot.get("mass_mg", 0.0)) + moved_mg

    container["volume_uL"] = float(container.get("volume_uL", 0.0)) + moved_uL
    container["mass_mg"] = float(container.get("mass_mg", 0.0)) + moved_mg
    comps = container.setdefault("components", {})
    if isinstance(comps, dict):
        comps[content_id] = float(comps.get(content_id, 0.0)) + moved_mg

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


def _apply_annotate_content(step: PlanStep, state: dict[str, Any]) -> MaterialUpdateResult:
    content_ref = _arg_string(step.args.get("content"))
    if content_ref is None:
        return _diag_result(step, state, "MAT_CONTENT_NOT_FOUND", "AnnotateContent requires content")
    content_id = _resolve_content_ref(state, content_ref)
    registry = state.setdefault("content_registry", {})
    if content_id is None or not isinstance(registry, dict) or not isinstance(registry.get(content_id), dict):
        return _diag_result(step, state, "MAT_CONTENT_NOT_FOUND", f"Unknown content '{content_ref}'")
    return MaterialUpdateResult(
        material_state=state,
        diagnostics=[],
        delta={"op": "AnnotateContent", "content_id": content_id},
    )


def _apply_mutation(step: PlanStep, state: dict[str, Any]) -> MaterialUpdateResult:
    target_expr = step.args.get("target")
    source_exprs = step.args.get("sources")
    if not isinstance(source_exprs, list):
        return _diag_result(step, state, "MAT_BINDING_NOT_FOUND", "Mutation requires source list")

    target_id = _resolve_target_ref(state, target_expr)
    if target_id is None:
        return _diag_result(
            step,
            state,
            "MAT_BINDING_NOT_FOUND",
            f"Unknown mutation target '{_ref_display(target_expr)}'",
        )

    working = deepcopy(state)
    applied_sources: list[dict[str, Any]] = []
    for source_expr in source_exprs:
        if _is_serialized_pair(source_expr):
            left = source_expr.get("left")
            right = source_expr.get("right")
            if _is_unit_ref(left):
                return _diag_result(
                    step,
                    state,
                    "MAT_UNIT_QUANTITY_UNSUPPORTED",
                    "Mutation does not support quantified unit_ref sources",
                )
            qty = _arg_quantity(right)
            if qty is None:
                return _diag_result(step, state, "MAT_UNSUPPORTED_UNIT", "Mutation quantified source must carry volume or mass unit")
            source_id = _resolve_source_ref(working, left, qty=qty)
            if source_id is None:
                return _diag_result(
                    step,
                    state,
                    "MAT_BINDING_NOT_FOUND",
                    f"Unknown mutation source '{_ref_display(left)}'",
                )
            if source_id == target_id:
                applied_sources.append({"mode": "quantified_self_noop", "source": source_id, "target": target_id, "qty": qty})
                continue
            transfer = _apply_transfer_by_qty(step=step, state=working, src_id=source_id, dst_id=target_id, qty=qty)
            if not transfer.ok:
                return transfer
            working = transfer.material_state
            applied_sources.append(
                {
                    "mode": "quantified",
                    "source": source_id,
                    "target": target_id,
                    "qty": qty,
                    "transfer_delta": transfer.delta,
                }
            )
            continue

        if _is_unit_ref(source_expr):
            collect = _collect_unit_into_container(
                step=step,
                state=working,
                target_id=target_id,
                unit=source_expr,
            )
            if not collect.ok:
                return collect
            working = collect.material_state
            applied_sources.append(
                {
                    "mode": "unit_collect",
                    "unit_id": source_expr.get("id"),
                    "target": target_id,
                    "collection_delta": collect.delta,
                }
            )
            continue

        source_id = _resolve_source_ref(working, source_expr, qty=None)
        if source_id is None:
            return _diag_result(
                step,
                state,
                "MAT_BINDING_NOT_FOUND",
                f"Unknown mutation source '{_ref_display(source_expr)}'",
            )
        if source_id == target_id:
            applied_sources.append({"mode": "full_self_noop", "source": source_id, "target": target_id})
            continue
        source = _container(working, source_id)
        target = _container(working, target_id)
        if source is None or target is None:
            return _diag_result(step, state, "MAT_BINDING_NOT_FOUND", "Mutation references unknown container")
        moved_uL = float(source.get("volume_uL", 0.0))
        moved_mg = float(source.get("mass_mg", 0.0))
        cap_diag = _check_capacity_guard(step=step, state=working, container_id=target_id, added_uL=moved_uL)
        if cap_diag is not None:
            return cap_diag
        _move_explicit(source, target, moved_uL, moved_mg, component_ratio=1.0)
        applied_sources.append(
            {
                "mode": "full",
                "source": source_id,
                "target": target_id,
                "moved_uL": moved_uL,
                "moved_mg": moved_mg,
            }
        )

    return MaterialUpdateResult(
        material_state=working,
        diagnostics=[],
        delta={
            "op": "Mutation",
            "target": target_id,
            "sources": applied_sources,
        },
    )


def _apply_transfer_by_qty(
    step: PlanStep,
    state: dict[str, Any],
    src_id: str,
    dst_id: str,
    qty: dict[str, Any],
) -> MaterialUpdateResult:
    unit = str(qty["unit"])
    value = float(qty["value"])
    if unit in _VOLUME_TO_UL:
        requested_uL = value * _VOLUME_TO_UL[unit]
        return _apply_transfer_volume(step, state, src_id, dst_id, requested_uL)
    if unit in _MASS_TO_MG:
        requested_mg = value * _MASS_TO_MG[unit]
        return _apply_transfer_mass(step, state, src_id, dst_id, requested_mg)
    return _diag_result(
        step=step,
        state=state,
        code="MAT_UNSUPPORTED_UNIT",
        message=f"Unsupported transfer unit '{unit}'",
    )


def _apply_transfer_volume(
    step: PlanStep,
    state: dict[str, Any],
    src_id: str,
    dst_id: str,
    requested_uL: float,
) -> MaterialUpdateResult:
    src = state["containers"][src_id]
    dst = state["containers"][dst_id]
    src_volume = float(src.get("volume_uL", 0.0))
    if not _inventory_check_enabled(state) and src_volume < requested_uL:
        _top_up_source_for_estimate(source=src, qty=requested_uL - src_volume, mode="volume", source_name=src_id)
        src_volume = float(src.get("volume_uL", 0.0))

    if requested_uL < 0:
        return _diag_result(step, state, "MAT_UNSUPPORTED_UNIT", "Negative transfer amount is not allowed")
    cap_diag = _check_capacity_guard(step=step, state=state, container_id=dst_id, added_uL=requested_uL)
    if cap_diag is not None:
        return cap_diag

    if src_volume >= requested_uL:
        ratio = 0.0 if src_volume == 0 else requested_uL / src_volume
        _move_ratio(src, dst, ratio)
        return MaterialUpdateResult(
            material_state=state,
            diagnostics=[],
            delta={"op": "material_move", "mode": "volume", "source": src_id, "dest": dst_id, "moved_uL": requested_uL},
        )

    if src_volume > 0:
        return _diag_result(step, state, "MAT_INSUFFICIENT_VOLUME", f"Insufficient source volume in '{src_id}'")

    density = _density_mg_per_uL(src)
    if density is None:
        return _diag_result(step, state, "MAT_MISSING_DENSITY", f"Need density metadata for '{src_id}'")
    if density <= 0:
        return _diag_result(step, state, "MAT_INVALID_DENSITY", f"Invalid density metadata for '{src_id}'")

    requested_mg = requested_uL * density
    src_mass = float(src.get("mass_mg", 0.0))
    effective_src_mass = max(src_mass, src_volume * density)
    effective_src_volume = max(src_volume, effective_src_mass / density)
    if effective_src_mass < requested_mg:
        return _diag_result(step, state, "MAT_INSUFFICIENT_MASS", f"Insufficient source mass in '{src_id}'")

    src["mass_mg"] = effective_src_mass
    src["volume_uL"] = effective_src_volume
    component_ratio = 0.0 if effective_src_mass == 0 else requested_mg / effective_src_mass
    _move_explicit(
        src=src,
        dst=dst,
        moved_volume_uL=requested_uL,
        moved_mass_mg=requested_mg,
        component_ratio=component_ratio,
    )
    return MaterialUpdateResult(
        material_state=state,
        diagnostics=[],
        delta={
            "op": "material_move",
            "mode": "bridge_volume_to_mass",
            "source": src_id,
            "dest": dst_id,
            "requested_uL": requested_uL,
            "converted_mg": requested_mg,
            "density_mg_per_uL": density,
        },
    )


def _apply_transfer_mass(
    step: PlanStep,
    state: dict[str, Any],
    src_id: str,
    dst_id: str,
    requested_mg: float,
) -> MaterialUpdateResult:
    src = state["containers"][src_id]
    dst = state["containers"][dst_id]
    src_mass = float(src.get("mass_mg", 0.0))
    if not _inventory_check_enabled(state) and src_mass < requested_mg:
        _top_up_source_for_estimate(source=src, qty=requested_mg - src_mass, mode="mass", source_name=src_id)
        src_mass = float(src.get("mass_mg", 0.0))

    if requested_mg < 0:
        return _diag_result(step, state, "MAT_UNSUPPORTED_UNIT", "Negative transfer amount is not allowed")

    if src_mass >= requested_mg:
        ratio = 0.0 if src_mass == 0 else requested_mg / src_mass
        moved_uL = ratio * float(src.get("volume_uL", 0.0))
        cap_diag = _check_capacity_guard(step=step, state=state, container_id=dst_id, added_uL=moved_uL)
        if cap_diag is not None:
            return cap_diag
        _move_ratio(src, dst, ratio)
        return MaterialUpdateResult(
            material_state=state,
            diagnostics=[],
            delta={"op": "material_move", "mode": "mass", "source": src_id, "dest": dst_id, "moved_mg": requested_mg},
        )

    if src_mass > 0:
        return _diag_result(step, state, "MAT_INSUFFICIENT_MASS", f"Insufficient source mass in '{src_id}'")

    density = _density_mg_per_uL(src)
    if density is None:
        return _diag_result(step, state, "MAT_MISSING_DENSITY", f"Need density metadata for '{src_id}'")
    if density <= 0:
        return _diag_result(step, state, "MAT_INVALID_DENSITY", f"Invalid density metadata for '{src_id}'")

    requested_uL = requested_mg / density
    cap_diag = _check_capacity_guard(step=step, state=state, container_id=dst_id, added_uL=requested_uL)
    if cap_diag is not None:
        return cap_diag
    src_volume = float(src.get("volume_uL", 0.0))
    effective_src_volume = max(src_volume, src_mass / density)
    effective_src_mass = max(src_mass, effective_src_volume * density)
    if effective_src_volume < requested_uL:
        return _diag_result(step, state, "MAT_INSUFFICIENT_VOLUME", f"Insufficient source volume in '{src_id}'")

    src["volume_uL"] = effective_src_volume
    src["mass_mg"] = effective_src_mass
    component_ratio = 0.0 if effective_src_volume == 0 else requested_uL / effective_src_volume
    _move_explicit(
        src=src,
        dst=dst,
        moved_volume_uL=requested_uL,
        moved_mass_mg=requested_mg,
        component_ratio=component_ratio,
    )
    return MaterialUpdateResult(
        material_state=state,
        diagnostics=[],
        delta={
            "op": "material_move",
            "mode": "bridge_mass_to_volume",
            "source": src_id,
            "dest": dst_id,
            "requested_mg": requested_mg,
            "converted_uL": requested_uL,
            "density_mg_per_uL": density,
        },
    )


def _apply_sep(step: PlanStep, state: dict[str, Any]) -> MaterialUpdateResult:
    sample_arg = step.args.get("sample")
    bind_name = _arg_string(step.args.get("bind"))
    program = _arg_call(step.args.get("program"))
    if bind_name is None or program is None:
        return _diag_result(step, state, "MAT_BINDING_NOT_FOUND", "sep requires sample/program/bind")

    source_id = _resolve_structured_ref(state, sample_arg, create_if_identifier=not _inventory_check_enabled(state))
    if source_id is None:
        if _inventory_check_enabled(state):
            return _diag_result(step, state, "MAT_BINDING_NOT_FOUND", f"Unknown sep sample '{_ref_display(sample_arg)}'")
        sample_name = _arg_string(sample_arg)
        if sample_name is None:
            return _diag_result(step, state, "MAT_BINDING_NOT_FOUND", "sep requires sample/program/bind")
        source_id = _resolve_or_create_container_ref(state, sample_name)
    source = _container(state, source_id)
    if source is None:
        return _diag_result(step, state, "MAT_BINDING_NOT_FOUND", f"Unknown sep sample '{_ref_display(sample_arg)}'")

    program_kind = str(program.get("name")) if isinstance(program.get("name"), str) else "sep_program"
    keep_source = _call_arg_string(program, "keep_source")

    working = deepcopy(state)
    source = _container(working, source_id)
    if source is None:
        return _diag_result(step, state, "MAT_BINDING_NOT_FOUND", f"Unknown sep sample '{_ref_display(sample_arg)}'")

    slot0_id = f"{step.step_id}::0"
    slot1_id = f"{step.step_id}::1"
    if program_kind == "centrifuge_program" and keep_source == "supernatant":
        slot0_id = source_id
    elif program_kind == "centrifuge_program" and keep_source == "pellet":
        slot1_id = source_id

    slot0 = _ensure_container(working, slot0_id)
    slot1 = _ensure_container(working, slot1_id)

    if slot0_id == source_id and slot1_id == source_id:
        return _diag_result(step, state, "MAT_STATE_INVARIANT_VIOLATION", "sep cannot alias both slots to the source container")

    partition = partition_sep_material(
        state=working,
        source=source,
        slot0=slot0,
        slot1=slot1,
        program_kind=program_kind,
    )
    diagnostics = _partition_fallback_diagnostics(step, partition)

    binding_events = _bind_indexed_group(
        working,
        bind_name,
        {"0": slot0_id, "1": slot1_id},
        step.step_id,
    )

    return MaterialUpdateResult(
        material_state=working,
        diagnostics=diagnostics,
        delta={
            "op": "sep",
            "program_kind": program_kind,
            "bind": bind_name,
            "slots": {"0": slot0_id, "1": slot1_id},
            "keep_source": keep_source,
            "partition": partition,
            "binding_events": binding_events,
        },
    )


def _partition_fallback_diagnostics(step: PlanStep, partition: dict[str, Any]) -> list[Diagnostic]:
    fallback_components = partition.get("fallback_components")
    if not isinstance(fallback_components, list):
        return []
    diagnostics: list[Diagnostic] = []
    for entry in fallback_components:
        if not isinstance(entry, dict):
            continue
        component = str(entry.get("component", "") or "<unknown>")
        partition_class = str(entry.get("partition_class", "") or "unknown")
        reason = str(entry.get("reason", "") or "fallback")
        diagnostics.append(
            Diagnostic(
                code="MAT_CONTENT_PARTITION_FALLBACK",
                message=(
                    f"Component '{component}' used conservative 0.50/0.50 partition "
                    f"for class '{partition_class}' ({reason}); provide explicit "
                    "component_partition_ratios if this behavior is intended"
                ),
                span=step.span,
                severity="warning",
                node_id=step.step_id,
            )
        )
    return diagnostics


def _apply_frac(step: PlanStep, state: dict[str, Any]) -> MaterialUpdateResult:
    sample_arg = step.args.get("sample")
    bind_name = _arg_string(step.args.get("bind"))
    program = _arg_call(step.args.get("program"))
    if bind_name is None or program is None:
        return _diag_result(step, state, "MAT_BINDING_NOT_FOUND", "frac requires sample/program/bind")

    bins = _call_arg_int(program, "bins")
    if bins is None or bins <= 0:
        return _diag_result(step, state, "MAT_BINDING_NOT_FOUND", "frac requires positive bins")

    source_id = _resolve_structured_ref(state, sample_arg, create_if_identifier=not _inventory_check_enabled(state))
    if source_id is None:
        if _inventory_check_enabled(state):
            return _diag_result(step, state, "MAT_BINDING_NOT_FOUND", f"Unknown frac sample '{_ref_display(sample_arg)}'")
        sample_name = _arg_string(sample_arg)
        if sample_name is None:
            return _diag_result(step, state, "MAT_BINDING_NOT_FOUND", "frac requires sample/program/bind")
        source_id = _resolve_or_create_container_ref(state, sample_name)
    source = _container(state, source_id)
    if source is None:
        return _diag_result(step, state, "MAT_BINDING_NOT_FOUND", f"Unknown frac sample '{_ref_display(sample_arg)}'")

    working = deepcopy(state)
    source = _container(working, source_id)
    if source is None:
        return _diag_result(step, state, "MAT_BINDING_NOT_FOUND", f"Unknown frac sample '{_ref_display(sample_arg)}'")

    source_volume = float(source.get("volume_uL", 0.0))
    source_mass = float(source.get("mass_mg", 0.0))
    split_ratio = 1.0 / bins
    slot_bindings: dict[str, str] = {}

    for i in range(bins - 1):
        slot_id = f"{step.step_id}::{i}"
        slot = _ensure_container(working, slot_id)
        _move_explicit(source, slot, source_volume * split_ratio, source_mass * split_ratio, component_ratio=split_ratio)
        slot_bindings[str(i)] = slot_id

    last_slot_id = f"{step.step_id}::{bins - 1}"
    last_slot = _ensure_container(working, last_slot_id)
    residual_volume = float(source.get("volume_uL", 0.0))
    residual_mass = float(source.get("mass_mg", 0.0))
    _move_explicit(source, last_slot, residual_volume, residual_mass, component_ratio=1.0)
    slot_bindings[str(bins - 1)] = last_slot_id
    binding_events = _bind_indexed_group(working, bind_name, slot_bindings, step.step_id)

    return MaterialUpdateResult(
        material_state=working,
        diagnostics=[],
        delta={
            "op": "frac",
            "bind": bind_name,
            "bins": bins,
            "slots": dict(slot_bindings),
            "split_ratio": split_ratio,
            "binding_events": binding_events,
        },
    )
