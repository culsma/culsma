"""Material mutation source dispatch."""

from __future__ import annotations

from abc import ABC, abstractmethod
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from culsma.common.diagnostics import Diagnostic
from culsma.pipeline.plan_nodes import PlanStep
from culsma.runtime.material.contents_state import (
    apply_target_addition_impact,
    invalidate_contents_state,
    moved_snapshot_from_delta,
    moved_snapshot_from_explicit,
)
from culsma.runtime.material.args import arg_call, arg_quantity
from culsma.runtime.material.diagnostics import diagnostic_result
from culsma.runtime.material.ledger import (
    check_capacity_guard,
    collect_unit_into_container,
    container,
    container_component_quantity_total,
    density_mg_per_uL,
    ensure_container,
    move_explicit,
    move_ratio,
    container_count_cells,
    component_quantity_merge_conflict,
)
from culsma.runtime.material.partition import (
    partition_sep_material,
    separation_cell_material_state,
)
from culsma.runtime.material.refs import (
    is_serialized_pair,
    is_unit_ref,
    ref_display,
    resolve_source_ref,
    resolve_target_ref,
)
from culsma.runtime.material.result import MaterialUpdateResult
from culsma.runtime.material.scientific_model_adapter import (
    ScientificModelPartitionAdapter,
)
from culsma.runtime.material.suspension import (
    merged_cell_material_state,
    refresh_cell_suspension_relationship,
    resolve_count_aliquot,
    transferred_cell_material_state,
)
from culsma.runtime.material.units import COUNT_TO_CELLS, MASS_TO_MG, VOLUME_TO_UL


@dataclass(frozen=True)
class MutationSourceContext:
    step: PlanStep
    state: dict[str, Any]
    target_id: str
    source_expr: Any
    source_ordinal: int
    material_effect_adapter: ScientificModelPartitionAdapter | None


class MutationSourceHandler(ABC):
    @abstractmethod
    def handles(self, ctx: MutationSourceContext) -> bool:
        raise NotImplementedError

    @abstractmethod
    def apply(self, ctx: MutationSourceContext) -> MaterialUpdateResult:
        raise NotImplementedError


class QuantifiedUnitSourceHandler(MutationSourceHandler):
    def handles(self, ctx: MutationSourceContext) -> bool:
        if not is_serialized_pair(ctx.source_expr):
            return False
        return is_unit_ref(ctx.source_expr.get("left"))

    def apply(self, ctx: MutationSourceContext) -> MaterialUpdateResult:
        return diagnostic_result(
            ctx.step,
            ctx.state,
            "MAT_UNIT_QUANTITY_UNSUPPORTED",
            "Mutation does not support quantified unit_ref sources",
        )


class QuantifiedSourcePartitionHandler(MutationSourceHandler):
    def handles(self, ctx: MutationSourceContext) -> bool:
        if not is_serialized_pair(ctx.source_expr):
            return False
        return is_source_partition_ref(ctx.source_expr.get("left"))

    def apply(self, ctx: MutationSourceContext) -> MaterialUpdateResult:
        pair = ctx.source_expr
        qty = _quantified_source_qty(ctx)
        if qty is None:
            return diagnostic_result(ctx.step, ctx.state, "MAT_UNSUPPORTED_UNIT", "Mutation quantified source must carry volume, mass, or count unit")
        transfer = apply_source_partition_transfer(
            step=ctx.step,
            state=ctx.state,
            target_id=ctx.target_id,
            partition_ref=pair.get("left"),
            qty=qty,
            source_ordinal=ctx.source_ordinal,
            material_effect_adapter=ctx.material_effect_adapter,
        )
        if not transfer.ok:
            return transfer
        return MaterialUpdateResult(
            material_state=transfer.material_state,
            diagnostics=transfer.diagnostics,
            delta={
                "mode": "quantified_source_partition",
                "target": ctx.target_id,
                "qty": qty,
                "transfer_delta": transfer.delta,
            },
        )


