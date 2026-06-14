"""Material mutation source dispatch."""

from __future__ import annotations

from abc import ABC, abstractmethod
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from culsma.common.diagnostics import Diagnostic
from culsma.pipeline.plan_nodes import PlanStep
from culsma.runtime.material.contents_state import (
    ContentsPartSelection,
    apply_target_addition_impact,
    invalidate_contents_state,
    is_container_contents_index,
    moved_snapshot_from_delta,
    moved_snapshot_from_explicit,
    record_self_transfer_disturbance,
    record_source_selection_impact,
    record_target_addition_impact,
    resolve_indexed_part,
)
from culsma.runtime.material.args import arg_call, arg_quantity
from culsma.runtime.material.diagnostics import diagnostic_result
from culsma.runtime.material.ledger import (
    check_capacity_guard,
    collect_unit_into_container,
    container,
    container_component_classes,
    density_mg_per_uL,
    ensure_container,
    move_explicit,
    move_ratio,
)
from culsma.runtime.material.partition import normalize_source_partition_slot_bulk, partition_sep_material
from culsma.runtime.material.refs import (
    inventory_check_enabled,
    is_serialized_pair,
    is_unit_ref,
    ref_display,
    resolve_source_ref,
    resolve_target_ref,
    top_up_source_for_estimate,
)
from culsma.runtime.material.result import MaterialUpdateResult
from culsma.runtime.material.units import MASS_TO_MG, VOLUME_TO_UL


