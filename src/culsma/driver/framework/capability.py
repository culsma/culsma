"""Shared capability policy for driver requirement checks."""

from __future__ import annotations

from dataclasses import dataclass

from culsma.driver.base import DriverCapabilityResult
from culsma.pipeline.plan_nodes import PlanStep


@dataclass(frozen=True)
class CapabilityPolicy:
    supported_requirements: set[str] | None = None
    supported_constraint_option_keys: set[str] | None = None

    def evaluate(self, step: PlanStep) -> DriverCapabilityResult:
        gate = step.gate or {}
        constraint = gate.get("constraint") if isinstance(gate, dict) else None
        requirements = ()
        option_keys = ()
        if isinstance(constraint, dict):
            raw_requirements = constraint.get("requirements")
            if isinstance(raw_requirements, list):
                requirements = tuple(item for item in raw_requirements if isinstance(item, str))
            raw_options = constraint.get("options")
            if isinstance(raw_options, dict):
                option_keys = tuple(key for key in raw_options.keys() if isinstance(key, str))
        if self.supported_requirements is not None:
            unsupported = tuple(req for req in requirements if req not in self.supported_requirements)
            if unsupported:
                return DriverCapabilityResult(
                    ok=False,
                    code="DRV_REQ_UNSUPPORTED",
                    unsupported_requirements=unsupported,
                    payload={"step_id": step.step_id, "op": step.op, "constraint": constraint},
                )
        if self.supported_constraint_option_keys is not None:
            unsupported_options = tuple(key for key in option_keys if key not in self.supported_constraint_option_keys)
            if unsupported_options:
                return DriverCapabilityResult(
                    ok=False,
                    code="DRV_REQ_OPTION_UNSUPPORTED",
                    unsupported_constraint_options=unsupported_options,
                    payload={"step_id": step.step_id, "op": step.op, "constraint": constraint},
                )
        return DriverCapabilityResult(
            ok=True,
            code="DRV_REQ_OK",
            payload={"step_id": step.step_id, "op": step.op, "constraint": constraint},
        )