class QuantifiedContainerSourceHandler(MutationSourceHandler):
    def handles(self, ctx: MutationSourceContext) -> bool:
        return is_serialized_pair(ctx.source_expr)

    def apply(self, ctx: MutationSourceContext) -> MaterialUpdateResult:
        pair = ctx.source_expr
        left = pair.get("left")
        qty = _quantified_source_qty(ctx)
        if qty is None:
            return diagnostic_result(ctx.step, ctx.state, "MAT_UNSUPPORTED_UNIT", "Mutation quantified source must carry volume, mass, or count unit")
        source_id = resolve_source_ref(ctx.state, left)
        if source_id is None:
            return diagnostic_result(
                ctx.step,
                ctx.state,
                "MAT_BINDING_NOT_FOUND",
                f"Unknown mutation source '{ref_display(left)}'",
            )
        if source_id == ctx.target_id:
            return MaterialUpdateResult(
                material_state=ctx.state,
                diagnostics=[],
                delta={"mode": "quantified_self_noop", "source": source_id, "target": ctx.target_id, "qty": qty},
            )
        source_before = deepcopy(container(ctx.state, source_id))
        transfer = apply_transfer_by_qty(step=ctx.step, state=ctx.state, src_id=source_id, dst_id=ctx.target_id, qty=qty)
        if not transfer.ok:
            return transfer
        invalidate_contents_state(transfer.material_state, source_id, reason="whole_container_transfer")
        moved_snapshot = moved_snapshot_from_delta(source_before, transfer.delta)
        target_impact = apply_target_addition_impact(
            step=ctx.step,
            state=transfer.material_state,
            target_id=ctx.target_id,
            moved_snapshot=moved_snapshot,
        )
        return MaterialUpdateResult(
            material_state=transfer.material_state,
            diagnostics=transfer.diagnostics,
            delta={
                "mode": "quantified",
                "source": source_id,
                "target": ctx.target_id,
                "qty": qty,
                "transfer_delta": transfer.delta,
                "contents_state_impact": {
                    "source": {"action": "stale", "reason": "whole_container_transfer"},
                    "target": target_impact,
                },
            },
        )


class UnitCollectSourceHandler(MutationSourceHandler):
    def handles(self, ctx: MutationSourceContext) -> bool:
        return is_unit_ref(ctx.source_expr)

    def apply(self, ctx: MutationSourceContext) -> MaterialUpdateResult:
        collect = collect_unit_into_container(
            step=ctx.step,
            state=ctx.state,
            target_id=ctx.target_id,
            unit=ctx.source_expr,
        )
        if not collect.ok:
            return collect
        target_impact = apply_target_addition_impact(
            step=ctx.step,
            state=collect.material_state,
            target_id=ctx.target_id,
            moved_snapshot=None,
        )
        return MaterialUpdateResult(
            material_state=collect.material_state,
            diagnostics=collect.diagnostics,
            delta={
                "mode": "unit_collect",
                "unit_id": ctx.source_expr.get("id"),
                "target": ctx.target_id,
                "collection_delta": collect.delta,
                "contents_state_impact": {"target": target_impact},
            },
        )


class SourcePartitionHandler(MutationSourceHandler):
    def handles(self, ctx: MutationSourceContext) -> bool:
        return is_source_partition_ref(ctx.source_expr)

    def apply(self, ctx: MutationSourceContext) -> MaterialUpdateResult:
        transfer = apply_source_partition_transfer(
            step=ctx.step,
            state=ctx.state,
            target_id=ctx.target_id,
            partition_ref=ctx.source_expr,
            qty=None,
            source_ordinal=ctx.source_ordinal,
            material_effect_adapter=ctx.material_effect_adapter,
        )
        if not transfer.ok:
            return transfer
        return MaterialUpdateResult(
            material_state=transfer.material_state,
            diagnostics=transfer.diagnostics,
            delta={
                "mode": "full_source_partition",
                "target": ctx.target_id,
                "transfer_delta": transfer.delta,
            },
        )


