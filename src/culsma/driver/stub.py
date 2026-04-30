"""Deterministic stub driver for runtime verification."""

from __future__ import annotations

from dataclasses import dataclass, field

from culsma.driver.base import DriverCapabilityResult, DriverResult
from culsma.driver.framework.capability import CapabilityPolicy
from culsma.pipeline.plan_nodes import PlanStep


@dataclass
class StubDriver:
    fail_ops: set[str] = field(default_factory=set)
    non_fatal_fail_ops: set[str] = field(default_factory=set)
    op_payloads: dict[str, dict[str, object]] = field(default_factory=dict)
    step_payloads: dict[str, dict[str, object]] = field(default_factory=dict)
    supported_requirements: set[str] | None = None
    supported_constraint_option_keys: set[str] | None = None

    def check(self, step: PlanStep) -> DriverCapabilityResult:
        return CapabilityPolicy(
            supported_requirements=self.supported_requirements,
            supported_constraint_option_keys=self.supported_constraint_option_keys,
        ).evaluate(step)

    def execute(self, step: PlanStep) -> DriverResult:
        if step.op in self.non_fatal_fail_ops:
            return DriverResult(
                ok=False,
                code="DRV_SIMULATED_NON_FATAL_FAILURE",
                payload={"step_id": step.step_id, "op": step.op, "error_severity": "non_fatal"},
            )
        if step.op in self.fail_ops:
            return DriverResult(
                ok=False,
                code="DRV_SIMULATED_FAILURE",
                payload={"step_id": step.step_id, "op": step.op, "error_severity": "fatal"},
            )
        payload = {"step_id": step.step_id, "op": step.op}
        op_payload = self.op_payloads.get(step.op)
        if isinstance(op_payload, dict):
            payload.update(op_payload)
        step_payload = self.step_payloads.get(step.step_id)
        if isinstance(step_payload, dict):
            payload.update(step_payload)
        return DriverResult(
            ok=True,
            code="DRV_OK",
            payload=payload,
        )
