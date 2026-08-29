"""Container contents-state runtime helpers."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from culsma.common.diagnostics import Diagnostic
from culsma.pipeline.plan_nodes import PlanStep
from culsma.runtime.material.args import arg_call, arg_quantity, arg_string, call_arg_int, call_arg_string
from culsma.runtime.material.diagnostics import diagnostic_result
from culsma.runtime.material.ledger import (
    check_capacity_guard,
    container,
    container_component_classes,
    container_component_quantities,
    container_count_cells,
    normalize_material_state_detail_ledger,
    component_quantity_merge_conflict,
    ensure_container,
    move_explicit,
    refresh_container_aggregates,
    transfer_scientific_model_relationships,
)
from culsma.runtime.material.separation import (
    apply_separation_material,
    separation_cell_material_state,
    separation_slot_contract,
)
from culsma.runtime.material.refs import (
    bind_indexed_group,
    is_serialized_pair,
    ref_display,
    resolve_structured_ref,
    resolve_target_ref,
)
from culsma.runtime.material.result import MaterialUpdateResult
from culsma.runtime.material.scientific_model_adapter import (
    ResolvedMaterialEffect,
    ScientificModelPartitionAdapter,
)
from culsma.runtime.material.separation_fate import (
    ExplicitContentFate,
    parse_explicit_content_fates,
)
from culsma.runtime.material.suspension import (
    cell_material_state,
    cell_suspension_relationship,
    merged_cell_material_state,
    refresh_cell_suspension_relationship,
    refresh_cell_suspension_relationship_record,
    resolve_count_aliquot,
    transferred_cell_material_state,
)
from culsma.runtime.material.units import COUNT_TO_CELLS, MASS_TO_MG, VOLUME_TO_UL


@dataclass(frozen=True)
class ContentsPartSelection:
    source_id: str
    slot: str
    part: dict[str, Any]
    state_record: dict[str, Any]


@dataclass(frozen=True)
class ContentsStateImpact:
    action: str
    reason: str | None = None
    details: dict[str, Any] | None = None


@dataclass(frozen=True)
class ContentsStateSummary:
    source_id: str
    kind: str
    program_kind: str
    slots: list[str]


@dataclass(frozen=True)
class ContentsPartitionTransition:
    contents_state: dict[str, Any]
    partition: dict[str, Any]
    slot_ids: dict[str, str]
    split_ratio: float | None = None


@dataclass(frozen=True)
class ContentsStateTransitionPlan:
    transition: str
    step: PlanStep
    payload: dict[str, Any] = field(default_factory=dict)


def is_container_contents_index(value: Any) -> bool:
    if not isinstance(value, dict) or value.get("kind") != "IRIndex":
        return False
    base = value.get("base")
    return isinstance(base, dict) and base.get("kind") == "IRMember" and base.get("member") == "contents"


def invalidate_contents_state(state: dict[str, Any], container_id: str, *, reason: str) -> None:
    contents_states = state.get("contents_states")
    if not isinstance(contents_states, dict):
        return
    record = contents_states.get(container_id)
    if not isinstance(record, dict):
        return
    record["valid"] = False
    record["invalid_reason"] = reason


def apply_target_addition_impact(
    *,
    step: PlanStep,
    state: dict[str, Any],
    target_id: str,
    moved_snapshot: dict[str, Any] | None,
) -> dict[str, Any]:
    impact = _classify_target_addition(
        step=step,
        state=state,
        target_id=target_id,
        moved_snapshot=moved_snapshot,
    )
    action = impact.get("action")
    if action == "preserve_add_to_part":
        moved = deepcopy(moved_snapshot)
        if not isinstance(moved, dict):
            return {"action": "stale", "reason": "missing_material_snapshot"}
        part = impact.get("part")
        move_explicit(
            moved,
            part,
            component_ratio=1.0,
        )
        return {
            "action": "preserve_add_to_part",
            "slot": impact.get("slot"),
            "contract": impact.get("contract"),
        }
    if action == "stale":
        invalidate_contents_state(state, target_id, reason=str(impact.get("reason") or "material_transfer"))
    return {key: value for key, value in impact.items() if key != "part"}


def moved_snapshot_from_delta(source_before: Any, delta: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(source_before, dict):
        return None
    mode = delta.get("mode")
    source_volume = float(source_before.get("volume_uL", 0.0))
    source_mass = float(source_before.get("mass_mg", 0.0))
    if mode == "volume":
        moved_uL = float(delta.get("moved_uL", 0.0))
        ratio = 0.0 if source_volume == 0.0 else moved_uL / source_volume
        moved_mg = source_mass * ratio
    elif mode == "mass":
        moved_mg = float(delta.get("moved_mg", 0.0))
        ratio = 0.0 if source_mass == 0.0 else moved_mg / source_mass
        moved_uL = source_volume * ratio
    elif mode == "bridge_volume_to_mass":
        moved_uL = float(delta.get("requested_uL", 0.0))
        moved_mg = float(delta.get("converted_mg", 0.0))
        ratio = _best_effort_component_ratio(source_before, moved_uL=moved_uL, moved_mg=moved_mg)
    elif mode == "bridge_mass_to_volume":
        moved_uL = float(delta.get("converted_uL", 0.0))
        moved_mg = float(delta.get("requested_mg", 0.0))
        ratio = _best_effort_component_ratio(source_before, moved_uL=moved_uL, moved_mg=moved_mg)
    else:
        return None
    return moved_snapshot_from_explicit(source_before, ratio=ratio)


def moved_snapshot_from_explicit(
    source_before: dict[str, Any],
    *,
    ratio: float,
) -> dict[str, Any]:
    snapshot = {"volume_uL": 0.0, "mass_mg": 0.0, "components": {}, "metadata": {}}
    source_copy = deepcopy(source_before)
    move_explicit(source_copy, snapshot, component_ratio=ratio)
    return snapshot


def mark_contents_state_mixed(state: dict[str, Any], container_id: str, *, step_id: str) -> dict[str, Any]:
    contents_states = state.get("contents_states")
    if not isinstance(contents_states, dict):
        return {"action": "none", "reason": "no_contents_states"}
    record = contents_states.get(container_id)
    if not isinstance(record, dict) or record.get("valid") is False:
        return {"action": "none", "reason": "no_valid_contents_state"}
    previous_kind = record.get("kind")
    record["valid"] = False
    record["invalid_reason"] = "explicit_mixing"
    record["previous_kind"] = previous_kind
    record["kind"] = "mixed"
    record["mixed_by_step"] = step_id
    return {"action": "mixed", "reason": "explicit_mixing", "previous_kind": previous_kind}


class MaterialIndexedPartsStateManager:
    def __init__(
        self,
        material_effect_adapter: ScientificModelPartitionAdapter | None = None,
    ) -> None:
        self.material_effect_adapter = material_effect_adapter

    def apply_partition_or_index_change(
        self,
        transition_plan: ContentsStateTransitionPlan,
        state: dict[str, Any],
    ) -> MaterialUpdateResult:
        step = transition_plan.step
        if transition_plan.transition == "sep":
            return self.apply_sep(step, state)
        if transition_plan.transition == "frac":
            return self.apply_frac(step, state)
        if transition_plan.transition == "agit":
            return self.apply_agit(step, state)
        if transition_plan.transition == "select":
            return self.apply_mutation_transition(step, state)
        if transition_plan.transition == "add":
            return self.apply_mutation_transition(step, state)
        return diagnostic_result(
            step,
            state,
            "MAT_UNSUPPORTED_CONTENTS_STATE_TRANSITION",
            f"Unsupported contents-state transition '{transition_plan.transition}'",
        )

    def apply_sep(self, step: PlanStep, state: dict[str, Any]) -> MaterialUpdateResult:
        sample_arg = step.args.get("sample")
        bind_name = arg_string(step.args.get("bind"))
        program = arg_call(step.args.get("program"))
        if program is None:
            return diagnostic_result(step, state, "MAT_BINDING_NOT_FOUND", "sep requires sample/program")

        source_id = resolve_structured_ref(state, sample_arg, create_if_identifier=False)
        if source_id is None:
            return diagnostic_result(
                step,
                state,
                "MAT_BINDING_NOT_FOUND",
                f"Unknown sep sample '{ref_display(sample_arg)}'",
            )
        source = container(state, source_id)
        if source is None:
            return diagnostic_result(step, state, "MAT_BINDING_NOT_FOUND", f"Unknown sep sample '{ref_display(sample_arg)}'")

        program_kind = str(program.get("name")) if isinstance(program.get("name"), str) else "sep_program"
        keep_source = call_arg_string(program, "keep_source")
        explicit_fates, fate_issues = parse_explicit_content_fates(
            step.args.get("component_fates"),
            slot_contract=separation_slot_contract(program_kind),
            known_components=(
                set(source.get("components", {}))
                if isinstance(source.get("components"), dict)
                else set()
            ),
        )
        if fate_issues:
            issue = fate_issues[0]
            return diagnostic_result(step, state, issue.code, issue.message)

        working = deepcopy(state)

        if bind_name is None:
            transition = self.record_sep_transition(
                step=step,
                state=working,
                source_id=source_id,
                program=program,
                keep_source=keep_source,
                explicit_fates=explicit_fates,
            )
            if isinstance(transition, MaterialUpdateResult):
                return transition
            diagnostics = _partition_fallback_diagnostics(step, transition.partition)
            return MaterialUpdateResult(
                material_state=working,
                diagnostics=diagnostics,
                delta={
                    "op": "sep",
                    "mode": "contents_state",
                    "program_kind": program_kind,
                    "source": source_id,
                    "keep_source": keep_source,
                    "contents_state": transition.contents_state,
                    "partition": transition.partition,
                },
            )

        source = container(working, source_id)
        if source is None:
            return diagnostic_result(step, state, "MAT_BINDING_NOT_FOUND", f"Unknown sep sample '{ref_display(sample_arg)}'")
        slot0_id = f"{step.step_id}::0"
        slot1_id = f"{step.step_id}::1"
        if program_kind == "centrifuge_program" and keep_source == "supernatant":
            slot0_id = source_id
        elif program_kind == "centrifuge_program" and keep_source == "pellet":
            slot1_id = source_id
        if slot0_id == source_id and slot1_id == source_id:
            return diagnostic_result(
                step,
                state,
                "MAT_STATE_INVARIANT_VIOLATION",
                "sep cannot alias both slots to the source container",
            )
        slot0 = ensure_container(working, slot0_id)
        slot1 = ensure_container(working, slot1_id)
        separation_result = apply_separation_material(
            state=working,
            source=source,
            slot0=slot0,
            slot1=slot1,
            program=program,
            explicit_fates=explicit_fates,
            material_effect_adapter=self.material_effect_adapter,
            request_id=step.step_id,
            source_id=source_id,
        )
        if separation_result.failure is not None:
            return diagnostic_result(
                step,
                state,
                separation_result.failure.code,
                separation_result.failure.message,
            )
        partition = separation_result.record
        refresh_separation_relationships(
            working,
            source_id,
            slot0_id,
            slot1_id,
            program_kind,
            partition,
            effect=separation_result.effect,
        )
        diagnostics = _partition_fallback_diagnostics(step, partition)
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
                "source": source_id,
                "bind": bind_name,
                "slots": {"0": slot0_id, "1": slot1_id},
                "keep_source": keep_source,
                "partition": partition,
                "binding_events": binding_events,
            },
        )

    def apply_frac(self, step: PlanStep, state: dict[str, Any]) -> MaterialUpdateResult:
        sample_arg = step.args.get("sample")
        bind_name = arg_string(step.args.get("bind"))
        program = arg_call(step.args.get("program"))
        if program is None:
            return diagnostic_result(step, state, "MAT_BINDING_NOT_FOUND", "frac requires sample/program")

        bins = call_arg_int(program, "bins")
        if bins is None or bins <= 0:
            return diagnostic_result(step, state, "MAT_BINDING_NOT_FOUND", "frac requires positive bins")

        source_id = resolve_structured_ref(state, sample_arg, create_if_identifier=False)
        if source_id is None:
            return diagnostic_result(
                step,
                state,
                "MAT_BINDING_NOT_FOUND",
                f"Unknown frac sample '{ref_display(sample_arg)}'",
            )
        source = container(state, source_id)
        if source is None:
            return diagnostic_result(step, state, "MAT_BINDING_NOT_FOUND", f"Unknown frac sample '{ref_display(sample_arg)}'")

        working = deepcopy(state)
        source = container(working, source_id)
        if source is None:
            return diagnostic_result(step, state, "MAT_BINDING_NOT_FOUND", f"Unknown frac sample '{ref_display(sample_arg)}'")

        program_kind = str(program.get("name")) if isinstance(program.get("name"), str) else "frac_program"
        if bind_name is None:
            transition = self.record_frac_transition(
                step=step,
                state=working,
                source_id=source_id,
                bins=bins,
                program_kind=program_kind,
            )
            if isinstance(transition, MaterialUpdateResult):
                return transition
            return MaterialUpdateResult(
                material_state=working,
                diagnostics=[],
                delta={
                    "op": "frac",
                    "mode": "contents_state",
                    "source": source_id,
                    "bins": bins,
                    "split_ratio": transition.split_ratio,
                    "contents_state": transition.contents_state,
                },
            )

        source_volume = float(source.get("volume_uL", 0.0))
        source_mass = float(source.get("mass_mg", 0.0))
        source_cells = container_count_cells(source)
        split_ratio = 1.0 / bins
        slot_bindings: dict[str, str] = {}
        for i in range(bins - 1):
            slot_id = f"{step.step_id}::{i}"
            slot = ensure_container(working, slot_id)
            moved_volume = source_volume * split_ratio
            moved_mass = source_mass * split_ratio
            current_volume = float(source.get("volume_uL", 0.0))
            current_mass = float(source.get("mass_mg", 0.0))
            current_cells = container_count_cells(source)
            component_ratio = (
                moved_volume / current_volume
                if current_volume > 0
                else (
                    moved_mass / current_mass
                    if current_mass > 0
                    else (source_cells * split_ratio / current_cells if current_cells > 0 else 0.0)
                )
            )
            move_explicit(source, slot, component_ratio=component_ratio)
            refresh_cell_suspension_relationship(working, slot_id, forced_state="suspension")
            slot_bindings[str(i)] = slot_id

        last_slot_id = f"{step.step_id}::{bins - 1}"
        last_slot = ensure_container(working, last_slot_id)
        residual_volume = float(source.get("volume_uL", 0.0))
        residual_mass = float(source.get("mass_mg", 0.0))
        move_explicit(source, last_slot, component_ratio=1.0)
        refresh_cell_suspension_relationship(working, last_slot_id, forced_state="suspension")
        refresh_cell_suspension_relationship(working, source_id)
        slot_bindings[str(bins - 1)] = last_slot_id

        binding_events = bind_indexed_group(working, bind_name, slot_bindings, step.step_id)
        return MaterialUpdateResult(
            material_state=working,
            diagnostics=[],
            delta={
                "op": "frac",
                "bind": bind_name,
                "source": source_id,
                "bins": bins,
                "slots": dict(slot_bindings),
                "split_ratio": split_ratio,
                "binding_events": binding_events,
            },
        )

    def apply_agit(self, step: PlanStep, state: dict[str, Any]) -> MaterialUpdateResult:
        sample_arg = step.args.get("sample")
        sample_ids = self._resolve_structured_ref_group_ids(state, sample_arg)
        if sample_ids is not None:
            impacts = {
                sample_id: mark_contents_state_mixed(state, sample_id, step_id=step.step_id)
                for sample_id in sample_ids
            }
            return MaterialUpdateResult(
                material_state=state,
                diagnostics=[],
                delta={"op": "agit", "samples": sample_ids, "contents_state_impacts": impacts},
            )
        sample_id = resolve_structured_ref(state, sample_arg, create_if_identifier=False)
        if sample_id is None:
            return diagnostic_result(
                step,
                state,
                "MAT_BINDING_NOT_FOUND",
                f"Unknown agit sample '{ref_display(sample_arg)}'",
            )
        impact = mark_contents_state_mixed(state, sample_id, step_id=step.step_id)
        return MaterialUpdateResult(
            material_state=state,
            diagnostics=[],
            delta={"op": "agit", "sample": sample_id, "contents_state_impact": impact},
        )

    def _resolve_structured_ref_group_ids(self, state: dict[str, Any], value: Any) -> list[str] | None:
        if not isinstance(value, dict) or value.get("kind") != "IRGroup":
            return None
        elements = value.get("elements")
        if not isinstance(elements, list):
            return None
        sample_ids: list[str] = []
        for element in elements:
            sample_id = resolve_structured_ref(state, element, create_if_identifier=False)
            if sample_id is None:
                return None
            sample_ids.append(sample_id)
        return sample_ids

    def apply_mutation_transition(self, step: PlanStep, state: dict[str, Any]) -> MaterialUpdateResult:
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

        from culsma.runtime.material.mutation import MutationSourceContext, MutationSourceDispatcher

        working = deepcopy(state)
        applied_sources: list[dict[str, Any]] = []
        diagnostics: list[Diagnostic] = []
        dispatcher = MutationSourceDispatcher()
        for source_ordinal, source_expr in enumerate(source_exprs):
            contents_ref = _contents_ref_from_mutation_source(source_expr)
            if contents_ref is None:
                result = dispatcher.apply(
                    MutationSourceContext(
                        step=step,
                        state=working,
                        target_id=target_id,
                        source_expr=source_expr,
                        source_ordinal=source_ordinal,
                        material_effect_adapter=self.material_effect_adapter,
                    )
                )
            else:
                result = self.apply_contents_state_transfer(
                    step=step,
                    state=working,
                    target_id=target_id,
                    contents_ref=contents_ref,
                    qty=_contents_qty_from_mutation_source(source_expr),
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

    def apply_contents_index_mutation(self, step: PlanStep, state: dict[str, Any]) -> MaterialUpdateResult:
        return self.apply_mutation_transition(step, state)

    def apply_contents_state_transfer(
        self,
        *,
        step: PlanStep,
        state: dict[str, Any],
        target_id: str,
        contents_ref: dict[str, Any],
        qty: dict[str, Any] | None,
    ) -> MaterialUpdateResult:
        selection = self.resolve_indexed_part(step=step, state=state, contents_ref=contents_ref)
        if isinstance(selection, MaterialUpdateResult):
            return selection

        source = container(state, selection.source_id)
        target = container(state, target_id)
        if source is None or target is None:
            return diagnostic_result(
                step,
                state,
                "MAT_BINDING_NOT_FOUND",
                "container.contents transfer references unknown container",
            )

        if selection.source_id == target_id:
            self.record_self_transfer_disturbance(state=state, selection=selection)
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
        moved_uL, moved_mg, moved_cells, ratio, mode, count_resolution = amount

        if ratio == 0 and moved_uL == 0 and moved_mg == 0 and moved_cells == 0:
            return MaterialUpdateResult(
                material_state=state,
                diagnostics=[],
                delta={
                    "op": "contents_state_transfer",
                    "mode": mode,
                    "source": selection.source_id,
                    "selected_slot": selection.slot,
                    "dest": target_id,
                    "moved_uL": 0.0,
                    "moved_mg": 0.0,
                    "moved_cells": 0.0,
                    **count_resolution,
                    "contents_state_impact": {
                        "source": {"action": "unchanged", "reason": "zero_quantity_noop"},
                        "target": {"action": "unchanged", "reason": "zero_quantity_noop"},
                    },
                },
            )

        physical_added_uL = float(count_resolution.get("resolved_transfer_volume_uL", moved_uL))
        cap_diag = check_capacity_guard(
            step=step,
            state=state,
            container_id=target_id,
            added_uL=physical_added_uL,
        )
        if cap_diag is not None:
            return cap_diag
        conflict_component = component_quantity_merge_conflict(selection.part, target)
        if conflict_component is not None:
            return diagnostic_result(
                step,
                state,
                "MAT_CONTENT_QUANTITY_AXIS_CONFLICT",
                (
                    f"Content '{conflict_component}' cannot merge from contents of "
                    f"'{selection.source_id}' into '{target_id}' because their quantity axes differ"
                ),
            )

        part_before = deepcopy(selection.part)
        selected_cell_state = cell_material_state(selection.part)
        incoming_cell_state = transferred_cell_material_state(part_before, moved_cells=moved_cells)
        target_cell_state = merged_cell_material_state(target, incoming_cell_state)
        _move_contents_part_material(
            part=selection.part,
            source=source,
            target=target,
            target_id=target_id,
            ratio=ratio,
        )
        refresh_cell_suspension_relationship_record(
            state,
            selection.part,
            forced_state=selected_cell_state if isinstance(selected_cell_state, str) else None,
        )
        refresh_cell_suspension_relationship(state, selection.source_id)
        refresh_cell_suspension_relationship(
            state,
            target_id,
            forced_state=target_cell_state,
        )
        moved_snapshot = moved_snapshot_from_explicit(
            part_before,
            ratio=ratio,
        )
        target_impact = self.record_target_addition_impact(
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
                "moved_cells": moved_cells,
                **count_resolution,
                "contents_state_impact": {
                    "source": self.record_source_selection_impact(state=state, selection=selection),
                    "target": target_impact,
                },
            },
        )

    def record_sep_transition(
        self,
        *,
        step: PlanStep,
        state: dict[str, Any],
        source_id: str,
        program: dict[str, Any],
        keep_source: str | None,
        explicit_fates: dict[str, ExplicitContentFate],
    ) -> ContentsPartitionTransition | MaterialUpdateResult:
        detail_error = normalize_material_state_detail_ledger(state)
        if detail_error is not None:
            return diagnostic_result(step, state, "MAT_INVALID_COMPONENT_QUANTITY", detail_error)
        source = container(state, source_id)
        if source is None:
            return diagnostic_result(step, state, "MAT_BINDING_NOT_FOUND", f"Unknown sep sample '{source_id}'")

        program_kind = str(program.get("name")) if isinstance(program.get("name"), str) else "sep_program"

        slot0_id = f"{step.step_id}::0"
        slot1_id = f"{step.step_id}::1"
        if program_kind == "centrifuge_program" and keep_source == "supernatant":
            slot0_id = source_id
        elif program_kind == "centrifuge_program" and keep_source == "pellet":
            slot1_id = source_id

        if slot0_id == source_id and slot1_id == source_id:
            return diagnostic_result(
                step,
                state,
                "MAT_STATE_INVARIANT_VIOLATION",
                "sep cannot alias both slots to the source container",
            )

        slot0 = ensure_container(state, slot0_id)
        slot1 = ensure_container(state, slot1_id)
        separation_result = apply_separation_material(
            state=state,
            source=source,
            slot0=slot0,
            slot1=slot1,
            program=program,
            explicit_fates=explicit_fates,
            material_effect_adapter=self.material_effect_adapter,
            request_id=step.step_id,
            source_id=source_id,
        )
        if separation_result.failure is not None:
            return diagnostic_result(
                step,
                state,
                separation_result.failure.code,
                separation_result.failure.message,
            )
        partition = separation_result.record
        refresh_separation_relationships(
            state,
            source_id,
            slot0_id,
            slot1_id,
            program_kind,
            partition,
            effect=separation_result.effect,
        )
        contents_state = record_partitioned_contents_state(
            state=state,
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
        remove_transient_containers(state, [slot0_id, slot1_id], preserve=source_id)
        return ContentsPartitionTransition(
            contents_state=contents_state,
            partition=partition,
            slot_ids={"0": slot0_id, "1": slot1_id},
        )

    def record_frac_transition(
        self,
        *,
        step: PlanStep,
        state: dict[str, Any],
        source_id: str,
        bins: int,
        program_kind: str,
    ) -> ContentsPartitionTransition | MaterialUpdateResult:
        detail_error = normalize_material_state_detail_ledger(state)
        if detail_error is not None:
            return diagnostic_result(step, state, "MAT_INVALID_COMPONENT_QUANTITY", detail_error)
        source = container(state, source_id)
        if source is None:
            return diagnostic_result(step, state, "MAT_BINDING_NOT_FOUND", f"Unknown frac sample '{source_id}'")

        source_volume = float(source.get("volume_uL", 0.0))
        source_mass = float(source.get("mass_mg", 0.0))
        source_cells = container_count_cells(source)
        split_ratio = 1.0 / bins
        slot_bindings: dict[str, str] = {}

        for i in range(bins - 1):
            slot_id = f"{step.step_id}::{i}"
            slot = ensure_container(state, slot_id)
            moved_volume = source_volume * split_ratio
            moved_mass = source_mass * split_ratio
            current_volume = float(source.get("volume_uL", 0.0))
            current_mass = float(source.get("mass_mg", 0.0))
            current_cells = container_count_cells(source)
            component_ratio = (
                moved_volume / current_volume
                if current_volume > 0
                else (
                    moved_mass / current_mass
                    if current_mass > 0
                    else (source_cells * split_ratio / current_cells if current_cells > 0 else 0.0)
                )
            )
            move_explicit(source, slot, component_ratio=component_ratio)
            refresh_cell_suspension_relationship(state, slot_id, forced_state="suspension")
            slot_bindings[str(i)] = slot_id

        last_slot_id = f"{step.step_id}::{bins - 1}"
        last_slot = ensure_container(state, last_slot_id)
        residual_volume = float(source.get("volume_uL", 0.0))
        residual_mass = float(source.get("mass_mg", 0.0))
        move_explicit(source, last_slot, component_ratio=1.0)
        refresh_cell_suspension_relationship(state, last_slot_id, forced_state="suspension")
        refresh_cell_suspension_relationship(state, source_id)
        slot_bindings[str(bins - 1)] = last_slot_id

        parts = {slot: container(state, slot_id) for slot, slot_id in slot_bindings.items()}
        concrete_parts = {slot: part for slot, part in parts.items() if isinstance(part, dict)}
        contents_state = record_partitioned_contents_state(
            state=state,
            source_id=source_id,
            source=source,
            parts=concrete_parts,
            kind="fractionated",
            producer_op="frac",
            program_kind=program_kind,
            slot_contract={slot: f"fraction_{slot}" for slot in slot_bindings},
            preservation_contract=None,
            step_id=step.step_id,
        )
        remove_transient_containers(state, list(slot_bindings.values()), preserve=source_id)
        return ContentsPartitionTransition(
            contents_state=contents_state,
            partition={},
            slot_ids=dict(slot_bindings),
            split_ratio=split_ratio,
        )

    def resolve_indexed_part(
        self,
        *,
        step: PlanStep,
        state: dict[str, Any],
        contents_ref: dict[str, Any],
    ) -> ContentsPartSelection | MaterialUpdateResult:
        source_id = _resolve_contents_state_source_id(state, contents_ref)
        if source_id is None:
            return diagnostic_result(
                step,
                state,
                "MAT_BINDING_NOT_FOUND",
                f"Unknown container contents source '{ref_display(contents_ref)}'",
            )
        slot_key = _contents_state_slot_key(contents_ref)
        if slot_key is None:
            return diagnostic_result(step, state, "MAT_CONTENTS_STATE_INDEX_OUT_OF_RANGE", "container.contents index must be static")

        contents_states = _material_contents_states(state)
        record = contents_states.get(source_id)
        if not isinstance(record, dict) or record.get("valid") is False:
            return diagnostic_result(
                step,
                state,
                "MAT_CONTENTS_STATE_NOT_INDEXED",
                f"Container '{source_id}' has no active contents state",
            )
        parts = record.get("parts")
        part = parts.get(slot_key) if isinstance(parts, dict) else None
        if not isinstance(part, dict):
            return diagnostic_result(
                step,
                state,
                "MAT_CONTENTS_STATE_INDEX_OUT_OF_RANGE",
                f"Container '{source_id}' contents state has no slot {slot_key}",
            )
        contract = record.get("preservation_contract")
        if isinstance(contract, dict) and not _preservation_contract_satisfied(step=step, contract=contract):
            invalidate_contents_state(state, source_id, reason="preservation_contract_not_satisfied")
            return diagnostic_result(
                step,
                state,
                "MAT_CONTENTS_STATE_PRESERVATION_NOT_SATISFIED",
                f"Container '{source_id}' contents state requires its preservation condition before reading slot {slot_key}",
            )
        return ContentsPartSelection(
            source_id=source_id,
            slot=slot_key,
            part=part,
            state_record=record,
        )

    def record_source_selection_impact(self, *, state: dict[str, Any], selection: ContentsPartSelection) -> dict[str, Any]:
        return {"action": "preserve_remove_from_part", "slot": selection.slot}

    def record_self_transfer_disturbance(self, *, state: dict[str, Any], selection: ContentsPartSelection) -> dict[str, Any]:
        invalidate_contents_state(state, selection.source_id, reason="contents_self_transfer")
        return {"action": "stale", "reason": "contents_self_transfer", "slot": selection.slot}

    def record_target_addition_impact(
        self,
        *,
        step: PlanStep,
        state: dict[str, Any],
        target_id: str,
        moved_snapshot: dict[str, Any] | None,
    ) -> dict[str, Any]:
        return apply_target_addition_impact(
            step=step,
            state=state,
            target_id=target_id,
            moved_snapshot=moved_snapshot,
        )

    def record_partitioned(
        self,
        *,
        state: dict[str, Any],
        source_id: str,
        source: dict[str, Any],
        parts: dict[str, dict[str, Any]],
        kind: str,
        producer_op: str,
        program_kind: str,
        slot_contract: Any,
        preservation_contract: dict[str, Any] | None,
        step_id: str,
    ) -> ContentsStateSummary:
        summary = record_partitioned_contents_state(
            state=state,
            source_id=source_id,
            source=source,
            parts=parts,
            kind=kind,
            producer_op=producer_op,
            program_kind=program_kind,
            slot_contract=slot_contract,
            preservation_contract=preservation_contract,
            step_id=step_id,
        )
        return ContentsStateSummary(
            source_id=str(summary["source"]),
            kind=str(summary["kind"]),
            program_kind=str(summary["program_kind"]),
            slots=list(summary["slots"]),
        )


def resolve_indexed_part(
    *,
    step: PlanStep,
    state: dict[str, Any],
    contents_ref: dict[str, Any],
) -> ContentsPartSelection | MaterialUpdateResult:
    return MaterialIndexedPartsStateManager().resolve_indexed_part(
        step=step,
        state=state,
        contents_ref=contents_ref,
    )


def record_source_selection_impact(*, state: dict[str, Any], selection: ContentsPartSelection) -> dict[str, Any]:
    return MaterialIndexedPartsStateManager().record_source_selection_impact(state=state, selection=selection)


def record_self_transfer_disturbance(*, state: dict[str, Any], selection: ContentsPartSelection) -> dict[str, Any]:
    return MaterialIndexedPartsStateManager().record_self_transfer_disturbance(state=state, selection=selection)


def record_target_addition_impact(
    *,
    step: PlanStep,
    state: dict[str, Any],
    target_id: str,
    moved_snapshot: dict[str, Any] | None,
) -> dict[str, Any]:
    return MaterialIndexedPartsStateManager().record_target_addition_impact(
        step=step,
        state=state,
        target_id=target_id,
        moved_snapshot=moved_snapshot,
    )


def record_partitioned_contents_state(
    *,
    state: dict[str, Any],
    source_id: str,
    source: dict[str, Any],
    parts: dict[str, dict[str, Any]],
    kind: str,
    producer_op: str,
    program_kind: str,
    slot_contract: Any,
    preservation_contract: dict[str, Any] | None,
    step_id: str,
) -> dict[str, Any]:
    copied_parts = {slot: deepcopy(part) for slot, part in parts.items()}
    for slot_part in parts.values():
        if slot_part is source:
            continue
        residual_uL = float(slot_part.get("volume_uL", 0.0))
        residual_mg = float(slot_part.get("mass_mg", 0.0))
        if residual_uL or residual_mg or container_count_cells(slot_part):
            move_explicit(slot_part, source, component_ratio=1.0)
    contract = slot_contract if isinstance(slot_contract, dict) else {slot: f"slot_{slot}" for slot in copied_parts}
    record = {
        "kind": kind,
        "producer_op": producer_op,
        "program_kind": program_kind,
        "source": source_id,
        "slot_contract": dict(contract),
        "parts": copied_parts,
        "valid": True,
        "step_id": step_id,
    }
    if preservation_contract is not None:
        record["preservation_contract"] = dict(preservation_contract)
    contents_states = _material_contents_states(state)
    contents_states[source_id] = record
    return {
        "source": source_id,
        "kind": kind,
        "program_kind": program_kind,
        "slots": sorted(copied_parts),
    }


def remove_transient_containers(state: dict[str, Any], container_ids: list[str], *, preserve: str) -> None:
    containers = state.setdefault("containers", {})
    if not isinstance(containers, dict):
        return
    for container_id in container_ids:
        if container_id != preserve:
            containers.pop(container_id, None)


def _contents_ref_from_mutation_source(source_expr: Any) -> dict[str, Any] | None:
    candidate = source_expr.get("left") if is_serialized_pair(source_expr) else source_expr
    return candidate if is_container_contents_index(candidate) else None


def _contents_qty_from_mutation_source(source_expr: Any) -> dict[str, Any] | None:
    if not is_serialized_pair(source_expr):
        return None
    return arg_quantity(source_expr.get("right"))


def _mutation_touches_active_contents_state(
    *,
    step: PlanStep,
    state: dict[str, Any],
    source_exprs: list[Any],
) -> bool:
    contents_states = state.get("contents_states")
    if not isinstance(contents_states, dict):
        return False
    target_id = resolve_target_ref(state, step.args.get("target"))
    if target_id is not None and _has_active_contents_state(contents_states, target_id):
        return True
    for source_expr in source_exprs:
        source_id = _mutation_source_container_id(state, source_expr)
        if source_id is not None and _has_active_contents_state(contents_states, source_id):
            return True
    return False


def _has_active_contents_state(contents_states: dict[str, Any], container_id: str) -> bool:
    record = contents_states.get(container_id)
    return isinstance(record, dict) and record.get("valid") is not False


def _mutation_source_container_id(state: dict[str, Any], source_expr: Any) -> str | None:
    candidate = source_expr.get("left") if is_serialized_pair(source_expr) else source_expr
    if isinstance(candidate, dict) and candidate.get("kind") == "IRSourcePartitionRef":
        return resolve_structured_ref(state, candidate.get("source"), create_if_identifier=False)
    return resolve_structured_ref(state, candidate, create_if_identifier=False)


def _contents_index_source_expr(value: dict[str, Any]) -> Any:
    base = value.get("base")
    if not isinstance(base, dict):
        return None
    return base.get("base")


def _resolve_contents_state_source_id(state: dict[str, Any], value: dict[str, Any]) -> str | None:
    source_expr = _contents_index_source_expr(value)
    return resolve_structured_ref(state, source_expr, create_if_identifier=False)


def _contents_state_slot_key(value: dict[str, Any]) -> str | None:
    index = value.get("index")
    if isinstance(index, dict) and index.get("kind") == "IRQuantity":
        raw = index.get("value")
        unit = index.get("unit")
        if unit is None and isinstance(raw, (int, float)) and float(raw).is_integer():
            return str(int(raw))
    return None


def _material_contents_states(state: dict[str, Any]) -> dict[str, Any]:
    contents_states = state.setdefault("contents_states", {})
    if not isinstance(contents_states, dict):
        state["contents_states"] = {}
        contents_states = state["contents_states"]
    return contents_states


def _classify_target_addition(
    *,
    step: PlanStep,
    state: dict[str, Any],
    target_id: str,
    moved_snapshot: dict[str, Any] | None,
) -> dict[str, Any]:
    contents_states = state.get("contents_states")
    if not isinstance(contents_states, dict):
        return {"action": "none", "reason": "no_contents_states"}
    record = contents_states.get(target_id)
    if not isinstance(record, dict) or record.get("valid") is False:
        return {"action": "none", "reason": "no_valid_target_contents_state"}
    if moved_snapshot is None:
        return {"action": "stale", "reason": "missing_material_snapshot"}
    contract = record.get("preservation_contract")
    if not _preservation_contract_satisfied(step=step, contract=contract):
        return {"action": "stale", "reason": "preservation_contract_not_satisfied"}
    parts = record.get("parts")
    slot_key = contract.get("default_incoming_slot") if isinstance(contract, dict) else None
    part = parts.get(slot_key) if isinstance(parts, dict) and isinstance(slot_key, str) else None
    if not isinstance(part, dict):
        return {"action": "stale", "reason": "preservation_contract_missing_incoming_slot"}
    return {
        "action": "preserve_add_to_part",
        "slot": slot_key,
        "part": part,
        "contract": contract.get("kind") if isinstance(contract, dict) else None,
    }


def _preservation_contract_satisfied(
    *,
    step: PlanStep,
    contract: Any,
) -> bool:
    if not isinstance(contract, dict):
        return False
    if contract.get("kind") != "field_retention":
        return False
    required_field = contract.get("field")
    if not isinstance(required_field, str) or not _step_gate_has_env_value(step, "field", required_field):
        return False
    return True


def _step_gate_has_env_value(step: PlanStep, key: str, expected: str) -> bool:
    gate = step.gate
    if not isinstance(gate, dict):
        return False
    layers = gate.get("env_layers")
    if isinstance(layers, list):
        return any(
            isinstance(layer, dict) and _env_payload_has_value(layer.get("env"), key, expected)
            for layer in layers
        )
    return _env_payload_has_value(gate.get("env"), key, expected)


def _env_payload_has_value(env: Any, key: str, expected: str) -> bool:
    if not isinstance(env, dict):
        return False
    value = env.get(key)
    if isinstance(value, dict):
        return value.get("name") == expected or value.get("value") == expected
    return value == expected


def _contents_transfer_amount(
    *,
    step: PlanStep,
    state: dict[str, Any],
    selection: ContentsPartSelection,
    qty: dict[str, Any] | None,
) -> tuple[float, float, float, float, str, dict[str, Any]] | MaterialUpdateResult:
    part = selection.part
    if qty is None:
        return (
            float(part.get("volume_uL", 0.0)),
            float(part.get("mass_mg", 0.0)),
            container_count_cells(part),
            1.0,
            "contents_state_full",
            {},
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
            return diagnostic_result(
                step,
                state,
                "MAT_INSUFFICIENT_VOLUME",
                f"Insufficient contents-state volume in '{selection.source_id}'",
            )
        ratio = 0.0 if part_volume == 0 else moved_uL / part_volume
        moved_mg = part_mass * ratio
        return moved_uL, moved_mg, container_count_cells(part) * ratio, ratio, "contents_state_volume", {}
    if unit in MASS_TO_MG:
        moved_mg = value * MASS_TO_MG[unit]
        if part_mass < moved_mg:
            return diagnostic_result(
                step,
                state,
                "MAT_INSUFFICIENT_MASS",
                f"Insufficient contents-state mass in '{selection.source_id}'",
            )
        ratio = 0.0 if part_mass == 0 else moved_mg / part_mass
        moved_uL = part_volume * ratio
        return moved_uL, moved_mg, container_count_cells(part) * ratio, ratio, "contents_state_mass", {}
    if unit in COUNT_TO_CELLS:
        moved_cells = value * COUNT_TO_CELLS[unit]
        relationship = cell_suspension_relationship(part)
        resolution = resolve_count_aliquot(
            step=step,
            state=state,
            container=part,
            source_id=selection.source_id,
            requested_cells=moved_cells,
            relationship=relationship,
        )
        if isinstance(resolution, MaterialUpdateResult):
            return resolution
        return (
            resolution.moved_bulk_volume_uL,
            resolution.moved_bulk_mass_mg,
            resolution.requested_cells,
            resolution.component_ratio,
            "contents_state_count_resolved_volume",
            {
                "requested_cells": resolution.requested_cells,
                "component_ratio": resolution.component_ratio,
                "carrier_volume_uL": resolution.carrier_volume_uL,
                "resolved_transfer_volume_uL": resolution.resolved_transfer_volume_uL,
                "moved_bulk_volume_uL": resolution.moved_bulk_volume_uL,
                "concentration_cells_per_uL": resolution.concentration_cells_per_uL,
                "concentration_source": resolution.concentration_source,
                "policy_id": resolution.policy_id,
            },
        )
    return diagnostic_result(step, state, "MAT_UNSUPPORTED_UNIT", f"Unsupported transfer unit '{unit}'")


def _move_contents_part_material(
    *,
    part: dict[str, Any],
    source: dict[str, Any],
    target: dict[str, Any],
    target_id: str,
    ratio: float,
) -> None:
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
    part_quantities = container_component_quantities(part)
    source_quantities = container_component_quantities(source)
    target_quantities = container_component_quantities(target, create=bool(part_quantities))
    moved_component_ids: set[str] = set()
    for name, amount in list(part_components.items()):
        moved = float(amount) * ratio
        part_components[name] = _clamp_near_zero(float(amount) - moved)
        source_components[name] = _clamp_near_zero(float(source_components.get(name, 0.0)) - moved)
        target_components[name] = float(target_components.get(name, 0.0)) + moved
        part_quantity = part_quantities.get(name) if isinstance(part_quantities, dict) else None
        if isinstance(part_quantity, dict):
            moved_quantity = float(part_quantity.get("value", amount)) * ratio
            part_quantity["value"] = _clamp_near_zero(float(part_quantity.get("value", amount)) - moved_quantity)
            if isinstance(source_quantities, dict) and isinstance(source_quantities.get(name), dict):
                source_quantities[name]["value"] = _clamp_near_zero(
                    float(source_quantities[name].get("value", 0.0)) - moved_quantity
                )
            if isinstance(target_quantities, dict):
                target_quantity = target_quantities.get(name)
                if not isinstance(target_quantity, dict):
                    target_quantity = deepcopy(part_quantity)
                    target_quantity["value"] = 0.0
                    target_quantities[name] = target_quantity
                target_quantity["value"] = float(target_quantity.get("value", 0.0)) + moved_quantity
        if moved > 1e-12:
            moved_component_ids.add(str(name))
            part_class = part_classes.get(name) if isinstance(part_classes, dict) else None
            if isinstance(part_class, str) and isinstance(target_classes, dict):
                target_classes[name] = part_class
        if part_components.get(name) == 0.0 and isinstance(part_classes, dict):
            part_classes.pop(name, None)
        if source_components.get(name) == 0.0 and isinstance(source_classes, dict):
            source_classes.pop(name, None)
    transfer_scientific_model_relationships(
        source=part,
        target=target,
        target_id=target_id,
        moved_component_ids=moved_component_ids,
    )
    refresh_container_aggregates(part)
    refresh_container_aggregates(source)
    refresh_container_aggregates(target)


def _clamp_near_zero(value: float) -> float:
    return 0.0 if abs(value) <= 1e-12 else value


def refresh_separation_relationships(
    state: dict[str, Any],
    source_id: str,
    slot0_id: str,
    slot1_id: str,
    program_kind: str,
    partition: dict[str, Any],
    *,
    effect: ResolvedMaterialEffect | None,
) -> None:
    slot0 = container(state, slot0_id)
    slot1 = container(state, slot1_id)
    source = container(state, source_id)
    refresh_scientific_model_relationships(
        source,
        source_id,
        slot="source",
        effect=None,
    )
    refresh_cell_suspension_relationship(state, source_id)
    refresh_cell_suspension_relationship(
        state,
        slot0_id,
        forced_state=separation_cell_material_state(
            program_kind,
            slot="0",
            partition=partition,
            output=slot0,
            effect=effect,
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
            effect=effect,
        ),
    )
    refresh_scientific_model_relationships(
        slot0,
        slot0_id,
        slot="0",
        effect=effect,
    )
    refresh_scientific_model_relationships(
        slot1,
        slot1_id,
        slot="1",
        effect=effect,
    )


def refresh_scientific_model_relationships(
    output: dict[str, Any] | None,
    output_id: str,
    *,
    slot: str,
    effect: ResolvedMaterialEffect | None,
) -> None:
    if not isinstance(output, dict):
        return
    relationships = output.setdefault("material_relationships", [])
    if not isinstance(relationships, list):
        relationships = []
        output["material_relationships"] = relationships
    relationships[:] = [
        relationship
        for relationship in relationships
        if not (
            isinstance(relationship, dict)
            and relationship.get("subtype") == "scientific_model_relation"
        )
    ]
    if effect is None:
        return
    components = output.get("components")
    if not isinstance(components, dict):
        return
    effects_by_component = {
        component.source_component_id: component
        for component in effect.component_effects
    }
    for component_id, amount in components.items():
        if not isinstance(amount, (int, float)) or abs(float(amount)) <= 1e-12:
            continue
        component_effect = effects_by_component.get(component_id)
        transition = next(
            (
                component_output
                for component_output in component_effect.outputs
                if component_output.part_id == slot
            ),
            None,
        ) if component_effect is not None else None
        next_relation = transition.next_relation if transition is not None else None
        if not isinstance(next_relation, str) or next_relation == "free":
            continue
        relationship = {
            "kind": "association",
            "subtype": "scientific_model_relation",
            "dispersed_component_ids": [component_id],
            "material_state": next_relation,
            "material_state_source": "scientific_model_provider",
            "associated_with": output_id,
        }
        if transition is not None and transition.next_label is not None:
            relationship["label"] = transition.next_label
        if transition is not None and transition.transition_provenance is not None:
            provenance = transition.transition_provenance
            relationship["provenance"] = {
                "provider_id": provenance.provider_id,
                "provider_version": provenance.provider_version,
                "model_id": provenance.model_id,
                "model_version": provenance.model_version,
                "configuration": dict(provenance.configuration),
            }
        relationships.append(relationship)


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


def _best_effort_component_ratio(source: dict[str, Any], *, moved_uL: float, moved_mg: float) -> float:
    source_mass = float(source.get("mass_mg", 0.0))
    if source_mass > 0.0:
        return moved_mg / source_mass
    source_volume = float(source.get("volume_uL", 0.0))
    if source_volume > 0.0:
        return moved_uL / source_volume
    return 0.0