class FullContainerSourceHandler(MutationSourceHandler):
    def handles(self, ctx: MutationSourceContext) -> bool:
        return True

    def apply(self, ctx: MutationSourceContext) -> MaterialUpdateResult:
        source_id = resolve_source_ref(ctx.state, ctx.source_expr)
        if source_id is None:
            return diagnostic_result(
                ctx.step,
                ctx.state,
                "MAT_BINDING_NOT_FOUND",
                f"Unknown mutation source '{ref_display(ctx.source_expr)}'",
            )
        if source_id == ctx.target_id:
            return MaterialUpdateResult(
                material_state=ctx.state,
                diagnostics=[],
                delta={"mode": "full_self_noop", "source": source_id, "target": ctx.target_id},
            )
        source = container(ctx.state, source_id)
        target = container(ctx.state, ctx.target_id)
        if source is None or target is None:
            return diagnostic_result(ctx.step, ctx.state, "MAT_BINDING_NOT_FOUND", "Mutation references unknown container")
        moved_uL = float(source.get("volume_uL", 0.0))
        moved_mg = float(source.get("mass_mg", 0.0))
        moved_cells = container_count_cells(source)
        cap_diag = check_capacity_guard(step=ctx.step, state=ctx.state, container_id=ctx.target_id, added_uL=moved_uL)
        if cap_diag is not None:
            return cap_diag
        conflict = _quantity_axis_conflict(ctx.step, ctx.state, source, target, source_id, ctx.target_id)
        if conflict is not None:
            return conflict
        source_before = deepcopy(source)
        moved_cell_state = transferred_cell_material_state(source, moved_cells=moved_cells)
        move_explicit(source, target, component_ratio=1.0)
        refresh_cell_suspension_relationship(ctx.state, source_id)
        refresh_cell_suspension_relationship(
            ctx.state,
            ctx.target_id,
            forced_state=merged_cell_material_state(target, moved_cell_state),
        )
        invalidate_contents_state(ctx.state, source_id, reason="whole_container_transfer")
        moved_snapshot = moved_snapshot_from_explicit(source_before, ratio=1.0)
        target_impact = apply_target_addition_impact(
            step=ctx.step,
            state=ctx.state,
            target_id=ctx.target_id,
            moved_snapshot=moved_snapshot,
        )
        return MaterialUpdateResult(
            material_state=ctx.state,
            diagnostics=[],
            delta={
                "mode": "full",
                "source": source_id,
                "target": ctx.target_id,
                "moved_uL": moved_uL,
                "moved_mg": moved_mg,
                "moved_cells": moved_cells,
                "contents_state_impact": {
                    "source": {"action": "stale", "reason": "whole_container_transfer"},
                    "target": target_impact,
                },
            },
        )


class MutationSourceDispatcher:
    def __init__(self, handlers: tuple[MutationSourceHandler, ...] | None = None) -> None:
        self.handlers = handlers or (
            QuantifiedUnitSourceHandler(),
            QuantifiedSourcePartitionHandler(),
            QuantifiedContainerSourceHandler(),
            UnitCollectSourceHandler(),
            SourcePartitionHandler(),
            FullContainerSourceHandler(),
        )

    def apply(self, ctx: MutationSourceContext) -> MaterialUpdateResult:
        for handler in self.handlers:
            if handler.handles(ctx):
                return handler.apply(ctx)
        return diagnostic_result(ctx.step, ctx.state, "MAT_BINDING_NOT_FOUND", "Mutation source is unsupported")


