"""Separation and fractionation material operation implementations."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from culsma.common.diagnostics import Diagnostic
from culsma.pipeline.plan_nodes import PlanStep
from culsma.runtime.material.args import arg_call, arg_string, call_arg_int, call_arg_string
from culsma.runtime.material.contents_state import record_partitioned_contents_state, remove_transient_containers
from culsma.runtime.material.diagnostics import diagnostic_result
from culsma.runtime.material.ledger import container, ensure_container, move_explicit
from culsma.runtime.material.partition import normalize_source_partition_slot_bulk, partition_sep_material
from culsma.runtime.material.refs import (
    bind_indexed_group,
    inventory_check_enabled,
    ref_display,
    resolve_or_create_container_ref,
    resolve_structured_ref,
)
from culsma.runtime.material.result import MaterialUpdateResult


def apply_sep(step: PlanStep, state: dict[str, Any]) -> MaterialUpdateResult:
    sample_arg = step.args.get("sample")
    bind_name = arg_string(step.args.get("bind"))
    program = arg_call(step.args.get("program"))
    if program is None:
        return diagnostic_result(step, state, "MAT_BINDING_NOT_FOUND", "sep requires sample/program")

    source_id = resolve_structured_ref(state, sample_arg, create_if_identifier=not inventory_check_enabled(state))
    if source_id is None:
        if inventory_check_enabled(state):
            return diagnostic_result(step, state, "MAT_BINDING_NOT_FOUND", f"Unknown sep sample '{ref_display(sample_arg)}'")
        sample_name = arg_string(sample_arg)
        if sample_name is None:
            return diagnostic_result(step, state, "MAT_BINDING_NOT_FOUND", "sep requires sample/program")
        source_id = resolve_or_create_container_ref(state, sample_name)
    source = container(state, source_id)
    if source is None:
        return diagnostic_result(step, state, "MAT_BINDING_NOT_FOUND", f"Unknown sep sample '{ref_display(sample_arg)}'")

    program_kind = str(program.get("name")) if isinstance(program.get("name"), str) else "sep_program"
    keep_source = call_arg_string(program, "keep_source")

    working = deepcopy(state)
    source = container(working, source_id)
    if source is None:
        return diagnostic_result(step, state, "MAT_BINDING_NOT_FOUND", f"Unknown sep sample '{ref_display(sample_arg)}'")

    slot0_id = f"{step.step_id}::0"
    slot1_id = f"{step.step_id}::1"
    if program_kind == "centrifuge_program" and keep_source == "supernatant":
        slot0_id = source_id
    elif program_kind == "centrifuge_program" and keep_source == "pellet":
        slot1_id = source_id

    slot0 = ensure_container(working, slot0_id)
    slot1 = ensure_container(working, slot1_id)

    if slot0_id == source_id and slot1_id == source_id:
        return diagnostic_result(step, state, "MAT_STATE_INVARIANT_VIOLATION", "sep cannot alias both slots to the source container")

    partition = partition_sep_material(
        state=working,
        source=source,
        slot0=slot0,
        slot1=slot1,
        program_kind=program_kind,
    )
    diagnostics = partition_fallback_diagnostics(step, partition)
    if bind_name is None:
        normalize_source_partition_slot_bulk(slot0)
        normalize_source_partition_slot_bulk(slot1)
        contents_state = record_partitioned_contents_state(
            state=working,
            source_id=source_id,
            source=source,
            parts={"0": slot0, "1": slot1},
            kind="partitioned",
            producer_op="sep",
            program_kind=program_kind,
            slot_contract=partition.get("slot_contract"),
            preservation_contract=partition.get("preservation_contract"),
            step_id=step.step_id,
        )
        remove_transient_containers(working, [slot0_id, slot1_id], preserve=source_id)
        return MaterialUpdateResult(
            material_state=working,
            diagnostics=diagnostics,
            delta={
                "op": "sep",
                "mode": "contents_state",
                "program_kind": program_kind,
                "source": source_id,
                "keep_source": keep_source,
                "contents_state": contents_state,
                "partition": partition,
            },
        )

    binding_events = bind_indexed_group(
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


def apply_frac(step: PlanStep, state: dict[str, Any]) -> MaterialUpdateResult:
    sample_arg = step.args.get("sample")
    bind_name = arg_string(step.args.get("bind"))
    program = arg_call(step.args.get("program"))
    if program is None:
        return diagnostic_result(step, state, "MAT_BINDING_NOT_FOUND", "frac requires sample/program")

    bins = call_arg_int(program, "bins")
    if bins is None or bins <= 0:
        return diagnostic_result(step, state, "MAT_BINDING_NOT_FOUND", "frac requires positive bins")

    source_id = resolve_structured_ref(state, sample_arg, create_if_identifier=not inventory_check_enabled(state))
    if source_id is None:
        if inventory_check_enabled(state):
            return diagnostic_result(step, state, "MAT_BINDING_NOT_FOUND", f"Unknown frac sample '{ref_display(sample_arg)}'")
        sample_name = arg_string(sample_arg)
        if sample_name is None:
            return diagnostic_result(step, state, "MAT_BINDING_NOT_FOUND", "frac requires sample/program")
        source_id = resolve_or_create_container_ref(state, sample_name)
    source = container(state, source_id)
    if source is None:
        return diagnostic_result(step, state, "MAT_BINDING_NOT_FOUND", f"Unknown frac sample '{ref_display(sample_arg)}'")

    working = deepcopy(state)
    source = container(working, source_id)
    if source is None:
        return diagnostic_result(step, state, "MAT_BINDING_NOT_FOUND", f"Unknown frac sample '{ref_display(sample_arg)}'")

    source_volume = float(source.get("volume_uL", 0.0))
    source_mass = float(source.get("mass_mg", 0.0))
    split_ratio = 1.0 / bins
    slot_bindings: dict[str, str] = {}

    for i in range(bins - 1):
        slot_id = f"{step.step_id}::{i}"
        slot = ensure_container(working, slot_id)
        moved_volume = source_volume * split_ratio
        moved_mass = source_mass * split_ratio
        current_volume = float(source.get("volume_uL", 0.0))
        current_mass = float(source.get("mass_mg", 0.0))
        component_ratio = (
            moved_volume / current_volume
            if current_volume > 0
            else (moved_mass / current_mass if current_mass > 0 else 0.0)
        )
        move_explicit(source, slot, moved_volume, moved_mass, component_ratio=component_ratio)
        slot_bindings[str(i)] = slot_id

    last_slot_id = f"{step.step_id}::{bins - 1}"
    last_slot = ensure_container(working, last_slot_id)
    residual_volume = float(source.get("volume_uL", 0.0))
    residual_mass = float(source.get("mass_mg", 0.0))
    move_explicit(source, last_slot, residual_volume, residual_mass, component_ratio=1.0)
    slot_bindings[str(bins - 1)] = last_slot_id
    if bind_name is None:
        parts = {slot: container(working, slot_id) for slot, slot_id in slot_bindings.items()}
        concrete_parts = {slot: part for slot, part in parts.items() if isinstance(part, dict)}
        contents_state = record_partitioned_contents_state(
            state=working,
            source_id=source_id,
            source=source,
            parts=concrete_parts,
            kind="fractionated",
            producer_op="frac",
            program_kind=str(program.get("name")) if isinstance(program.get("name"), str) else "frac_program",
            slot_contract={slot: f"fraction_{slot}" for slot in slot_bindings},
            preservation_contract=None,
            step_id=step.step_id,
        )
        remove_transient_containers(working, list(slot_bindings.values()), preserve=source_id)
        return MaterialUpdateResult(
            material_state=working,
            diagnostics=[],
            delta={
                "op": "frac",
                "mode": "contents_state",
                "source": source_id,
                "bins": bins,
                "split_ratio": split_ratio,
                "contents_state": contents_state,
            },
        )

    binding_events = bind_indexed_group(working, bind_name, slot_bindings, step.step_id)

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


def partition_fallback_diagnostics(step: PlanStep, partition: dict[str, Any]) -> list[Diagnostic]:
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
