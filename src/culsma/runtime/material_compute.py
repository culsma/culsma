"""Deterministic material-state compute for runtime steps."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from culsma.pipeline.plan_nodes import PlanStep
from culsma.common.diagnostics import Diagnostic


_VOLUME_TO_UL: dict[str, float] = {
    "uL": 1.0,
    "ul": 1.0,
    "mL": 1000.0,
    "ml": 1000.0,
    "L": 1_000_000.0,
}

_MASS_TO_MG: dict[str, float] = {
    "ug": 0.001,
    "mg": 1.0,
    "g": 1000.0,
    "kg": 1_000_000.0,
}

_DEFAULT_CONTAINER_CAPACITY_UL: dict[str, float] = {
    "container": 1000.0,
    "tube": 1500.0,
    "well": 200.0,
    "chamber": 1000.0,
}

_CONSERVATION_ABS_EPS = 1e-12
_CONSERVATION_REL_EPS = 1e-9
_CONSERVATION_OPS = {"Mutation", "sep", "frac"}


@dataclass(frozen=True)
class MaterialUpdateResult:
    material_state: dict[str, Any]
    diagnostics: list[Diagnostic] = field(default_factory=list)
    delta: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.diagnostics


def apply_step(step: PlanStep, material_state: dict[str, Any]) -> MaterialUpdateResult:
    """Apply deterministic material update for one runtime step."""
    state = deepcopy(material_state)
    state.setdefault("containers", {})
    _initialize_bindings(state)
    before_totals = _state_totals(state)

    if step.op == "AllocContainer":
        result = _apply_alloc_container(step, state)
    elif step.op == "DefineContent":
        result = _apply_define_content(step, state)
    elif step.op == "LoadContent":
        result = _apply_load_content(step, state)
    elif step.op == "AnnotateContent":
        result = _apply_annotate_content(step, state)
    elif step.op == "Mutation":
        result = _apply_mutation(step, state)
    elif step.op == "sep":
        result = _apply_sep(step, state)
    elif step.op == "frac":
        result = _apply_frac(step, state)
    else:
        result = MaterialUpdateResult(material_state=material_state, diagnostics=[], delta={})

    if result.ok and step.op in _CONSERVATION_OPS and _inventory_check_enabled(state):
        after_totals = _state_totals(result.material_state)
        if not _totals_conserved(before_totals, after_totals):
            return _diag_result(
                step=step,
                state=result.material_state,
                code="MAT_CONSERVATION_VIOLATION",
                message=f"Conservation check failed for op '{step.op}'",
            )

    return result


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
            if kind == "surface":
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
    content_id = code or name or step.step_id
    registry = state.setdefault("content_registry", {})
    if not isinstance(registry, dict):
        state["content_registry"] = {}
        registry = state["content_registry"]
    existing = registry.get(content_id)
    candidate = {
        "content_kind": kind,
        "content_type": ctype,
        "content_code": code,
        "content_name": name,
    }
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

    source_volume = float(source.get("volume_uL", 0.0))
    source_mass = float(source.get("mass_mg", 0.0))
    split_ratio = 0.5

    if slot0_id == source_id:
        moved_uL = source_volume * (1.0 - split_ratio)
        moved_mg = source_mass * (1.0 - split_ratio)
        _move_explicit(source, slot1, moved_uL, moved_mg, component_ratio=(1.0 - split_ratio))
    elif slot1_id == source_id:
        moved_uL = source_volume * split_ratio
        moved_mg = source_mass * split_ratio
        _move_explicit(source, slot0, moved_uL, moved_mg, component_ratio=split_ratio)
    else:
        # Materialize both outputs as new containers; source is consumed into the group.
        _move_explicit(source, slot0, source_volume * split_ratio, source_mass * split_ratio, component_ratio=split_ratio)
        residual_volume = float(source.get("volume_uL", 0.0))
        residual_mass = float(source.get("mass_mg", 0.0))
        _move_explicit(source, slot1, residual_volume, residual_mass, component_ratio=1.0)

    binding_events = _bind_indexed_group(
        working,
        bind_name,
        {"0": slot0_id, "1": slot1_id},
        step.step_id,
    )

    return MaterialUpdateResult(
        material_state=working,
        diagnostics=[],
        delta={
            "op": "sep",
            "program_kind": program_kind,
            "bind": bind_name,
            "slots": {"0": slot0_id, "1": slot1_id},
            "keep_source": keep_source,
            "split_ratio": split_ratio,
            "binding_events": binding_events,
        },
    )


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


def _move_ratio(src: dict[str, Any], dst: dict[str, Any], ratio: float) -> None:
    moved_volume = ratio * float(src.get("volume_uL", 0.0))
    moved_mass = ratio * float(src.get("mass_mg", 0.0))
    _move_explicit(src=src, dst=dst, moved_volume_uL=moved_volume, moved_mass_mg=moved_mass, component_ratio=ratio)


def _move_explicit(
    src: dict[str, Any],
    dst: dict[str, Any],
    moved_volume_uL: float,
    moved_mass_mg: float,
    component_ratio: float,
) -> None:
    src["volume_uL"] = float(src.get("volume_uL", 0.0)) - moved_volume_uL
    dst["volume_uL"] = float(dst.get("volume_uL", 0.0)) + moved_volume_uL
    src["mass_mg"] = float(src.get("mass_mg", 0.0)) - moved_mass_mg
    dst["mass_mg"] = float(dst.get("mass_mg", 0.0)) + moved_mass_mg

    src_comp = src.setdefault("components", {})
    dst_comp = dst.setdefault("components", {})
    for name, amount in list(src_comp.items()):
        moved = component_ratio * float(amount)
        src_comp[name] = float(amount) - moved
        dst_comp[name] = float(dst_comp.get(name, 0.0)) + moved


def _remove_ratio(source: dict[str, Any], ratio: float) -> None:
    source["volume_uL"] = float(source.get("volume_uL", 0.0)) * (1.0 - ratio)
    source["mass_mg"] = float(source.get("mass_mg", 0.0)) * (1.0 - ratio)
    comp = source.setdefault("components", {})
    for name, amount in list(comp.items()):
        comp[name] = float(amount) * (1.0 - ratio)


def _primary_concentration(container: dict[str, Any]) -> float | None:
    volume = float(container.get("volume_uL", 0.0))
    if volume <= 0:
        return None
    comp = container.get("components")
    if not isinstance(comp, dict) or not comp:
        return None
    first = next(iter(comp.values()))
    return float(first) / volume


def _quantity_to_uL(qty: dict[str, Any]) -> float | None:
    unit = str(qty["unit"])
    if unit not in _VOLUME_TO_UL:
        return None
    return float(qty["value"]) * _VOLUME_TO_UL[unit]


def _density_mg_per_uL(container: dict[str, Any]) -> float | None:
    metadata = container.get("metadata")
    if not isinstance(metadata, dict):
        return None
    value = metadata.get("density_g_per_mL")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return -1.0


def _is_qualified_name(name: str) -> bool:
    if "::" not in name:
        return False
    head, tail = name.split("::", 1)
    return bool(head) and bool(tail)


def _is_serialized_pair(value: Any) -> bool:
    return isinstance(value, dict) and value.get("kind") == "IRPair"


def _is_unit_ref(value: Any) -> bool:
    return isinstance(value, dict) and value.get("kind") == "unit_ref"


def _initialize_bindings(state: dict[str, Any]) -> None:
    bindings = state.setdefault("bindings", {})
    if not isinstance(bindings, dict):
        state["bindings"] = {}
        bindings = state["bindings"]
    containers = state.setdefault("containers", {})
    for container_id in containers:
        if isinstance(container_id, str) and container_id not in bindings:
            bindings[container_id] = container_id
    indexed_bindings = state.setdefault("indexed_bindings", {})
    if not isinstance(indexed_bindings, dict):
        state["indexed_bindings"] = {}


def _inventory_check_enabled(state: dict[str, Any]) -> bool:
    raw = state.get("_inventory_check")
    if isinstance(raw, bool):
        return raw
    return True


def _provision_source_for_estimate(state: dict[str, Any], name: str, qty: dict[str, Any]) -> str:
    source_id = _resolve_or_create_container_ref(state, name)
    source = _ensure_container(state, source_id)
    unit = str(qty["unit"])
    value = float(qty["value"])
    if unit in _VOLUME_TO_UL:
        requested_uL = value * _VOLUME_TO_UL[unit]
        _top_up_source_for_estimate(source=source, qty=requested_uL, mode="volume", source_name=name)
    elif unit in _MASS_TO_MG:
        requested_mg = value * _MASS_TO_MG[unit]
        _top_up_source_for_estimate(source=source, qty=requested_mg, mode="mass", source_name=name)
    return source_id


def _top_up_source_for_estimate(source: dict[str, Any], qty: float, mode: str, source_name: str) -> None:
    if qty <= 0:
        return
    comps = source.setdefault("components", {})
    if mode == "volume":
        source["volume_uL"] = float(source.get("volume_uL", 0.0)) + qty
        source["mass_mg"] = float(source.get("mass_mg", 0.0)) + qty
        comps[source_name] = float(comps.get(source_name, 0.0)) + qty
    else:
        source["mass_mg"] = float(source.get("mass_mg", 0.0)) + qty
        source["volume_uL"] = float(source.get("volume_uL", 0.0)) + qty
        comps[source_name] = float(comps.get(source_name, 0.0)) + qty


def _resolve_container_ref(state: dict[str, Any], name: str) -> str | None:
    containers = state.setdefault("containers", {})
    if _is_qualified_name(name):
        return name if isinstance(containers.get(name), dict) else None
    bindings = state.setdefault("bindings", {})
    bound = bindings.get(name) if isinstance(bindings, dict) else None
    if isinstance(bound, str) and isinstance(containers.get(bound), dict):
        return bound
    if isinstance(containers.get(name), dict):
        return name
    return None


def _resolve_target_ref(state: dict[str, Any], value: Any) -> str | None:
    name = _arg_string(value)
    if name is not None:
        return _resolve_or_create_container_ref(state, name)
    return _resolve_structured_ref(state, value, create_if_identifier=True)


def _resolve_source_ref(state: dict[str, Any], value: Any, qty: dict[str, Any] | None) -> str | None:
    name = _arg_string(value)
    if name is not None:
        resolved = _resolve_container_ref(state, name)
        if resolved is not None:
            return resolved
        if _inventory_check_enabled(state):
            return None
        if qty is not None:
            return _provision_source_for_estimate(state=state, name=name, qty=qty)
        return _resolve_or_create_container_ref(state, name)
    return _resolve_structured_ref(state, value, create_if_identifier=not _inventory_check_enabled(state))


def _resolve_structured_ref(state: dict[str, Any], value: Any, *, create_if_identifier: bool) -> str | None:
    if not isinstance(value, dict):
        return None
    kind = value.get("kind")
    if kind == "IRIdentifier":
        name = value.get("name")
        if not isinstance(name, str):
            return None
        if create_if_identifier:
            return _resolve_or_create_container_ref(state, name)
        return _resolve_container_ref(state, name)
    if kind != "IRIndex":
        return None
    base = value.get("base")
    index = value.get("index")
    if not isinstance(base, dict) or base.get("kind") != "IRIdentifier":
        return None
    group_name = base.get("name")
    if not isinstance(group_name, str):
        return None
    slot = _static_index_key(index)
    if slot is None:
        return None
    indexed_bindings = state.setdefault("indexed_bindings", {})
    if not isinstance(indexed_bindings, dict):
        return None
    group = indexed_bindings.get(group_name)
    if not isinstance(group, dict):
        return None
    bound = group.get(slot)
    if isinstance(bound, str) and _container(state, bound) is not None:
        return bound
    return None


def _resolve_content_ref(state: dict[str, Any], name: str) -> str | None:
    registry = state.setdefault("content_registry", {})
    bindings = state.setdefault("content_bindings", {})
    if isinstance(bindings, dict):
        bound = bindings.get(name)
        if isinstance(bound, str):
            if isinstance(registry, dict) and isinstance(registry.get(bound), dict):
                return bound
    if isinstance(registry, dict) and isinstance(registry.get(name), dict):
        return name
    return None


def _collect_unit_into_container(
    *,
    step: PlanStep,
    state: dict[str, Any],
    target_id: str,
    unit: dict[str, Any],
) -> MaterialUpdateResult:
    container = _container(state, target_id)
    if container is None:
        return _diag_result(step, state, "MAT_BINDING_NOT_FOUND", f"Unknown collection target '{target_id}'")
    metadata = container.setdefault("metadata", {})
    if not isinstance(metadata, dict):
        container["metadata"] = {}
        metadata = container["metadata"]
    collected_units = metadata.setdefault("collected_units", [])
    if not isinstance(collected_units, list):
        metadata["collected_units"] = []
        collected_units = metadata["collected_units"]
    collected_units.append(deepcopy(unit))
    metadata["unit_count"] = len(collected_units)
    return MaterialUpdateResult(
        material_state=state,
        diagnostics=[],
        delta={
            "op": "unit_collect",
            "target": target_id,
            "unit_id": unit.get("id"),
            "unit_count": metadata["unit_count"],
        },
    )


def _check_capacity_guard(
    *,
    step: PlanStep,
    state: dict[str, Any],
    container_id: str,
    added_uL: float,
) -> MaterialUpdateResult | None:
    container = _container(state, container_id)
    if container is None:
        return _diag_result(step, state, "MAT_BINDING_NOT_FOUND", f"Unknown target container '{container_id}'")
    metadata = container.get("metadata", {})
    if not isinstance(metadata, dict):
        return _diag_result(step, state, "MAT_INVALID_CAPACITY", f"Invalid capacity metadata for '{container_id}'")
    if "capacity_uL" not in metadata:
        return None
    raw = metadata.get("capacity_uL")
    try:
        capacity_uL = float(raw)
    except (TypeError, ValueError):
        return _diag_result(step, state, "MAT_INVALID_CAPACITY", f"Invalid capacity value for '{container_id}'")
    if capacity_uL <= 0:
        return _diag_result(step, state, "MAT_INVALID_CAPACITY", f"Invalid capacity value for '{container_id}'")
    current_uL = float(container.get("volume_uL", 0.0))
    if current_uL + float(added_uL) > capacity_uL + 1e-12:
        return _diag_result(
            step,
            state,
            "MAT_CONTAINER_OVERFLOW",
            f"Container '{container_id}' capacity exceeded ({current_uL + float(added_uL)}uL > {capacity_uL}uL)",
        )
    return None


def _default_container_capacity_uL(kind: str | None) -> float | None:
    if kind is None:
        return _DEFAULT_CONTAINER_CAPACITY_UL["container"]
    if kind == "surface":
        return None
    return _DEFAULT_CONTAINER_CAPACITY_UL.get(kind, _DEFAULT_CONTAINER_CAPACITY_UL["container"])


def _normalize_capacity_uL(value: Any) -> float | None:
    qty = _arg_quantity(value)
    if qty is None:
        return None
    unit = str(qty["unit"])
    if unit not in _VOLUME_TO_UL:
        return None
    capacity_uL = float(qty["value"]) * _VOLUME_TO_UL[unit]
    if capacity_uL <= 0:
        return None
    return capacity_uL


def _resolve_or_create_container_ref(state: dict[str, Any], name: str) -> str:
    resolved = _resolve_container_ref(state, name)
    if resolved is not None:
        return resolved
    if _is_qualified_name(name):
        _ensure_container(state, name)
        return name
    _ensure_container(state, name)
    _bind_name(state, name, name, step_id=None)
    return name


def _static_index_key(value: Any) -> str | None:
    if not isinstance(value, dict) or value.get("kind") != "IRQuantity":
        return None
    unit = value.get("unit")
    raw = value.get("value")
    if unit is not None or not isinstance(raw, (int, float)):
        return None
    if float(raw) < 0 or not float(raw).is_integer():
        return None
    return str(int(raw))


def _bind_name(state: dict[str, Any], name: str, container_id: str, step_id: str | None) -> list[dict[str, Any]]:
    bindings = state.setdefault("bindings", {})
    if not isinstance(bindings, dict):
        state["bindings"] = {}
        bindings = state["bindings"]
    previous = bindings.get(name)
    bindings[name] = container_id
    if isinstance(previous, str) and previous != container_id:
        return [
            {
                "event": "BINDING_OVERWRITTEN",
                "name": name,
                "old_container_id": previous,
                "new_container_id": container_id,
                "step_id": step_id,
            }
        ]
    return []


def _bind_indexed_group(
    state: dict[str, Any],
    group_name: str,
    slots: dict[str, str],
    step_id: str | None,
) -> list[dict[str, Any]]:
    indexed_bindings = state.setdefault("indexed_bindings", {})
    if not isinstance(indexed_bindings, dict):
        state["indexed_bindings"] = {}
        indexed_bindings = state["indexed_bindings"]
    previous = indexed_bindings.get(group_name)
    indexed_bindings[group_name] = dict(slots)

    if not isinstance(previous, dict):
        return []

    events: list[dict[str, Any]] = []
    for slot, new_container_id in slots.items():
        old_container_id = previous.get(slot)
        if isinstance(old_container_id, str) and old_container_id != new_container_id:
            events.append(
                {
                    "event": "BINDING_OVERWRITTEN",
                    "name": f"{group_name}[{slot}]",
                    "old_container_id": old_container_id,
                    "new_container_id": new_container_id,
                    "step_id": step_id,
                }
            )
    return events


def _state_totals(state: dict[str, Any]) -> dict[str, float]:
    total_volume = 0.0
    total_mass = 0.0
    total_components = 0.0
    containers = state.setdefault("containers", {})
    for obj in containers.values():
        if not isinstance(obj, dict):
            continue
        volume_uL = float(obj.get("volume_uL", 0.0))
        mass_mg = float(obj.get("mass_mg", 0.0))
        density = _density_mg_per_uL(obj)
        if density is not None and density > 0:
            total_volume += max(volume_uL, mass_mg / density)
            total_mass += max(mass_mg, volume_uL * density)
        else:
            total_volume += volume_uL
            total_mass += mass_mg
        comp = obj.get("components", {})
        if isinstance(comp, dict):
            total_components += sum(float(v) for v in comp.values())
    return {"volume_uL": total_volume, "mass_mg": total_mass, "components": total_components}


def _close_enough(before: float, after: float) -> bool:
    delta = abs(before - after)
    if delta <= _CONSERVATION_ABS_EPS:
        return True
    scale = max(abs(before), abs(after), _CONSERVATION_ABS_EPS)
    return (delta / scale) <= _CONSERVATION_REL_EPS


def _totals_conserved(before: dict[str, float], after: dict[str, float]) -> bool:
    return all(
        _close_enough(float(before.get(key, 0.0)), float(after.get(key, 0.0)))
        for key in ("volume_uL", "mass_mg", "components")
    )


def _container(state: dict[str, Any], container_id: str) -> dict[str, Any] | None:
    containers = state.setdefault("containers", {})
    obj = containers.get(container_id)
    return obj if isinstance(obj, dict) else None


def _ensure_container(state: dict[str, Any], container_id: str) -> dict[str, Any]:
    containers = state.setdefault("containers", {})
    obj = containers.setdefault(
        container_id,
        {"volume_uL": 0.0, "mass_mg": 0.0, "components": {}, "metadata": {}},
    )
    if not isinstance(obj, dict):
        containers[container_id] = {"volume_uL": 0.0, "mass_mg": 0.0, "components": {}, "metadata": {}}
    return containers[container_id]


def _arg_string(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        if value.get("kind") == "IRString":
            inner = value.get("value")
            return inner if isinstance(inner, str) else None
        if value.get("kind") == "IRIdentifier":
            inner = value.get("name")
            return inner if isinstance(inner, str) else None
    return None


def _arg_numeric(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):
        if value.get("kind") == "IRQuantity":
            inner = value.get("value")
            if isinstance(inner, (int, float)):
                return float(inner)
    return None


def _arg_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, dict) and value.get("kind") == "IRBoolean":
        inner = value.get("value")
        return inner if isinstance(inner, bool) else None
    return None


def _arg_quantity(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict) and value.get("kind") == "IRQuantity":
        v = value.get("value")
        u = value.get("unit")
        if isinstance(v, (int, float)) and isinstance(u, str):
            return {"value": float(v), "unit": u}
    return None


def _arg_call(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict) and value.get("kind") == "IRCall":
        return value
    return None


def _call_arg_value(call: dict[str, Any], name: str) -> Any:
    args = call.get("args")
    if not isinstance(args, list):
        return None
    for arg in args:
        if isinstance(arg, dict) and arg.get("kind") == "IRArg" and arg.get("name") == name:
            return arg.get("value")
    return None


def _call_arg_string(call: dict[str, Any], name: str) -> str | None:
    return _arg_string(_call_arg_value(call, name))


def _call_arg_int(call: dict[str, Any], name: str) -> int | None:
    value = _call_arg_value(call, name)
    if isinstance(value, dict) and value.get("kind") == "IRQuantity":
        raw = value.get("value")
        unit = value.get("unit")
        if unit is None and isinstance(raw, (int, float)) and float(raw).is_integer():
            return int(raw)
    return None


def _diag_result(step: PlanStep, state: dict[str, Any], code: str, message: str) -> MaterialUpdateResult:
    return MaterialUpdateResult(
        material_state=state,
        diagnostics=[Diagnostic(code=code, message=message, span=step.span, node_id=step.step_id)],
        delta={},
    )


def _ref_display(value: Any) -> str:
    if isinstance(value, str):
        return value
    if not isinstance(value, dict):
        return "<invalid-ref>"
    kind = value.get("kind")
    if kind == "IRIdentifier":
        name = value.get("name")
        return name if isinstance(name, str) else "<identifier>"
    if kind == "IRIndex":
        base = _ref_display(value.get("base"))
        slot = _static_index_key(value.get("index"))
        return f"{base}[{slot if slot is not None else '?'}]"
    if kind == "IRString":
        inner = value.get("value")
        return inner if isinstance(inner, str) else "<string>"
    return f"<{kind or 'unknown-ref'}>"