def apply_mutation(
    step: PlanStep,
    state: dict[str, Any],
    *,
    material_effect_adapter: ScientificModelPartitionAdapter | None = None,
) -> MaterialUpdateResult:
    target_expr = step.args.get("target")
    source_exprs = step.args.get("sources")
    if not isinstance(source_exprs, list):
        return diagnostic_result(step, state, "MAT_BINDING_NOT_FOUND", "Mutation requires source list")

    target_id = resolve_target_ref(state, target_expr)
    if target_id is None:
        return diagnostic_result(
            step,
            state,
            "MAT_BINDING_NOT_FOUND",
            f"Unknown mutation target '{ref_display(target_expr)}'",
        )

    working = deepcopy(state)
    applied_sources: list[dict[str, Any]] = []
    diagnostics: list[Diagnostic] = []
    dispatcher = MutationSourceDispatcher()
    for source_ordinal, source_expr in enumerate(source_exprs):
        result = dispatcher.apply(
            MutationSourceContext(
                step=step,
                state=working,
                target_id=target_id,
                source_expr=source_expr,
                source_ordinal=source_ordinal,
                material_effect_adapter=material_effect_adapter,
            )
        )
        if not result.ok:
            return result
        working = result.material_state
        diagnostics.extend(result.diagnostics)
        applied_sources.append(result.delta)

    return MaterialUpdateResult(
        material_state=working,
        diagnostics=diagnostics,
        delta={
            "op": "Mutation",
            "target": target_id,
            "sources": applied_sources,
        },
    )


def is_source_partition_ref(value: Any) -> bool:
    return isinstance(value, dict) and value.get("kind") == "IRSourcePartitionRef"