@dataclass(frozen=True)
class MutationSourceContext:
    step: PlanStep
    state: dict[str, Any]
    target_id: str
    source_expr: Any
    source_ordinal: int


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
            return diagnostic_result(ctx.step, ctx.state, "MAT_UNSUPPORTED_UNIT", "Mutation quantified source must carry volume or mass unit")
        transfer = apply_source_partition_transfer(
            step=ctx.step,
            state=ctx.state,
            target_id=ctx.target_id,
            partition_ref=pair.get("left"),
            qty=qty,
            source_ordinal=ctx.source_ordinal,
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


class QuantifiedContentsStateHandler(MutationSourceHandler):
    def handles(self, ctx: MutationSourceContext) -> bool:
        if not is_serialized_pair(ctx.source_expr):
            return False
        return is_container_contents_index(ctx.source_expr.get("left"))

    def apply(self, ctx: MutationSourceContext) -> MaterialUpdateResult:
        pair = ctx.source_expr
        qty = _quantified_source_qty(ctx)
        if qty is None:
            return diagnostic_result(ctx.step, ctx.state, "MAT_UNSUPPORTED_UNIT", "Mutation quantified source must carry volume or mass unit")
        transfer = apply_contents_state_transfer(
            step=ctx.step,
            state=ctx.state,
            target_id=ctx.target_id,
            contents_ref=pair.get("left"),
            qty=qty,
        )
        if not transfer.ok:
            return transfer
        return MaterialUpdateResult(
            material_state=transfer.material_state,
            diagnostics=transfer.diagnostics,
            delta={
                "mode": "quantified_contents_state",
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
            return diagnostic_result(ctx.step, ctx.state, "MAT_UNSUPPORTED_UNIT", "Mutation quantified source must carry volume or mass unit")
        source_id = resolve_source_ref(ctx.state, left, qty=qty)
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


class ContentsStateSourceHandler(MutationSourceHandler):
    def handles(self, ctx: MutationSourceContext) -> bool:
        return is_container_contents_index(ctx.source_expr)

    def apply(self, ctx: MutationSourceContext) -> MaterialUpdateResult:
        transfer = apply_contents_state_transfer(
            step=ctx.step,
            state=ctx.state,
            target_id=ctx.target_id,
            contents_ref=ctx.source_expr,
            qty=None,
        )
        if not transfer.ok:
            return transfer
        return MaterialUpdateResult(
            material_state=transfer.material_state,
            diagnostics=transfer.diagnostics,
            delta={
                "mode": "full_contents_state",
                "target": ctx.target_id,
                "transfer_delta": transfer.delta,
            },
        )


class FullContainerSourceHandler(MutationSourceHandler):
    def handles(self, ctx: MutationSourceContext) -> bool:
        return True

    def apply(self, ctx: MutationSourceContext) -> MaterialUpdateResult:
        source_id = resolve_source_ref(ctx.state, ctx.source_expr, qty=None)
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
        cap_diag = check_capacity_guard(step=ctx.step, state=ctx.state, container_id=ctx.target_id, added_uL=moved_uL)
        if cap_diag is not None:
            return cap_diag
        source_before = deepcopy(source)
        move_explicit(source, target, moved_uL, moved_mg, component_ratio=1.0)
        invalidate_contents_state(ctx.state, source_id, reason="whole_container_transfer")
        moved_snapshot = moved_snapshot_from_explicit(source_before, moved_uL=moved_uL, moved_mg=moved_mg, ratio=1.0)
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
            QuantifiedContentsStateHandler(),
            QuantifiedContainerSourceHandler(),
            UnitCollectSourceHandler(),
            SourcePartitionHandler(),
            ContentsStateSourceHandler(),
            FullContainerSourceHandler(),
        )

    def apply(self, ctx: MutationSourceContext) -> MaterialUpdateResult:
        for handler in self.handlers:
            if handler.handles(ctx):
                return handler.apply(ctx)
        return diagnostic_result(ctx.step, ctx.state, "MAT_BINDING_NOT_FOUND", "Mutation source is unsupported")


def apply_mutation(step: PlanStep, state: dict[str, Any]) -> MaterialUpdateResult:
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


def apply_contents_state_transfer(
    *,
    step: PlanStep,
    state: dict[str, Any],
    target_id: str,
    contents_ref: dict[str, Any],
    qty: dict[str, Any] | None,
) -> MaterialUpdateResult:
    selection = resolve_indexed_part(step=step, state=state, contents_ref=contents_ref)
    if isinstance(selection, MaterialUpdateResult):
        return selection

    source = container(state, selection.source_id)
    target = container(state, target_id)
    if source is None or target is None:
        return diagnostic_result(step, state, "MAT_BINDING_NOT_FOUND", "container.contents transfer references unknown container")

    if selection.source_id == target_id:
        record_self_transfer_disturbance(state=state, selection=selection)
        return MaterialUpdateResult(
            material_state=state,
            diagnostics=[],
            delta={
                "op": "contents_state_transfer",
                "mode": "contents_state_self_disturbance",
                "source": selection.source_id,
                "selected_slot": selection.slot,
                "dest": target_id,
                "moved_uL": 0.0,
                "moved_mg": 0.0,
            },
        )

    amount = _contents_transfer_amount(step=step, state=state, selection=selection, qty=qty)
    if isinstance(amount, MaterialUpdateResult):
        return amount
    moved_uL, moved_mg, ratio, mode = amount

    cap_diag = check_capacity_guard(step=step, state=state, container_id=target_id, added_uL=moved_uL)
    if cap_diag is not None:
        return cap_diag

    part_before = deepcopy(selection.part)
    _move_contents_part_material(
        part=selection.part,
        source=source,
        target=target,
        moved_uL=moved_uL,
        moved_mg=moved_mg,
        ratio=ratio,
    )
    moved_snapshot = moved_snapshot_from_explicit(
        part_before,
        moved_uL=moved_uL,
        moved_mg=moved_mg,
        ratio=ratio,
    )
    target_impact = record_target_addition_impact(
        step=step,
        state=state,
        target_id=target_id,
        moved_snapshot=moved_snapshot,
    )

    return MaterialUpdateResult(
        material_state=state,
        diagnostics=[],
        delta={
            "op": "contents_state_transfer",
            "mode": mode,
            "source": selection.source_id,
            "selected_slot": selection.slot,
            "dest": target_id,
            "moved_uL": moved_uL,
            "moved_mg": moved_mg,
            "contents_state_impact": {
                "source": record_source_selection_impact(state=state, selection=selection),
                "target": target_impact,
            },
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
) -> MaterialUpdateResult:
    program = arg_call(partition_ref.get("program"))
    if program is None:
        return diagnostic_result(step, state, "MAT_BINDING_NOT_FOUND", "source partition requires a concrete program")
    slot_key = _source_partition_slot_key(partition_ref.get("index"))
    if slot_key not in {"0", "1"}:
        return diagnostic_result(step, state, "MAT_BINDING_NOT_FOUND", "source partition index must be 0 or 1")

    source_id = resolve_source_ref(state, partition_ref.get("source"), qty=qty)
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

    partition = partition_sep_material(
        state=state,
        source=source,
        slot0=slot0,
        slot1=slot1,
        program_kind=program_kind,
    )
    normalize_source_partition_slot_bulk(slot0)
    normalize_source_partition_slot_bulk(slot1)
    diagnostics = _partition_fallback_diagnostics(step, partition)
    selected_id = slot0_id if slot_key == "0" else slot1_id
    selected = container(state, selected_id)
    if selected is None:
        return diagnostic_result(step, state, "MAT_BINDING_NOT_FOUND", "Source partition selected unknown slot")

    selected_before = deepcopy(selected)
    if qty is None:
        moved_uL = float(selected.get("volume_uL", 0.0))
        moved_mg = float(selected.get("mass_mg", 0.0))
        cap_diag = check_capacity_guard(step=step, state=state, container_id=target_id, added_uL=moved_uL)
        if cap_diag is not None:
            return cap_diag
        move_explicit(selected, target, moved_uL, moved_mg, component_ratio=1.0)
        moved_snapshot = moved_snapshot_from_explicit(
            selected_before,
            moved_uL=moved_uL,
            moved_mg=moved_mg,
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
        }
    else:
        transfer = apply_transfer_by_qty(step=step, state=state, src_id=selected_id, dst_id=target_id, qty=qty)
        if not transfer.ok:
            return transfer
        state = transfer.material_state
        transfer_delta = transfer.delta
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
        if residual_uL or residual_mg:
            move_explicit(residual, source_after, residual_uL, residual_mg, component_ratio=1.0)
    containers = state.setdefault("containers", {})
    if isinstance(containers, dict):
        containers.pop(slot0_id, None)
        containers.pop(slot1_id, None)
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
    src_volume = float(src.get("volume_uL", 0.0))
    if not inventory_check_enabled(state) and src_volume < requested_uL:
        top_up_source_for_estimate(source=src, qty=requested_uL - src_volume, mode="volume", source_name=src_id)
        src_volume = float(src.get("volume_uL", 0.0))

    if requested_uL < 0:
        return diagnostic_result(step, state, "MAT_UNSUPPORTED_UNIT", "Negative transfer amount is not allowed")
    cap_diag = check_capacity_guard(step=step, state=state, container_id=dst_id, added_uL=requested_uL)
    if cap_diag is not None:
        return cap_diag

    if src_volume >= requested_uL:
        ratio = 0.0 if src_volume == 0 else requested_uL / src_volume
        move_ratio(src, dst, ratio)
        return MaterialUpdateResult(
            material_state=state,
            diagnostics=[],
            delta={"op": "material_move", "mode": "volume", "source": src_id, "dest": dst_id, "moved_uL": requested_uL},
        )

    if src_volume > 0:
        return diagnostic_result(step, state, "MAT_INSUFFICIENT_VOLUME", f"Insufficient source volume in '{src_id}'")

    density = density_mg_per_uL(src)
    if density is None:
        return diagnostic_result(step, state, "MAT_MISSING_DENSITY", f"Need density metadata for '{src_id}'")
    if density <= 0:
        return diagnostic_result(step, state, "MAT_INVALID_DENSITY", f"Invalid density metadata for '{src_id}'")

    requested_mg = requested_uL * density
    src_mass = float(src.get("mass_mg", 0.0))
    effective_src_mass = max(src_mass, src_volume * density)
    effective_src_volume = max(src_volume, effective_src_mass / density)
    if effective_src_mass < requested_mg:
        return diagnostic_result(step, state, "MAT_INSUFFICIENT_MASS", f"Insufficient source mass in '{src_id}'")

    src["mass_mg"] = effective_src_mass
    src["volume_uL"] = effective_src_volume
    component_ratio = 0.0 if effective_src_mass == 0 else requested_mg / effective_src_mass
    move_explicit(
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
    if not inventory_check_enabled(state) and src_mass < requested_mg:
        top_up_source_for_estimate(source=src, qty=requested_mg - src_mass, mode="mass", source_name=src_id)
        src_mass = float(src.get("mass_mg", 0.0))

    if requested_mg < 0:
        return diagnostic_result(step, state, "MAT_UNSUPPORTED_UNIT", "Negative transfer amount is not allowed")

    if src_mass >= requested_mg:
        ratio = 0.0 if src_mass == 0 else requested_mg / src_mass
        moved_uL = ratio * float(src.get("volume_uL", 0.0))
        cap_diag = check_capacity_guard(step=step, state=state, container_id=dst_id, added_uL=moved_uL)
        if cap_diag is not None:
            return cap_diag
        move_ratio(src, dst, ratio)
        return MaterialUpdateResult(
            material_state=state,
            diagnostics=[],
            delta={"op": "material_move", "mode": "mass", "source": src_id, "dest": dst_id, "moved_mg": requested_mg},
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

    src["volume_uL"] = effective_src_volume
    src["mass_mg"] = effective_src_mass
    component_ratio = 0.0 if effective_src_volume == 0 else requested_uL / effective_src_volume
    move_explicit(
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


def _contents_transfer_amount(
    *,
    step: PlanStep,
    state: dict[str, Any],
    selection: ContentsPartSelection,
    qty: dict[str, Any] | None,
) -> tuple[float, float, float, str] | MaterialUpdateResult:
    part = selection.part
    if qty is None:
        return (
            float(part.get("volume_uL", 0.0)),
            float(part.get("mass_mg", 0.0)),
            1.0,
            "contents_state_full",
        )

    unit = str(qty["unit"])
    value = float(qty["value"])
    if value < 0:
        return diagnostic_result(step, state, "MAT_UNSUPPORTED_UNIT", "Negative transfer amount is not allowed")
    part_volume = float(part.get("volume_uL", 0.0))
    part_mass = float(part.get("mass_mg", 0.0))
    if unit in VOLUME_TO_UL:
        moved_uL = value * VOLUME_TO_UL[unit]
        if part_volume < moved_uL:
            return diagnostic_result(step, state, "MAT_INSUFFICIENT_VOLUME", f"Insufficient contents-state volume in '{selection.source_id}'")
        ratio = 0.0 if part_volume == 0 else moved_uL / part_volume
        moved_mg = part_mass * ratio
        return moved_uL, moved_mg, ratio, "contents_state_volume"
    if unit in MASS_TO_MG:
        moved_mg = value * MASS_TO_MG[unit]
        if part_mass < moved_mg:
            return diagnostic_result(step, state, "MAT_INSUFFICIENT_MASS", f"Insufficient contents-state mass in '{selection.source_id}'")
        ratio = 0.0 if part_mass == 0 else moved_mg / part_mass
        moved_uL = part_volume * ratio
        return moved_uL, moved_mg, ratio, "contents_state_mass"
    return diagnostic_result(step, state, "MAT_UNSUPPORTED_UNIT", f"Unsupported transfer unit '{unit}'")


def _move_contents_part_material(
    *,
    part: dict[str, Any],
    source: dict[str, Any],
    target: dict[str, Any],
    moved_uL: float,
    moved_mg: float,
    ratio: float,
) -> None:
    part["volume_uL"] = _clamp_near_zero(float(part.get("volume_uL", 0.0)) - moved_uL)
    part["mass_mg"] = _clamp_near_zero(float(part.get("mass_mg", 0.0)) - moved_mg)
    source["volume_uL"] = _clamp_near_zero(float(source.get("volume_uL", 0.0)) - moved_uL)
    source["mass_mg"] = _clamp_near_zero(float(source.get("mass_mg", 0.0)) - moved_mg)
    target["volume_uL"] = float(target.get("volume_uL", 0.0)) + moved_uL
    target["mass_mg"] = float(target.get("mass_mg", 0.0)) + moved_mg

    part_components = part.setdefault("components", {})
    source_components = source.setdefault("components", {})
    target_components = target.setdefault("components", {})
    if not isinstance(part_components, dict):
        part["components"] = {}
        return
    if not isinstance(source_components, dict):
        source["components"] = {}
        source_components = source["components"]
    if not isinstance(target_components, dict):
        target["components"] = {}
        target_components = target["components"]

    part_classes = container_component_classes(part)
    target_classes = container_component_classes(target, create=True)
    source_classes = container_component_classes(source)
    for name, amount in list(part_components.items()):
        moved = float(amount) * ratio
        part_components[name] = _clamp_near_zero(float(amount) - moved)
        source_components[name] = _clamp_near_zero(float(source_components.get(name, 0.0)) - moved)
        target_components[name] = float(target_components.get(name, 0.0)) + moved
        if moved > 1e-12:
            part_class = part_classes.get(name) if isinstance(part_classes, dict) else None
            if isinstance(part_class, str) and isinstance(target_classes, dict):
                target_classes[name] = part_class
        if part_components.get(name) == 0.0 and isinstance(part_classes, dict):
            part_classes.pop(name, None)
        if source_components.get(name) == 0.0 and isinstance(source_classes, dict):
            source_classes.pop(name, None)


def _clamp_near_zero(value: float) -> float:
    return 0.0 if abs(value) <= 1e-12 else value
