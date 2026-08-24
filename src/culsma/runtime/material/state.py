"""Material state-change planning and dispatch."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from culsma.pipeline.plan_nodes import PlanStep
from culsma.runtime.material.container_content import (
    apply_alloc_container,
    apply_annotate_content,
    apply_define_content,
    apply_load_content,
)
from culsma.runtime.material.suspension import apply_finalize_container_contents
from culsma.runtime.material.contents_state import (
    ContentsStateTransitionPlan,
    MaterialIndexedPartsStateManager,
    is_container_contents_index,
)
from culsma.runtime.material.diagnostics import diagnostic_result
from culsma.runtime.material.mutation import apply_mutation
from culsma.runtime.material.refs import is_serialized_pair, resolve_structured_ref, resolve_target_ref
from culsma.runtime.material.result import MaterialUpdateResult


@dataclass(frozen=True)
class MaterialStateChangePlan:
    kind: str
    step: PlanStep
    payload: dict[str, Any] = field(default_factory=dict)


class MaterialStateManager:
    def __init__(self, indexed_parts_state_manager: MaterialIndexedPartsStateManager | None = None) -> None:
        self.indexed_parts_state_manager = indexed_parts_state_manager or MaterialIndexedPartsStateManager()

    def plan_material_state_change(
        self,
        *,
        step: PlanStep,
        state: dict[str, Any],
    ) -> MaterialStateChangePlan | None:
        if step.op in {"AllocContainer", "DefineContent", "LoadContent", "AnnotateContent", "FinalizeContainerContents"}:
            return MaterialStateChangePlan(kind="container_record", step=step)

        if step.op in {"sep", "frac", "agit"}:
            return MaterialStateChangePlan(
                kind="partition_or_index",
                step=step,
                payload={"contents_plan": ContentsStateTransitionPlan(transition=step.op, step=step)},
            )

        if step.op == "Mutation":
            source_exprs = step.args.get("sources")
            if not isinstance(source_exprs, list):
                return MaterialStateChangePlan(kind="quantity_or_composition", step=step)
            for source_expr in source_exprs:
                if _contents_ref_from_mutation_source(source_expr) is not None:
                    return MaterialStateChangePlan(
                        kind="partition_or_index",
                        step=step,
                        payload={"contents_plan": ContentsStateTransitionPlan(transition="select", step=step)},
                    )
            if _mutation_touches_active_contents_state(step=step, state=state, source_exprs=source_exprs):
                return MaterialStateChangePlan(
                    kind="partition_or_index",
                    step=step,
                    payload={"contents_plan": ContentsStateTransitionPlan(transition="add", step=step)},
                )
            return MaterialStateChangePlan(kind="quantity_or_composition", step=step)

        return None

    def apply_change(self, change_plan: MaterialStateChangePlan, state: dict[str, Any]) -> MaterialUpdateResult:
        step = change_plan.step
        if change_plan.kind == "container_record":
            return self._apply_container_record(step, state)
        if change_plan.kind == "quantity_or_composition":
            return apply_mutation(step, state)
        if change_plan.kind == "partition_or_index":
            contents_plan = change_plan.payload.get("contents_plan")
            if not isinstance(contents_plan, ContentsStateTransitionPlan):
                return diagnostic_result(
                    step,
                    state,
                    "MAT_STATE_INVARIANT_VIOLATION",
                    "Missing partition/index material-state plan",
                )
            return self.indexed_parts_state_manager.apply_partition_or_index_change(contents_plan, state)
        return diagnostic_result(
            step,
            state,
            "MAT_UNSUPPORTED_MATERIAL_STATE_CHANGE",
            f"Unsupported material state change '{change_plan.kind}'",
        )

    def _apply_container_record(self, step: PlanStep, state: dict[str, Any]) -> MaterialUpdateResult:
        if step.op == "AllocContainer":
            return apply_alloc_container(step, state)
        if step.op == "DefineContent":
            return apply_define_content(step, state)
        if step.op == "LoadContent":
            return apply_load_content(step, state)
        if step.op == "AnnotateContent":
            return apply_annotate_content(step, state)
        if step.op == "FinalizeContainerContents":
            return apply_finalize_container_contents(step, state)
        return diagnostic_result(
            step,
            state,
            "MAT_UNSUPPORTED_MATERIAL_STATE_CHANGE",
            f"Unsupported container record material state change '{step.op}'",
        )


def _contents_ref_from_mutation_source(source_expr: Any) -> dict[str, Any] | None:
    candidate = source_expr.get("left") if is_serialized_pair(source_expr) else source_expr
    return candidate if is_container_contents_index(candidate) else None


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