def apply_source_partition_transfer(
    *,
    step: PlanStep,
    state: dict[str, Any],
    target_id: str,
    partition_ref: dict[str, Any],
    qty: dict[str, Any] | None,
    source_ordinal: int,
    material_effect_adapter: ScientificModelPartitionAdapter | None,
) -> MaterialUpdateResult:
    program = arg_call(partition_ref.get("program"))
    if program is None:
        return diagnostic_result(step, state, "MAT_BINDING_NOT_FOUND", "source partition requires a concrete program")
    slot_key = _source_partition_slot_key(partition_ref.get("index"))
    if slot_key not in {"0", "1"}:
        return diagnostic_result(step, state, "MAT_BINDING_NOT_FOUND", "source partition index must be 0 or 1")

    source_id = resolve_source_ref(state, partition_ref.get("source"))
    if source_id is None:
        return diagnostic_result(
            step,
            state,
            "MAT_BINDING_NOT_FOUND",
            f"Unknown source partition source '{ref_display(partition_ref.get('source'))}'",
        )
    source = container(state, source_id)
    target = container(state, target_id)
    if source is None or target is None:
        return diagnostic_result(step, state, "MAT_BINDING_NOT_FOUND", "Source partition references unknown container")

    program_kind = str(program.get("name")) if isinstance(program.get("name"), str) else "sep_program"
    slot0_id = f"{step.step_id}::partition::{source_ordinal}::0"
    slot1_id = f"{step.step_id}::partition::{source_ordinal}::1"
    slot0 = ensure_container(state, slot0_id)
    slot1 = ensure_container(state, slot1_id)

    partition_result = partition_sep_material(
        state=state,
        source=source,
        slot0=slot0,
        slot1=slot1,
        program=program,
        material_effect_adapter=material_effect_adapter,
        request_id=f"{step.step_id}:source_partition:{source_ordinal}",
        source_id=source_id,
    )
    if partition_result.failure is not None:
        return diagnostic_result(
            step,
            state,
            partition_result.failure.code,
            partition_result.failure.message,
        )
    partition = partition_result.record
    refresh_cell_suspension_relationship(
        state,
        slot0_id,
        forced_state=separation_cell_material_state(
            program_kind,
            slot="0",
            partition=partition,
            output=slot0,
            effect=partition_result.effect,
        ),
    )
    refresh_cell_suspension_relationship(
        state,
        slot1_id,
        forced_state=separation_cell_material_state(
            program_kind,
            slot="1",
            partition=partition,
            output=slot1,
            effect=partition_result.effect,
        ),
    )
    diagnostics = _partition_fallback_diagnostics(step, partition)
    selected_id = slot0_id if slot_key == "0" else slot1_id
    selected = container(state, selected_id)
    if selected is None:
        return diagnostic_result(step, state, "MAT_BINDING_NOT_FOUND", "Source partition selected unknown slot")

    selected_before = deepcopy(selected)
    if qty is None:
        moved_uL = float(selected.get("volume_uL", 0.0))
        moved_mg = float(selected.get("mass_mg", 0.0))
        moved_cells = container_count_cells(selected)
        selected_cell_state = transferred_cell_material_state(selected_before, moved_cells=moved_cells)
        cap_diag = check_capacity_guard(step=step, state=state, container_id=target_id, added_uL=moved_uL)
        if cap_diag is not None:
            return cap_diag
        conflict = _quantity_axis_conflict(step, state, selected, target, selected_id, target_id)
        if conflict is not None:
            return conflict
        move_explicit(selected, target, component_ratio=1.0)
        moved_snapshot = moved_snapshot_from_explicit(
            selected_before,
            ratio=1.0,
        )
        transfer_delta = {
            "op": "material_move",
            "mode": "source_partition_full",
            "source": source_id,
            "selected_slot": slot_key,
            "dest": target_id,
            "moved_uL": moved_uL,
            "moved_mg": moved_mg,
            "moved_cells": moved_cells,
        }
    else:
        transfer = apply_transfer_by_qty(step=step, state=state, src_id=selected_id, dst_id=target_id, qty=qty)
        if not transfer.ok:
            return transfer
        state = transfer.material_state
        transfer_delta = transfer.delta
        moved_cells = float(transfer.delta.get("moved_cells", 0.0))
        selected_cell_state = transferred_cell_material_state(selected_before, moved_cells=moved_cells)
        moved_snapshot = moved_snapshot_from_delta(selected_before, transfer.delta)

    source_after = container(state, source_id)
    if source_after is None:
        return diagnostic_result(step, state, "MAT_BINDING_NOT_FOUND", "Source partition lost source container")
    for residual_id in (slot0_id, slot1_id):
        residual = container(state, residual_id)
        if residual is None:
            continue
        residual_uL = float(residual.get("volume_uL", 0.0))
        residual_mg = float(residual.get("mass_mg", 0.0))
        if residual_uL or residual_mg or container_count_cells(residual):
            conflict = _quantity_axis_conflict(step, state, residual, source_after, residual_id, source_id)
            if conflict is not None:
                return conflict
            move_explicit(residual, source_after, component_ratio=1.0)
    containers = state.setdefault("containers", {})
    if isinstance(containers, dict):
        containers.pop(slot0_id, None)
        containers.pop(slot1_id, None)
    refresh_cell_suspension_relationship(state, source_id)
    refresh_cell_suspension_relationship(
        state,
        target_id,
        forced_state=merged_cell_material_state(target, selected_cell_state),
    )
    invalidate_contents_state(state, source_id, reason="source_partition_transfer")
    if source_id == target_id:
        target_impact = {"action": "stale", "reason": "source_partition_self_transfer"}
    else:
        target_impact = apply_target_addition_impact(
            step=step,
            state=state,
            target_id=target_id,
            moved_snapshot=moved_snapshot,
        )

    return MaterialUpdateResult(
        material_state=state,
        diagnostics=diagnostics,
        delta={
            "op": "source_partition_transfer",
            "program_kind": program_kind,
            "source": source_id,
            "target": target_id,
            "selected_slot": slot_key,
            "partition": partition,
            "transfer": transfer_delta,
            "contents_state_impact": {
                "source": {"action": "stale", "reason": "source_partition_transfer"},
                "target": target_impact,
            },
        },
    )


