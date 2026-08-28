"""Runtime step dispatch and execution handlers."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from culsma.common.diagnostics import Diagnostic
from culsma.pipeline.plan_nodes import PlanProgram, PlanStep, ProtocolPlan
from culsma.runtime.session import RuntimeSession
from culsma.runtime.values import UNRESOLVED


_MATERIAL_BOOTSTRAP_OPS = {
    "AllocContainer",
    "DefineContent",
    "LoadContent",
    "AnnotateContent",
    "FinalizeContainerContents",
}


@dataclass
class RuntimeStepState:
    resolved_step: PlanStep | None = None
    driver_code: str | None = None
    driver_payload: dict[str, Any] = field(default_factory=dict)
    material_delta: dict[str, Any] | None = None
    observation_delta: dict[str, Any] | None = None
    recorded: bool = False


class BaseRuntimeStepHandler:
    def handle(self, step: PlanStep, session: RuntimeSession) -> bool:
        state = self.prepare(step, session)

        gate_decision = session.gate_evaluator.evaluate(step, session.state, session=session)
        if gate_decision == "skip":
            session.record_skipped(step, "runtime_condition_false")
            state.recorded = True
            return False
        if gate_decision == "error":
            session.record_failed(
                step,
                reason="runtime_condition_unresolved",
                diagnostic=Diagnostic(
                    code="RT_RUNTIME_CONDITION_UNRESOLVED",
                    message=f"Runtime condition could not be evaluated for step '{step.step_id}'",
                    span=step.span,
                    node_id=step.step_id,
                ),
            )
            state.recorded = True
            return session.fail_fast

        ref_group = session.ref_reuse_decider.group_for_step(step.step_id, session)
        if ref_group is not None:
            ref_decision = session.ref_reuse_decider.decide(ref_group, session)
            session.event_log.emit(
                "REF_DECISION",
                step.step_id,
                payload={
                    "ref_protocol": ref_group.ref_protocol,
                    "ref_call_id": ref_group.ref_call_id,
                    "call_path": ref_group.call_path,
                    "ref_policy": ref_decision.policy,
                    "ref_decision": ref_decision.action,
                    "reason": ref_decision.reason,
                    "cache_key": ref_decision.cache_key,
                    "input_signature": ref_decision.input_signature,
                },
                span=step.span,
            )
            if ref_decision.action == "reuse":
                session.ref_reuse_decider.mark_reused(ref_group, session)
                state.recorded = True
                return False
            session.ref_pending_updates[ref_group.last_step_id] = session.ref_reuse_decider.cache_update_payload(
                ref_group,
                ref_decision,
            )

        session.mark_running(step)
        aborted = self.execute_current_step(step, session, state)
        if state.recorded:
            return aborted
        self.record_terminal_result(step, session, state)
        return aborted

    def prepare(self, _step: PlanStep, _session: RuntimeSession) -> RuntimeStepState:
        return RuntimeStepState()

    def execute_current_step(self, _step: PlanStep, _session: RuntimeSession, _state: RuntimeStepState) -> bool:
        return False

    def record_terminal_result(self, step: PlanStep, session: RuntimeSession, state: RuntimeStepState) -> None:
        session.record_completed(
            step,
            driver_code=state.driver_code or "RUNTIME_OK",
            driver_payload=state.driver_payload,
            material_delta=state.material_delta,
            observation_delta=state.observation_delta,
        )
        state.recorded = True


class ControlStepHandler(BaseRuntimeStepHandler):
    def execute_current_step(self, step: PlanStep, session: RuntimeSession, state: RuntimeStepState) -> bool:
        self._apply_runtime_control(step, session)
        state.driver_code = "RUNTIME_CONTROL"
        state.driver_payload = {"op": step.op}
        return False

    def _apply_runtime_control(self, control_step: PlanStep, session: RuntimeSession) -> None:
        frames = _loop_frames(control_step.step_id)
        if not frames:
            return
        loop_prefix, current_iteration = frames[-1]
        current_index = session.step_index_by_id.get(control_step.step_id, -1)
        reason = "runtime_break" if control_step.op == "control_break" else "runtime_continue"
        for step in session.ordered_steps[current_index + 1 :]:
            if session.state.step_status.get(step.step_id) != "pending":
                continue
            candidate_iteration = _loop_iteration_for_prefix(step.step_id, loop_prefix)
            if candidate_iteration is None:
                continue
            if control_step.op == "control_continue" and candidate_iteration != current_iteration:
                continue
            if control_step.op == "control_break" and candidate_iteration < current_iteration:
                continue
            session.record_skipped(step, reason)


class LocalStateStepHandler(BaseRuntimeStepHandler):
    def execute_current_step(self, step: PlanStep, session: RuntimeSession, state: RuntimeStepState) -> bool:
        if step.op == "assign_local":
            return self._assign_local(step, session, state)
        if step.op == "assign_member":
            return self._assign_member(step, session, state)
        if step.op == "append":
            return self._append(step, session, state)
        return False

    def _assign_local(self, step: PlanStep, session: RuntimeSession, state: RuntimeStepState) -> bool:
        target = step.args.get("target")
        value_expr = step.args.get("value")
        if not isinstance(target, str):
            session.record_failed(
                step,
                reason="local_assign_invalid_target",
                diagnostic=Diagnostic(
                    code="RT_LOCAL_ASSIGN_INVALID_TARGET",
                    message=f"Local assignment target is invalid for step '{step.step_id}'",
                    span=step.span,
                    node_id=step.step_id,
                ),
            )
            state.recorded = True
            return session.fail_fast
        value = session.value_resolver.eval_local_value(target, value_expr, session.state)
        if value is UNRESOLVED:
            session.record_failed(
                step,
                reason="local_assign_unresolved",
                diagnostic=Diagnostic(
                    code="RT_LOCAL_ASSIGN_UNRESOLVED",
                    message=f"Local assignment value could not be evaluated for step '{step.step_id}'",
                    span=step.span,
                    node_id=step.step_id,
                ),
            )
            state.recorded = True
            return session.fail_fast
        local_bindings = session.state.artifacts.setdefault("local_bindings", {})
        serialized_value = session.value_resolver.value_to_serialized(value)
        if isinstance(local_bindings, dict):
            local_bindings[target] = serialized_value
        state.driver_code = "LOCAL_ASSIGN"
        state.driver_payload = {"target": target, "value": serialized_value}
        return False

    def _assign_member(self, step: PlanStep, session: RuntimeSession, state: RuntimeStepState) -> bool:
        target_expr = step.args.get("target")
        value = session.value_resolver.eval_method_arg(step.args.get("value"), session.state)
        if value is UNRESOLVED:
            session.record_failed(
                step,
                reason="member_assign_value_unresolved",
                diagnostic=Diagnostic(
                    code="RT_MEMBER_ASSIGN_VALUE_UNRESOLVED",
                    message=f"Member assignment value could not be evaluated for step '{step.step_id}'",
                    span=step.span,
                    node_id=step.step_id,
                ),
            )
            state.recorded = True
            return session.fail_fast
        assign_target = session.value_resolver.resolve_member_assign_target(target_expr, session.state)
        if assign_target is UNRESOLVED:
            session.record_failed(
                step,
                reason="member_assign_target_invalid",
                diagnostic=Diagnostic(
                    code="RT_MEMBER_ASSIGN_TARGET_INVALID",
                    message=f"Member assignment target is invalid for step '{step.step_id}'",
                    span=step.span,
                    node_id=step.step_id,
                ),
            )
            state.recorded = True
            return session.fail_fast
        target_obj, target_key = assign_target
        target_obj[target_key] = session.value_resolver.deep_serialize(deepcopy(value))
        state.driver_code = "RUNTIME_MEMBER_ASSIGN"
        state.driver_payload = {"target": target_key}
        return False

    def _append(self, step: PlanStep, session: RuntimeSession, state: RuntimeStepState) -> bool:
        receiver_expr = step.args.get("self")
        appended_value = session.value_resolver.eval_method_arg(step.args.get("arg0"), session.state)
        if appended_value is UNRESOLVED:
            session.record_failed(
                step,
                reason="append_value_unresolved",
                diagnostic=Diagnostic(
                    code="RT_APPEND_VALUE_UNRESOLVED",
                    message=f"Append value could not be evaluated for step '{step.step_id}'",
                    span=step.span,
                    node_id=step.step_id,
                ),
            )
            state.recorded = True
            return session.fail_fast
        target_list = session.value_resolver.resolve_append_target(receiver_expr, session.state)
        if not isinstance(target_list, list):
            session.record_failed(
                step,
                reason="append_target_invalid",
                diagnostic=Diagnostic(
                    code="RT_APPEND_TARGET_INVALID",
                    message=f"Append target is not a list receiver for step '{step.step_id}'",
                    span=step.span,
                    node_id=step.step_id,
                ),
            )
            state.recorded = True
            return session.fail_fast
        target_list.append(deepcopy(appended_value))
        state.driver_code = "RUNTIME_APPEND"
        state.driver_payload = {"op": "append"}
        return False


class RepeatStepHandler(BaseRuntimeStepHandler):
    def execute_current_step(self, step: PlanStep, session: RuntimeSession, state: RuntimeStepState) -> bool:
        repeat_result = _execute_runtime_repeat_bind(step=step, session=session)
        session.extend_diagnostics(repeat_result["diagnostics"])
        for event in repeat_result["events"]:
            session.event_log.emit(event.kind, event.step_id, payload=event.payload, span=event.span)
        if repeat_result["status"] == "completed":
            session.record_completed(
                step,
                driver_code=repeat_result["driver_code"],
                driver_payload=repeat_result["driver_payload"],
            )
            state.recorded = True
            return False
        session.record_failed(
            step,
            reason=repeat_result["reason"],
            payload_extra={},
        )
        state.recorded = True
        return session.fail_fast


class DriverBackedStepHandler(BaseRuntimeStepHandler):
    def execute_current_step(self, step: PlanStep, session: RuntimeSession, state: RuntimeStepState) -> bool:
        runtime_step = session.value_resolver.resolve_step_args(step, session.state)
        material_result = _preflight_material_step(runtime_step, session)
        if material_result is not None and not material_result.ok:
            session.extend_diagnostics(material_result.diagnostics)
            session.record_failed(
                step,
                reason="material_compute_error",
                diagnostic=Diagnostic(
                    code="RT_MATERIAL_ERROR",
                    message=f"Material compute failed for step '{step.step_id}'",
                    span=step.span,
                    node_id=step.step_id,
                ),
                driver_code="RUNTIME_MATERIAL_REJECTED",
            )
            state.recorded = True
            return session.fail_fast

        driver_step = _step_with_material_resolution(
            runtime_step,
            material_result.delta if material_result is not None else None,
        )
        state.resolved_step = driver_step
        capability = session.driver.check(driver_step)
        if not capability.ok:
            unsupported_parts = list(capability.unsupported_requirements) + list(
                capability.unsupported_constraint_options
            )
            session.record_failed(
                step,
                reason="driver_requirement_unsupported",
                diagnostic=Diagnostic(
                    code="RT_DRIVER_REQUIREMENT_UNSUPPORTED",
                    message=(
                        f"Driver cannot satisfy requirements for step '{step.step_id}': "
                        f"{', '.join(unsupported_parts) or capability.code}"
                    ),
                    span=step.span,
                    node_id=step.step_id,
                ),
                driver_code=capability.code,
                driver_payload=capability.payload,
                history_extra={
                    "unsupported_requirements": list(capability.unsupported_requirements),
                    "unsupported_constraint_options": list(capability.unsupported_constraint_options),
                },
                payload_extra={
                    "unsupported_requirements": list(capability.unsupported_requirements),
                    "unsupported_constraint_options": list(capability.unsupported_constraint_options),
                },
            )
            state.recorded = True
            return session.fail_fast

        result = session.driver.execute(driver_step)
        if result.ok:
            observation_delta: dict[str, Any] | None = None
            material_delta = (material_result.delta or None) if material_result is not None else None
            if material_result is not None:
                session.extend_diagnostics(material_result.diagnostics)
                _commit_material_result(
                    step=runtime_step,
                    source_step=step,
                    session=session,
                    material_result=material_result,
                )
            observation_delta = session.observation_recorder.record(
                driver_step,
                session,
                driver_code=result.code,
                driver_payload=result.payload,
            )
            state.driver_code = result.code
            state.driver_payload = result.payload
            state.material_delta = material_delta
            state.observation_delta = observation_delta
            return False

        severity = _driver_error_severity(result.payload)
        session.record_failed(
            step,
            reason="driver_error",
            diagnostic=Diagnostic(
                code="RT_DRIVER_ERROR",
                message=(
                    f"Driver execution failed for step '{step.step_id}' "
                    f"with code '{result.code}' (severity={severity})"
                ),
                span=step.span,
                node_id=step.step_id,
            ),
            driver_code=result.code,
            driver_payload=result.payload,
            history_extra={"driver_error_severity": severity},
            payload_extra={"driver_error_severity": severity},
        )
        state.recorded = True
        return session.fail_fast and severity == "fatal"


class InternalMaterialStepHandler(BaseRuntimeStepHandler):
    """Execute runtime-only material operations without exposing them to drivers."""

    def execute_current_step(self, step: PlanStep, session: RuntimeSession, state: RuntimeStepState) -> bool:
        runtime_step = session.value_resolver.resolve_step_args(step, session.state)
        state.resolved_step = runtime_step
        material_result = _preflight_material_step(runtime_step, session)
        if material_result is None:
            material_result = session.material_compute.apply_step(
                step=runtime_step,
                material_state={"containers": {}},
            )
        session.extend_diagnostics(material_result.diagnostics)
        if not material_result.ok:
            session.record_failed(
                step,
                reason="material_compute_error",
                diagnostic=Diagnostic(
                    code="RT_MATERIAL_ERROR",
                    message=f"Material compute failed for step '{step.step_id}'",
                    span=step.span,
                    node_id=step.step_id,
                ),
                driver_code="RUNTIME_MATERIAL_REJECTED",
            )
            state.recorded = True
            return session.fail_fast
        _commit_material_result(
            step=runtime_step,
            source_step=step,
            session=session,
            material_result=material_result,
        )
        state.driver_code = "RUNTIME_MATERIAL_INTERNAL"
        state.driver_payload = {"op": runtime_step.op, "internal": True}
        state.material_delta = material_result.delta or None
        return False


class RuntimeStepDispatcher:
    def __init__(self) -> None:
        self.control_handler = ControlStepHandler()
        self.local_state_handler = LocalStateStepHandler()
        self.repeat_handler = RepeatStepHandler()
        self.internal_material_handler = InternalMaterialStepHandler()
        self.driver_handler = DriverBackedStepHandler()

    def dispatch(self, step: PlanStep, session: RuntimeSession) -> bool:
        if step.op in {"control_break", "control_continue"}:
            return self.control_handler.handle(step, session)
        if step.op in {"assign_local", "assign_member", "append"}:
            return self.local_state_handler.handle(step, session)
        if step.op == "repeat_bind":
            return self.repeat_handler.handle(step, session)
        if step.op == "FinalizeContainerContents":
            return self.internal_material_handler.handle(step, session)
        return self.driver_handler.handle(step, session)


def _preflight_material_step(runtime_step: PlanStep, session: RuntimeSession):
    material_state = session.state.artifacts.get("material_state")
    if not isinstance(material_state, dict):
        if runtime_step.op not in _MATERIAL_BOOTSTRAP_OPS:
            return None
        material_state = {"containers": {}}
    return session.material_compute.apply_step(
        step=runtime_step,
        material_state=material_state,
    )


def _commit_material_result(*, step: PlanStep, source_step: PlanStep, session: RuntimeSession, material_result: Any) -> None:
    session.state.artifacts["material_state"] = material_result.material_state
    if session.material_accounting_recorder is not None and session.material_accounting is not None:
        session.material_accounting_recorder.record(
            step=step,
            result=material_result,
            accounting=session.material_accounting,
        )
    material_delta = material_result.delta or None
    for binding_event in session.observation_recorder.extract_binding_overwrite_events(material_delta):
        session.event_log.emit(
            "BINDING_OVERWRITTEN",
            source_step.step_id,
            payload=binding_event,
            span=source_step.span,
        )


def _step_with_material_resolution(step: PlanStep, material_delta: dict[str, Any] | None) -> PlanStep:
    if step.op != "Mutation" or not isinstance(material_delta, dict):
        return step
    sources = step.args.get("sources")
    source_deltas = material_delta.get("sources")
    if not isinstance(sources, list) or not isinstance(source_deltas, list):
        return step

    resolved_sources = deepcopy(sources)
    resolution_records: list[dict[str, Any]] = []
    for ordinal, (source, source_delta) in enumerate(zip(resolved_sources, source_deltas)):
        if not _is_count_pair(source):
            continue
        resolution = _find_count_resolution(source_delta)
        if resolution is None:
            continue
        resolved_uL = float(resolution["resolved_transfer_volume_uL"])
        requested = deepcopy(source.get("right"))
        source["right"] = {
            "kind": "IRQuantity",
            "value": resolved_uL,
            "unit": "uL",
            "span": requested.get("span") if isinstance(requested, dict) else None,
        }
        resolution_records.append(
            {
                "source_ordinal": ordinal,
                "requested": requested,
                "resolved": deepcopy(source["right"]),
                "concentration_cells_per_uL": resolution.get("concentration_cells_per_uL"),
                "concentration_source": resolution.get("concentration_source"),
                "policy_id": resolution.get("policy_id"),
            }
        )
    if not resolution_records:
        return step
    args = deepcopy(step.args)
    args["sources"] = resolved_sources
    args["_runtime_material_resolution"] = {"sources": resolution_records}
    return PlanStep(
        step_id=step.step_id,
        op=step.op,
        args=args,
        deps=list(step.deps),
        gate=deepcopy(step.gate),
        span=step.span,
    )


def _is_count_pair(value: Any) -> bool:
    if not isinstance(value, dict) or value.get("kind") != "IRPair":
        return False
    quantity = value.get("right")
    return (
        isinstance(quantity, dict)
        and quantity.get("kind") == "IRQuantity"
        and quantity.get("unit") == "cells"
    )


def _find_count_resolution(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    resolved = value.get("resolved_transfer_volume_uL")
    if isinstance(resolved, (int, float)):
        return value
    for child in value.values():
        found = _find_count_resolution(child)
        if found is not None:
            return found
    return None


def _loop_frames(step_id: str) -> list[tuple[str, int]]:
    parts = step_id.split(".")
    frames: list[tuple[str, int]] = []
    for idx, part in enumerate(parts):
        if not part.startswith("i"):
            continue
        if idx == 0 or not parts[idx - 1].startswith("s"):
            continue
        try:
            iteration = int(part[1:])
        except ValueError:
            continue
        frames.append((".".join(parts[:idx]), iteration))
    return frames


def _loop_iteration_for_prefix(step_id: str, loop_prefix: str) -> int | None:
    for candidate_prefix, iteration in _loop_frames(step_id):
        if candidate_prefix == loop_prefix:
            return iteration
    return None


def _driver_error_severity(payload: dict[str, Any]) -> str:
    raw = payload.get("error_severity") if isinstance(payload, dict) else None
    if isinstance(raw, str) and raw.lower() in {"fatal", "non_fatal"}:
        return raw.lower()
    return "fatal"


def _execute_runtime_repeat_bind(*, step: PlanStep, session: RuntimeSession) -> dict[str, Any]:
    binding = step.args.get("binding")
    iterable_expr = step.args.get("iterable")
    body_steps = step.args.get("body_steps")
    if not isinstance(binding, str) or not isinstance(body_steps, list) or not all(isinstance(item, PlanStep) for item in body_steps):
        return {
            "status": "failed",
            "diagnostics": [
                Diagnostic(
                    code="RT_REPEAT_BODY_INVALID",
                    message=f"Runtime repeat body is malformed for step '{step.step_id}'",
                    span=step.span,
                    node_id=step.step_id,
                )
            ],
            "events": [],
            "driver_code": "RUNTIME_REPEAT",
            "driver_payload": {"op": "repeat_bind"},
            "reason": "repeat_body_invalid",
        }

    items = session.value_resolver.eval_repeat_items(iterable_expr, session.state)
    if items is UNRESOLVED:
        return {
            "status": "failed",
            "diagnostics": [
                Diagnostic(
                    code="RT_REPEAT_ITERABLE_INVALID",
                    message=f"Runtime repeat iterable is invalid for step '{step.step_id}'",
                    span=step.span,
                    node_id=step.step_id,
                )
            ],
            "events": [],
            "driver_code": "RUNTIME_REPEAT",
            "driver_payload": {"op": "repeat_bind"},
            "reason": "repeat_iterable_invalid",
        }

    local_bindings = session.state.artifacts.setdefault("local_bindings", {})
    previous_binding_present = isinstance(local_bindings, dict) and binding in local_bindings
    previous_binding = deepcopy(local_bindings.get(binding)) if isinstance(local_bindings, dict) and binding in local_bindings else None
    nested_events = []
    nested_diagnostics = []
    completed_iterations = 0
    status = "completed"
    reason: str | None = None

    from culsma.runtime.executor import run

    try:
        for iteration_index, item in enumerate(items):
            if isinstance(local_bindings, dict):
                local_bindings[binding] = session.value_resolver.value_to_serialized(deepcopy(item))
            iteration_steps = _instantiate_runtime_repeat_steps(
                parent_step_id=step.step_id,
                iteration_index=iteration_index,
                templates=body_steps,
            )
            iteration_plan = PlanProgram(
                plans=[
                    ProtocolPlan(
                        protocol_id=f"{step.step_id}::i{iteration_index}",
                        protocol_name=f"{step.step_id}::i{iteration_index}",
                        steps=iteration_steps,
                        span=step.span,
                    )
                ],
                diagnostics=[],
                span=step.span,
            )
            iteration_result = run(
                plan=iteration_plan,
                driver=session.driver,
                state=session.state,
                on_error=session.on_error,
            )
            nested_events.extend(iteration_result.events)
            nested_diagnostics.extend(iteration_result.diagnostics)
            completed_iterations += 1
            if _runtime_repeat_iteration_failed(iteration_steps, session.state):
                status = "failed"
                reason = "repeat_body_failed"
                break
            control_action = _runtime_repeat_iteration_control_action(iteration_steps, session.state)
            if control_action == "break":
                break
            if control_action == "continue":
                continue
    finally:
        if isinstance(local_bindings, dict):
            if previous_binding_present:
                local_bindings[binding] = previous_binding
            else:
                local_bindings.pop(binding, None)

    return {
        "status": status,
        "diagnostics": nested_diagnostics,
        "events": nested_events,
        "driver_code": "RUNTIME_REPEAT",
        "driver_payload": {"op": "repeat_bind", "iterations": completed_iterations},
        "reason": reason or "repeat_body_failed",
    }


def _instantiate_runtime_repeat_steps(
    *,
    parent_step_id: str,
    iteration_index: int,
    templates: list[PlanStep],
) -> list[PlanStep]:
    prefix = f"{parent_step_id}.i{iteration_index}"
    out: list[PlanStep] = []
    for template in templates:
        out.append(
            PlanStep(
                step_id=f"{prefix}.{template.step_id}",
                op=template.op,
                args=deepcopy(template.args),
                deps=[f"{prefix}.{dep}" for dep in template.deps],
                gate=deepcopy(template.gate),
                span=template.span,
            )
        )
    return out


def _runtime_repeat_iteration_failed(steps: list[PlanStep], state) -> bool:
    return any(state.step_status.get(step.step_id) == "failed" for step in steps)


def _runtime_repeat_iteration_control_action(steps: list[PlanStep], state) -> str | None:
    for step in steps:
        if step.op == "control_break" and state.step_status.get(step.step_id) == "completed":
            return "break"
        if step.op == "control_continue" and state.step_status.get(step.step_id) == "completed":
            return "continue"
    return None
