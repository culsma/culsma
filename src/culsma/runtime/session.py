"""Shared runtime session state for one run."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from culsma.common.diagnostics import Diagnostic
from culsma.driver.base import Driver
from culsma.pipeline.plan_nodes import PlanProgram, PlanStep, ProtocolPlan
from culsma.runtime.event_log import EventLog
from culsma.runtime.material.compute import MaterialCompute
from culsma.runtime.state import RuntimeState


@dataclass
class RuntimeSession:
    plan: PlanProgram
    driver: Driver
    state: RuntimeState
    diagnostics: list[Diagnostic]
    event_log: EventLog
    step_by_id: dict[str, PlanStep]
    ordered_steps: list[PlanStep]
    step_index_by_id: dict[str, int]
    protocol_plan_by_last_step_id: dict[str, ProtocolPlan]
    ref_groups: dict[str, Any]
    ref_groups_by_first: dict[str, Any]
    ref_cache: dict[str, Any]
    material_compute: MaterialCompute
    initial_material_state: dict[str, Any] | None = None
    ref_pending_updates: dict[str, dict[str, Any]] = field(default_factory=dict)
    on_error: str = "abort"
    fail_fast: bool = True
    gate_evaluator: Any = None
    ref_reuse_decider: Any = None
    value_resolver: Any = None
    observation_recorder: Any = None
    protocol_output_recorder: Any = None
    material_accounting_recorder: Any = None
    material_accounting: Any = None
    finalizer: Any = None

    def emit_diagnostic(self, diagnostic: Diagnostic) -> None:
        self.diagnostics.append(diagnostic)

    def extend_diagnostics(self, diagnostics: list[Diagnostic]) -> None:
        self.diagnostics.extend(diagnostics)

    def mark_running(self, step: PlanStep) -> None:
        self.state.step_status[step.step_id] = "running"
        payload = {"op": step.op}
        if step.gate is not None:
            payload["gate"] = step.gate
        self.event_log.emit("STEP_STARTED", step.step_id, payload=payload, span=step.span)

    def record_completed(
        self,
        step: PlanStep,
        *,
        driver_code: str,
        driver_payload: dict[str, Any],
        material_delta: dict[str, Any] | None = None,
        observation_delta: dict[str, Any] | None = None,
        history_extra: dict[str, Any] | None = None,
        payload_extra: dict[str, Any] | None = None,
    ) -> None:
        self.state.step_status[step.step_id] = "completed"
        history = {"step_id": step.step_id, "status": "completed", "driver_code": driver_code}
        if history_extra:
            history.update(history_extra)
        self.state.history.append(history)

        payload = {"driver_code": driver_code, "driver_payload": driver_payload}
        if step.gate is not None:
            payload["gate"] = step.gate
        if material_delta is not None:
            payload["material_delta"] = material_delta
            payload["material_state_snapshot"] = self.state.artifacts.get("material_state")
        if observation_delta is not None:
            payload["observation_delta"] = observation_delta
        if payload_extra:
            payload.update(payload_extra)
        self.event_log.emit("STEP_COMPLETED", step.step_id, payload=payload, span=step.span)

        if self.protocol_output_recorder is not None:
            self.protocol_output_recorder.capture_if_ready(step, self)
        self._apply_ref_cache_update(step.step_id)

    def record_failed(
        self,
        step: PlanStep,
        *,
        reason: str,
        diagnostic: Diagnostic | None = None,
        driver_code: str | None = None,
        driver_payload: dict[str, Any] | None = None,
        history_extra: dict[str, Any] | None = None,
        payload_extra: dict[str, Any] | None = None,
    ) -> None:
        self.state.step_status[step.step_id] = "failed"
        history = {"step_id": step.step_id, "status": "failed", "reason": reason}
        if driver_code is not None:
            history["driver_code"] = driver_code
        if history_extra:
            history.update(history_extra)
        self.state.history.append(history)
        if diagnostic is not None:
            self.emit_diagnostic(diagnostic)

        payload: dict[str, Any] = {"reason": reason}
        if driver_code is not None:
            payload["driver_code"] = driver_code
        if driver_payload is not None:
            payload["driver_payload"] = driver_payload
        if step.gate is not None:
            payload["gate"] = step.gate
        if payload_extra:
            payload.update(payload_extra)
        self.event_log.emit("STEP_FAILED", step.step_id, payload=payload, span=step.span)
        self.ref_pending_updates.pop(step.step_id, None)

    def record_skipped(self, step: PlanStep, reason: str) -> None:
        self.state.step_status[step.step_id] = "skipped"
        skip_reasons = self.state.artifacts.setdefault("skip_reasons", {})
        if isinstance(skip_reasons, dict):
            skip_reasons[step.step_id] = reason
        self.state.history.append(
            {"step_id": step.step_id, "status": "skipped", "reason": reason, "deps": list(step.deps)}
        )
        self.event_log.emit(
            "STEP_SKIPPED",
            step.step_id,
            payload={"reason": reason, "deps": list(step.deps)},
            span=step.span,
        )

    def _apply_ref_cache_update(self, step_id: str) -> None:
        ref_cache_update = self.ref_pending_updates.pop(step_id, None)
        if ref_cache_update is None:
            return
        self.ref_cache[ref_cache_update["cache_key"]] = {
            "input_signature": ref_cache_update["input_signature"],
            "ref_protocol": ref_cache_update["ref_protocol"],
            "call_path": ref_cache_update["call_path"],
            "ref_call_id": ref_cache_update["ref_call_id"],
            "step_ids": ref_cache_update["step_ids"],
        }