def apply_transfer_by_qty(
    step: PlanStep,
    state: dict[str, Any],
    src_id: str,
    dst_id: str,
    qty: dict[str, Any],
) -> MaterialUpdateResult:
    unit = str(qty["unit"])
    value = float(qty["value"])
    if unit in VOLUME_TO_UL:
        requested_uL = value * VOLUME_TO_UL[unit]
        return _apply_transfer_volume(step, state, src_id, dst_id, requested_uL)
    if unit in MASS_TO_MG:
        requested_mg = value * MASS_TO_MG[unit]
        return _apply_transfer_mass(step, state, src_id, dst_id, requested_mg)
    if unit in COUNT_TO_CELLS:
        requested_cells = value * COUNT_TO_CELLS[unit]
        return _apply_transfer_count(step, state, src_id, dst_id, requested_cells)
    return diagnostic_result(
        step=step,
        state=state,
        code="MAT_UNSUPPORTED_UNIT",
        message=f"Unsupported transfer unit '{unit}'",
    )


def _quantified_source_qty(ctx: MutationSourceContext) -> dict[str, Any] | None:
    if not is_serialized_pair(ctx.source_expr):
        return None
    return arg_quantity(ctx.source_expr.get("right"))


def _source_partition_slot_key(value: Any) -> str | None:
    if isinstance(value, dict) and value.get("kind") == "IRQuantity":
        raw = value.get("value")
        unit = value.get("unit")
        if unit is None and isinstance(raw, (int, float)) and float(raw).is_integer():
            return str(int(raw))
    return None


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


def _apply_transfer_volume(
    step: PlanStep,
    state: dict[str, Any],
    src_id: str,
    dst_id: str,
    requested_uL: float,
) -> MaterialUpdateResult:
    src = state["containers"][src_id]
    dst = state["containers"][dst_id]
    src_volume = container_component_quantity_total(src, "volume")

    if requested_uL < 0:
        return diagnostic_result(step, state, "MAT_UNSUPPORTED_UNIT", "Negative transfer amount is not allowed")
    cap_diag = check_capacity_guard(step=step, state=state, container_id=dst_id, added_uL=requested_uL)
    if cap_diag is not None:
        return cap_diag

    if src_volume >= requested_uL:
        ratio = 0.0 if src_volume == 0 else requested_uL / src_volume
        moved_cells = container_count_cells(src) * ratio
        moved_cell_state = transferred_cell_material_state(src, moved_cells=moved_cells)
        conflict = _quantity_axis_conflict(step, state, src, dst, src_id, dst_id)
        if conflict is not None:
            return conflict
        move_ratio(src, dst, ratio)
        refresh_cell_suspension_relationship(state, src_id)
        refresh_cell_suspension_relationship(
            state, dst_id, forced_state=merged_cell_material_state(dst, moved_cell_state)
        )
        return MaterialUpdateResult(
            material_state=state,
            diagnostics=[],
            delta={
                "op": "material_move",
                "mode": "volume",
                "source": src_id,
                "dest": dst_id,
                "moved_uL": requested_uL,
                "moved_cells": moved_cells,
            },
        )

    if src_volume > 0:
        return diagnostic_result(step, state, "MAT_INSUFFICIENT_VOLUME", f"Insufficient source volume in '{src_id}'")

    density = density_mg_per_uL(src)
    if density is None:
        return diagnostic_result(step, state, "MAT_MISSING_DENSITY", f"Need density metadata for '{src_id}'")
    if density <= 0:
        return diagnostic_result(step, state, "MAT_INVALID_DENSITY", f"Invalid density metadata for '{src_id}'")

    requested_mg = requested_uL * density
    src_mass = container_component_quantity_total(src, "mass")
    effective_src_mass = max(src_mass, src_volume * density)
    effective_src_volume = max(src_volume, effective_src_mass / density)
    if effective_src_mass < requested_mg:
        return diagnostic_result(step, state, "MAT_INSUFFICIENT_MASS", f"Insufficient source mass in '{src_id}'")

    component_ratio = 0.0 if effective_src_mass == 0 else requested_mg / effective_src_mass
    moved_cells = container_count_cells(src) * component_ratio
    moved_cell_state = transferred_cell_material_state(src, moved_cells=moved_cells)
    conflict = _quantity_axis_conflict(step, state, src, dst, src_id, dst_id)
    if conflict is not None:
        return conflict
    move_explicit(
        src=src,
        dst=dst,
        component_ratio=component_ratio,
    )
    refresh_cell_suspension_relationship(state, src_id)
    refresh_cell_suspension_relationship(
        state, dst_id, forced_state=merged_cell_material_state(dst, moved_cell_state)
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
            "moved_cells": moved_cells,
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
    src_mass = container_component_quantity_total(src, "mass")

    if requested_mg < 0:
        return diagnostic_result(step, state, "MAT_UNSUPPORTED_UNIT", "Negative transfer amount is not allowed")

    if src_mass >= requested_mg:
        ratio = 0.0 if src_mass == 0 else requested_mg / src_mass
        moved_uL = ratio * float(src.get("volume_uL", 0.0))
        moved_cells = container_count_cells(src) * ratio
        moved_cell_state = transferred_cell_material_state(src, moved_cells=moved_cells)
        cap_diag = check_capacity_guard(step=step, state=state, container_id=dst_id, added_uL=moved_uL)
        if cap_diag is not None:
            return cap_diag
        conflict = _quantity_axis_conflict(step, state, src, dst, src_id, dst_id)
        if conflict is not None:
            return conflict
        move_ratio(src, dst, ratio)
        refresh_cell_suspension_relationship(state, src_id)
        refresh_cell_suspension_relationship(
            state, dst_id, forced_state=merged_cell_material_state(dst, moved_cell_state)
        )
        return MaterialUpdateResult(
            material_state=state,
            diagnostics=[],
            delta={
                "op": "material_move",
                "mode": "mass",
                "source": src_id,
                "dest": dst_id,
                "moved_mg": requested_mg,
                "moved_cells": moved_cells,
            },
        )

    if src_mass > 0:
        return diagnostic_result(step, state, "MAT_INSUFFICIENT_MASS", f"Insufficient source mass in '{src_id}'")

    density = density_mg_per_uL(src)
    if density is None:
        return diagnostic_result(step, state, "MAT_MISSING_DENSITY", f"Need density metadata for '{src_id}'")
    if density <= 0:
        return diagnostic_result(step, state, "MAT_INVALID_DENSITY", f"Invalid density metadata for '{src_id}'")

    requested_uL = requested_mg / density
    cap_diag = check_capacity_guard(step=step, state=state, container_id=dst_id, added_uL=requested_uL)
    if cap_diag is not None:
        return cap_diag
    src_volume = float(src.get("volume_uL", 0.0))
    effective_src_volume = max(src_volume, src_mass / density)
    effective_src_mass = max(src_mass, effective_src_volume * density)
    if effective_src_volume < requested_uL:
        return diagnostic_result(step, state, "MAT_INSUFFICIENT_VOLUME", f"Insufficient source volume in '{src_id}'")

    component_ratio = 0.0 if effective_src_volume == 0 else requested_uL / effective_src_volume
    moved_cells = container_count_cells(src) * component_ratio
    moved_cell_state = transferred_cell_material_state(src, moved_cells=moved_cells)
    conflict = _quantity_axis_conflict(step, state, src, dst, src_id, dst_id)
    if conflict is not None:
        return conflict
    move_explicit(
        src=src,
        dst=dst,
        component_ratio=component_ratio,
    )
    refresh_cell_suspension_relationship(state, src_id)
    refresh_cell_suspension_relationship(
        state, dst_id, forced_state=merged_cell_material_state(dst, moved_cell_state)
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
            "moved_cells": moved_cells,
            "density_mg_per_uL": density,
        },
    )


def _apply_transfer_count(
    step: PlanStep,
    state: dict[str, Any],
    src_id: str,
    dst_id: str,
    requested_cells: float,
) -> MaterialUpdateResult:
    src = state["containers"][src_id]
    dst = state["containers"][dst_id]
    if requested_cells < 0 or not requested_cells.is_integer():
        return diagnostic_result(
            step,
            state,
            "MAT_CELL_COUNT_VALUE_INVALID",
            "Transferred cell count must be a non-negative integer",
        )

    available_cells = container_count_cells(src)

    relationship = refresh_cell_suspension_relationship(state, src_id)
    resolution = resolve_count_aliquot(
        step=step,
        state=state,
        container=src,
        source_id=src_id,
        requested_cells=requested_cells,
        relationship=relationship,
    )
    if isinstance(resolution, MaterialUpdateResult):
        return resolution
    if resolution.requested_cells == 0:
        return MaterialUpdateResult(
            material_state=state,
            diagnostics=[],
            delta={
                "op": "material_move",
                "mode": "count_resolved_volume",
                "source": src_id,
                "dest": dst_id,
                "requested_cells": 0.0,
                "moved_cells": 0.0,
                "component_ratio": 0.0,
                "carrier_volume_uL": 0.0,
                "resolved_transfer_volume_uL": 0.0,
                "moved_uL": 0.0,
                "moved_bulk_volume_uL": 0.0,
                "moved_mg": 0.0,
                "concentration_cells_per_uL": resolution.concentration_cells_per_uL,
                "concentration_source": resolution.concentration_source,
                "policy_id": resolution.policy_id,
            },
        )
    cap_diag = check_capacity_guard(
        step=step,
        state=state,
        container_id=dst_id,
        added_uL=resolution.resolved_transfer_volume_uL,
    )
    if cap_diag is not None:
        return cap_diag
    conflict = _quantity_axis_conflict(step, state, src, dst, src_id, dst_id)
    if conflict is not None:
        return conflict
    target_quantities = dst.get("component_quantities")
    target_was_empty = not isinstance(target_quantities, dict) or not any(
        isinstance(quantity, dict) and abs(float(quantity.get("value", 0.0))) > 1e-12
        for quantity in target_quantities.values()
    )
    move_ratio(src, dst, resolution.component_ratio)
    refresh_cell_suspension_relationship(state, src_id)
    target_relationship = refresh_cell_suspension_relationship(
        state,
        dst_id,
        forced_state=merged_cell_material_state(dst, "suspension"),
        concentration_source=resolution.concentration_source if target_was_empty else "derived",
    )
    return MaterialUpdateResult(
        material_state=state,
        diagnostics=[],
        delta={
            "op": "material_move",
            "mode": "count_resolved_volume",
            "source": src_id,
            "dest": dst_id,
            "requested_cells": resolution.requested_cells,
            "moved_cells": resolution.requested_cells,
            "component_ratio": resolution.component_ratio,
            "carrier_volume_uL": resolution.carrier_volume_uL,
            "resolved_transfer_volume_uL": resolution.resolved_transfer_volume_uL,
            "moved_uL": resolution.moved_bulk_volume_uL,
            "moved_bulk_volume_uL": resolution.moved_bulk_volume_uL,
            "moved_mg": resolution.moved_bulk_mass_mg,
            "concentration_cells_per_uL": resolution.concentration_cells_per_uL,
            "concentration_source": resolution.concentration_source,
            "policy_id": resolution.policy_id,
            "target_relationship": target_relationship,
        },
    )


def _quantity_axis_conflict(
    step: PlanStep,
    state: dict[str, Any],
    source: dict[str, Any],
    target: dict[str, Any],
    source_id: str,
    target_id: str,
) -> MaterialUpdateResult | None:
    component = component_quantity_merge_conflict(source, target)
    if component is None:
        return None
    return diagnostic_result(
        step,
        state,
        "MAT_CONTENT_QUANTITY_AXIS_CONFLICT",
        (
            f"Content '{component}' cannot merge from '{source_id}' into '{target_id}' "
            "because their quantity dimensions or units differ"
        ),
    )
